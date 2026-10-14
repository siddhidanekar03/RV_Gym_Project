from typing import List, Optional
from pydantic import BaseModel, Field


class TrainerProfileResponse(BaseModel):
    id: str
    userId: str
    name: str
    specialization: str
    bio: Optional[str] = None
    certifications: List[str] = []
    experienceYears: int
    rating: float
    maxClients: int
    isAcceptingClients: bool


class AssignedMemberItem(BaseModel):
    id: str
    name: str
    email: str
    phone: Optional[str] = None
    membershipPlan: str
    membershipStatus: str
    validUntil: Optional[str] = None
    streakDays: int


class AssignedMemberListResponse(BaseModel):
    members: List[AssignedMemberItem]


class TrainerAssignmentRequest(BaseModel):
    trainerId: str
    memberId: str
    notes: Optional[str] = None


class TrainerAssignmentResponse(BaseModel):
    success: bool
    message: str
    assignmentId: str
