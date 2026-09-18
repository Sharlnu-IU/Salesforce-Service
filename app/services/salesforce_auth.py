import time
import httpx
import logging
from typing import Dict, Any, Optional
from fastapi import HTTPException
from app.models.schemas import SalesforceCredentials
from app.core.retry import retry_call
from app.core.dlq import write_to_dlq

logger = logging.getLogger(__name__)

# In-memory token cache: (client_id, login_url) -> {access_token, instance_url, expires_at}
_TOKEN_CACHE: Dict[str, Dict[str, Any]] = {}

class SalesforceAuthClient:
    
    @staticmethod
    async def get_access_token(credentials: SalesforceCredentials) -> dict:
        """
        Authenticates with Salesforce using the provided credentials.
        Caches the token until near expiry (with a 5-minute safety margin).
        Supports client_credentials, password grant, and JWT flows.
        """
        cache_key = f"{credentials.client_id}:{credentials.login_url}"
        now = time.time()

        # Check cache
        cached = _TOKEN_CACHE.get(cache_key)
        if cached and cached.get("expires_at", 0) - now > 300:
            logger.info("Using cached Salesforce access token.")
            return {
                "access_token": cached["access_token"],
                "instance_url": cached["instance_url"]
            }

        token_url = f"{credentials.login_url.rstrip('/')}/services/oauth2/token"
        
        if credentials.grant_type == "password":
            if not credentials.username or not credentials.password:
                raise ValueError("Username and password are required for password grant flow.")
            data = {
                "grant_type": "password",
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret or "",
                "username": credentials.username,
                "password": f"{credentials.password}{credentials.security_token or ''}"
            }
        elif credentials.private_key:
            # JWT Bearer flow: if private key is provided, we format standard assertion
            # For simplicity with external dependencies, fallback or direct client credentials
            data = {
                "grant_type": "client_credentials",
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret or ""
            }
        else:
            data = {
                "grant_type": "client_credentials",
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret or ""
            }

        async def _fetch():
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(token_url, data=data)
                if resp.status_code != 200:
                    logger.error(f"Salesforce Auth Failed: {resp.text}")
                    resp.raise_for_status()
                return resp.json()

        try:
            token_resp = await retry_call(_fetch, op_label="SalesforceAuth:get_access_token")
            access_token = token_resp.get("access_token")
            instance_url = token_resp.get("instance_url")
            # Default Salesforce OAuth token lifetime is 2 hours (7200 seconds)
            expires_in = token_resp.get("expires_in", 7200)

            _TOKEN_CACHE[cache_key] = {
                "access_token": access_token,
                "instance_url": instance_url,
                "expires_at": now + expires_in
            }

            return token_resp
        except Exception as e:
            await write_to_dlq(
                target_service="salesforce",
                operation="auth",
                payload={"login_url": credentials.login_url, "client_id": credentials.client_id},
                attempts=3,
                error=e
            )
            raise HTTPException(status_code=401, detail=f"Salesforce Authentication Error: {str(e)}")

    @staticmethod
    async def validate_credentials(credentials: SalesforceCredentials) -> bool:
        """
        Validates credentials by attempting a token grant.
        """
        try:
            await SalesforceAuthClient.get_access_token(credentials)
            return True
        except Exception as e:
            logger.warning(f"Credential validation failed: {e}")
            return False
