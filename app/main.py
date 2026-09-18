import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text
from app.core.database import engine, AsyncSessionLocal
from app.models.base import Base
import app.models  # Ensures all models (Job, AuditLog, FailedExternalCall) are registered on Base
from app.services.storage import StorageService
from app.services.job_service import JobService
from app.api import credentials, scan, batch, normalization, maintenance, key, audit

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure tables exist in PostgreSQL
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

app = FastAPI(
    title="Salesforce Master Service",
    description="Service to extract, normalize, and store Salesforce data.",
    version="1.0.0",
    lifespan=lifespan
)

# Include all API Routers
app.include_router(credentials.router)
app.include_router(scan.router)
app.include_router(batch.router)
app.include_router(normalization.router)
app.include_router(maintenance.router)
app.include_router(key.router)
app.include_router(audit.router)

@app.get("/api/health")
async def health_check():
    """
    Public liveness and readiness probe checking PostgreSQL and MinIO connectivity.
    """
    db_status = "ok"
    minio_status = "ok"

    # 1. DB check
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Health check DB error: {e}")
        db_status = "unreachable"

    # 2. MinIO check
    try:
        storage = StorageService()
        storage.s3_client.head_bucket(Bucket=storage.bucket)
    except Exception as e:
        logger.error(f"Health check MinIO error: {e}")
        minio_status = "unreachable"

    overall = "ok" if (db_status == "ok" and minio_status == "ok") else "degraded"

    return {
        "status": overall,
        "service": "Salesforce Master Service",
        "dependencies": {
            "database": db_status,
            "minio": minio_status
        }
    }

@app.get("/api/stats")
async def service_stats():
    """
    Public lightweight service-level counters.
    """
    try:
        async with AsyncSessionLocal() as session:
            stats = await JobService.get_scan_statistics(session)
            return {
                "service": "Salesforce Master Service",
                "scans": stats
            }
    except Exception as e:
        return {
            "service": "Salesforce Master Service",
            "error": str(e)
        }
