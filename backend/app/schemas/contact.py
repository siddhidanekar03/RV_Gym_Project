from typing import Optional
from pydantic import BaseModel, Field, field_validator
from backend.app.core.validation import validate_and_normalize_phone


class ContactRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    phone: str = Field(..., min_length=7, max_length=50)
    email: Optional[str] = None
    message: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        res = validate_and_normalize_phone(v, required=True, field_name="phone")
        if not res:
            raise ValueError("Phone number is required.")
        return res


class ContactResponse(BaseModel):
    success: bool
    message: str
    id: str
