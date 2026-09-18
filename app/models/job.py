import enum
from sqlalchemy import Column, String, DateTime, Enum, JSON
from sqlalchemy.sql import func
from app.models.base import Base

class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    BATCH_REQUESTED = "BATCH_REQUESTED"
    BATCH_PROCESSING = "BATCH_PROCESSING"
    BATCH_READY = "BATCH_READY"
    DOWNLOADING = "DOWNLOADING"
    DOWNLOADED = "DOWNLOADED"
    EXTRACTING = "EXTRACTING"
    EXTRACTED = "EXTRACTED"
    NORMALIZING = "NORMALIZING"
    NORMALIZED = "NORMALIZED"
    UPLOADING_TO_MINIO = "UPLOADING_TO_MINIO"
    UPLOADED_TO_MINIO = "UPLOADED_TO_MINIO"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class Job(Base):
    __tablename__ = "jobs"

    scan_id = Column(String, primary_key=True, index=True)
    organization_id = Column(String, index=True, nullable=False)
    status = Column(Enum(JobStatus), default=JobStatus.PENDING, nullable=False)
    
    # Batch tracking
    batch_job_ids = Column(JSON, nullable=True)  # Store object_name -> SF batch job id
    batch_status = Column(JSON, nullable=True) # Store object_name -> SF status
    batch_requested_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps for stages
    downloaded_at = Column(DateTime(timezone=True), nullable=True)
    extracted_at = Column(DateTime(timezone=True), nullable=True)
    normalized_at = Column(DateTime(timezone=True), nullable=True)
    minio_uploaded_at = Column(DateTime(timezone=True), nullable=True)
    
    # Extracted data tracking
    file_paths = Column(JSON, nullable=True)
    file_sizes = Column(JSON, nullable=True)
    entity_record_counts = Column(JSON, nullable=True)
    normalization_stats = Column(JSON, nullable=True)
    minio_object_keys = Column(JSON, nullable=True)
    
    # Core auditing timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_heartbeat = Column(DateTime(timezone=True), nullable=True)
