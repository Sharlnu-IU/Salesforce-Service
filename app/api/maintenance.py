from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import hmac_auth_required
from app.models.schemas import MaintenanceCleanupRequest, MaintenanceDetectCrashedRequest
from app.services.job_service import JobService

router = APIRouter(
    prefix="/api/maintenance",
    tags=["maintenance"],
    dependencies=[Depends(hmac_auth_required)]
)

@router.post("/cleanup")
async def cleanup_old_scans(
    request: MaintenanceCleanupRequest = MaintenanceCleanupRequest(),
    db: AsyncSession = Depends(get_db)
):
    """
    Deletes scan records and local files older than N days.
    """
    deleted_count = await JobService.cleanup_old_jobs(db, days_old=request.days_old)
    return {
        "status": "success",
        "days_threshold": request.days_old,
        "deleted_jobs_count": deleted_count
    }

@router.post("/detect-crashed")
async def detect_crashed_jobs(
    request: MaintenanceDetectCrashedRequest = MaintenanceDetectCrashedRequest(),
    db: AsyncSession = Depends(get_db)
):
    """
    Scans for active jobs with stale heartbeats and transitions them to FAILED.
    """
    crashed_ids = await JobService.detect_crashed_jobs(db, timeout_minutes=request.timeout_minutes)
    return {
        "status": "success",
        "timeout_minutes": request.timeout_minutes,
        "crashed_jobs_detected": len(crashed_ids),
        "crashed_scan_ids": crashed_ids
    }
