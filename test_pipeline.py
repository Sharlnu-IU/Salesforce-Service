import asyncio
import logging
from app.services.pipeline import PipelineService
from app.models.schemas import SalesforceCredentials

logging.basicConfig(level=logging.INFO)

async def main():
    print("Testing End-to-End Pipeline...")
    
    pipeline = PipelineService()
    
    soql = "SELECT Id, Name, Type, BillingCity, BillingState, BillingStreet, BillingPostalCode, BillingCountry FROM Account"
    
    await pipeline.run_pipeline(
        scan_id="test_local_scan_id",
        object_name="Account",
        soql=soql,
        credentials=None
    )
    print("Test finished!")

if __name__ == "__main__":
    asyncio.run(main())
