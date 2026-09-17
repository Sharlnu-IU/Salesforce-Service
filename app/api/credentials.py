from fastapi import APIRouter, HTTPException
from app.models.schemas import SalesforceCredentials
from app.services.salesforce_auth import SalesforceAuthClient

router = APIRouter(prefix="/api", tags=["Credentials"])

@router.post("/validate-credentials")
async def validate_credentials(request: SalesforceCredentials):
    try:
        response = await SalesforceAuthClient.get_access_token(request)
        return {
            "status": "valid", 
            "instance_url": response.get("instance_url"),
            "message": "Credentials successfully verified."
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
