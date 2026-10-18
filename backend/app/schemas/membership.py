from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from backend.app.core.validation import validate_and_normalize_phone


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
    model_config = ConfigDict(populate_by_name=True)

    planId: str = Field(..., alias="plan_id")
    branchId: Optional[str] = Field(default="narsobawadi", alias="branch_id")
    name: str = Field(..., min_length=2, max_length=150)
    phone: str = Field(..., min_length=7, max_length=50)
    email: Optional[str] = None
    acceptedTerms: bool = Field(..., alias="accepted_terms")

    @field_validator("phone")
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        res = validate_and_normalize_phone(v, required=True, field_name="phone")
        if not res:
            raise ValueError("Phone number is required.")
        return res


class AssignMembershipRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    userId: str = Field(..., alias="user_id")
    planId: str = Field(..., alias="plan_id")
    branchId: Optional[str] = Field(default="narsobawadi", alias="branch_id")
    recordPayment: bool = Field(default=False, alias="record_payment")
    paymentMethod: Optional[str] = Field(default="cash", alias="payment_method")
    paymentAmount: Optional[float] = Field(default=None, alias="payment_amount")
    referenceNumber: Optional[str] = Field(default=None, alias="reference_number")
    notes: Optional[str] = None


class EnrollmentDetail(BaseModel):
    id: str
    userId: Optional[str] = None
    planId: str
    planName: str
    durationDays: Optional[int] = None
    branchId: Optional[str] = "narsobawadi"
    branchName: Optional[str] = "Narsobawadi Main Campus"
    price: int
    currency: str = "₹"
    name: str
    phone: str
    email: Optional[str] = ""
    status: str
    enrolledAt: str
    verifiedAt: Optional[str] = None
    verifiedBy: Optional[str] = None
    rejectionReason: Optional[str] = None
    notes: Optional[str] = None
    invoiceId: Optional[str] = None
    invoiceNumber: Optional[str] = None
    invoiceStatus: Optional[str] = None
    totalAmount: Optional[float] = None
    amountPaid: Optional[float] = None
    balanceDue: Optional[float] = None


class EnrollmentResponse(BaseModel):
    success: bool
    message: str
    enrollment: EnrollmentDetail


class EnrollmentApprovalRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    recordPayment: bool = Field(default=False, alias="record_payment")
    paymentMethod: Optional[str] = Field(default="cash", alias="payment_method")
    paymentAmount: Optional[float] = Field(default=None, alias="payment_amount")
    referenceNumber: Optional[str] = Field(default=None, alias="reference_number")
    notes: Optional[str] = None


class EnrollmentRejectionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reason: str = Field(..., min_length=2, max_length=500)
    notes: Optional[str] = None


class EnrollmentListResponse(BaseModel):
    success: bool = True
    enrollments: List[EnrollmentDetail]
    totalCount: int
    pendingCount: int
    paymentPendingCount: int


class MyEnrollmentResponse(BaseModel):
    enrollment: Optional[EnrollmentDetail] = None


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
