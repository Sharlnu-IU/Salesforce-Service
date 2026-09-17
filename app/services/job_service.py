import logging
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.job import Job, JobStatus

logger = logging.getLogger(__name__)

class JobService:
    @staticmethod
    async def create_job(db: AsyncSession, organization_id: str) -> Job:
        scan_id = str(uuid.uuid4())
        job = Job(
            scan_id=scan_id,
            organization_id=organization_id,
            status=JobStatus.PENDING,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        logger.info(f"Created new job {scan_id} for org {organization_id}")
        return job
        
    @staticmethod
    async def get_job(db: AsyncSession, scan_id: str) -> Job:
        result = await db.execute(select(Job).where(Job.scan_id == scan_id))
        return result.scalars().first()
        
    @staticmethod
    async def update_status(db: AsyncSession, scan_id: str, status: JobStatus, **kwargs) -> Job:
        job = await JobService.get_job(db, scan_id)
        if not job:
            logger.error(f"Attempted to update status for non-existent job {scan_id}")
            return None
            
        job.status = status
        
        # Update specific timestamps based on status transitions
        now = datetime.now(timezone.utc)
        if status == JobStatus.BATCH_REQUESTED:
            job.batch_requested_at = now
        elif status == JobStatus.DOWNLOADED:
            job.downloaded_at = now
        elif status == JobStatus.EXTRACTED:
            job.extracted_at = now
        elif status == JobStatus.NORMALIZED:
            job.normalized_at = now
        elif status == JobStatus.UPLOADING_TO_MINIO:
            # Let's use minio_uploaded_at when COMPLETED instead
            pass
        elif status == JobStatus.COMPLETED:
            job.minio_uploaded_at = now
            
        # Update any other specific fields passed via kwargs
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)
                
        await db.commit()
        await db.refresh(job)
        logger.info(f"Job {scan_id} updated to status {status.value}")
        return job
