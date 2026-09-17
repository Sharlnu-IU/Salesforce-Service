from pydantic import BaseModel
from typing import Optional

class SalesforceCredentials(BaseModel):
    login_url: str = "https://login.salesforce.com"
    client_id: str
    client_secret: str
    grant_type: Optional[str] = "client_credentials"
    username: Optional[str] = None
    password: Optional[str] = None
    security_token: Optional[str] = None

class ScanStartRequest(BaseModel):
    organization_id: str
    object_name: str
    soql: str
