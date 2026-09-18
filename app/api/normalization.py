import os
import glob
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import hmac_auth_required
from app.models.schemas import NormalizationRequest
from app.models.job import JobStatus
from app.services.job_service import JobService
from app.services.normalization.service import NormalizationService, SUPPORTED_CATALOG
from app.services.storage import StorageService

router = APIRouter(
    prefix="/api/normalization",
    tags=["normalization"],
    dependencies=[Depends(hmac_auth_required)]
)

@router.get("/supported-objects")
async def get_supported_objects():
    """
    Returns the static catalog of supported Salesforce objects and their output relational tables.
    """
    return {
        "supported_objects": SUPPORTED_CATALOG
    }

@router.post("/{scan_id}/normalize")
async def normalize_scan(
    scan_id: str,
    request: NormalizationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Runs normalization on extracted CSV files for a scan, with optional MinIO upload.
    """
    job = await JobService.get_job(db, scan_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scan not found")

    extracted_dir = os.path.join("data", "scans", scan_id, "extracted")
    normalized_dir = os.path.join("data", "scans", scan_id, "normalized")
    
    if not os.path.exists(extracted_dir):
        raise HTTPException(status_code=400, detail="No extracted files found for this scan. Run extraction first.")

    norm_service = NormalizationService(output_dir=normalized_dir)
    await JobService.update_status(db, scan_id, JobStatus.NORMALIZING)

    csv_files = glob.glob(os.path.join(extracted_dir, "*.csv"))
    all_files = []
    stats = {}

    for csv_path in csv_files:
        obj_name = os.path.splitext(os.path.basename(csv_path))[0]
        try:
            created, s = norm_service.normalize_csv(
                object_name=obj_name,
                csv_filepath=csv_path,
                output_format=request.format,
                target_dir=normalized_dir
            )
            all_files.extend(created)
            stats.update(s)
        except Exception as e:
            continue

    await JobService.update_status(db, scan_id, JobStatus.NORMALIZED, normalization_stats=stats)

    uploaded_keys = []
    if request.upload_to_minio:
        await JobService.update_status(db, scan_id, JobStatus.UPLOADING_TO_MINIO)
        storage_service = StorageService()
        uploaded_keys = await storage_service.upload_normalized_data(
            scan_id=scan_id,
            organization_id=job.organization_id,
            processing_date=request.processing_date,
            table_files=all_files
        )
        await JobService.update_status(db, scan_id, JobStatus.COMPLETED, minio_object_keys=uploaded_keys)

    return {
        "scan_id": scan_id,
        "format": request.format,
        "created_tables": [os.path.basename(f) for f in all_files],
        "statistics": stats,
        "minio_uploaded": bool(request.upload_to_minio),
        "uploaded_keys": uploaded_keys
    }

@router.post("/{scan_id}/normalize/{object_name}")
async def normalize_single_object(
    scan_id: str,
    object_name: str,
    output_format: str = Query("parquet", regex="^(parquet|json)$"),
    db: AsyncSession = Depends(get_db)
):
    """
    Normalizes a single extracted Salesforce object for a given scan.
    """
    job = await JobService.get_job(db, scan_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scan not found")

    csv_path = os.path.join("data", "scans", scan_id, "extracted", f"{object_name.lower()}.csv")
    if not os.path.exists(csv_path):
        raise HTTPException(status_code=404, detail=f"Extracted CSV not found for object: {object_name}")

    target_dir = os.path.join("data", "scans", scan_id, "normalized")
    norm_service = NormalizationService(output_dir=target_dir)

    created, stats = norm_service.normalize_csv(
        object_name=object_name,
        csv_filepath=csv_path,
        output_format=output_format,
        target_dir=target_dir
    )

    return {
        "scan_id": scan_id,
        "object_name": object_name,
        "created_files": [os.path.basename(f) for f in created],
        "statistics": stats
    }

@router.get("/{scan_id}/tables")
async def list_normalized_tables(scan_id: str, db: AsyncSession = Depends(get_db)):
    """
    Lists normalized table files currently present for a scan.
    """
    job = await JobService.get_job(db, scan_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scan not found")

    norm_dir = os.path.join("data", "scans", scan_id, "normalized")
    files = glob.glob(os.path.join(norm_dir, "*.*")) if os.path.exists(norm_dir) else []

    return {
        "scan_id": scan_id,
        "tables": [os.path.basename(f) for f in files],
        "minio_object_keys": job.minio_object_keys or []
    }
