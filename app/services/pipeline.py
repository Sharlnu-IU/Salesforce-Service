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

logger = logging.getLogger(__name__)

class PipelineService:
    def __init__(self):
        self.settings = get_settings()
        self.normalization_service = NormalizationService(output_dir="data/normalized")
        self.storage_service = StorageService()
        
    async def run_pipeline(self, object_name: str, soql: str, credentials: SalesforceCredentials = None):
        """
        Executes the end-to-end extraction, normalization, and upload pipeline.
        If credentials are not provided, uses defaults from settings (assumes client_credentials).
        """
        logger.info(f"Starting pipeline for object: {object_name}")
        job_id = None
        csv_file = None
        parquet_files = []
        
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
            bulk_client = SalesforceBulkClient(
                instance_url=token_resp["instance_url"],
                access_token=token_resp["access_token"]
            )
            
            logger.info(f"2. Submitting Bulk API job. SOQL: {soql}")
            job_id = await bulk_client.create_query_job(soql)
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
                
            # Download
            os.makedirs("data/raw", exist_ok=True)
            csv_file = f"data/raw/{object_name.lower()}_{job_id}.csv"
            
            logger.info(f"3. Downloading results to {csv_file}")
            await bulk_client.download_job_results(job_id, csv_file)
            
            # 3. Normalize
            logger.info(f"4. Normalizing {object_name} data...")
            parquet_files = self.normalization_service.normalize_csv(object_name, csv_file)
            
            # 4. Upload to Storage
            logger.info("5. Uploading Parquet files to Storage...")
            date_prefix = datetime.utcnow().strftime('%Y/%m/%d')
            
            for pf in parquet_files:
                filename = os.path.basename(pf)
                # Structure: normalized/account/2026/09/17/accounts.parquet
                s3_key = f"normalized/{object_name.lower()}/{date_prefix}/{filename}"
                success = self.storage_service.upload_file(pf, s3_key)
                
                if not success:
                    logger.error(f"Failed to upload {pf}")
                    
            logger.info("Pipeline completed successfully.")
            
        except Exception as e:
            logger.error(f"Pipeline failed: {str(e)}")
            raise
        finally:
            # Cleanup local files (optional, but good practice in production)
            logger.info("6. Cleaning up local temporary files...")
            if csv_file and os.path.exists(csv_file):
                os.remove(csv_file)
            for pf in parquet_files:
                if os.path.exists(pf):
                    os.remove(pf)
