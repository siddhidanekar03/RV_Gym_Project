from typing import List, Optional
from datetime import date
from pydantic import BaseModel, Field


class BranchItem(BaseModel):
    id: str
    organizationId: str
    name: str
    code: str
    address: Optional[str] = None
    city: str
    state: str
    phone: Optional[str] = None
    email: Optional[str] = None
    isActive: bool


class BranchListResponse(BaseModel):
    branches: List[BranchItem]


class MemberBranchAccessRequest(BaseModel):
    userId: str
    branchId: str
    expiresAt: Optional[date] = None
    notes: Optional[str] = None


class MemberBranchAccessResponse(BaseModel):
    success: bool
    message: str
    grantId: str
