import requests
import time
import json

base_url = "http://localhost:8000/api/scan"

def test_api():
    print("1. Starting scan via API...")
    payload = {
        "organization_id": "test_org_123",
        "object_name": "Account",
        "soql": "SELECT Id, Name, Type, BillingCity, BillingState FROM Account"
    }
    
    resp = requests.post(f"{base_url}/start", json=payload)
    if resp.status_code != 202:
        print(f"Failed to start scan: {resp.text}")
        return
        
    data = resp.json()
    scan_id = data["scan_id"]
    print(f"Scan started with ID: {scan_id}")
    
    print("2. Polling status via API...")
    while True:
        status_resp = requests.get(f"{base_url}/{scan_id}/status")
        if status_resp.status_code != 200:
            print(f"Failed to get status: {status_resp.text}")
            break
            
        status_data = status_resp.json()
        current_status = status_data["status"]
        print(f"Current Status: {current_status}")
        
        if current_status in ["COMPLETED", "FAILED", "CANCELLED"]:
            print("\nFinal Job Data:")
            print(json.dumps(status_data, indent=2))
            break
            
        time.sleep(3)

if __name__ == "__main__":
    test_api()
