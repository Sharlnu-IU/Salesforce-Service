from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import List, Dict

DEFAULT_OBJECT_QUERIES: Dict[str, str] = {
    "Account": "SELECT Id, Name, Type, BillingCity, BillingState, BillingStreet, BillingPostalCode, BillingCountry FROM Account",
    "Contact": "SELECT Id, AccountId, FirstName, LastName, Email, Phone, Title FROM Contact",
    "Opportunity": "SELECT Id, AccountId, Name, StageName, Amount, CloseDate, Probability FROM Opportunity",
    "Lead": "SELECT Id, FirstName, LastName, Company, Email, Status, LeadSource FROM Lead",
    "Case": "SELECT Id, AccountId, ContactId, CaseNumber, Subject, Status, Priority FROM Case",
    "Task": "SELECT Id, WhoId, WhatId, Subject, Status, Priority, ActivityDate FROM Task",
    "Event": "SELECT Id, WhoId, WhatId, Subject, StartDateTime, EndDateTime, Description FROM Event",
    "Campaign": "SELECT Id, Name, Status, StartDate, EndDate, ExpectedRevenue FROM Campaign",
    "User": "SELECT Id, Username, LastName, FirstName, Email, IsActive, Department, Title FROM User",
}

class Settings(BaseSettings):
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    
    # Database
    DATABASE_URL: str
    
    # Salesforce API
    SF_LOGIN_URL: str
    SF_CLIENT_ID: str
    SF_CLIENT_SECRET: str
    SF_API_VERSION: str = "v60.0"
    
    # Bulk API Polling
    SF_BULK_POLL_INTERVAL_SECONDS: int = 5
    SF_BULK_MAX_WAIT_MINUTES: int = 30
    
    # MinIO
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET: str
    MINIO_SECURE: bool = False
    
    # HMAC Security
    HMAC_ENABLED: bool = True
    HMAC_SECRET_KEY_CORE: str
    HMAC_SECRET_KEY_ENGINEER: str = "your_engineer_secret"
    HMAC_SIGNATURE_MAX_AGE: int = 300  # seconds
    
    # Resilience & DLQ
    EXTERNAL_CALL_MAX_RETRIES: int = 3
    EXTERNAL_CALL_RETRY_DELAYS: List[float] = [1.0, 2.0, 4.0]
    EXTERNAL_CALL_JITTER: bool = True
    DLQ_PAYLOAD_MAX_BYTES: int = 65536
    
    # Supported Salesforce Objects
    SUPPORTED_OBJECTS: List[str] = [
        "Account", "Contact", "Opportunity", "Lead", "Case", "Task", "Event", "Campaign", "User"
    ]
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache()
def get_settings():
    return Settings()

