from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator

from backend.app.core.validation import validate_and_normalize_phone


class MemberPersonalUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    phone: Optional[str] = Field(None, max_length=50)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=30)
    profile_photo_url: Optional[str] = Field(None, max_length=500)
    address: Optional[str] = None
    emergency_contact_name: Optional[str] = Field(None, max_length=150)
    emergency_contact_phone: Optional[str] = Field(None, max_length=50)

    @field_validator("phone", "emergency_contact_phone")
    @classmethod
    def validate_phones(cls, v: Optional[str], info) -> Optional[str]:
        return validate_and_normalize_phone(v, required=False, field_name=info.field_name)

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, v: Optional[date]) -> Optional[date]:
        if v:
            today = date.today()
            if v > today:
                raise ValueError("Date of birth cannot be in the future.")
            age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))
            if age < 12:
                raise ValueError("Member must be at least 12 years of age to register.")
            if age > 115:
                raise ValueError("Please provide a valid date of birth.")
        return v


class MemberHealthUpdate(BaseModel):
    past_injuries: Optional[str] = None
    current_injuries: Optional[str] = None
    health_conditions: Optional[str] = None
    exercise_restrictions: Optional[str] = None
    allergies: Optional[str] = None
    surgery_history: Optional[str] = None
    current_medications: Optional[str] = None
    has_medication_consent: Optional[bool] = None
    fitness_goals: Optional[str] = None
    health_notes: Optional[str] = None


class MemberTargetsUpdate(BaseModel):
    height_cm: Optional[Decimal] = Field(None, ge=Decimal("80.0"), le=Decimal("260.0"))
    target_weight_kg: Optional[Decimal] = Field(None, ge=Decimal("20.0"), le=Decimal("350.0"))
    primary_goal: Optional[str] = Field(None, max_length=50)


class MemberProfileUpdateRequest(BaseModel):
    personal: Optional[MemberPersonalUpdate] = None
    health: Optional[MemberHealthUpdate] = None
    targets: Optional[MemberTargetsUpdate] = None


class BodyMeasurementCreate(BaseModel):
    recorded_date: date
    weight_kg: Optional[Decimal] = Field(None, ge=Decimal("20.0"), le=Decimal("350.0"))
    height_cm: Optional[Decimal] = Field(None, ge=Decimal("80.0"), le=Decimal("260.0"))
    body_fat_pct: Optional[Decimal] = Field(None, ge=Decimal("3.0"), le=Decimal("65.0"))
    chest_cm: Optional[Decimal] = Field(None, ge=Decimal("10.0"), le=Decimal("200.0"))
    waist_cm: Optional[Decimal] = Field(None, ge=Decimal("10.0"), le=Decimal("200.0"))
    hips_cm: Optional[Decimal] = Field(None, ge=Decimal("10.0"), le=Decimal("200.0"))
    arms_cm: Optional[Decimal] = Field(None, ge=Decimal("10.0"), le=Decimal("100.0"))
    thighs_cm: Optional[Decimal] = Field(None, ge=Decimal("10.0"), le=Decimal("150.0"))
    calves_cm: Optional[Decimal] = Field(None, ge=Decimal("10.0"), le=Decimal("100.0"))
    notes: Optional[str] = None

    @field_validator("recorded_date")
    @classmethod
    def validate_date(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("Measurement date cannot be in the future.")
        return v


class BodyMeasurementResponse(BaseModel):
    id: str
    userId: str
    recordedDate: str
    weightKg: Optional[float] = None
    heightCm: Optional[float] = None
    bodyFatPct: Optional[float] = None
    chestCm: Optional[float] = None
    waistCm: Optional[float] = None
    hipsCm: Optional[float] = None
    armsCm: Optional[float] = None
    thighsCm: Optional[float] = None
    calvesCm: Optional[float] = None
    recordedById: Optional[str] = None
    recordedByRole: str = "member"
    notes: Optional[str] = None
    createdAt: str


class MemberProfileResponse(BaseModel):
    # Member identity
    id: str
    name: str
    email: str
    phone: Optional[str] = None
    role: str
    branchId: Optional[str] = None
    branchName: Optional[str] = None
    assignedTrainerId: Optional[str] = None
    assignedTrainerName: Optional[str] = None

    # Membership
    membershipId: Optional[str] = None
    membershipStatus: str
    membershipPlan: Optional[str] = None
    validUntil: Optional[str] = None
    memberSince: Optional[str] = None
    streakDays: int = 0

    # Personal details
    dateOfBirth: Optional[str] = None
    calculatedAge: Optional[int] = None
    gender: Optional[str] = None
    profilePhotoUrl: Optional[str] = None
    address: Optional[str] = None
    emergencyContactName: Optional[str] = None
    emergencyContactPhone: Optional[str] = None

    # Physical Targets
    heightCm: Optional[float] = None
    targetWeightKg: Optional[float] = None
    primaryGoal: str = "general_fitness"

    # Health & Injury History (scoped or redacted based on viewer role)
    pastInjuries: Optional[str] = None
    currentInjuries: Optional[str] = None
    healthConditions: Optional[str] = None
    exerciseRestrictions: Optional[str] = None
    allergies: Optional[str] = None
    surgeryHistory: Optional[str] = None
    currentMedications: Optional[str] = None
    hasMedicationConsent: bool = False
    fitnessGoals: Optional[str] = None
    healthNotes: Optional[str] = None
    lastHealthUpdate: Optional[str] = None

    # Access scoping metadata
    accessScope: str = "full"  # 'full' | 'coach_training' | 'front_desk_reception'
    privacyNotice: str = (
        "Health information is strictly confidential. Only training-relevant movement restrictions "
        "and physical limits are shared with your assigned strength coach to ensure safe exercise programming."
    )
    latestMeasurement: Optional[BodyMeasurementResponse] = None
