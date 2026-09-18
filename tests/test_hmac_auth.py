import sys
import os
sys.path.insert(0, os.path.abspath("."))
import time
import asyncio
import uuid
from starlette.requests import Request
from fastapi import HTTPException
from app.core.config import get_settings
from app.core.security import (
    generate_canonical_string,
    compute_hmac_sha256,
    hmac_auth_required
)

async def test_hmac_flow():
    settings = get_settings()
    core_secret = settings.HMAC_SECRET_KEY_CORE
    eng_secret = settings.HMAC_SECRET_KEY_ENGINEER
    
    print("Testing HMAC Authentication...")

    # Helper to mock Starlette Request
    def create_mock_request(method: str, path: str, headers: dict, body: bytes = b""):
        scope = {
            "type": "http",
            "method": method.upper(),
            "path": path,
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": ("127.0.0.1", 12345),
        }
        req = Request(scope)
        # Mock body receive
        async def mock_receive():
            return {"type": "http.request", "body": body}
        req._receive = mock_receive
        return req

    # 1. Valid Coordinator Request
    now = str(time.time())
    nonce = str(uuid.uuid4())
    body = b'{"test": "payload"}'
    can_str = generate_canonical_string("POST", "/api/scan/start", now, nonce, body)
    sig = compute_hmac_sha256(core_secret, can_str)

    headers = {
        "X-SF-Signature": sig,
        "X-SF-Timestamp": now,
        "X-SF-Client-ID": "coordinator",
        "X-SF-Nonce": nonce,
        "Content-Type": "application/json"
    }
    req = create_mock_request("POST", "/api/scan/start", headers, body)
    auth_ctx = await hmac_auth_required(req)
    assert auth_ctx["role"] == "coordinator"
    print("  [PASS] Valid Coordinator HMAC accepted")

    # 2. Replay attack rejection (same nonce)
    req_replay = create_mock_request("POST", "/api/scan/start", headers, body)
    try:
        await hmac_auth_required(req_replay)
        assert False, "Should have failed on replay"
    except HTTPException as e:
        assert e.status_code == 401
        assert "Replay attack" in e.detail
        print("  [PASS] Nonce replay rejected")

    # 3. Invalid signature rejection
    bad_headers = headers.copy()
    bad_headers["X-SF-Nonce"] = str(uuid.uuid4())
    bad_headers["X-SF-Signature"] = "invalid_signature_hash"
    req_bad_sig = create_mock_request("POST", "/api/scan/start", bad_headers, body)
    try:
        await hmac_auth_required(req_bad_sig)
        assert False, "Should have failed on bad signature"
    except HTTPException as e:
        assert e.status_code == 401
        assert "Invalid HMAC signature" in e.detail
        print("  [PASS] Invalid signature rejected")

    # 4. Expired timestamp rejection
    old_ts = str(time.time() - 400) # Exceeds 300s max age
    old_nonce = str(uuid.uuid4())
    old_can = generate_canonical_string("POST", "/api/scan/start", old_ts, old_nonce, body)
    old_sig = compute_hmac_sha256(core_secret, old_can)
    expired_headers = {
        "X-SF-Signature": old_sig,
        "X-SF-Timestamp": old_ts,
        "X-SF-Client-ID": "coordinator",
        "X-SF-Nonce": old_nonce
    }
    req_expired = create_mock_request("POST", "/api/scan/start", expired_headers, body)
    try:
        await hmac_auth_required(req_expired)
        assert False, "Should have failed on expired timestamp"
    except HTTPException as e:
        assert e.status_code == 401
        assert "expired" in e.detail
        print("  [PASS] Expired timestamp rejected")

    # 5. Valid Engineer GET Request
    eng_now = str(time.time())
    eng_nonce = str(uuid.uuid4())
    eng_can = generate_canonical_string("GET", "/api/key/verify", eng_now, eng_nonce, b"")
    eng_sig = compute_hmac_sha256(eng_secret, eng_can)
    eng_headers = {
        "X-SF-Signature": eng_sig,
        "X-SF-Timestamp": eng_now,
        "X-SF-Client-ID": "engineer",
        "X-SF-Nonce": eng_nonce
    }
    req_eng = create_mock_request("GET", "/api/key/verify", eng_headers, b"")
    eng_auth = await hmac_auth_required(req_eng)
    assert eng_auth["role"] == "engineer"
    print("  [PASS] Valid Engineer GET accepted")

    # 6. Engineer POST rejection (Permission denied)
    eng_post_now = str(time.time())
    eng_post_nonce = str(uuid.uuid4())
    eng_post_can = generate_canonical_string("POST", "/api/scan/start", eng_post_now, eng_post_nonce, body)
    eng_post_sig = compute_hmac_sha256(eng_secret, eng_post_can)
    eng_post_headers = {
        "X-SF-Signature": eng_post_sig,
        "X-SF-Timestamp": eng_post_now,
        "X-SF-Client-ID": "engineer",
        "X-SF-Nonce": eng_post_nonce
    }
    req_eng_post = create_mock_request("POST", "/api/scan/start", eng_post_headers, body)
    try:
        await hmac_auth_required(req_eng_post)
        assert False, "Engineer should be forbidden on POST"
    except HTTPException as e:
        assert e.status_code == 403
        assert "restricted to read-only" in e.detail
        print("  [PASS] Engineer POST forbidden (read-only enforced)")

    print("\nALL HMAC SECURITY TESTS PASSED SUCCESSFULLY!\n")

if __name__ == "__main__":
    asyncio.run(test_hmac_flow())
