from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.database import engine
from app.models.base import Base
from app.models.job import Job
from app.api import credentials, scan

@asynccontextmanager
async def lifespan(app: FastAPI):
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

app.include_router(credentials.router)
app.include_router(scan.router)

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "Salesforce Master Service"}
