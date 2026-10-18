import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import desc
from fastapi import HTTPException, status

from backend.app.models.user import User
from backend.app.models.member_profile import MemberProfile, MemberBodyMeasurement
from backend.app.models.audit import AuditLog
from backend.app.schemas.member_profile import (
    MemberProfileUpdateRequest,
    MemberProfileResponse,
    BodyMeasurementCreate,
    BodyMeasurementResponse,
)


def get_or_create_member_profile(db: Session, user: User) -> MemberProfile:
    """Retrieve existing MemberProfile or initialize a default linked profile."""
    profile = db.query(MemberProfile).filter(MemberProfile.user_id == user.id).first()
    if not profile:
        profile = MemberProfile(
            id=str(uuid.uuid4()),
            user_id=user.id,
            primary_goal="general_fitness",
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def serialize_measurement(m: MemberBodyMeasurement) -> BodyMeasurementResponse:
    """Serialize MemberBodyMeasurement ORM model to Pydantic response."""
    return BodyMeasurementResponse(
        id=m.id,
        userId=m.user_id,
        recordedDate=m.recorded_date.isoformat(),
        weightKg=float(m.weight_kg) if m.weight_kg is not None else None,
        heightCm=float(m.height_cm) if m.height_cm is not None else None,
        bodyFatPct=float(m.body_fat_pct) if m.body_fat_pct is not None else None,
        chestCm=float(m.chest_cm) if m.chest_cm is not None else None,
        waistCm=float(m.waist_cm) if m.waist_cm is not None else None,
        hipsCm=float(m.hips_cm) if m.hips_cm is not None else None,
        armsCm=float(m.arms_cm) if m.arms_cm is not None else None,
        thighsCm=float(m.thighs_cm) if m.thighs_cm is not None else None,
        calvesCm=float(m.calves_cm) if m.calves_cm is not None else None,
        recordedById=m.recorded_by_id,
        recordedByRole=m.recorded_by_role,
        notes=m.notes,
        createdAt=m.created_at.isoformat() if m.created_at else "",
    )


def serialize_member_profile(
    user: User,
    profile: MemberProfile,
    viewer: User,
) -> MemberProfileResponse:
    """
    Construct role-scoped MemberProfileResponse applying least-privilege health privacy controls.
    """
    # Determine access scope
    is_self = user.id == viewer.id
    is_org_admin = viewer.role in ("org_admin", "admin")
    is_branch_mgr = viewer.role in ("branch_manager", "manager") and viewer.branch_id == user.branch_id
    is_assigned_coach = viewer.role == "trainer" and user.assigned_trainer_id == viewer.id
    is_front_desk = viewer.role in ("front_desk", "staff")

    if not (is_self or is_org_admin or is_branch_mgr or is_assigned_coach or is_front_desk):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not have permission to view this member profile.",
        )

    # Latest measurement
    latest_m = (
        profile.measurements[0]
        if profile.measurements and len(profile.measurements) > 0
        else None
    )
    latest_resp = serialize_measurement(latest_m) if latest_m else None

    # Base response with identity and membership fields
    resp = MemberProfileResponse(
        id=user.id,
        name=user.name,
        email=user.email if (is_self or is_org_admin or is_branch_mgr or is_front_desk) else "Confidential",
        phone=user.phone if (is_self or is_org_admin or is_branch_mgr or is_front_desk) else None,
        role=user.role,
        branchId=user.branch_id,
        branchName=user.branch.name if user.branch else "Narsobawadi Main Campus",
        assignedTrainerId=user.assigned_trainer_id,
        assignedTrainerName=user.assigned_trainer.name if user.assigned_trainer else None,
        membershipId=user.membership_id,
        membershipStatus=user.membership_status,
        membershipPlan=user.membership_plan.name if user.membership_plan else "No Plan Assigned",
        validUntil=user.valid_until.strftime("%B %d, %Y") if user.valid_until else "Pending",
        memberSince=user.member_since.strftime("%B %Y") if user.member_since else "Recent",
        streakDays=user.streak_days,
        dateOfBirth=profile.date_of_birth.isoformat() if profile.date_of_birth else None,
        calculatedAge=profile.calculate_age(),
        gender=profile.gender,
        profilePhotoUrl=profile.profile_photo_url,
        address=profile.address if (is_self or is_org_admin or is_branch_mgr) else None,
        emergencyContactName=profile.emergency_contact_name if (is_self or is_org_admin or is_branch_mgr or is_front_desk) else None,
        emergencyContactPhone=profile.emergency_contact_phone if (is_self or is_org_admin or is_branch_mgr or is_front_desk) else None,
        heightCm=float(profile.height_cm) if profile.height_cm is not None else None,
        targetWeightKg=float(profile.target_weight_kg) if profile.target_weight_kg is not None else None,
        primaryGoal=profile.primary_goal or "general_fitness",
        fitnessGoals=profile.fitness_goals,
        lastHealthUpdate=profile.last_health_update.isoformat() if profile.last_health_update else None,
        latestMeasurement=latest_resp,
    )

    # Sensitive Health Data Scoping
    if is_self or is_org_admin or is_branch_mgr:
        resp.accessScope = "full"
        resp.pastInjuries = profile.past_injuries
        resp.currentInjuries = profile.current_injuries
        resp.healthConditions = profile.health_conditions
        resp.exerciseRestrictions = profile.exercise_restrictions
        resp.allergies = profile.allergies
        resp.surgeryHistory = profile.surgery_history
        resp.currentMedications = profile.current_medications if profile.has_medication_consent or is_self else "Restricted without explicit member consent"
        resp.hasMedicationConsent = profile.has_medication_consent
        resp.healthNotes = profile.health_notes
    elif is_assigned_coach:
        resp.accessScope = "coach_training"
        # Coach only receives training-relevant physical limitations, injuries, movement restrictions, and allergies
        resp.pastInjuries = profile.past_injuries
        resp.currentInjuries = profile.current_injuries
        resp.healthConditions = None  # Redacted: confidential medical conditions
        resp.exerciseRestrictions = profile.exercise_restrictions
        resp.allergies = profile.allergies
        resp.surgeryHistory = None  # Redacted: confidential surgical history
        resp.currentMedications = None  # Redacted
        resp.hasMedicationConsent = profile.has_medication_consent
        resp.healthNotes = None  # Redacted: confidential health notes
    elif is_front_desk:
        resp.accessScope = "front_desk_reception"
        # Front desk staff receive NO sensitive health/injury/medical disclosures
        resp.pastInjuries = None
        resp.currentInjuries = None
        resp.healthConditions = None
        resp.exerciseRestrictions = None
        resp.allergies = None
        resp.surgeryHistory = None
        resp.currentMedications = None
        resp.healthNotes = None

    return resp


def update_member_profile(
    db: Session,
    user: User,
    profile: MemberProfile,
    req: MemberProfileUpdateRequest,
    actor: User,
) -> MemberProfileResponse:
    """Update personal, health, and target details with audit trail for sensitive changes."""
    is_self = user.id == actor.id
    is_admin = actor.role in ("org_admin", "admin", "branch_manager", "manager")
    is_coach = actor.role == "trainer" and user.assigned_trainer_id == actor.id

    if not (is_self or is_admin or is_coach):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this member profile.",
        )

    # 1. Update personal details
    if req.personal and (is_self or is_admin):
        p = req.personal
        if p.name and p.name.strip():
            user.name = p.name.strip()
        if p.phone is not None:
            user.phone = p.phone.strip() if p.phone else None
        if p.date_of_birth is not None:
            profile.date_of_birth = p.date_of_birth
        if p.gender is not None:
            profile.gender = p.gender.strip() if p.gender else None
        if p.profile_photo_url is not None:
            profile.profile_photo_url = p.profile_photo_url.strip() if p.profile_photo_url else None
        if p.address is not None:
            profile.address = p.address.strip() if p.address else None
        if p.emergency_contact_name is not None:
            profile.emergency_contact_name = p.emergency_contact_name.strip() if p.emergency_contact_name else None
        if p.emergency_contact_phone is not None:
            profile.emergency_contact_phone = p.emergency_contact_phone.strip() if p.emergency_contact_phone else None

    # 2. Update targets
    if req.targets:
        t = req.targets
        if t.height_cm is not None:
            profile.height_cm = t.height_cm
        if t.target_weight_kg is not None:
            profile.target_weight_kg = t.target_weight_kg
        if t.primary_goal is not None:
            profile.primary_goal = t.primary_goal.strip() if t.primary_goal else "general_fitness"

    # 3. Update health disclosures (requires member consent or self-update)
    if req.health:
        h = req.health
        profile.past_injuries = h.past_injuries
        profile.current_injuries = h.current_injuries
        profile.health_conditions = h.health_conditions
        profile.exercise_restrictions = h.exercise_restrictions
        profile.allergies = h.allergies
        profile.surgery_history = h.surgery_history
        if h.has_medication_consent is not None:
            profile.has_medication_consent = h.has_medication_consent
        if profile.has_medication_consent or is_self:
            profile.current_medications = h.current_medications
        profile.fitness_goals = h.fitness_goals
        profile.health_notes = h.health_notes
        profile.last_health_update = datetime.now(timezone.utc)

        # Audit sensitive health update
        audit = AuditLog(
            actor_id=actor.id,
            action="profile.health_update",
            resource_type="member_profile",
            resource_id=profile.id,
            details={
                "target_user_id": user.id,
                "has_injuries": bool(profile.current_injuries or profile.past_injuries),
                "has_restrictions": bool(profile.exercise_restrictions),
                "has_medication_consent": profile.has_medication_consent,
            },
        )
        db.add(audit)

    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    db.refresh(profile)

    return serialize_member_profile(user, profile, actor)


def record_member_measurement(
    db: Session,
    user: User,
    profile: MemberProfile,
    data: BodyMeasurementCreate,
    actor: User,
) -> BodyMeasurementResponse:
    """Record a dated time-series body measurement and update profile current height/weight."""
    role = "member"
    if actor.role in ("org_admin", "admin", "branch_manager", "manager"):
        role = "staff"
    elif actor.role == "trainer":
        role = "coach"

    measurement = MemberBodyMeasurement(
        id=str(uuid.uuid4()),
        user_id=user.id,
        recorded_date=data.recorded_date,
        weight_kg=data.weight_kg,
        height_cm=data.height_cm,
        body_fat_pct=data.body_fat_pct,
        chest_cm=data.chest_cm,
        waist_cm=data.waist_cm,
        hips_cm=data.hips_cm,
        arms_cm=data.arms_cm,
        thighs_cm=data.thighs_cm,
        calves_cm=data.calves_cm,
        recorded_by_id=actor.id,
        recorded_by_role=role,
        notes=data.notes,
    )
    db.add(measurement)

    # Sync latest height and target weight if updated
    if data.height_cm is not None:
        profile.height_cm = data.height_cm
    profile.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(measurement)

    return serialize_measurement(measurement)


def list_member_measurements(
    db: Session,
    user_id: str,
    viewer: User,
    limit: int = 50,
    offset: int = 0,
) -> List[BodyMeasurementResponse]:
    """Retrieve historical time-series measurements with role-based scoping."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member account not found.")

    is_self = user.id == viewer.id
    is_admin = viewer.role in ("org_admin", "admin")
    is_branch_mgr = viewer.role in ("branch_manager", "manager") and viewer.branch_id == user.branch_id
    is_assigned_coach = viewer.role == "trainer" and user.assigned_trainer_id == viewer.id

    if not (is_self or is_admin or is_branch_mgr or is_assigned_coach):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    items = (
        db.query(MemberBodyMeasurement)
        .filter(MemberBodyMeasurement.user_id == user_id)
        .order_by(desc(MemberBodyMeasurement.recorded_date), desc(MemberBodyMeasurement.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [serialize_measurement(m) for m in items]
