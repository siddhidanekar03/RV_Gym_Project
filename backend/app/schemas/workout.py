from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkoutPlanExerciseBase(BaseModel):
    day_number: int = Field(default=1, ge=1, le=7)
    day_name: Optional[str] = Field(None, max_length=50)
    exercise_order: int = Field(default=1, ge=1, le=100)
    name: str = Field(..., min_length=2, max_length=120)
    instructions: Optional[str] = Field(None, max_length=2000)
    sets: Optional[int] = Field(None, ge=1, le=50)
    reps: Optional[int] = Field(None, ge=1, le=500)
    target_duration_seconds: Optional[int] = Field(None, ge=1, le=86400)
    target_distance_meters: Optional[float] = Field(None, ge=0.0, le=100000.0)
    target_weight_kg: Optional[float] = Field(None, ge=0.0, le=1000.0)
    rest_seconds: Optional[int] = Field(None, ge=0, le=1800)
    notes: Optional[str] = Field(None, max_length=500)


class WorkoutPlanExerciseCreate(WorkoutPlanExerciseBase):
    pass


class WorkoutPlanExerciseResponse(WorkoutPlanExerciseBase):
    id: str
    workout_plan_id: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WorkoutPlanCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    goal: str = Field(default="general_fitness", max_length=50)
    difficulty: str = Field(default="intermediate", max_length=30)
    duration_weeks: Optional[int] = Field(None, ge=1, le=52)
    branch_id: Optional[str] = None
    organization_id: Optional[str] = None
    trainer_id: Optional[str] = None
    status: str = Field(default="draft", max_length=20)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    exercises: Optional[List[WorkoutPlanExerciseCreate]] = []

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("Plan name must be at least 2 characters.")
        return cleaned

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"draft", "active", "completed", "archived"}
        if v.lower() not in allowed:
            raise ValueError(f"Status must be one of: {', '.join(sorted(allowed))}")
        return v.lower()

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        allowed = {"beginner", "intermediate", "advanced"}
        if v.lower() not in allowed:
            raise ValueError(f"Difficulty must be one of: {', '.join(sorted(allowed))}")
        return v.lower()


class WorkoutPlanUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    goal: Optional[str] = Field(None, max_length=50)
    difficulty: Optional[str] = Field(None, max_length=30)
    duration_weeks: Optional[int] = Field(None, ge=1, le=52)
    status: Optional[str] = Field(None, max_length=20)
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        allowed = {"draft", "active", "completed", "archived"}
        if v.lower() not in allowed:
            raise ValueError(f"Status must be one of: {', '.join(sorted(allowed))}")
        return v.lower()


class WorkoutPlanResponse(BaseModel):
    id: str
    organization_id: Optional[str] = None
    branch_id: Optional[str] = None
    trainer_id: Optional[str] = None
    trainer_name: Optional[str] = None
    name: str
    description: Optional[str] = None
    goal: str
    difficulty: str
    duration_weeks: Optional[int] = None
    status: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    exercises: List[WorkoutPlanExerciseResponse] = []
    assigned_member_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WorkoutPlanAssignRequest(BaseModel):
    member_id: str
    notes: Optional[str] = Field(None, max_length=500)


class WorkoutPlanAssignmentResponse(BaseModel):
    id: str
    workout_plan_id: str
    member_id: str
    member_name: Optional[str] = None
    assigned_by_id: Optional[str] = None
    assigned_at: datetime
    is_active: bool
    notes: Optional[str] = None
    plan: Optional[WorkoutPlanResponse] = None

    model_config = ConfigDict(from_attributes=True)


class WorkoutSessionExerciseRecord(BaseModel):
    plan_exercise_id: Optional[str] = None
    exercise_name: str = Field(..., min_length=1, max_length=120)
    exercise_order: int = Field(default=1, ge=1, le=100)
    sets_completed: Optional[int] = Field(None, ge=0, le=50)
    reps_completed: Optional[int] = Field(None, ge=0, le=500)
    weight_kg: Optional[float] = Field(None, ge=0.0, le=1000.0)
    duration_seconds: Optional[int] = Field(None, ge=0, le=86400)
    distance_meters: Optional[float] = Field(None, ge=0.0, le=100000.0)
    is_completed: bool = True
    notes: Optional[str] = Field(None, max_length=500)


class WorkoutSessionExerciseResponse(BaseModel):
    id: str
    session_id: str
    plan_exercise_id: Optional[str] = None
    exercise_name: str
    exercise_order: int
    sets_completed: Optional[int] = None
    reps_completed: Optional[int] = None
    weight_kg: Optional[float] = None
    duration_seconds: Optional[int] = None
    distance_meters: Optional[float] = None
    is_completed: bool
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class WorkoutSessionStartRequest(BaseModel):
    workout_plan_id: Optional[str] = None
    session_name: Optional[str] = Field(None, max_length=120)
    notes: Optional[str] = Field(None, max_length=1000)


class WorkoutSessionUpdateRequest(BaseModel):
    status: Optional[str] = Field(None, max_length=20)
    session_name: Optional[str] = Field(None, max_length=120)
    notes: Optional[str] = Field(None, max_length=1000)
    exercises: Optional[List[WorkoutSessionExerciseRecord]] = None
    completed_at: Optional[datetime] = None

    @field_validator("status")
    @classmethod
    def validate_session_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        allowed = {"in_progress", "completed", "abandoned"}
        if v.lower() not in allowed:
            raise ValueError(f"Session status must be one of: {', '.join(sorted(allowed))}")
        return v.lower()


class WorkoutSessionResponse(BaseModel):
    id: str
    workout_plan_id: Optional[str] = None
    plan_name: Optional[str] = None
    member_id: str
    member_name: Optional[str] = None
    branch_id: Optional[str] = None
    session_date: date
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str
    session_name: Optional[str] = None
    notes: Optional[str] = None
    is_coach_verified: bool = False
    verified_by_id: Optional[str] = None
    points_awarded: int = 0
    exercises: List[WorkoutSessionExerciseResponse] = []

    model_config = ConfigDict(from_attributes=True)


class CoachVerifySessionRequest(BaseModel):
    is_coach_verified: bool = True
    notes: Optional[str] = Field(None, max_length=500)


class FitnessProgressRecordCreate(BaseModel):
    record_type: str = Field(..., max_length=50)
    value: Optional[float] = Field(None, ge=0.0, le=1000.0)
    unit: Optional[str] = Field(None, max_length=20)
    text_value: Optional[str] = Field(None, max_length=1000)
    recorded_date: Optional[date] = None
    is_private: bool = True
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("record_type")
    @classmethod
    def validate_record_type(cls, v: str) -> str:
        allowed = {"body_weight", "personal_record", "body_fat", "chest", "waist", "hips", "biceps", "notes", "other"}
        cleaned = v.strip().lower()
        if cleaned not in allowed:
            raise ValueError(f"Record type must be one of: {', '.join(sorted(allowed))}")
        return cleaned


class FitnessProgressRecordResponse(BaseModel):
    id: str
    user_id: str
    user_name: Optional[str] = None
    record_type: str
    value: Optional[float] = None
    unit: Optional[str] = None
    text_value: Optional[str] = None
    recorded_date: date
    is_private: bool
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
