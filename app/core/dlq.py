import json
import logging
from typing import Any, Optional
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.dlq import FailedExternalCall

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {
    "password",
    "client_secret",
    "access_token",
    "token",
    "security_token",
    "private_key",
    "authorization",
    "x-sf-signature",
    "secret",
}

def scrub_payload(data: Any) -> Any:
    """
    Recursively redacts sensitive credentials and secrets from dictionaries/lists.
    """
    if isinstance(data, dict):
        scrubbed = {}
        for k, v in data.items():
            if str(k).lower() in SENSITIVE_KEYS:
                scrubbed[k] = "[REDACTED]"
            else:
                scrubbed[k] = scrub_payload(v)
        return scrubbed
    elif isinstance(data, list):
        return [scrub_payload(item) for item in data]
    return data

async def write_to_dlq(
    target_service: str,
    operation: str,
    payload: Any,
    attempts: int,
    error: Exception,
    organization_id: Optional[str] = None,
    scan_id: Optional[str] = None,
) -> None:
    """
    Persists an exhausted external call failure into failed_external_calls table.
    Guaranteed to never raise an exception so callers are never broken by DLQ logging.
    """
    try:
        settings = get_settings()
        clean_payload = scrub_payload(payload)
        
        # Ensure payload is JSON serializable and capped by byte limit
        try:
            payload_json_str = json.dumps(clean_payload, default=str)
            if len(payload_json_str.encode("utf-8")) > settings.DLQ_PAYLOAD_MAX_BYTES:
                clean_payload = {"_truncated": True, "preview": payload_json_str[: settings.DLQ_PAYLOAD_MAX_BYTES]}
        except Exception:
            clean_payload = {"_error": "Payload not JSON serializable", "raw": str(clean_payload)[:1000]}

        record = FailedExternalCall(
            target_service=target_service,
            operation=operation,
            organization_id=organization_id,
            scan_id=scan_id,
            payload=clean_payload if isinstance(clean_payload, dict) else {"data": clean_payload},
            attempts=attempts,
            last_error=str(error),
            status="FAILED",
        )

        async with AsyncSessionLocal() as session:
            session.add(record)
            await session.commit()
            
        logger.info(f"Recorded failed external call to DLQ: {target_service}:{operation} for scan {scan_id}")
    except Exception as dlq_err:
        logger.error(f"Failed to record call to DLQ: {dlq_err}", exc_info=True)
