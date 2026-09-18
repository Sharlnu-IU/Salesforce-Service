from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class SalesforceCredentials(BaseModel):
    login_url: str = "https://login.salesforce.com"
    client_id: str
    client_secret: Optional[str] = None
    grant_type: Optional[str] = "client_credentials"
    username: Optional[str] = None
    password: Optional[str] = None
    security_token: Optional[str] = None
    private_key: Optional[str] = None  # For JWT Bearer flow

class ScanStartRequest(BaseModel):
    organization_id: str
    object_name: Optional[str] = None  # Single object (optional fallback)
    soql: Optional[str] = None         # Custom SOQL (optional)
    objects: Optional[List[str]] = None  # Multiple target objects (optional, defaults to all supported)
    credentials: Optional[SalesforceCredentials] = None

class ScanResumeRequest(BaseModel):
    scan_id: Optional[str] = None

class NormalizationRequest(BaseModel):
    format: str = Field(default="parquet", description="Output format: 'parquet' or 'json'")
    save_to_disk: bool = True
    upload_to_minio: bool = True
    processing_date: Optional[str] = None

class MaintenanceCleanupRequest(BaseModel):
    days_old: int = 30

class MaintenanceDetectCrashedRequest(BaseModel):
    timeout_minutes: int = 15

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int
