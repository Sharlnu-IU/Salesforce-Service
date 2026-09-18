import os
import logging
import httpx
import aiofiles
from typing import Optional, Dict, Any
from fastapi import HTTPException
from app.core.config import get_settings
from app.core.retry import retry_call
from app.core.dlq import write_to_dlq

logger = logging.getLogger(__name__)

class SalesforceBulkClient:
    def __init__(self, instance_url: str, access_token: str, organization_id: Optional[str] = None, scan_id: Optional[str] = None):
        self.settings = get_settings()
        self.instance_url = instance_url.rstrip("/")
        self.access_token = access_token
        self.api_version = self.settings.SF_API_VERSION
        self.organization_id = organization_id
        self.scan_id = scan_id

    @property
    def base_url(self) -> str:
        return f"{self.instance_url}/services/data/{self.api_version}/jobs/query"

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    async def create_query_job(self, soql: str, operation: str = "query") -> str:
        """
        Submits a Bulk API 2.0 query job for the given SOQL string.
        Returns the remote Salesforce job ID.
        """
        payload = {
            "operation": operation,
            "query": soql
        }

        async def _call():
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.base_url, json=payload, headers=self.headers)
                if response.status_code not in (200, 201):
                    response.raise_for_status()
                return response.json().get("id")

        try:
            job_id = await retry_call(_call, op_label="SalesforceBulk:create_query_job")
            return job_id
        except Exception as e:
            await write_to_dlq(
                target_service="salesforce",
                operation="create_query_job",
                payload={"soql": soql},
                attempts=self.settings.EXTERNAL_CALL_MAX_RETRIES,
                error=e,
                organization_id=self.organization_id,
                scan_id=self.scan_id
            )
            raise

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Retrieves the current status of a Bulk API 2.0 query job.
        States: UploadComplete, InProgress, Aborted, JobComplete, Failed.
        """
        url = f"{self.base_url}/{job_id}"

        async def _call():
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(url, headers=self.headers)
                if response.status_code != 200:
                    response.raise_for_status()
                return response.json()

        try:
            return await retry_call(_call, op_label=f"SalesforceBulk:get_job_status:{job_id}")
        except Exception as e:
            logger.warning(f"Failed to fetch job status for {job_id}: {e}")
            raise

    async def abort_job(self, job_id: str) -> bool:
        """
        Aborts a running Bulk API 2.0 query job on Salesforce (best-effort).
        """
        url = f"{self.base_url}/{job_id}"
        payload = {"state": "Aborted"}

        async def _call():
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.patch(url, json=payload, headers=self.headers)
                return resp.status_code in (200, 204)

        try:
            logger.info(f"Aborting remote Salesforce Bulk API job {job_id}...")
            return await retry_call(_call, op_label=f"SalesforceBulk:abort_job:{job_id}")
        except Exception as e:
            logger.warning(f"Failed to abort remote Bulk API job {job_id}: {e}")
            return False

    async def close_job(self, job_id: str) -> bool:
        """
        Marks a Bulk API job closed/deleted.
        """
        url = f"{self.base_url}/{job_id}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.delete(url, headers=self.headers)
                return resp.status_code in (200, 204)
        except Exception:
            return False

    async def download_job_results(self, job_id: str, output_filepath: str, locator: Optional[str] = None):
        """
        Streams the CSV results of a completed Bulk API 2.0 query job to local disk.
        Supports locator pagination if provided.
        """
        url = f"{self.base_url}/{job_id}/results"
        params = {"locator": locator} if locator else {}
        download_headers = self.headers.copy()
        download_headers["Accept"] = "text/csv"

        os.makedirs(os.path.dirname(output_filepath), exist_ok=True)

        async def _download():
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("GET", url, params=params, headers=download_headers) as response:
                    if response.status_code != 200:
                        response.raise_for_status()
                    async with aiofiles.open(output_filepath, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=16384):
                            await f.write(chunk)

        try:
            await retry_call(_download, op_label=f"SalesforceBulk:download_results:{job_id}")
            logger.info(f"Successfully downloaded Bulk API results for {job_id} to {output_filepath}")
        except Exception as e:
            await write_to_dlq(
                target_service="salesforce",
                operation="download_job_results",
                payload={"job_id": job_id, "output_filepath": output_filepath},
                attempts=self.settings.EXTERNAL_CALL_MAX_RETRIES,
                error=e,
                organization_id=self.organization_id,
                scan_id=self.scan_id
            )
            raise
