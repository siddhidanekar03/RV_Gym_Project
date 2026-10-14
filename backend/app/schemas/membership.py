from typing import List, Optional
from pydantic import BaseModel, Field


class PlanItem(BaseModel):
    id: str
    name: str
    category: str = "general"
    accessScope: str = "single_branch"
    price: int
    currency: str = "₹"
    billingCycle: str
    durationDays: int
    status: str = "active"
    featured: bool = False
    perks: List[str]


class PlansResponse(BaseModel):
    plans: List[PlanItem]


class EnrollmentRequest(BaseModel):
    planId: str
    name: str = Field(..., min_length=2, max_length=150)
    phone: str = Field(..., min_length=8, max_length=50)
    email: Optional[str] = None
    acceptedTerms: bool


class EnrollmentDetail(BaseModel):
    id: str
    planId: str
    planName: str
    price: int
    currency: str
    name: str
    phone: str
    email: Optional[str] = ""
    status: str
    enrolledAt: str
    invoiceId: Optional[str] = None
    invoiceNumber: Optional[str] = None


class EnrollmentResponse(BaseModel):
    success: bool
    message: str
    enrollment: EnrollmentDetail


class RenewalRequest(BaseModel):
    planId: Optional[str] = None


class RenewalResponse(BaseModel):
    success: bool
    message: str
    validUntil: str
    invoiceNumber: str


class FreezeRequest(BaseModel):
    userId: str
    freezeDays: int = Field(..., ge=1, le=90)
    reason: Optional[str] = None


class FreezeResponse(BaseModel):
    success: bool
    message: str
    status: str
    newValidUntil: str


class CancelRequest(BaseModel):
    userId: str
    reason: Optional[str] = None


class CancelResponse(BaseModel):
    success: bool
    message: str
    status: str
