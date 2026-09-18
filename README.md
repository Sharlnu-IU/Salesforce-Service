# Salesforce Master Service

This service is a dedicated extraction pipeline designed to pull data out of Salesforce on demand and hand it off in a clean, organized form. 

It exposes a REST API built with FastAPI that allows a Coordinator system to start an extraction scan, check its progress, and download the resulting clean data.

## 🚀 How it Works

When you trigger a new scan for an organization, the service performs the following steps in the background:
1. **Auth:** Logs into Salesforce using OAuth 2.0 (Client Credentials flow) to retrieve a temporary access token.
2. **Batch Export:** Submits a Salesforce Bulk API 2.0 query job for the requested record type (e.g., Accounts, Contacts).
3. **Polling & Download:** Periodically polls the Salesforce Bulk API until the data is fully compiled, then downloads the raw CSV file to local storage.
4. **Extraction & Normalization:** Parses the raw CSV using `pandas` and normalizes the data (flattening nested structures into relational tables). The clean tables are saved locally as compressed Parquet files.
5. **Storage:** Uploads the normalized Parquet files to an S3-compatible MinIO object storage bucket, partitioned by organization and date.
6. **Cleanup:** Safely deletes the local temporary files.

The entire process is tracked in a PostgreSQL database so you can monitor the exact phase of the pipeline in real-time.

---

## 🛠️ Setup & Installation

### 1. Salesforce App & User Setup
To allow this service to authenticate with Salesforce, configure an OAuth application using the **OAuth 2.0 Client Credentials Flow**:

#### A. Create the App
1. Log into your Salesforce Developer Edition or Sandbox as an Administrator.
2. Navigate to **Setup** ➔ **App Manager** (or **External Client App Manager**).
3. Click **New Connected App** (or **New External Client App**).
4. Fill in the required basic info (Connected App Name, API Name, Contact Email).
5. Under **API (Enable OAuth Settings)**:
   - Check **Enable OAuth Settings**.
   - Callback URL: `http://localhost:8000/oauth/callback` (or any valid URL; not used directly in Client Credentials flow).
   - Selected OAuth Scopes: Add **Manage user data via APIs (`api`)** and optionally **Perform requests at any time (`refresh_token, offline_access`)**.
   - Check **Enable Client Credentials Flow**.
6. Click **Save** and wait a few minutes for initial propagation.

#### B. Configure Policies & IP Relaxation
1. In **App Manager**, find your app, click the dropdown arrow on the right, and select **Manage** (or click **Manage Connected Apps**).
2. Click **Edit Policies**:
   - **Permitted Users**: Set to **"All users may self-authorize"** (or "Admin approved users are pre-authorized" if restricting by Profile/Permission Set).
   - **IP Relaxation**: Set to **"Relax IP restrictions"**. 
     > ⚠️ **Important:** If your org or profile enforces Login IP Ranges and this is left as "Enforce IP restrictions", any token request from an unrecognized local/container IP will fail with an `ip restricted` error.
   - **Client Credentials Flow**:
     - Under **Run As**, select an active Salesforce user who will act as the integration execution context.
3. Click **Save**.

#### C. Execution ("Run As") User Configuration
The execution user selected in the step above requires appropriate permissions to read the CRM records:
1. **Active Status:** Ensure the user account is Active and not locked.
2. **API Access:** The user's Profile or assigned Permission Set must have the **"API Enabled"** administrative permission checked.
3. **Object Permissions:** Grant **Read** (or **View All**) permissions on all objects you intend to export (`Account`, `Contact`, `Opportunity`, `Lead`, `Case`, etc.).
4. **Field-Level Security (FLS):** Ensure the user has read visibility on the fields requested in your SOQL queries (e.g., `BillingCity`, `BillingState`, etc.).
5. If using **"Admin approved users are pre-authorized"**, navigate to the app's **Manage** page, scroll to **Profiles** or **Permission Sets**, and explicitly add the execution user's profile/permission set.

#### D. Retrieve Consumer Key & Secret
1. Go back to **Setup** ➔ **App Manager**, find your app, click **View** (or click **Manage Consumer Details**).
2. Copy the **Consumer Key** (`SF_CLIENT_ID`) and **Consumer Secret** (`SF_CLIENT_SECRET`).
3. Add them to your `.env` file along with your org's `My Domain` login URL (`SF_LOGIN_URL`).
*(Note: Salesforce can take 5–10 minutes to propagate newly created OAuth credentials).*

### 2. Prerequisites
- Docker and Docker Compose (for PostgreSQL and MinIO)
- Python 3.10+
- A Salesforce Developer Edition org (or a Sandbox)

### 3. Infrastructure Setup
Start the required PostgreSQL and MinIO containers using Docker Compose:
```bash
docker compose up -d
```
*Note: This will spin up PostgreSQL on port `5432` and MinIO on port `9000`.*

### 4. Application Setup
Install the required Python dependencies:
```bash
python -m venv .venv
# Activate the virtual environment
.venv\Scripts\Activate.ps1  # Windows PowerShell
source .venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
```

### 5. Configuration
Create a `.env` file in the root of the project with the following credentials. (Use the `.env.example` as a template).

```ini
APP_ENV=development
LOG_LEVEL=DEBUG

# Database Configuration (matches docker-compose.yml)
DATABASE_URL=postgresql+asyncpg://salesforce:password@localhost:5432/salesforce_master

# Salesforce API Credentials
SF_LOGIN_URL=https://your-org-name.develop.my.salesforce.com
SF_CLIENT_ID=your_consumer_key
SF_CLIENT_SECRET=your_consumer_secret
SF_API_VERSION=v60.0

# MinIO Configuration
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=password123
MINIO_BUCKET=salesforce-data
MINIO_SECURE=false
```

> 📌 **Important Note on `SF_LOGIN_URL`:**
> The OAuth 2.0 Client Credentials flow **requires** your organization's specific **My Domain URL**. Generic endpoints like `https://login.salesforce.com` or `https://test.salesforce.com` will be rejected by Salesforce for Client Credentials grants.
> - **How to find it:** Log into Salesforce and copy the base domain from your browser's address bar (e.g., `https://orgfarm-xyz-dev-ed.develop.my.salesforce.com` or `https://company.my.salesforce.com`), or navigate to **Setup** ➔ **Company Settings** ➔ **My Domain** to view your **Current My Domain URL**.
> - **Format Examples:**
>   - **Developer Edition:** `https://<domain>.develop.my.salesforce.com`
>   - **Production / Scratch Org:** `https://<domain>.my.salesforce.com`
>   - **Sandbox:** `https://<domain>--<sandbox>.sandbox.my.salesforce.com`

---

## 🏃‍♂️ Running the Application

To start the FastAPI web server, run:
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🧪 Testing the Application (via the UI)

FastAPI automatically generates an interactive Swagger UI that allows you to test the API directly from your browser!

1. Open your browser and go to: **[http://localhost:8000/docs](http://localhost:8000/docs)**
2. You will see a list of available endpoints.

### Step 1: Start a Scan
1. Click on the green **`POST /api/scan/start`** endpoint to expand it.
2. Click **"Try it out"** in the top right corner.
3. In the Request Body text box, enter a payload like this:
   ```json
   {
     "organization_id": "test_org_123",
     "object_name": "Account",
     "soql": "SELECT Id, Name, Type, BillingCity, BillingState FROM Account"
   }
   ```
4. Click **Execute**.
5. Scroll down to the Response section. You should see a `202 Accepted` response with a unique `scan_id` (e.g., `"2f6bf985-df3a-4948-bf59-09b8f0400ab2"`). Copy this ID!

### Step 2: Monitor the Scan
1. Scroll down to the blue **`GET /api/scan/{scan_id}/status`** endpoint and click to expand it.
2. Click **"Try it out"**.
3. Paste the `scan_id` you copied earlier into the `scan_id` input box.
4. Click **Execute**.
5. You will see the current status of your job! If you click Execute repeatedly every few seconds, you can watch the `status` transition in real-time:
   `PENDING` ➔ `BATCH_REQUESTED` ➔ `BATCH_PROCESSING` ➔ `DOWNLOADING` ➔ `NORMALIZING` ➔ `UPLOADING_TO_MINIO` ➔ `COMPLETED`.

Once the status is `COMPLETED`, check your MinIO bucket (you can access the MinIO console at `http://localhost:9001` with `admin` / `password123`) to see your beautifully cleaned Parquet files securely stored and ready for use!
