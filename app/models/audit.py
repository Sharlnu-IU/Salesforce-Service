import uuid
from sqlalchemy import Column, String, Integer, DateTime, JSON
from sqlalchemy.sql import func
from app.models.base import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_category = Column(String, nullable=False, index=True)      # e.g., "auth", "scan", "api", "system"
    event_type = Column(String, nullable=False, index=True)          # e.g., "auth_success", "auth_failure", "scan_start"
    actor_client_id = Column(String, nullable=True, index=True)     # e.g., "coordinator", "engineer"
    actor_role = Column(String, nullable=True)                      # e.g., "admin", "readonly"
    organization_id = Column(String, nullable=True, index=True)
    entity_type = Column(String, nullable=True)                     # e.g., "scan", "user"
    resource_type = Column(String, nullable=True)
    resource_id = Column(String, nullable=True)
    http_method = Column(String, nullable=True)
    endpoint = Column(String, nullable=True)
    request_ip = Column(String, nullable=True)
    status_code = Column(Integer, nullable=True)
    outcome = Column(String, nullable=False, default="SUCCESS")     # "SUCCESS", "FAILURE", "DENIED"
    severity = Column(String, nullable=False, default="INFO")       # "INFO", "WARN", "ERROR", "CRITICAL"
    error_detail = Column(String, nullable=True)
    extra_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
