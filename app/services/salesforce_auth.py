import httpx
import logging
from app.models.schemas import SalesforceCredentials
from fastapi import HTTPException

logger = logging.getLogger(__name__)

class SalesforceAuthClient:
    
    @staticmethod
    async def get_access_token(credentials: SalesforceCredentials) -> dict:
        """
        Authenticates with Salesforce using the provided credentials.
        Returns the OAuth response (access_token, instance_url, etc).
        """
        token_url = f"{credentials.login_url.rstrip('/')}/services/oauth2/token"
        
        if not credentials.username or not credentials.password:
            raise ValueError("Username and password are required for this flow.")
            
        data = {
            "grant_type": "password",
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "username": credentials.username,
            "password": f"{credentials.password}{credentials.security_token or ''}"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, data=data)
            
            if response.status_code != 200:
                logger.error(f"Salesforce Auth Failed: {response.text}")
                raise HTTPException(status_code=401, detail="Failed to authenticate with Salesforce. Please check credentials.")
                
            return response.json()
            
    @staticmethod
    async def validate_credentials(credentials: SalesforceCredentials) -> bool:
        """
        Validates credentials by attempting to get a token.
        """
        try:
            await SalesforceAuthClient.get_access_token(credentials)
            return True
        except Exception as e:
            logger.error(f"Credential validation error: {e}")
            return False
