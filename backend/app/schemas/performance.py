from typing import Optional, List, Dict, Any
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator


class WorkoutExerciseLogItem(BaseModel):
    exerciseName: str = Field(..., min_length=1, max_length=150)
    sets: Optional[int] = Field(None, ge=1, le=50)
    reps: Optional[int] = Field(None, ge=1, le=500)
    weightKg: Optional[float] = Field(None, ge=0.0, le=1000.0)
    durationSeconds: Optional[int] = Field(None, ge=0, le=86400)
    distanceMeters: Optional[float] = Field(None, ge=0.0, le=100000.0)
    notes: Optional[str] = None


class WorkoutCompletionRequest(BaseModel):
    sessionName: str = Field(..., min_length=2, max_length=150)
    sessionDate: Optional[date] = None
    workoutPlanId: Optional[str] = None
    durationMinutes: Optional[int] = Field(None, ge=1, le=600)
    rpe: Optional[int] = Field(None, ge=1, le=10)  # Rate of Perceived Exertion (1 to 10)
    notes: Optional[str] = None
    exercises: List[WorkoutExerciseLogItem] = Field(default_factory=list)

    @field_validator("sessionDate")
    @classmethod
    def validate_date(cls, v: Optional[date]) -> date:
        today = date.today()
        if v and v > today:
            raise ValueError("Workout session date cannot be in the future.")
        return v or today


class WeightHistoryItem(BaseModel):
    date: str
    weightKg: float
    recordedBy: str
    recordedByRole: str = "member"
    notes: Optional[str] = None


class PersonalRecordItem(BaseModel):
    exerciseName: str
    value: float
    unit: str = "kg"
    reps: int = 1
    recordedAt: str
    isCoachVerified: bool = False


class PerformanceSummaryResponse(BaseModel):
    userId: str
    userName: str
    primaryGoal: str = "general_fitness"

    # Weight tracking
    currentWeightKg: Optional[float] = None
    baselineWeightKg: Optional[float] = None
    netWeightChangeKg: Optional[float] = None  # latest - baseline
    goalWeightKg: Optional[float] = None
    goalProgressPct: Optional[float] = None
    goalStatusMessage: str

    # Activity & Workouts
    workoutsCompletedThisWeek: int = 0
    workoutsCompletedThisMonth: int = 0
    totalCompletedWorkouts: int = 0
    attendanceThisMonth: int = 0
    streakDays: int = 0

    # Records and recent measurements
    recentPRs: List[PersonalRecordItem] = Field(default_factory=list)
    latestMeasurements: Optional[Dict[str, Any]] = None
    lastMeasurementDate: Optional[str] = None


class CoachMemberProgressItem(BaseModel):
    memberId: str
    memberName: str
    memberEmail: str
    memberPhone: Optional[str] = None
    membershipStatus: str
    membershipPlan: Optional[str] = None
    streakDays: int = 0
    primaryGoal: str = "general_fitness"
    currentWeightKg: Optional[float] = None
    baselineWeightKg: Optional[float] = None
    netWeightChangeKg: Optional[float] = None
    goalWeightKg: Optional[float] = None
    workoutsCompletedThisMonth: int = 0
    lastWorkoutDate: Optional[str] = None
    lastMeasurementDate: Optional[str] = None
    hasHealthRestrictions: bool = False
    movementRestrictions: Optional[str] = None
    activeAssignedPlanName: Optional[str] = None
