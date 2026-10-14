from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from backend.app.schemas.membership import EnrollmentDetail


class AdminContactItem(BaseModel):
    id: str
    submittedAt: str
    name: str
    phone: str
    email: Optional[str] = ""
    message: Optional[str] = ""
    status: str


class StaffDutyItem(BaseModel):
    name: str
    shift: str
    role: str


class AdminOverviewResponse(BaseModel):
    totalMembers: int
    activeTodayInGym: int
    recentEnrollments: List[EnrollmentDetail]
    recentContacts: List[AdminContactItem]
    staffDuty: List[StaffDutyItem]
