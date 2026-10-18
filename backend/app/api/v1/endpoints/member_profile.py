import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.auth import get_current_user, require_roles
from backend.app.models.user import User
from backend.app.schemas.member_profile import (
    MemberProfileUpdateRequest,
    MemberProfileResponse,
    BodyMeasurementCreate,
    BodyMeasurementResponse,
)
from backend.app.services.member_profile_service import (
    get_or_create_member_profile,
    serialize_member_profile,
    update_member_profile,
    record_member_measurement,
    list_member_measurements,
)

router = APIRouter(prefix="/profile")


@router.get("/me", response_model=MemberProfileResponse)
def get_my_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve the authenticated member profile with full personal and health details."""
    profile = get_or_create_member_profile(db, current_user)
    return serialize_member_profile(current_user, profile, current_user)


@router.put("/me", response_model=MemberProfileResponse)
def update_my_profile(
    payload: MemberProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update authenticated member personal details, health disclosures, or targets."""
    profile = get_or_create_member_profile(db, current_user)
    return update_member_profile(db, current_user, profile, payload, current_user)


@router.get("/member/{member_id}", response_model=MemberProfileResponse)
def get_member_profile_by_id(
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve member profile by ID.
    Enforces role-based least-privilege scoping:
    - Org Admin / Admin: Operational full access.
    - Branch Manager: Branch members only.
    - Coach: Assigned members only (health data scoped to movement restrictions).
    - Front Desk: Reception and emergency info only (health notes redacted).
    - Other Members: Forbidden (HTTP 403).
    """
    target_user = db.query(User).filter(User.id == member_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member account not found.",
        )

    profile = get_or_create_member_profile(db, target_user)
    return serialize_member_profile(target_user, profile, current_user)


@router.put("/member/{member_id}", response_model=MemberProfileResponse)
def update_member_profile_by_id(
    member_id: str,
    payload: MemberProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update member profile by authorized staff or assigned coach.
    """
    target_user = db.query(User).filter(User.id == member_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member account not found.",
        )

    # Permission check
    is_self = target_user.id == current_user.id
    is_admin = current_user.role in ("org_admin", "admin")
    is_branch_mgr = current_user.role in ("branch_manager", "manager") and current_user.branch_id == target_user.branch_id
    is_assigned_coach = current_user.role == "trainer" and target_user.assigned_trainer_id == current_user.id

    if not (is_self or is_admin or is_branch_mgr or is_assigned_coach):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this member profile.",
        )

    profile = get_or_create_member_profile(db, target_user)
    return update_member_profile(db, target_user, profile, payload, current_user)


@router.post("/measurements", response_model=BodyMeasurementResponse)
def log_my_measurement(
    payload: BodyMeasurementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Log a new dated time-series body measurement for the authenticated user."""
    profile = get_or_create_member_profile(db, current_user)
    return record_member_measurement(db, current_user, profile, payload, current_user)


@router.get("/measurements", response_model=List[BodyMeasurementResponse])
def get_my_measurements(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List historical time-series measurements for the authenticated member."""
    return list_member_measurements(db, current_user.id, current_user, limit=limit, offset=offset)


@router.post("/member/{member_id}/measurements", response_model=BodyMeasurementResponse)
def log_member_measurement(
    member_id: str,
    payload: BodyMeasurementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Log a dated measurement for a member by authorized staff or coach."""
    target_user = db.query(User).filter(User.id == member_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member account not found.",
        )

    is_self = target_user.id == current_user.id
    is_admin = current_user.role in ("org_admin", "admin")
    is_branch_mgr = current_user.role in ("branch_manager", "manager") and current_user.branch_id == target_user.branch_id
    is_assigned_coach = current_user.role == "trainer" and target_user.assigned_trainer_id == current_user.id

    if not (is_self or is_admin or is_branch_mgr or is_assigned_coach):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to log measurements for this member.",
        )

    profile = get_or_create_member_profile(db, target_user)
    return record_member_measurement(db, target_user, profile, payload, current_user)


@router.get("/member/{member_id}/measurements", response_model=List[BodyMeasurementResponse])
def get_member_measurements_by_id(
    member_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List historical time-series measurements for a member by authorized personnel."""
    return list_member_measurements(db, member_id, current_user, limit=limit, offset=offset)
