import os
import asyncio
import logging
from datetime import datetime
from app.core.config import get_settings
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
        self.normalization_service = NormalizationService(output_dir="data/normalized")
        self.storage_service = StorageService()
        
    async def run_pipeline(self, scan_id: str, object_name: str, soql: str, credentials: SalesforceCredentials = None):
        """
        Executes the end-to-end extraction, normalization, and upload pipeline.
        Updates the PostgreSQL Job record at each step.
        """
        logger.info(f"Starting pipeline for scan {scan_id}, object: {object_name}")
        job_id = None
        csv_file = None
        parquet_files = []
        
        async with AsyncSessionLocal() as db:
            try:
                # 1. Auth
                if not credentials:
                    credentials = SalesforceCredentials(
                        login_url=self.settings.SF_LOGIN_URL,
                        client_id=self.settings.SF_CLIENT_ID,
                        client_secret=self.settings.SF_CLIENT_SECRET,
                        grant_type='client_credentials'
                    )
                    
                logger.info("1. Authenticating to Salesforce...")
                token_resp = await SalesforceAuthClient.get_access_token(credentials)
                
                # 2. Bulk API Export
                await JobService.update_status(db, scan_id, JobStatus.BATCH_REQUESTED)
                
                bulk_client = SalesforceBulkClient(
                    instance_url=token_resp["instance_url"],
                    access_token=token_resp["access_token"]
                )
                
                logger.info(f"2. Submitting Bulk API job. SOQL: {soql}")
                job_id = await bulk_client.create_query_job(soql)
                
                await JobService.update_status(db, scan_id, JobStatus.BATCH_PROCESSING, batch_job_ids={object_name: job_id})
                logger.info(f"Job created: {job_id}. Polling for completion...")
                
                # Poll
                while True:
                    status = await bulk_client.get_job_status(job_id)
                    state = status.get("state")
                    
                    if state in ["JobComplete", "Failed", "Aborted"]:
                        break
                        
                    await asyncio.sleep(5)
                    
                if state != "JobComplete":
                    raise Exception(f"Bulk job failed with state: {state}")
                    
                await JobService.update_status(db, scan_id, JobStatus.BATCH_READY, batch_status={object_name: state})
                    
                # Download
                await JobService.update_status(db, scan_id, JobStatus.DOWNLOADING)
                os.makedirs("data/raw", exist_ok=True)
                csv_file = f"data/raw/{object_name.lower()}_{job_id}.csv"
                
                logger.info(f"3. Downloading results to {csv_file}")
                await bulk_client.download_job_results(job_id, csv_file)
                
                file_size = os.path.getsize(csv_file)
                await JobService.update_status(
                    db, scan_id, JobStatus.DOWNLOADED, 
                    file_paths=[csv_file], 
                    file_sizes=[file_size]
                )
                
                # 3. Normalize
                await JobService.update_status(db, scan_id, JobStatus.NORMALIZING)
                logger.info(f"4. Normalizing {object_name} data...")
                parquet_files = self.normalization_service.normalize_csv(object_name, csv_file)
                
                await JobService.update_status(db, scan_id, JobStatus.NORMALIZED)
                
                # 4. Upload to Storage
                await JobService.update_status(db, scan_id, JobStatus.UPLOADING_TO_MINIO)
                logger.info("5. Uploading Parquet files to Storage...")
                date_prefix = datetime.utcnow().strftime('%Y/%m/%d')
                
                uploaded_keys = []
                for pf in parquet_files:
                    filename = os.path.basename(pf)
                    s3_key = f"normalized/{object_name.lower()}/{date_prefix}/{filename}"
                    success = self.storage_service.upload_file(pf, s3_key)
                    
                    if success:
                        uploaded_keys.append(s3_key)
                    else:
                        logger.error(f"Failed to upload {pf}")
                        raise Exception(f"Failed to upload {pf} to MinIO")
                        
                # 5. Complete
                await JobService.update_status(db, scan_id, JobStatus.COMPLETED, minio_object_keys=uploaded_keys)
                logger.info(f"Pipeline completed successfully for scan {scan_id}.")
                
            except Exception as e:
                logger.error(f"Pipeline failed for scan {scan_id}: {str(e)}")
                # We do a best-effort failure recording
                try:
                    await JobService.update_status(db, scan_id, JobStatus.FAILED)
                except:
                    pass
                raise
            finally:
                # Cleanup local files
                logger.info("6. Cleaning up local temporary files...")
                if csv_file and os.path.exists(csv_file):
                    os.remove(csv_file)
                for pf in parquet_files:
                    if os.path.exists(pf):
                        os.remove(pf)
