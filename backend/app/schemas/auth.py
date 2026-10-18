from typing import Optional, Dict, Any, List
from pydantic import BaseModel, EmailStr, Field, field_validator
from backend.app.core.validation import validate_and_normalize_phone


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    membershipId: Optional[str] = Field(None, max_length=50)
    acceptedTerms: bool = Field(...)

    @field_validator("phone")
    @classmethod
    def validate_phone_number(cls, v: Optional[str]) -> Optional[str]:
        return validate_and_normalize_phone(v, required=False, field_name="phone")


class SafeUserResponse(BaseModel):
    id: str
    email: str
    name: str
    phone: Optional[str] = None
    role: str
    staffRole: Optional[str] = None
    branchId: Optional[str] = None
    membershipId: Optional[str] = None
    membershipPlan: Optional[str] = None
    memberSince: Optional[str] = None
    validUntil: Optional[str] = None
    status: str
    streakDays: int = 0
    attendanceThisMonth: int = 0
    todayCheckedIn: bool = False
    prs: Optional[Dict[str, str]] = None
    assignedPlan: Optional[Dict[str, str]] = None
    attendanceHistory: Optional[List[str]] = None


class AuthResponse(BaseModel):
    user: SafeUserResponse
    message: str
    csrfToken: Optional[str] = None


class LogoutResponse(BaseModel):
    success: bool
    message: str


class CsrfResponse(BaseModel):
    csrfToken: str
