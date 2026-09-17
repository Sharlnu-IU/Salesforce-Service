import logging
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.schemas import ScanStartRequest
from app.services.job_service import JobService
from app.services.pipeline import PipelineService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scan", tags=["scan"])

async def execute_background_pipeline(scan_id: str, object_name: str, soql: str):
    """
    Wrapper function to execute the pipeline in the background.
    """
    pipeline = PipelineService()
    try:
        await pipeline.run_pipeline(scan_id=scan_id, object_name=object_name, soql=soql)
    except Exception as e:
        logger.error(f"Background pipeline failed for scan {scan_id}: {e}")

@router.post("/start", status_code=202)
async def start_scan(
    request: ScanStartRequest, 
    background_tasks: BackgroundTasks, 
    db: AsyncSession = Depends(get_db)
):
    """
    Starts a new data extraction scan in the background.
    """
    job = await JobService.create_job(db, organization_id=request.organization_id)
    
    # Schedule the pipeline execution in the background
    background_tasks.add_task(
        execute_background_pipeline,
        scan_id=job.scan_id,
        object_name=request.object_name,
        soql=request.soql
    )
    
    return {"scan_id": job.scan_id, "status": "accepted"}

@router.get("/{scan_id}/status")
async def get_scan_status(scan_id: str, db: AsyncSession = Depends(get_db)):
    """
    Returns the current status of a scan.
    """
    job = await JobService.get_job(db, scan_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scan not found")
        
    return {
        "scan_id": job.scan_id,
        "organization_id": job.organization_id,
        "status": job.status,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "batch_job_ids": job.batch_job_ids,
        "batch_status": job.batch_status
    }
