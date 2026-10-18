import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.app.core.database import get_db
from backend.app.core.auth import get_current_user, require_roles
from backend.app.models.user import User
from backend.app.models.workout import WorkoutSession
from backend.app.schemas.performance import (
    PerformanceSummaryResponse,
    WeightHistoryItem,
    WorkoutCompletionRequest,
    CoachMemberProgressItem,
)
from backend.app.schemas.workout import WorkoutSessionResponse
from backend.app.services.performance_service import (
    get_performance_summary,
    get_weight_history,
    log_completed_workout_session,
    get_coach_assigned_members_progress,
)

router = APIRouter(prefix="/performance")


@router.get("/summary", response_model=PerformanceSummaryResponse)
def get_my_performance_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve comprehensive performance and progress summary for authenticated member."""
    return get_performance_summary(db, current_user.id, current_user)


@router.get("/member/{member_id}/summary", response_model=PerformanceSummaryResponse)
def get_member_performance_summary(
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve member performance summary for authorized staff or assigned coach."""
    return get_performance_summary(db, member_id, current_user)


@router.get("/weight-history", response_model=List[WeightHistoryItem])
def get_my_weight_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve chronological dated weight records for authenticated member progress charts."""
    return get_weight_history(db, current_user.id, current_user)


@router.get("/member/{member_id}/weight-history", response_model=List[WeightHistoryItem])
def get_member_weight_history(
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve chronological dated weight records for member by authorized personnel."""
    return get_weight_history(db, member_id, current_user)


@router.get("/workouts", response_model=List[WorkoutSessionResponse])
def get_my_completed_workouts(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List completed workout sessions for authenticated member."""
    sessions = (
        db.query(WorkoutSession)
        .filter(WorkoutSession.member_id == current_user.id, WorkoutSession.status == "completed")
        .order_by(desc(WorkoutSession.session_date), desc(WorkoutSession.completed_at))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return sessions


@router.get("/member/{member_id}/workouts", response_model=List[WorkoutSessionResponse])
def get_member_completed_workouts(
    member_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List completed workout sessions for a member by authorized staff or coach."""
    target_user = db.query(User).filter(User.id == member_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member account not found.")

    is_self = target_user.id == current_user.id
    is_admin = current_user.role in ("org_admin", "admin")
    is_branch_mgr = current_user.role in ("branch_manager", "manager") and current_user.branch_id == target_user.branch_id
    is_assigned_coach = current_user.role == "trainer" and target_user.assigned_trainer_id == current_user.id

    if not (is_self or is_admin or is_branch_mgr or is_assigned_coach):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    sessions = (
        db.query(WorkoutSession)
        .filter(WorkoutSession.member_id == member_id, WorkoutSession.status == "completed")
        .order_by(desc(WorkoutSession.session_date), desc(WorkoutSession.completed_at))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return sessions


@router.post("/workouts/complete", response_model=WorkoutSessionResponse)
def record_completed_workout(
    payload: WorkoutCompletionRequest,
    target_user_id: Optional[str] = Query(None, alias="memberId"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Record an authentic completed workout session with exercise performance logs.
    Members log for themselves; coaches or admins may log on behalf of an assigned member.
    """
    target_user = current_user
    if target_user_id and target_user_id != current_user.id:
        target_user = db.query(User).filter(User.id == target_user_id).first()
        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target member not found.")

    session = log_completed_workout_session(db, target_user, payload, current_user)
    return session


@router.get("/coach/members", response_model=List[CoachMemberProgressItem])
def get_coach_members_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("trainer", "org_admin", "admin")),
):
    """
    Coach view: list progress summaries, goal status, and movement restrictions
    for all actively assigned members.
    """
    return get_coach_assigned_members_progress(db, current_user)
