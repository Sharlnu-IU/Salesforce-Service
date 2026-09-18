# Salesforce Master Service — Project Write-Up

## 1. Overview & Purpose

The **Salesforce Master Service** is a dedicated, self-contained data extraction and normalization engine built with **Python**, **FastAPI**, **PostgreSQL**, and **MinIO**. 

Its sole objective is to pull customer CRM data out of Salesforce on demand, normalize semi-structured and nested records into clean relational schemas, save them in compressed **Parquet** format, and publish them to shared object storage under standardized partitioned paths.

The service operates as an isolated microservice controlled by an external **Coordinator** system via an HMAC-signed REST API.

---

## 2. What Was Built

### A. Salesforce Authentication & Session Management
* **OAuth 2.0 Integration:** Supports both Client Credentials and Username-Password flows via `SalesforceAuthClient`.
* **Token Caching:** Implements an in-memory token cache with a 5-minute pre-expiry buffer to minimize redundant authentication round-trips.
* **Ephemeral Credentials:** Credentials provided in requests are used immediately in memory to acquire temporary bearer tokens and are never persisted to disk or the database.

### B. Bulk Export Engine (Bulk API 2.0)
* **Multi-Object Ingestion:** Manages Salesforce Bulk API 2.0 query jobs across all 8 supported CRM entity types (`Account`, `Contact`, `Opportunity`, `Lead`, `Case`, `Task`, `Event`, `Campaign`, `User`).
* **Asynchronous Polling & Heartbeats:** Polls Salesforce job status periodically while refreshing a database heartbeat to support active crash detection.
* **Streamed Downloads:** Asynchronously streams raw CSV result files to isolated local scratch directories (`data/scans/{scan_id}/extracted/`).
* **Remote Job Cancellation:** Supports best-effort remote job abortion (`abort_job`) when a scan is cancelled by the Coordinator.

### C. Normalization Layer (All 8 Objects)
Implements an extensible normalization hierarchy (`BaseNormalizer`) that transforms raw Salesforce CSV data into 13 discrete relational tables:

| Salesforce Object | Output Relational Tables |
|---|---|
| **Account** | `accounts`, `account_addresses`, `account_teams` |
| **Contact** | `contacts`, `contact_roles` |
| **Opportunity** | `opportunities`, `opportunity_line_items`, `opportunity_contact_roles` |
| **Lead** | `leads` |
| **Case** | `cases`, `case_comments` |
| **Task & Event** | `tasks`, `events` |
| **Campaign** | `campaigns`, `campaign_members` |
| **User** | `users` |

Output tables are serialized directly to **compressed Parquet files** via PyArrow (with JSON export supported on demand).

### D. Object Storage Publishing (MinIO / S3)
* **Standard Partitioning:** Publishes normalized tables according to the design path hierarchy:
  `salesforce/{table_name}/glynac_organization_id={org_id}/processing_date={date}/{table}.parquet`
* **Automated Provisioning:** Automatically checks for and creates the target bucket (`salesforce-data`) if it does not exist.
* **Non-Blocking I/O:** Uploads are executed asynchronously with retry wrapping and Dead-Letter Queue reporting on failures.

### E. Security & Dual-Key HMAC Authentication
* **Request Signing:** Every non-public route requires 4 HMAC-SHA256 headers: `X-SF-Signature`, `X-SF-Timestamp`, `X-SF-Client-ID`, and `X-SF-Nonce`.
* **Canonical Signature:** Computed as: `HMAC_SHA256(secret, "METHOD\nPATH\nTIMESTAMP\nNONCE\nSHA256(BODY)")`.
* **Replay Protection:** In-memory nonce cache rejects replayed requests.
* **Freshness Window:** Validates that timestamps are within $\pm 300\text{s}$.
* **Dual-Key Access Control:**
  * **Coordinator Key:** Full access (GET, POST, DELETE).
  * **Engineer Key:** Read-only access (GET only; rejects POST/DELETE with `403 Forbidden`).
* **Audit Trail:** Every auth event (success, missing header, invalid signature, replay, permission denial) is automatically logged to `audit_logs`.

### F. Resilience, Retry & Dead-Letter Queue (DLQ)
* **Bounded Retries with Backoff & Jitter (`retry.py`):** Automatically retries transient network errors (timeouts, connection drops) and HTTP `408/429/5xx` responses with randomized exponential delays.
* **Dead-Letter Queue (`dlq.py`):** If retries are exhausted, the failure is written to the `failed_external_calls` table with automatic sensitive payload scrubbing (redacting passwords, client secrets, and bearer tokens). Guaranteed never to raise exceptions.

### G. Job State Machine & Crash Recovery
* **PostgreSQL State Tracking:** Tracks every scan across a 14-stage lifecycle (`PENDING` $\rightarrow$ `BATCH_REQUESTED` $\rightarrow$ `BATCH_PROCESSING` $\rightarrow$ `BATCH_READY` $\rightarrow$ `DOWNLOADING` $\rightarrow$ `DOWNLOADED` $\rightarrow$ `EXTRACTING` $\rightarrow$ `EXTRACTED` $\rightarrow$ `NORMALIZING` $\rightarrow$ `NORMALIZED` $\rightarrow$ `UPLOADING_TO_MINIO` $\rightarrow$ `UPLOADED_TO_MINIO` $\rightarrow$ `COMPLETED`, plus `FAILED` and `CANCELLED`).
* **Heartbeat Crash Detection:** Background task flags active jobs with expired heartbeats as `FAILED`.
* **Resumption:** Provides a `POST /api/scan/{id}/resume` endpoint to resume interrupted or failed scans without losing completed progress.

### H. Complete REST API Surface
Implemented 18 endpoints across 7 functional routers:
* `/api/scan`: `start`, `{id}/status`, `{id}/cancel`, `{id}/resume`, `list`, `statistics`, `{id}/remove`.
* `/api/batch`: `info`.
* `/api/normalization`: `{id}/normalize`, `{id}/normalize/{object}`, `{id}/tables`, `supported-objects`.
* `/api/maintenance`: `cleanup`, `detect-crashed`.
* `/api/key`: `verify`.
* `/api/audit`: `logs`, `stats`.
* Public: `/api/health` (DB + MinIO readiness probe) and `/api/stats`.

---

## 3. How It Was Tested & Confirmed Working

The service was validated through both comprehensive automated test suites and real live end-to-end extraction against Salesforce.

### A. Automated Unit & Integration Tests

| Test Suite | File | What Was Tested | Result |
|---|---|---|:---:|
| **Normalizers Suite** | `tests/test_all_normalizers.py` | Ingests synthetic CRM records for all 8 objects, verifies relational splitting, validates row counts, and verifies Parquet readability. | **PASS** |
| **HMAC Security Suite** | `tests/test_hmac_auth.py` | Tests valid signatures, blocks replayed nonces, rejects invalid signatures, rejects expired timestamps, allows Engineer GET, and blocks Engineer POST. | **PASS** |
| **Resilience & DLQ Suite** | `tests/test_resilience_dlq.py` | Tests transient exception classification, retry backoff recovery, payload scrubbing, and PostgreSQL DLQ persistence. | **PASS** |
| **API Endpoints Suite** | `tests/test_api_endpoints.py` | Tests all 10 endpoint categories in-process via ASGI transport against live database and storage dependencies. | **PASS** |

### B. Live End-to-End Extraction Test (`tests/test_live_scan.py`)

A full end-to-end run was executed against a live Salesforce Developer Edition organization (`orgfarm-8293235b36-dev-ed.develop.my.salesforce.com`) and completed in **10.93 seconds**:

```json
{
  "scan_id": "d03ac78c-7bd8-4d12-bb03-caca6425d9b4",
  "organization_id": "test_org_001",
  "status": "COMPLETED",
  "pipeline_progress": {
    "batch_requested_at": "2026-09-18T01:38:17.449286+00:00",
    "downloaded_at": "2026-09-18T01:38:27.470627+00:00",
    "extracted_at": "2026-09-18T01:38:27.486689+00:00",
    "normalized_at": "2026-09-18T01:38:27.530923+00:00",
    "minio_uploaded_at": "2026-09-18T01:38:27.595116+00:00",
    "duration_seconds": 10.93
  },
  "entity_record_counts": {
    "account": 29
  },
  "batch_job_ids": {
    "Account": "750g800000IR8okAAD"
  },
  "batch_status": {
    "Account": "JobComplete"
  },
  "normalization_stats": {
    "accounts": 13,
    "account_addresses": 12,
    "account_teams": 0
  },
  "minio_object_keys": [
    "salesforce/accounts/glynac_organization_id=test_org_001/processing_date=2026-09-18/accounts.parquet",
    "salesforce/account_addresses/glynac_organization_id=test_org_001/processing_date=2026-09-18/account_addresses.parquet",
    "salesforce/account_teams/glynac_organization_id=test_org_001/processing_date=2026-09-18/account_teams.parquet"
  ]
}
```

Inspection in the MinIO Console verified that all Parquet files were correctly partitioned and readable.

---

## 4. What Is Incomplete / Out-of-Scope

### Scope Adherence (DESIGN.md §9)
All features specified in [DESIGN.md](DESIGN.md) have been implemented. The following were intentionally excluded in accordance with **Section 9 ("What NOT To Build")**:
1. **No Deduplication or Delta Tracking:** As specified, every scan produces a full, fresh snapshot of the organization's data. There is no change-data-capture (CDC) or diffing logic.
2. **No PII Masking / Redaction:** CRM data passes through intact into internal secure storage without field obfuscation.

### Potential Future Enhancements
* **Distributed Nonce Caching:** The current nonce replay cache is in-memory within the FastAPI application process. In a horizontally scaled cluster behind a round-robin load balancer, sharing nonces via Redis would prevent cross-instance replays.
* **Result Paging for Gigabyte-Scale Datasets:** Bulk API 2.0 query results exceeding 1GB return a `locator` parameter for paging. While supported in `SalesforceBulkClient`, multi-gigabyte datasets could be streamed in parallel chunks directly to MinIO.
