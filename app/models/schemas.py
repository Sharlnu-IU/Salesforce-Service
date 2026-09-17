from pydantic import BaseModel
from typing import Optional

class SalesforceCredentials(BaseModel):
    login_url: str = "https://login.salesforce.com"
    client_id: str
    client_secret: str
    username: Optional[str] = None
    password: Optional[str] = None
    security_token: Optional[str] = None
