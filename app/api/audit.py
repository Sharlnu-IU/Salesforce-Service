from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from app.core.security import hmac_auth_required
from app.core.utils import build_pagination_info
from app.services.audit_service import AuditService

router = APIRouter(
    prefix="/api/audit",
    tags=["audit"],
    dependencies=[Depends(hmac_auth_required)]
)

@router.get("/logs")
async def get_audit_logs(
    organization_id: Optional[str] = None,
    event_category: Optional[str] = None,
    event_type: Optional[str] = None,
    outcome: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """
    Paginated audit log query with filtering by organization, category, event type, and outcome.
    """
    data = await AuditService.get_audit_logs(
        organization_id=organization_id,
        event_category=event_category,
        event_type=event_type,
        outcome=outcome,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size
    )

    pagination = build_pagination_info(page, page_size, data["total"])
    
    serialized = []
    for log in data["items"]:
        serialized.append({
            "id": log.id,
            "event_category": log.event_category,
            "event_type": log.event_type,
            "actor_client_id": log.actor_client_id,
            "actor_role": log.actor_role,
            "organization_id": log.organization_id,
            "endpoint": log.endpoint,
            "http_method": log.http_method,
            "outcome": log.outcome,
            "severity": log.severity,
            "error_detail": log.error_detail,
            "created_at": log.created_at
        })

    return {
        "items": serialized,
        "pagination": pagination
    }

@router.get("/stats")
async def get_audit_stats(window_minutes: int = Query(60, ge=1, le=1440)):
    """
    Rolling-window audit event aggregates and outcome counts.
    """
    return await AuditService.get_audit_stats(window_minutes=window_minutes)
