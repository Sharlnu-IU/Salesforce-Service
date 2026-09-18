# test_live_scan.py
import time
import uuid
import requests
import json
from app.core.config import get_settings
from app.core.security import generate_canonical_string, compute_hmac_sha256

settings = get_settings()
BASE_URL = "http://localhost:8000"

def get_hmac_headers(method: str, path: str, body: bytes = b""):
    now = str(time.time())
    nonce = str(uuid.uuid4())
    can = generate_canonical_string(method, path, now, nonce, body)
    sig = compute_hmac_sha256(settings.HMAC_SECRET_KEY_CORE, can)
    return {
        "X-SF-Signature": sig,
        "X-SF-Timestamp": now,
        "X-SF-Client-ID": "coordinator",
        "X-SF-Nonce": nonce,
        "Content-Type": "application/json"
    }

def run_live_test():
    # 1. Health Check
    health = requests.get(f"{BASE_URL}/api/health").json()
    print(f"1. Health Check: {health}")

    # 2. Start Scan for Account
    start_path = "/api/scan/start"
    payload = json.dumps({
        "organization_id": "test_org_001",
        "objects": ["Account"]
    }).encode("utf-8")
    
    headers = get_hmac_headers("POST", start_path, body=payload)
    resp = requests.post(f"{BASE_URL}{start_path}", headers=headers, data=payload)
    print(f"2. Start Scan Response ({resp.status_code}): {resp.text}")
    
    if resp.status_code != 202:
        return
    scan_id = resp.json()["scan_id"]

    # 3. Poll Scan Status
    status_path = f"/api/scan/{scan_id}/status"
    print(f"3. Polling status for scan {scan_id}...")
    while True:
        status_headers = get_hmac_headers("GET", status_path)
        status_resp = requests.get(f"{BASE_URL}{status_path}", headers=status_headers).json()
        current_status = status_resp["status"]
        print(f"   -> Status: {current_status}")

        if current_status in ("COMPLETED", "FAILED", "CANCELLED"):
            print("\nFinal Scan Details:")
            print(json.dumps(status_resp, indent=2, default=str))
            break
        time.sleep(3)

if __name__ == "__main__":
    run_live_test()
