from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.auth import get_current_user, require_roles, require_csrf
from backend.app.models.user import User
from backend.app.models.trainer import TrainerProfile
from backend.app.services.trainer_service import (
    get_trainer_assigned_members,
    verify_trainer_access_to_member,
    assign_member_to_trainer,
)
from backend.app.schemas.trainer import (
    TrainerProfileResponse,
    AssignedMemberItem,
    AssignedMemberListResponse,
    TrainerAssignmentRequest,
    TrainerAssignmentResponse,
)

router = APIRouter()


@router.get(
    "/trainer/profile",
    response_model=TrainerProfileResponse,
    dependencies=[Depends(require_roles("trainer", "org_admin", "admin", "branch_manager", "manager"))],
    summary="Get Current Coach Profile Details",
)
def get_coach_profile(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrainerProfileResponse:
    profile = db.query(TrainerProfile).filter(TrainerProfile.user_id == user.id).first()
    if not profile:
        # Default placeholder profile for coach if not yet initialized
        profile = TrainerProfile(
            user_id=user.id,
            specialization="Strength & Conditioning Coach",
            bio=f"Certified floor coach at {user.branch.name if user.branch else 'RVFitness'}.",
            certifications=["Certified Fitness Trainer", "CPR/AED"],
            experience_years=3,
            max_clients=20,
            is_accepting_clients=True,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

    return TrainerProfileResponse(
        id=profile.id,
        userId=user.id,
        name=user.name,
        specialization=profile.specialization,
        bio=profile.bio,
        certifications=profile.certifications or [],
        experienceYears=profile.experience_years,
        rating=float(profile.rating),
        maxClients=profile.max_clients,
        isAcceptingClients=profile.is_accepting_clients,
    )


@router.get(
    "/trainer/members",
    response_model=AssignedMemberListResponse,
    dependencies=[Depends(require_roles("trainer", "org_admin", "admin", "branch_manager", "manager"))],
    summary="List Members Assigned to Current Coach (Server-Side Isolation)",
)
def list_assigned_members(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssignedMemberListResponse:
    # If trainer: only assigned members. If supervisor/admin: all branch members.
    if user.role == "trainer":
        members = get_trainer_assigned_members(db, trainer_id=user.id)
    else:
        members = (
            db.query(User)
            .filter(User.role == "member", User.is_active == True)
            .order_by(User.name.asc())
            .all()
        )

    items = [
        AssignedMemberItem(
            id=m.id,
            name=m.name,
            email=m.email,
            phone=m.phone,
            membershipPlan=m.membership_plan.name if m.membership_plan else "General Access",
            membershipStatus=m.membership_status,
            validUntil=m.valid_until.isoformat() if m.valid_until else None,
            streakDays=m.streak_days,
        )
        for m in members
    ]
    return AssignedMemberListResponse(members=items)


@router.get(
    "/trainer/members/{member_id}",
    response_model=AssignedMemberItem,
    dependencies=[Depends(require_roles("trainer", "org_admin", "admin", "branch_manager", "manager"))],
    summary="Get Details of an Assigned Member (403 if Unassigned)",
)
def get_assigned_member(
    member_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssignedMemberItem:
    member = db.query(User).filter(User.id == member_id).first()
    if not member or member.role != "member":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    try:
        verify_trainer_access_to_member(trainer=user, member=member)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    return AssignedMemberItem(
        id=member.id,
        name=member.name,
        email=member.email,
        phone=member.phone,
        membershipPlan=member.membership_plan.name if member.membership_plan else "General Access",
        membershipStatus=member.membership_status,
        validUntil=member.valid_until.isoformat() if member.valid_until else None,
        streakDays=member.streak_days,
    )


@router.post(
    "/trainer/assignments",
    response_model=TrainerAssignmentResponse,
    dependencies=[Depends(require_csrf), Depends(require_roles("org_admin", "admin", "branch_manager", "manager"))],
    summary="Assign Member to Trainer (Supervisory Role)",
)
def assign_trainer(
    payload: TrainerAssignmentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrainerAssignmentResponse:
    try:
        assignment = assign_member_to_trainer(
            db=db,
            trainer_id=payload.trainerId,
            member_id=payload.memberId,
            actor=user,
            notes=payload.notes,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return TrainerAssignmentResponse(
        success=True,
        message="Member successfully assigned to coach.",
        assignmentId=assignment.id,
    )
