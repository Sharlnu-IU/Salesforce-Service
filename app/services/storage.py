import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional
import boto3
from botocore.exceptions import ClientError
from app.core.config import get_settings
from app.core.retry import retry_call
from app.core.dlq import write_to_dlq

logger = logging.getLogger(__name__)

class StorageService:
    def __init__(self):
        self.settings = get_settings()
        
        endpoint_url = self.settings.MINIO_ENDPOINT
        if not endpoint_url.startswith("http"):
            protocol = "https" if self.settings.MINIO_SECURE else "http"
            endpoint_url = f"{protocol}://{endpoint_url}"
            
        self.s3_client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=self.settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=self.settings.MINIO_SECRET_KEY,
            config=boto3.session.Config(signature_version='s3v4'),
            region_name='us-east-1'
        )
        self.bucket = self.settings.MINIO_BUCKET
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        """Ensures the configured bucket exists, creating it if it doesn't."""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket)
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code in ('404', 'NoSuchBucket'):
                logger.info(f"Bucket {self.bucket} not found. Creating it...")
                self.s3_client.create_bucket(Bucket=self.bucket)
            else:
                logger.error(f"Error checking bucket {self.bucket}: {e}")

    async def upload_file(self, local_path: str, object_name: str = None) -> bool:
        """
        Asynchronously uploads a local file to S3/MinIO with retries and DLQ logging.
        """
        if object_name is None:
            object_name = os.path.basename(local_path)

        def _do_upload():
            self.s3_client.upload_file(local_path, self.bucket, object_name)

        try:
            await retry_call(_do_upload, op_label=f"MinIO:upload_file:{object_name}")
            logger.info(f"Successfully uploaded {local_path} to s3://{self.bucket}/{object_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload {local_path} to {self.bucket}: {e}")
            await write_to_dlq(
                target_service="minio",
                operation="upload_file",
                payload={"local_path": local_path, "object_name": object_name},
                attempts=self.settings.EXTERNAL_CALL_MAX_RETRIES,
                error=e
            )
            return False

    async def upload_directory(self, local_dir: str, prefix: str) -> List[str]:
        """
        Uploads all files in a local directory to a given S3 prefix.
        """
        uploaded = []
        for root, _, files in os.walk(local_dir):
            for file in files:
                local_path = os.path.join(root, file)
                rel_path = os.path.relpath(local_path, local_dir).replace("\\", "/")
                s3_key = f"{prefix.rstrip('/')}/{rel_path}"
                success = await self.upload_file(local_path, s3_key)
                if success:
                    uploaded.append(s3_key)
        return uploaded

    async def upload_normalized_data(
        self,
        scan_id: str,
        organization_id: str,
        processing_date: Optional[str],
        table_files: List[str]
    ) -> List[str]:
        """
        Uploads normalized Parquet files following DESIGN.md §10.4 path convention:
        salesforce/{table_name}/glynac_organization_id={org_id}/processing_date={date}/{table}.parquet
        """
        date_str = processing_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        uploaded_keys = []

        for local_file in table_files:
            filename = os.path.basename(local_file)
            table_name = os.path.splitext(filename)[0]
            
            s3_key = (
                f"salesforce/{table_name}/"
                f"glynac_organization_id={organization_id}/"
                f"processing_date={date_str}/"
                f"{filename}"
            )
            
            success = await self.upload_file(local_file, s3_key)
            if success:
                uploaded_keys.append(s3_key)
            else:
                raise Exception(f"Failed to upload table file {local_file} to MinIO")

        return uploaded_keys

    async def list_files(self, prefix: str = "") -> List[str]:
        """Lists files in the bucket under a given prefix."""
        def _list():
            resp = self.s3_client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
            if 'Contents' in resp:
                return [obj['Key'] for obj in resp['Contents']]
            return []
        return await asyncio.to_thread(_list)
