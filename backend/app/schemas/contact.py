from typing import Optional
from pydantic import BaseModel, Field


class ContactRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    phone: str = Field(..., min_length=8, max_length=50)
    email: Optional[str] = None
    message: Optional[str] = None


class ContactResponse(BaseModel):
    success: bool
    message: str
    id: str
