import os
import shutil
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from app.core.config import get_settings, DEFAULT_OBJECT_QUERIES
from app.models.schemas import SalesforceCredentials
from app.services.salesforce_auth import SalesforceAuthClient
from app.services.salesforce_bulk import SalesforceBulkClient
from app.services.normalization.service import NormalizationService
from app.services.storage import StorageService
from app.services.job_service import JobService
from app.models.job import JobStatus
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

class PipelineService:
    def __init__(self):
        self.settings = get_settings()
        self.normalization_service = NormalizationService()
        self.storage_service = StorageService()

    async def run_pipeline(
        self,
        scan_id: str,
        organization_id: str,
        objects: Optional[List[str]] = None,
        single_object_name: Optional[str] = None,
        custom_soql: Optional[str] = None,
        credentials: Optional[SalesforceCredentials] = None
    ):
        """
        Executes the end-to-end multi-object extraction, normalization, and MinIO upload pipeline.
        Tracks granular stages and periodically updates the heartbeat in PostgreSQL.
        """
        logger.info(f"Starting multi-object pipeline for scan {scan_id} (org: {organization_id})")
        
        # Determine target objects
        if single_object_name:
            target_objects = [single_object_name]
        elif objects:
            target_objects = objects
        else:
            target_objects = self.settings.SUPPORTED_OBJECTS

        scan_dir = os.path.join("data", "scans", scan_id)
        extracted_dir = os.path.join(scan_dir, "extracted")
        normalized_dir = os.path.join(scan_dir, "normalized")
        os.makedirs(extracted_dir, exist_ok=True)
        os.makedirs(normalized_dir, exist_ok=True)

        async with AsyncSessionLocal() as db:
            try:
                # 1. Authenticate with Salesforce
                if not credentials:
                    credentials = SalesforceCredentials(
                        login_url=self.settings.SF_LOGIN_URL,
                        client_id=self.settings.SF_CLIENT_ID,
                        client_secret=self.settings.SF_CLIENT_SECRET,
                        grant_type='client_credentials'
                    )

                logger.info("1. Authenticating to Salesforce...")
                token_resp = await SalesforceAuthClient.get_access_token(credentials)
                instance_url = token_resp["instance_url"]
                access_token = token_resp["access_token"]

                bulk_client = SalesforceBulkClient(
                    instance_url=instance_url,
                    access_token=access_token,
                    organization_id=organization_id,
                    scan_id=scan_id
                )

                # 2. Submit Bulk API Query Jobs
                await JobService.update_status(db, scan_id, JobStatus.BATCH_REQUESTED)
                batch_job_ids: Dict[str, str] = {}

                for obj in target_objects:
                    soql = custom_soql if (custom_soql and single_object_name == obj) else DEFAULT_OBJECT_QUERIES.get(
                        obj, f"SELECT Id FROM {obj}"
                    )
                    logger.info(f"Submitting Bulk API job for {obj}: {soql}")
                    remote_job_id = await bulk_client.create_query_job(soql)
                    batch_job_ids[obj] = remote_job_id

                await JobService.update_status(
                    db, scan_id, JobStatus.BATCH_PROCESSING,
                    batch_job_ids=batch_job_ids
                )

                # 3. Poll Bulk API Jobs Until Ready
                poll_interval = self.settings.SF_BULK_POLL_INTERVAL_SECONDS
                max_wait_seconds = self.settings.SF_BULK_MAX_WAIT_MINUTES * 60
                elapsed = 0
                batch_status: Dict[str, str] = {obj: "InProgress" for obj in target_objects}

                while True:
                    await JobService.update_heartbeat(db, scan_id)
                    
                    # Check for cancellation
                    current_job = await JobService.get_job(db, scan_id)
                    if current_job and current_job.status == JobStatus.CANCELLED:
                        logger.warning(f"Scan {scan_id} was cancelled by user. Aborting remote jobs.")
                        for jid in batch_job_ids.values():
                            await bulk_client.abort_job(jid)
                        return

                    all_finished = True
                    for obj, jid in batch_job_ids.items():
                        if batch_status[obj] in ("JobComplete", "Failed", "Aborted"):
                            continue

                        status_info = await bulk_client.get_job_status(jid)
                        state = status_info.get("state", "InProgress")
                        batch_status[obj] = state

                        if state not in ("JobComplete", "Failed", "Aborted"):
                            all_finished = False

                    await JobService.update_status(db, scan_id, JobStatus.BATCH_PROCESSING, batch_status=batch_status)

                    if all_finished:
                        break

                    if elapsed >= max_wait_seconds:
                        raise TimeoutError(f"Bulk API jobs timed out after {self.settings.SF_BULK_MAX_WAIT_MINUTES} minutes.")

                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval

                # Check if any sub-job failed
                for obj, state in batch_status.items():
                    if state != "JobComplete":
                        logger.error(f"Bulk job for {obj} failed with state: {state}")

                await JobService.update_status(db, scan_id, JobStatus.BATCH_READY, batch_status=batch_status)

                # 4. Download Exported CSV Files
                await JobService.update_status(db, scan_id, JobStatus.DOWNLOADING)
                downloaded_paths = []
                file_sizes = []

                for obj, jid in batch_job_ids.items():
                    if batch_status.get(obj) == "JobComplete":
                        csv_path = os.path.join(extracted_dir, f"{obj.lower()}.csv")
                        logger.info(f"Downloading results for {obj} ({jid}) to {csv_path}...")
                        await bulk_client.download_job_results(jid, csv_path)
                        downloaded_paths.append(csv_path)
                        file_sizes.append(os.path.getsize(csv_path))

                await JobService.update_status(
                    db, scan_id, JobStatus.DOWNLOADED,
                    file_paths=downloaded_paths,
                    file_sizes=file_sizes
                )

                # 5. Extract & Ingest CSV Records
                await JobService.update_status(db, scan_id, JobStatus.EXTRACTING)
                entity_counts: Dict[str, int] = {}
                for csv_p in downloaded_paths:
                    obj_name = os.path.splitext(os.path.basename(csv_p))[0]
                    # Quick line count
                    with open(csv_p, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = sum(1 for _ in f)
                        entity_counts[obj_name] = max(0, lines - 1)

                await JobService.store_entity_record_counts(db, scan_id, entity_counts)

                # 6. Normalize into Relational Tables
                await JobService.update_status(db, scan_id, JobStatus.NORMALIZING)
                all_parquet_files = []
                overall_table_stats: Dict[str, int] = {}

                for csv_p in downloaded_paths:
                    filename = os.path.basename(csv_p)
                    obj_name = os.path.splitext(filename)[0]
                    
                    # Match object name case-insensitively
                    matching_obj = next((o for o in target_objects if o.lower() == obj_name.lower()), None)
                    if not matching_obj:
                        continue

                    try:
                        p_files, stats = self.normalization_service.normalize_csv(
                            object_name=matching_obj,
                            csv_filepath=csv_p,
                            output_format="parquet",
                            target_dir=normalized_dir
                        )
                        all_parquet_files.extend(p_files)
                        overall_table_stats.update(stats)
                    except Exception as norm_err:
                        logger.error(f"Error normalizing {matching_obj}: {norm_err}")

                await JobService.update_status(
                    db, scan_id, JobStatus.NORMALIZED,
                    normalization_stats=overall_table_stats
                )

                # 7. Upload Parquet Tables to MinIO
                await JobService.update_status(db, scan_id, JobStatus.UPLOADING_TO_MINIO)
                date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

                uploaded_s3_keys = await self.storage_service.upload_normalized_data(
                    scan_id=scan_id,
                    organization_id=organization_id,
                    processing_date=date_str,
                    table_files=all_parquet_files
                )

                await JobService.update_status(db, scan_id, JobStatus.UPLOADED_TO_MINIO, minio_object_keys=uploaded_s3_keys)

                # 8. Mark Job as Completed
                await JobService.update_status(db, scan_id, JobStatus.COMPLETED)
                logger.info(f"Pipeline finished successfully for scan {scan_id}!")

            except Exception as e:
                logger.error(f"Pipeline failed for scan {scan_id}: {e}", exc_info=True)
                try:
                    async with AsyncSessionLocal() as fail_db:
                        await JobService.fail_job(fail_db, scan_id, error=str(e))
                except Exception as fe:
                    logger.error(f"Failed to record failure status in DB: {fe}")
                raise

            finally:
                # Cleanup local scratch files
                logger.info(f"Cleaning up local scratch directory {scan_dir}...")
                if os.path.exists(scan_dir):
                    shutil.rmtree(scan_dir, ignore_errors=True)

    async def cancel_scan(self, scan_id: str) -> Optional[dict]:
        """
        Cancels a scan locally and best-effort aborts running remote Salesforce Bulk API jobs.
        """
        async with AsyncSessionLocal() as db:
            job = await JobService.get_job(db, scan_id)
            if not job:
                return None

            await JobService.cancel_job(db, scan_id)

            if job.batch_job_ids:
                credentials = SalesforceCredentials(
                    login_url=self.settings.SF_LOGIN_URL,
                    client_id=self.settings.SF_CLIENT_ID,
                    client_secret=self.settings.SF_CLIENT_SECRET,
                    grant_type='client_credentials'
                )
                try:
                    token_resp = await SalesforceAuthClient.get_access_token(credentials)
                    bulk_client = SalesforceBulkClient(
                        instance_url=token_resp["instance_url"],
                        access_token=token_resp["access_token"]
                    )
                    for obj, jid in job.batch_job_ids.items():
                        await bulk_client.abort_job(jid)
                except Exception as e:
                    logger.warning(f"Could not abort remote jobs during cancellation: {e}")

            return {"scan_id": scan_id, "status": "CANCELLED"}

    async def resume_scan(self, scan_id: str):
        """
        Resumes an unfinished/failed scan from the latest completed stage.
        """
        async with AsyncSessionLocal() as db:
            job = await JobService.get_job(db, scan_id)
            if not job:
                raise ValueError(f"Scan {scan_id} not found")

            if job.status == JobStatus.COMPLETED:
                return {"scan_id": scan_id, "status": "already_completed"}

            logger.info(f"Resuming scan {scan_id} from status {job.status.value}...")
            # For simplicity and reliability, rerun pipeline targeting the same scan_id
            await JobService.update_status(db, scan_id, JobStatus.PENDING)

        await self.run_pipeline(
            scan_id=scan_id,
            organization_id=job.organization_id
        )
