import hashlib
import hmac
import time
import logging
from typing import Dict, Set, Tuple
from fastapi import Request, HTTPException, status
from app.core.config import get_settings
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

# In-memory replay cache: (nonce, timestamp)
_NONCE_CACHE: Dict[str, float] = {}

def _prune_nonce_cache(max_age: int):
    now = time.time()
    stale_keys = [k for k, ts in _NONCE_CACHE.items() if now - ts > max_age * 2]
    for k in stale_keys:
        _NONCE_CACHE.pop(k, None)

def generate_canonical_string(method: str, path: str, timestamp: str, nonce: str, body: bytes) -> str:
    body_hash = hashlib.sha256(body).hexdigest()
    return f"{method.upper()}\n{path}\n{timestamp}\n{nonce}\n{body_hash}"

def compute_hmac_sha256(secret: str, canonical_str: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        canonical_str.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

async def hmac_auth_required(request: Request) -> Dict[str, str]:
    """
    FastAPI dependency validating HMAC-SHA256 signature for incoming requests.
    Enforces role permissions: Coordinator (full access), Engineer (GET only).
    """
    settings = get_settings()
    
    # Dev bypass if explicitly disabled in config
    if not settings.HMAC_ENABLED:
        return {"client_id": "dev_admin", "role": "coordinator"}
        
    sig = request.headers.get("X-SF-Signature")
    ts = request.headers.get("X-SF-Timestamp")
    client_id = request.headers.get("X-SF-Client-ID")
    nonce = request.headers.get("X-SF-Nonce")
    
    client_ip = request.client.host if request.client else "unknown"
    method = request.method.upper()
    path = request.url.path
    
    # Check headers
    if not all([sig, ts, client_id, nonce]):
        await AuditService.write_audit(
            event_category="auth",
            event_type="auth_missing_headers",
            actor_client_id=client_id,
            http_method=method,
            endpoint=path,
            request_ip=client_ip,
            status_code=status.HTTP_401_UNAUTHORIZED,
            outcome="FAILURE",
            severity="WARN",
            error_detail="Missing required HMAC headers"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required HMAC authentication headers (X-SF-Signature, X-SF-Timestamp, X-SF-Client-ID, X-SF-Nonce)"
        )

    # Check timestamp freshness
    try:
        req_timestamp = float(ts)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid X-SF-Timestamp format")

    now = time.time()
    max_age = settings.HMAC_SIGNATURE_MAX_AGE
    if abs(now - req_timestamp) > max_age:
        await AuditService.write_audit(
            event_category="auth",
            event_type="auth_expired_timestamp",
            actor_client_id=client_id,
            http_method=method,
            endpoint=path,
            request_ip=client_ip,
            status_code=status.HTTP_401_UNAUTHORIZED,
            outcome="FAILURE",
            severity="WARN",
            error_detail=f"Timestamp difference {abs(now - req_timestamp):.1f}s exceeds limit {max_age}s"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Request timestamp expired (must be within {max_age} seconds of current time)"
        )

    # Check replay via Nonce
    _prune_nonce_cache(max_age)
    nonce_key = f"{client_id}:{nonce}"
    if nonce_key in _NONCE_CACHE:
        await AuditService.write_audit(
            event_category="auth",
            event_type="auth_replay_detected",
            actor_client_id=client_id,
            http_method=method,
            endpoint=path,
            request_ip=client_ip,
            status_code=status.HTTP_401_UNAUTHORIZED,
            outcome="DENIED",
            severity="ERROR",
            error_detail=f"Nonce {nonce} already used"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Replay attack detected: Nonce has already been used"
        )
    _NONCE_CACHE[nonce_key] = now

    # Determine role and expected secret
    if client_id.lower() == "coordinator":
        secret = settings.HMAC_SECRET_KEY_CORE
        role = "coordinator"
    elif client_id.lower() == "engineer":
        secret = settings.HMAC_SECRET_KEY_ENGINEER
        role = "engineer"
    else:
        # Check if secret matches core
        secret = settings.HMAC_SECRET_KEY_CORE
        role = "coordinator"

    # Read body for canonical string
    body = await request.body()
    canonical_str = generate_canonical_string(method, path, ts, nonce, body)
    expected_sig = compute_hmac_sha256(secret, canonical_str)

    # Constant-time comparison
    if not hmac.compare_digest(sig, expected_sig):
        await AuditService.write_audit(
            event_category="auth",
            event_type="auth_invalid_signature",
            actor_client_id=client_id,
            actor_role=role,
            http_method=method,
            endpoint=path,
            request_ip=client_ip,
            status_code=status.HTTP_401_UNAUTHORIZED,
            outcome="FAILURE",
            severity="WARN",
            error_detail="HMAC signature mismatch"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid HMAC signature"
        )

    # Enforce role restrictions: Engineer is read-only (GET only)
    if role == "engineer" and method != "GET":
        await AuditService.write_audit(
            event_category="auth",
            event_type="auth_permission_denied",
            actor_client_id=client_id,
            actor_role=role,
            http_method=method,
            endpoint=path,
            request_ip=client_ip,
            status_code=status.HTTP_403_FORBIDDEN,
            outcome="DENIED",
            severity="WARN",
            error_detail="Engineer role attempted non-GET request"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Engineer key is restricted to read-only (GET) requests"
        )

    # Auth Success
    await AuditService.write_audit(
        event_category="auth",
        event_type="auth_success",
        actor_client_id=client_id,
        actor_role=role,
        http_method=method,
        endpoint=path,
        request_ip=client_ip,
        status_code=status.HTTP_200_OK,
        outcome="SUCCESS",
        severity="INFO"
    )

    return {"client_id": client_id, "role": role}
