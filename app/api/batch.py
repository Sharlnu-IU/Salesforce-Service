from fastapi import APIRouter, Depends
from app.core.config import get_settings, DEFAULT_OBJECT_QUERIES
from app.core.security import hmac_auth_required

router = APIRouter(
    prefix="/api/batch",
    tags=["batch"],
    dependencies=[Depends(hmac_auth_required)]
)

@router.get("/info")
async def get_batch_info():
    """
    Returns configured Bulk API settings, default SOQL queries, and supported objects.
    """
    settings = get_settings()
    return {
        "api_version": settings.SF_API_VERSION,
        "poll_interval_seconds": settings.SF_BULK_POLL_INTERVAL_SECONDS,
        "max_wait_minutes": settings.SF_BULK_MAX_WAIT_MINUTES,
        "supported_objects": settings.SUPPORTED_OBJECTS,
        "default_queries": DEFAULT_OBJECT_QUERIES
    }
