import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import select, func, and_
from app.core.database import AsyncSessionLocal
from app.models.audit import AuditLog

logger = logging.getLogger(__name__)

class AuditService:
    @staticmethod
    async def write_audit(
        event_category: str,
        event_type: str,
        organization_id: Optional[str] = None,
        outcome: str = "SUCCESS",
        actor_client_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        entity_type: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        http_method: Optional[str] = None,
        endpoint: Optional[str] = None,
        request_ip: Optional[str] = None,
        status_code: Optional[int] = None,
        severity: str = "INFO",
        error_detail: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Fire-and-forget insert into audit_logs. Never raises an exception.
        """
        try:
            log_entry = AuditLog(
                event_category=event_category,
                event_type=event_type,
                actor_client_id=actor_client_id,
                actor_role=actor_role,
                organization_id=organization_id,
                entity_type=entity_type,
                resource_type=resource_type,
                resource_id=resource_id,
                http_method=http_method,
                endpoint=endpoint,
                request_ip=request_ip,
                status_code=status_code,
                outcome=outcome,
                severity=severity,
                error_detail=error_detail,
                extra_metadata=extra_metadata,
            )
            async with AsyncSessionLocal() as session:
                session.add(log_entry)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to record audit log: {e}", exc_info=True)

    @staticmethod
    async def get_audit_logs(
        organization_id: Optional[str] = None,
        event_category: Optional[str] = None,
        event_type: Optional[str] = None,
        outcome: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """
        Queries paginated audit logs based on search criteria.
        """
        async with AsyncSessionLocal() as session:
            conditions = []
            if organization_id:
                conditions.append(AuditLog.organization_id == organization_id)
            if event_category:
                conditions.append(AuditLog.event_category == event_category)
            if event_type:
                conditions.append(AuditLog.event_type == event_type)
            if outcome:
                conditions.append(AuditLog.outcome == outcome)
            if from_date:
                conditions.append(AuditLog.created_at >= from_date)
            if to_date:
                conditions.append(AuditLog.created_at <= to_date)

            where_clause = and_(*conditions) if conditions else True

            # Count total
            count_stmt = select(func.count(AuditLog.id)).where(where_clause)
            count_res = await session.execute(count_stmt)
            total = count_res.scalar() or 0

            # Fetch page
            stmt = (
                select(AuditLog)
                .where(where_clause)
                .order_by(AuditLog.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            res = await session.execute(stmt)
            items = res.scalars().all()

            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    @staticmethod
    async def get_audit_stats(window_minutes: int = 60) -> Dict[str, Any]:
        """
        Calculates aggregate statistics over a rolling window.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        async with AsyncSessionLocal() as session:
            # Aggregate by outcome
            stmt = (
                select(AuditLog.outcome, func.count(AuditLog.id))
                .where(AuditLog.created_at >= cutoff)
                .group_by(AuditLog.outcome)
            )
            res = await session.execute(stmt)
            outcome_counts = dict(res.all())

            # Total events
            total = sum(outcome_counts.values())

            return {
                "window_minutes": window_minutes,
                "total_events": total,
                "outcomes": outcome_counts,
            }
