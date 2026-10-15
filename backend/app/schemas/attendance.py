from typing import List, Optional, Dict
from datetime import date
from pydantic import BaseModel, Field


class CheckInResponse(BaseModel):
    success: bool
    message: str
    streakDays: int
    attendanceThisMonth: int
    checkedInAt: str
    attendanceId: Optional[str] = None
    source: Optional[str] = "portal"


class QRTokenResponse(BaseModel):
    qrToken: str
    expiresAt: str
    secondsValid: int


class QRCheckInRequest(BaseModel):
    qrToken: str
    branchId: str = "narsobawadi"


class ManualCheckInRequest(BaseModel):
    branchId: str = "narsobawadi"
    reasonCode: str = Field(..., description="no_account | no_internet | qr_invalid | other")
    memberId: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    notes: Optional[str] = None


class ManagerOverrideRequest(BaseModel):
    attemptId: Optional[str] = None
    attempt_id: Optional[str] = None
    reason: Optional[str] = None
    override_reason: Optional[str] = None

    def get_attempt_id(self) -> str:
        aid = self.attemptId or self.attempt_id
        if not aid:
            raise ValueError("attemptId is required")
        return aid

    def get_reason(self) -> str:
        r = self.reason or self.override_reason
        if not r or len(r.strip()) < 5:
            raise ValueError("A detailed mandatory reason (at least 5 characters) is required for manager overrides.")
        return r.strip()


class PaperBackfillRequest(BaseModel):
    branchId: str = "narsobawadi"
    visitDate: date
    entryOperator: str = Field(..., min_length=2)
    reason: str = Field(..., min_length=3)
    memberId: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None


class MemberLookupItem(BaseModel):
    id: str
    name: str
    membershipId: str
    maskedPhone: str
    status: str
    validUntil: str
    planName: str
    isEligible: bool
    ineligibilityReason: Optional[str] = None
    streakDays: int = 0


class MemberLookupResponse(BaseModel):
    members: List[MemberLookupItem]


class OperatorAttendanceMetric(BaseModel):
    operatorId: str
    operatorName: str
    manualCount: int
    totalCount: int
    manualRatioPercent: float


class DailyAttendanceBreakdown(BaseModel):
    date: str
    totalCount: int
    qrCount: int
    manualCount: int
    overrideCount: int
    backfillCount: int


class MonthlyAttendanceReportResponse(BaseModel):
    branchId: str
    branchName: str
    year: int
    month: int
    monthName: str
    timezone: str
    distinctAttendanceDays: int
    totalCheckins: int
    qrCheckins: int
    manualCheckins: int
    backfilledCheckins: int
    managerOverrides: int
    operatorMetrics: List[OperatorAttendanceMetric] = []
    rejectedAttemptsCount: int = 0
    rejectedAttemptsByReason: Dict[str, int] = {}
    dailyBreakdown: List[DailyAttendanceBreakdown] = []


class MemberMonthlyReportResponse(BaseModel):
    userId: str
    userName: str
    membershipId: Optional[str] = None
    year: int
    month: int
    monthName: str
    distinctAttendanceDays: int
    checkinDates: List[str] = []
    streakDays: int = 0
