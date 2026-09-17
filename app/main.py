from fastapi import FastAPI

app = FastAPI(
    title="Salesforce Master Service",
    description="Service to extract, normalize, and store Salesforce data.",
    version="1.0.0"
)

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "Salesforce Master Service"}
