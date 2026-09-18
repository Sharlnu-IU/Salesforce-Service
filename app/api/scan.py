import os
import shutil
import logging
from typing import Optional
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import hmac_auth_required
from app.core.utils import build_pagination_info
from app.models.schemas import ScanStartRequest
from app.models.job import JobStatus
from app.services.job_service import JobService
from app.services.pipeline import PipelineService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/scan",
    tags=["scan"],
    dependencies=[Depends(hmac_auth_required)]
)

async def execute_background_pipeline(
    scan_id: str,
    organization_id: str,
    objects: Optional[list] = None,
    single_object_name: Optional[str] = None,
    custom_soql: Optional[str] = None
):
    pipeline = PipelineService()
    try:
        await pipeline.run_pipeline(
            scan_id=scan_id,
            organization_id=organization_id,
            objects=objects,
            single_object_name=single_object_name,
            custom_soql=custom_soql
        )
    except Exception as e:
        logger.error(f"Background pipeline failed for scan {scan_id}: {e}")

@router.post("/start", status_code=status.HTTP_202_ACCEPTED)
async def start_scan(
    request: ScanStartRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Starts a new Salesforce data extraction scan in the background.
    Extracts all supported objects (or specified subset). Returns 202 Accepted.
    """
    job = await JobService.create_job(db, organization_id=request.organization_id)

    background_tasks.add_task(
        execute_background_pipeline,
        scan_id=job.scan_id,
        organization_id=request.organization_id,
        objects=request.objects,
        single_object_name=request.object_name,
        custom_soql=request.soql
    )

    return {"scan_id": job.scan_id, "status": "accepted"}

@router.get("/{scan_id}/status")
async def get_scan_status(scan_id: str, db: AsyncSession = Depends(get_db)):
    """
    Returns current job status, granular stage timestamps, and duration metrics.
    """
    job = await JobService.get_job(db, scan_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scan not found")

    progress = await JobService.get_pipeline_progress(job)

    return {
        "scan_id": job.scan_id,
        "organization_id": job.organization_id,
        "status": job.status.value if hasattr(job.status, 'value') else str(job.status),
        "pipeline_progress": progress,
        "entity_record_counts": job.entity_record_counts,
        "batch_job_ids": job.batch_job_ids,
        "batch_status": job.batch_status,
        "normalization_stats": job.normalization_stats,
        "minio_object_keys": job.minio_object_keys,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "last_heartbeat": job.last_heartbeat
    }

@router.post("/{scan_id}/cancel")
async def cancel_scan(scan_id: str, db: AsyncSession = Depends(get_db)):
    """
    Cancels an active scan and best-effort aborts remote Salesforce query jobs.
    """
    job = await JobService.get_job(db, scan_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scan not found")

    pipeline = PipelineService()
    res = await pipeline.cancel_scan(scan_id)
    return res or {"scan_id": scan_id, "status": "CANCELLED"}

@router.post("/{scan_id}/resume")
async def resume_scan(
    scan_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Resumes an unfinished, failed, or cancelled scan.
    """
    job = await JobService.get_job(db, scan_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scan not found")

    if job.status == JobStatus.COMPLETED:
        return {"scan_id": scan_id, "status": "already_completed"}

    pipeline = PipelineService()
    background_tasks.add_task(pipeline.resume_scan, scan_id=scan_id)

    return {"scan_id": scan_id, "status": "resumed"}

@router.get("/list")
async def list_scans(
    organization_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns a paginated list of scans filtered by organization.
    """
    data = await JobService.list_jobs(db, organization_id=organization_id, page=page, page_size=page_size)
    pagination = build_pagination_info(page, page_size, data["total"])
    
    serialized_items = []
    for j in data["items"]:
        serialized_items.append({
            "scan_id": j.scan_id,
            "organization_id": j.organization_id,
            "status": j.status.value if hasattr(j.status, 'value') else str(j.status),
            "created_at": j.created_at,
            "updated_at": j.updated_at
        })

    return {
        "items": serialized_items,
        "pagination": pagination
    }

@router.get("/statistics")
async def get_scan_statistics(db: AsyncSession = Depends(get_db)):
    """
    Returns aggregate counts of scans by status.
    """
    return await JobService.get_scan_statistics(db)

@router.delete("/{scan_id}/remove")
async def remove_scan(scan_id: str, db: AsyncSession = Depends(get_db)):
    """
    Purges job records and local scratch files for a completed/failed scan.
    """
    job = await JobService.get_job(db, scan_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scan not found")

    # Block removal if job is actively running
    if job.status in (JobStatus.BATCH_PROCESSING, JobStatus.DOWNLOADING, JobStatus.NORMALIZING, JobStatus.UPLOADING_TO_MINIO):
        raise HTTPException(status_code=400, detail="Cannot delete a scan that is currently in progress")

    # Delete local files
    scan_dir = os.path.join("data", "scans", scan_id)
    if os.path.exists(scan_dir):
        shutil.rmtree(scan_dir, ignore_errors=True)

    await db.delete(job)
    await db.commit()

    return {"scan_id": scan_id, "deleted": True}
