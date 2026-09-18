from fastapi import APIRouter, Depends
from app.core.security import hmac_auth_required

router = APIRouter(
    prefix="/api/key",
    tags=["key"],
    dependencies=[Depends(hmac_auth_required)]
)

@router.get("/verify")
async def verify_key(auth_context: dict = Depends(hmac_auth_required)):
    """
    Returns caller's verified HMAC client identity, role, and permissions profile.
    """
    client_id = auth_context.get("client_id")
    role = auth_context.get("role")
    
    permissions = ["GET", "POST", "DELETE"] if role == "coordinator" else ["GET"]

    return {
        "status": "valid",
        "client_id": client_id,
        "role": role,
        "permissions": permissions
    }
