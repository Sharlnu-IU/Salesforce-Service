import asyncio
import os
from app.core.config import get_settings
from app.models.schemas import SalesforceCredentials
from app.services.salesforce_auth import SalesforceAuthClient
from app.services.salesforce_bulk import SalesforceBulkClient

async def main():
    settings = get_settings()
    
    creds = SalesforceCredentials(
        login_url=settings.SF_LOGIN_URL,
        client_id=settings.SF_CLIENT_ID,
        client_secret=settings.SF_CLIENT_SECRET,
        grant_type='client_credentials'
    )
    
    print("1. Authenticating...")
    token_resp = await SalesforceAuthClient.get_access_token(creds)
    access_token = token_resp["access_token"]
    instance_url = token_resp["instance_url"]
    print("Authenticated successfully.")
    
    bulk_client = SalesforceBulkClient(instance_url=instance_url, access_token=access_token)
    
    print("2. Submitting Bulk API Query Job for Account...")
    job_id = await bulk_client.create_query_job("SELECT Id, Name, Type, BillingCity, BillingState FROM Account")
    print(f"Job created with ID: {job_id}")
    
    print("3. Polling for job completion...")
    while True:
        status = await bulk_client.get_job_status(job_id)
        state = status.get("state")
        print(f"Current State: {state}")
        
        if state in ["JobComplete", "Failed", "Aborted"]:
            break
            
        await asyncio.sleep(5)
        
    if state == "JobComplete":
        output_file = f"account_export_{job_id}.csv"
        print(f"4. Job complete. Downloading results to {output_file}...")
        await bulk_client.download_job_results(job_id, output_file)
        
        size = os.path.getsize(output_file)
        print(f"Download complete! File size: {size} bytes.")
        
        with open(output_file, 'r', encoding='utf-8') as f:
            print("\nPreview of CSV:")
            print(f.readline().strip())
            print(f.readline().strip())
    else:
        print(f"Job did not complete successfully. Final state: {state}")

if __name__ == "__main__":
    asyncio.run(main())
