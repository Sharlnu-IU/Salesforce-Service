from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

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
    
    # MinIO
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET: str
    MINIO_SECURE: bool = False
    
    # HMAC Security
    HMAC_ENABLED: bool = True
    HMAC_SECRET_KEY_CORE: str
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache()
def get_settings():
    return Settings()
