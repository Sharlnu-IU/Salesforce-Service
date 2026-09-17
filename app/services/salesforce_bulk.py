import httpx
import logging
from fastapi import HTTPException
from app.core.config import get_settings
import aiofiles

logger = logging.getLogger(__name__)
settings = get_settings()

class SalesforceBulkClient:
    def __init__(self, instance_url: str, access_token: str):
        self.instance_url = instance_url.rstrip("/")
        self.access_token = access_token
        self.api_version = settings.SF_API_VERSION
        
    @property
    def base_url(self) -> str:
        return f"{self.instance_url}/services/data/{self.api_version}/jobs/query"
        
    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    async def create_query_job(self, soql: str) -> str:
        """
        Submits a Bulk API 2.0 query job.
        Returns the job ID.
        """
        payload = {
            "operation": "query",
            "query": soql
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.base_url, json=payload, headers=self.headers)
            
            if response.status_code != 200:
                logger.error(f"Failed to create Bulk API job: {response.text}")
                raise HTTPException(status_code=response.status_code, detail=f"Salesforce Bulk Error: {response.text}")
                
            data = response.json()
            return data.get("id")

    async def get_job_status(self, job_id: str) -> dict:
        """
        Retrieves the current status of a Bulk API 2.0 query job.
        Returns a dict containing 'state' and other info.
        Valid states: Open, UploadComplete, InProgress, Aborted, JobComplete, Failed
        """
        url = f"{self.base_url}/{job_id}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers)
            
            if response.status_code != 200:
                logger.error(f"Failed to get Bulk API job status for {job_id}: {response.text}")
                raise HTTPException(status_code=response.status_code, detail=f"Salesforce Bulk Error: {response.text}")
                
            return response.json()

    async def download_job_results(self, job_id: str, output_filepath: str):
        """
        Downloads the CSV results of a completed Bulk API 2.0 query job
        and streams it to the given local file path.
        """
        url = f"{self.base_url}/{job_id}/results"
        
        # We use a custom accept header for the results download
        download_headers = self.headers.copy()
        download_headers["Accept"] = "text/csv"
        
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url, headers=download_headers) as response:
                if response.status_code != 200:
                    await response.aread() # Read error message
                    logger.error(f"Failed to download Bulk API results for {job_id}: {response.text}")
                    raise HTTPException(status_code=response.status_code, detail=f"Salesforce Bulk Error: {response.text}")
                    
                async with aiofiles.open(output_filepath, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        await f.write(chunk)
