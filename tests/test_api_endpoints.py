import sys
import os
sys.path.insert(0, os.path.abspath("."))
import time
import uuid
import asyncio
import httpx
from app.main import app
from app.core.config import get_settings
from app.core.security import generate_canonical_string, compute_hmac_sha256

def make_hmac_headers(method: str, path: str, client_id: str = "coordinator", secret: str = None, body: bytes = b""):
    settings = get_settings()
    sec = secret or (settings.HMAC_SECRET_KEY_CORE if client_id == "coordinator" else settings.HMAC_SECRET_KEY_ENGINEER)
    now = str(time.time())
    nonce = str(uuid.uuid4())
    can = generate_canonical_string(method, path, now, nonce, body)
    sig = compute_hmac_sha256(sec, can)
    return {
        "X-SF-Signature": sig,
        "X-SF-Timestamp": now,
        "X-SF-Client-ID": client_id,
        "X-SF-Nonce": nonce,
        "Content-Type": "application/json"
    }

async def test_api_asgi():
    print("Testing REST API Endpoints in-process via ASGITransport...")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health check
        resp = await client.get("/api/health")
        assert resp.status_code == 200, f"Health check failed: {resp.text}"
        data = resp.json()
        print(f"  [PASS] GET /api/health -> {data['status']}")

        # 2. Service stats
        resp = await client.get("/api/stats")
        assert resp.status_code == 200
        print(f"  [PASS] GET /api/stats -> {resp.json()}")

        # 3. Key verify (Coordinator)
        path = "/api/key/verify"
        headers = make_hmac_headers("GET", path, client_id="coordinator")
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 200, f"Key verify failed: {resp.text}"
        key_data = resp.json()
        assert key_data["role"] == "coordinator"
        assert "POST" in key_data["permissions"]
        print(f"  [PASS] GET /api/key/verify (Coordinator) -> role={key_data['role']}")

        # 4. Key verify (Engineer)
        headers_eng = make_hmac_headers("GET", path, client_id="engineer")
        resp = await client.get(path, headers=headers_eng)
        assert resp.status_code == 200
        eng_data = resp.json()
        assert eng_data["role"] == "engineer"
        assert eng_data["permissions"] == ["GET"]
        print(f"  [PASS] GET /api/key/verify (Engineer) -> role={eng_data['role']}")

        # 5. Batch Info
        path = "/api/batch/info"
        headers = make_hmac_headers("GET", path)
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 200
        batch_info = resp.json()
        assert "Account" in batch_info["supported_objects"]
        print(f"  [PASS] GET /api/batch/info -> {len(batch_info['supported_objects'])} objects supported")

        # 6. Normalization Supported Objects
        path = "/api/normalization/supported-objects"
        headers = make_hmac_headers("GET", path)
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 200
        norm_info = resp.json()
        assert "Account" in norm_info["supported_objects"]
        assert "accounts" in norm_info["supported_objects"]["Account"]
        print(f"  [PASS] GET /api/normalization/supported-objects -> verified catalog")

        # 7. Scan list
        path = "/api/scan/list"
        headers = make_hmac_headers("GET", path)
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 200
        list_data = resp.json()
        assert "items" in list_data and "pagination" in list_data
        print(f"  [PASS] GET /api/scan/list -> {list_data['pagination']['total']} scans")

        # 8. Scan statistics
        path = "/api/scan/statistics"
        headers = make_hmac_headers("GET", path)
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 200
        print(f"  [PASS] GET /api/scan/statistics -> {resp.json()}")

        # 9. Maintenance detect crashed
        path = "/api/maintenance/detect-crashed"
        headers = make_hmac_headers("POST", path, body=b"{}")
        resp = await client.post(path, headers=headers, json={})
        assert resp.status_code == 200
        print(f"  [PASS] POST /api/maintenance/detect-crashed -> {resp.json()['status']}")

        # 10. Audit logs and stats
        path = "/api/audit/logs"
        headers = make_hmac_headers("GET", path)
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 200
        audit_data = resp.json()
        assert audit_data["pagination"]["total"] >= 1
        print(f"  [PASS] GET /api/audit/logs -> {audit_data['pagination']['total']} logs captured")

        path = "/api/audit/stats"
        headers = make_hmac_headers("GET", path)
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 200
        print(f"  [PASS] GET /api/audit/stats -> {resp.json()}")

    print("\nALL API ENDPOINT INTEGRATION TESTS PASSED SUCCESSFULLY!\n")

if __name__ == "__main__":
    asyncio.run(test_api_asgi())
