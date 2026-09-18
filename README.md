# Salesforce Master Service

This service is a dedicated, resilient extraction pipeline designed to pull data out of Salesforce on demand, normalize it into clean relational schemas, and upload it in compressed Parquet format to shared object storage (MinIO).

It exposes a REST API built with FastAPI that allows an external **Coordinator** system to initiate extraction scans, check progress, cancel/resume runs, inspect normalized tables, and query audit logs.

---

## 📚 Project Documentation
* **[Architecture Guide](docs/ARCHITECTURE.md):** Architectural diagrams, component interactions, and state machines.
* **[Design Specification](docs/DESIGN.md):** Full functional specification, milestones, and requirements.
* **[Project Write-Up](docs/WRITEUP.md):** Project recap, implementation details, verification results, and scope adherence.

---

## 🚀 How it Works


When a scan is triggered for an organization, the service executes the following end-to-end pipeline in the background:
1. **OAuth Authentication:** Obtains an ephemeral bearer token via Salesforce OAuth 2.0 (Client Credentials / Password flow) and caches it in memory until near expiry. Credentials are never persisted.
2. **Bulk Export Initiation:** Dispatches Salesforce Bulk API 2.0 query jobs for all supported Salesforce objects (`Account`, `Contact`, `Opportunity`, `Lead`, `Case`, `Task`, `Event`, `Campaign`, `User`).
3. **Polling & Heartbeats:** Periodically polls the Bulk API while refreshing a database heartbeat to ensure active crash detection. Supports cancellation during execution.
4. **Download:** Streams raw CSV results to temporary local storage (`data/scans/{scan_id}/extracted/`).
5. **Extraction & Relational Normalization:** Reads CSVs and passes records through object-specific normalizers to flatten nested fields into relational tables. Saves clean tables as compressed Parquet files.
6. **Publish to Object Storage (MinIO):** Uploads normalized Parquet files to MinIO under standard partitioned paths:
   `salesforce/{table_name}/glynac_organization_id={org_id}/processing_date={date}/{table}.parquet`
7. **Cleanup:** Purges local scratch files and transitions job status to `COMPLETED`.

---

## 📊 Supported Data Entities & Normalized Output Tables

| Salesforce Object | Output Normalized Relational Tables |
|---|---|
| **Account** | `accounts`, `account_addresses`, `account_teams` |
| **Contact** | `contacts`, `contact_roles` |
| **Opportunity** | `opportunities`, `opportunity_line_items`, `opportunity_contact_roles` |
| **Lead** | `leads` |
| **Case** | `cases`, `case_comments` |
| **Task & Event** | `tasks`, `events` |
| **Campaign** | `campaigns`, `campaign_members` |
| **User** | `users` |

---

## 🛠️ Setup & Installation

### 1. Prerequisites
- Docker and Docker Compose (for PostgreSQL and MinIO)
- Python 3.10+
- A Salesforce Developer Edition org (or Sandbox)

### 2. Salesforce Account & Connected App Setup
To allow this service to authenticate with Salesforce, configure an OAuth application using the **OAuth 2.0 Client Credentials Flow**:

#### A. Create the Connected App
1. Log into your Salesforce Developer Edition or Sandbox as a System Administrator.
2. Navigate to **Setup** ➔ **App Manager** (or **External Client App Manager**).
3. Click **New Connected App** (or **New External Client App**).
4. Fill in the required basic info (Connected App Name, API Name, Contact Email).
5. Under **API (Enable OAuth Settings)**:
   - Check **Enable OAuth Settings**.
   - Callback URL: `http://localhost:8000/oauth/callback` (or any valid URL; not used directly in Client Credentials flow).
   - Selected OAuth Scopes: Add **Manage user data via APIs (`api`)** and optionally **Perform requests at any time (`refresh_token, offline_access`)**.
   - Check **Enable Client Credentials Flow**.
6. Click **Save** and wait a few minutes for initial propagation.

#### B. Configure App Policies & IP Relaxation
1. In **App Manager**, find your newly created app, click the dropdown arrow on the far right, and select **Manage**.
2. Click **Edit Policies**:
   - **Permitted Users**: Set to **"All users may self-authorize"** (or "Admin approved users are pre-authorized" if restricting by Profile/Permission Set).
   - **IP Relaxation**: Set to **"Relax IP restrictions"**. 
     > ⚠️ **Important:** If your org or profile enforces Login IP Ranges and this is left as "Enforce IP restrictions", any token request from an unrecognized local/container IP will fail with an `ip restricted` error.
   - **Client Credentials Flow**:
     - Under **Run As**, click the lookup icon and select an active Salesforce user who will act as the integration execution context.
3. Click **Save**.

#### C. Execution ("Run As") User Configuration
The execution user selected in the step above requires appropriate permissions to read CRM records:
1. **Active Status:** Ensure the user account is **Active** and not locked.
2. **API Access:** The user's Profile or assigned Permission Set must have the **"API Enabled"** administrative permission enabled.
3. **Object Permissions:** Grant **Read** (or **View All**) permissions on all objects you intend to export (`Account`, `Contact`, `Opportunity`, `Lead`, `Case`, `Task`, `Event`, `Campaign`, `User`).
4. **Field-Level Security (FLS):** Ensure the user has read visibility on the fields requested in your queries (e.g., `BillingCity`, `BillingState`, etc.).
5. If using **"Admin approved users are pre-authorized"**, scroll down to **Profiles** or **Permission Sets** on the app's Manage page, and explicitly add the execution user's profile/permission set.

#### D. Retrieve Consumer Key, Secret & My Domain URL
1. Go back to **Setup** ➔ **App Manager**, find your app, click **View** (or click **Manage Consumer Details**).
2. Copy the **Consumer Key** (`SF_CLIENT_ID`) and **Consumer Secret** (`SF_CLIENT_SECRET`).
3. Find your org's **My Domain URL** (`SF_LOGIN_URL`):
   > 📌 **Important Note on `SF_LOGIN_URL`:**
   > The OAuth 2.0 Client Credentials flow **requires** your organization's specific **My Domain URL**. Generic endpoints like `https://login.salesforce.com` or `https://test.salesforce.com` will be rejected with an `unsupported_grant_type` or `invalid_client` error.
   > - **How to find it:** Copy the base domain from your browser address bar when logged in (e.g., `https://orgfarm-xyz-dev-ed.develop.my.salesforce.com`), or navigate to **Setup** ➔ **Company Settings** ➔ **My Domain** to view your **Current My Domain URL**.
   > - **Format Examples:**
   >   - **Developer Edition:** `https://<domain>.develop.my.salesforce.com`
   >   - **Production / Scratch Org:** `https://<domain>.my.salesforce.com`
   >   - **Sandbox:** `https://<domain>--<sandbox>.sandbox.my.salesforce.com`
4. Add these values to your `.env` file. *(Note: Salesforce can take 5–10 minutes to propagate newly created OAuth credentials).*


### 3. Infrastructure Setup
Start PostgreSQL and MinIO using Docker Compose:
```bash
docker compose up -d
```
* **PostgreSQL:** `localhost:5432` (database: `salesforce_master`, user: `salesforce`, password: `password`)
* **MinIO API:** `localhost:9000`
* **MinIO Web Console:** [http://localhost:9001](http://localhost:9001) (User: `admin`, Password: `password123`)

### 4. Application Setup
Install Python dependencies in a virtual environment:
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows PowerShell
pip install -r requirements.txt
```

### 5. Configuration

Create a `.env` file in the project root (see `.env.example`):
```ini
APP_ENV=development
LOG_LEVEL=INFO

# PostgreSQL Database
DATABASE_URL=postgresql+asyncpg://salesforce:password@localhost:5432/salesforce_master

# Salesforce API Credentials
SF_LOGIN_URL=https://your-domain.develop.my.salesforce.com
SF_CLIENT_ID=your_consumer_key
SF_CLIENT_SECRET=your_consumer_secret
SF_API_VERSION=v60.0

# MinIO Configuration
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=password123
MINIO_BUCKET=salesforce-data
MINIO_SECURE=false

# HMAC Security
HMAC_ENABLED=true
HMAC_SECRET_KEY_CORE=your_core_secret
HMAC_SECRET_KEY_ENGINEER=your_engineer_secret
HMAC_SIGNATURE_MAX_AGE=300
```

> 💡 **Tip:** Set `HMAC_ENABLED=false` in `.env` if you want to bypass signature verification during local testing with Swagger UI or Postman.

---

## 🏃‍♂️ Running the Service

Start the FastAPI application with Uvicorn:
```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
API Documentation (Swagger UI): [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🔒 Security & HMAC-SHA256 Authentication

When `HMAC_ENABLED=true`, all protected routes require 4 HMAC-SHA256 signature headers:
* `X-SF-Signature`: Cryptographic signature: `HMAC_SHA256(secret, "METHOD\nPATH\nTIMESTAMP\nNONCE\nSHA256(BODY)")`
* `X-SF-Timestamp`: Current epoch time in seconds (validated within $\pm 300\text{s}$).
* `X-SF-Client-ID`: Client identity (`coordinator` for full read/write; `engineer` for read-only `GET`).
* `X-SF-Nonce`: Unique UUID per request to prevent replay attacks.

---

## 📡 API Endpoints Summary

### Scan Router (`/api/scan`)
* `POST /api/scan/start` — Starts an extraction scan for an organization (202 Accepted).
* `GET /api/scan/{id}/status` — Returns job status, duration, record counts, and pipeline timestamps.
* `POST /api/scan/{id}/cancel` — Cancels an active scan and aborts remote Bulk API queries.
* `POST /api/scan/{id}/resume` — Resumes an interrupted scan from its latest stage.
* `GET /api/scan/list` — Paginated list of scans with organization filtering.
* `GET /api/scan/statistics` — Aggregate counts of scans grouped by status.
* `DELETE /api/scan/{id}/remove` — Purges completed/failed job records and scratch disk files.

### Batch & Normalization Routers
* `GET /api/batch/info` — Returns configured Bulk API query defaults and supported objects.
* `POST /api/normalization/{id}/normalize` — Triggers standalone normalization with optional MinIO upload.
* `POST /api/normalization/{id}/normalize/{object}` — Normalizes a single extracted object.
* `GET /api/normalization/{id}/tables` — Lists generated Parquet tables for a scan.
* `GET /api/normalization/supported-objects` — Static catalog of supported objects and relational tables.

### Maintenance & Observability Routers
* `POST /api/maintenance/detect-crashed` — Flags scans with expired heartbeats as `FAILED`.
* `POST /api/maintenance/cleanup` — Deletes scans and local files older than N days.
* `GET /api/key/verify` — Inspects caller's verified HMAC role and permissions.
* `POST /api/validate-credentials` — Live token grant test without starting a scan.
* `GET /api/audit/logs` — Paginated query of security, authentication, and job events.
* `GET /api/audit/stats` — Rolling-window audit statistics.
* `GET /api/health` — Public liveness and readiness probe (checks DB & MinIO).
* `GET /api/stats` — Public service-level metrics.

---

## 🧪 Running Automated Tests

Run the full automated test suite using the virtual environment:

```powershell
# 1. Test all 8 normalizers & Parquet generation
.venv\Scripts\python.exe tests/test_all_normalizers.py

# 2. Test dual-key HMAC security, replay prevention, and permissions
.venv\Scripts\python.exe tests/test_hmac_auth.py

# 3. Test resilience, exponential backoff, DLQ scrubbing & database persistence
.venv\Scripts\python.exe tests/test_resilience_dlq.py

# 4. Test all REST API endpoints in-process via ASGI
.venv\Scripts\python.exe tests/test_api_endpoints.py

# 5. Run live end-to-end extraction against Salesforce
.venv\Scripts\python.exe tests/test_live_scan.py
```
