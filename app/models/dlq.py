import uuid
from sqlalchemy import Column, String, Integer, DateTime, JSON
from sqlalchemy.sql import func
from app.models.base import Base

class FailedExternalCall(Base):
    __tablename__ = "failed_external_calls"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    target_service = Column(String, nullable=False, index=True)      # e.g., "salesforce", "minio"
    operation = Column(String, nullable=False)                       # e.g., "create_query_job", "upload_file"
    organization_id = Column(String, nullable=True, index=True)
    scan_id = Column(String, nullable=True, index=True)
    payload = Column(JSON, nullable=True)                            # Scrubbed and capped JSON
    attempts = Column(Integer, nullable=False, default=1)
    last_error = Column(String, nullable=True)
    status = Column(String, nullable=False, default="FAILED")        # "FAILED", "RETRIED", "RESOLVED"
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
