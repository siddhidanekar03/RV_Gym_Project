from typing import List, Optional
from datetime import date
from pydantic import BaseModel, Field, field_validator
import re


class LeaderboardEntry(BaseModel):
    rank: int
    name: str
    alias: Optional[str] = None
    category: str = "Points"
    score: str
    points: Optional[int] = 0
    distinctDays: Optional[int] = 0
    streak: int = 0
    visitsThisMonth: int = 0
    tier: Optional[str] = "Bronze"
    branchName: Optional[str] = None


class LeaderboardResponse(BaseModel):
    leaderboard: List[LeaderboardEntry]
    updatedAt: str
    total: int = 0
    page: int = 1
    limit: int = 50
    month: Optional[int] = None
    year: Optional[int] = None
    branchId: Optional[str] = None
    scope: str = "organization"


class MemberPreferencesResponse(BaseModel):
    userId: str
    alias: str
    isLeaderboardVisible: bool
    branchId: str


class MemberPreferencesUpdate(BaseModel):
    alias: Optional[str] = Field(None, min_length=3, max_length=30)
    isLeaderboardVisible: Optional[bool] = None

    @field_validator("alias")
    @classmethod
    def validate_alias(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if len(cleaned) < 3 or len(cleaned) > 30:
            raise ValueError("Alias must be between 3 and 30 characters.")
        if not re.match(r"^[A-Za-z0-9_-]+$", cleaned):
            raise ValueError("Alias may only contain alphanumeric characters, underscores, and hyphens.")
        return cleaned


class MemberSelfStandingResponse(BaseModel):
    rank: Optional[int] = None
    totalMembers: int = 0
    points: int = 0
    distinctDays: int = 0
    streakDays: int = 0
    alias: str
    isLeaderboardVisible: bool
    branchId: str
    branchName: str
    month: int
    year: int
    tier: str = "Bronze"


class PointLedgerItem(BaseModel):
    id: str
    sourceType: str
    sourceId: str
    points: int
    eventDate: date
    year: int
    month: int
    notes: Optional[str] = None
    createdAt: str


class PointLedgerHistoryResponse(BaseModel):
    entries: List[PointLedgerItem]
    totalPoints: int
    month: Optional[int] = None
    year: Optional[int] = None


class AdminPointAdjustmentRequest(BaseModel):
    userId: str
    points: int
    reason: str = Field(..., min_length=5, max_length=500)
    branchId: Optional[str] = None


class AdminPointAdjustmentResponse(BaseModel):
    success: bool
    ledgerId: str
    userId: str
    pointsAdjusted: int
    newMonthlyTotal: int
    reason: str


class ScoringRuleItem(BaseModel):
    activity: str
    points: int
    description: str
    frequencyLimit: str


class ScoringRulesResponse(BaseModel):
    rules: List[ScoringRuleItem]
    antiAbusePolicy: str
