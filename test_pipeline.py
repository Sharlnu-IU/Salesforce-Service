import asyncio
import logging
from app.services.pipeline import PipelineService
from app.models.schemas import SalesforceCredentials

logging.basicConfig(level=logging.INFO)

async def main():
    print("Testing End-to-End Pipeline...")
    
    # Use the test credentials for this script
    creds = SalesforceCredentials(
        login_url=settings.SF_LOGIN_URL,
        client_id=settings.SF_CLIENT_ID,
        client_secret=settings.SF_CLIENT_SECRET,
        grant_type='client_credentials'
    )
    
    pipeline = PipelineService()
    
    soql = "SELECT Id, Name, Type, BillingCity, BillingState, BillingStreet, BillingPostalCode, BillingCountry FROM Account"
    
    await pipeline.run_pipeline(
        object_name="Account",
        soql=soql,
        credentials=creds
    )
    print("Test finished!")

if __name__ == "__main__":
    asyncio.run(main())
