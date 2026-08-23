from pydantic import BaseModel, Field
from typing import Optional, Dict

class RawLead(BaseModel):
    company_name: str
    website: Optional[str] = None
    source: str = ""
    source_url: Optional[str] = None
    location: Optional[str] = None
    extra: Dict = Field(default_factory=dict)