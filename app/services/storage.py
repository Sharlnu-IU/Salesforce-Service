import boto3
import logging
import os
from botocore.exceptions import ClientError
from app.core.config import get_settings

logger = logging.getLogger(__name__)

class StorageService:
    def __init__(self):
        self.settings = get_settings()
        
        # Configure Boto3 client for MinIO/S3
        endpoint_url = self.settings.MINIO_ENDPOINT
        if not endpoint_url.startswith("http"):
            protocol = "https" if self.settings.MINIO_SECURE else "http"
            endpoint_url = f"{protocol}://{endpoint_url}"
            
        self.s3_client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=self.settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=self.settings.MINIO_SECRET_KEY,
            # We must use path style addressing for MinIO
            config=boto3.session.Config(signature_version='s3v4'),
            region_name='us-east-1' # Default fallback region
        )
        self.bucket = self.settings.MINIO_BUCKET
        self._ensure_bucket_exists()
        
    def _ensure_bucket_exists(self):
        """Ensures the configured bucket exists, creating it if it doesn't."""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                logger.info(f"Bucket {self.bucket} not found. Creating it...")
                self.s3_client.create_bucket(Bucket=self.bucket)
            else:
                logger.error(f"Error checking bucket {self.bucket}: {e}")
                raise

    def upload_file(self, local_path: str, object_name: str = None) -> bool:
        """
        Uploads a file to the S3/MinIO bucket.
        """
        if object_name is None:
            object_name = os.path.basename(local_path)

        try:
            self.s3_client.upload_file(local_path, self.bucket, object_name)
            logger.info(f"Successfully uploaded {local_path} to s3://{self.bucket}/{object_name}")
            return True
        except ClientError as e:
            logger.error(f"Failed to upload {local_path} to {self.bucket}: {e}")
            return False
            
    def list_files(self, prefix: str = "") -> list:
        """
        Lists files in the bucket, optionally filtered by a prefix.
        """
        try:
            response = self.s3_client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
            if 'Contents' in response:
                return [obj['Key'] for obj in response['Contents']]
            return []
        except ClientError as e:
            logger.error(f"Failed to list files in {self.bucket}: {e}")
            return []
