import os
import shutil
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, delete
from app.models.job import Job, JobStatus
from app.core.utils import calculate_duration

logger = logging.getLogger(__name__)

IN_PROGRESS_STATES = {
    JobStatus.BATCH_PROCESSING,
    JobStatus.DOWNLOADING,
    JobStatus.EXTRACTING,
    JobStatus.NORMALIZING,
    JobStatus.UPLOADING_TO_MINIO,
}

class JobService:
    @staticmethod
    async def create_job(db: AsyncSession, organization_id: str, scan_id: Optional[str] = None) -> Job:
        job_id = scan_id or str(uuid.uuid4())
        job = Job(
            scan_id=job_id,
            organization_id=organization_id,
            status=JobStatus.PENDING,
            last_heartbeat=datetime.now(timezone.utc)
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        logger.info(f"Created new job {job_id} for org {organization_id}")
        return job

    @staticmethod
    async def get_job(db: AsyncSession, scan_id: str) -> Optional[Job]:
        result = await db.execute(select(Job).where(Job.scan_id == scan_id))
        return result.scalars().first()

    @staticmethod
    async def update_status(db: AsyncSession, scan_id: str, status: JobStatus, **kwargs) -> Optional[Job]:
        job = await JobService.get_job(db, scan_id)
        if not job:
            logger.error(f"Attempted to update status for non-existent job {scan_id}")
            return None

        job.status = status
        now = datetime.now(timezone.utc)
        job.last_heartbeat = now

        # Update specific stage timestamps
        if status == JobStatus.BATCH_REQUESTED:
            job.batch_requested_at = now
        elif status == JobStatus.DOWNLOADED:
            job.downloaded_at = now
        elif status == JobStatus.EXTRACTED:
            job.extracted_at = now
        elif status == JobStatus.NORMALIZED:
            job.normalized_at = now
        elif status in (JobStatus.UPLOADED_TO_MINIO, JobStatus.COMPLETED):
            job.minio_uploaded_at = now

        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)

        await db.commit()
        await db.refresh(job)
        logger.info(f"Job {scan_id} updated to status {status.value}")
        return job

    @staticmethod
    async def update_heartbeat(db: AsyncSession, scan_id: str) -> None:
        """Updates the last_heartbeat timestamp to signal the job is alive."""
        job = await JobService.get_job(db, scan_id)
        if job and job.status in IN_PROGRESS_STATES:
            job.last_heartbeat = datetime.now(timezone.utc)
            await db.commit()

    @staticmethod
    async def fail_job(db: AsyncSession, scan_id: str, error: str) -> Optional[Job]:
        """Marks a job as FAILED and records the error detail."""
        return await JobService.update_status(
            db, scan_id, JobStatus.FAILED,
            normalization_stats={"error": error}
        )

    @staticmethod
    async def cancel_job(db: AsyncSession, scan_id: str) -> Optional[Job]:
        """Marks a job as CANCELLED."""
        job = await JobService.get_job(db, scan_id)
        if not job:
            return None
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            return job
        return await JobService.update_status(db, scan_id, JobStatus.CANCELLED)

    @staticmethod
    async def store_entity_record_counts(db: AsyncSession, scan_id: str, counts_by_object: Dict[str, int]) -> Optional[Job]:
        return await JobService.update_status(db, scan_id, JobStatus.EXTRACTED, entity_record_counts=counts_by_object)

    @staticmethod
    async def detect_crashed_jobs(db: AsyncSession, timeout_minutes: int = 15) -> List[str]:
        """
        Finds jobs in active in-progress states whose last_heartbeat is older than timeout_minutes.
        Flags them as FAILED.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        stmt = (
            select(Job)
            .where(
                and_(
                    Job.status.in_(IN_PROGRESS_STATES),
                    Job.last_heartbeat < cutoff
                )
            )
        )
        res = await db.execute(stmt)
        crashed = res.scalars().all()
        crashed_ids = []

        for job in crashed:
            logger.warning(f"Crash detected for job {job.scan_id} (last heartbeat: {job.last_heartbeat}). Marking FAILED.")
            job.status = JobStatus.FAILED
            crashed_ids.append(job.scan_id)

        if crashed:
            await db.commit()

        return crashed_ids

    @staticmethod
    async def cleanup_old_jobs(db: AsyncSession, days_old: int = 30) -> int:
        """
        Deletes job records and local scratch files older than N days.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)
        stmt = select(Job).where(Job.created_at < cutoff)
        res = await db.execute(stmt)
        old_jobs = res.scalars().all()
        deleted_count = 0

        for job in old_jobs:
            # Clean local files
            scan_dir = os.path.join("data", "scans", job.scan_id)
            if os.path.exists(scan_dir):
                shutil.rmtree(scan_dir, ignore_errors=True)
            await db.delete(job)
            deleted_count += 1

        if deleted_count > 0:
            await db.commit()
            logger.info(f"Cleaned up {deleted_count} jobs older than {days_old} days.")

        return deleted_count

    @staticmethod
    async def get_pipeline_progress(job: Job) -> Dict[str, Any]:
        """
        Builds per-stage progress timestamps and duration metrics.
        """
        return {
            "batch_requested_at": job.batch_requested_at.isoformat() if job.batch_requested_at else None,
            "downloaded_at": job.downloaded_at.isoformat() if job.downloaded_at else None,
            "extracted_at": job.extracted_at.isoformat() if job.extracted_at else None,
            "normalized_at": job.normalized_at.isoformat() if job.normalized_at else None,
            "minio_uploaded_at": job.minio_uploaded_at.isoformat() if job.minio_uploaded_at else None,
            "duration_seconds": calculate_duration(job.created_at, job.updated_at if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED) else None)
        }

    @staticmethod
    async def list_jobs(
        db: AsyncSession,
        organization_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        Returns paginated list of jobs.
        """
        conditions = []
        if organization_id:
            conditions.append(Job.organization_id == organization_id)

        where_clause = and_(*conditions) if conditions else True

        # Total
        count_stmt = select(func.count(Job.scan_id)).where(where_clause)
        count_res = await db.execute(count_stmt)
        total = count_res.scalar() or 0

        # Page
        stmt = (
            select(Job)
            .where(where_clause)
            .order_by(Job.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        res = await db.execute(stmt)
        jobs = res.scalars().all()

        return {
            "items": jobs,
            "total": total,
            "page": page,
            "page_size": page_size
        }

    @staticmethod
    async def get_scan_statistics(db: AsyncSession) -> Dict[str, Any]:
        """
        Aggregates job counts by status.
        """
        stmt = select(Job.status, func.count(Job.scan_id)).group_by(Job.status)
        res = await db.execute(stmt)
        status_counts = {str(status.value if hasattr(status, 'value') else status): count for status, count in res.all()}
        total = sum(status_counts.values())

        return {
            "total_scans": total,
            "by_status": status_counts
        }
