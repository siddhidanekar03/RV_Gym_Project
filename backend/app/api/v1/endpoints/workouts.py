from datetime import date, datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.auth import (
    get_current_user,
    require_roles,
    require_csrf,
)
from backend.app.models.user import User
from backend.app.models.workout import (
    WorkoutPlan,
    WorkoutPlanAssignment,
    WorkoutPlanExercise,
    WorkoutSession,
    WorkoutSessionExercise,
    FitnessProgressRecord,
)
from backend.app.models.leaderboard import PointLedgerEntry
from backend.app.schemas.workout import (
    WorkoutPlanCreate,
    WorkoutPlanUpdate,
    WorkoutPlanResponse,
    WorkoutPlanExerciseCreate,
    WorkoutPlanExerciseResponse,
    WorkoutPlanAssignRequest,
    WorkoutPlanAssignmentResponse,
    WorkoutSessionStartRequest,
    WorkoutSessionUpdateRequest,
    WorkoutSessionResponse,
    WorkoutSessionExerciseResponse,
    CoachVerifySessionRequest,
    FitnessProgressRecordCreate,
    FitnessProgressRecordResponse,
)
from backend.app.services.workout_service import (
    create_workout_plan,
    update_workout_plan,
    archive_workout_plan,
    get_workout_plan_by_id,
    list_workout_plans,
    add_exercise_to_plan,
    delete_exercise_from_plan,
    assign_plan_to_member,
    unassign_plan_from_member,
    get_member_assigned_plans,
    start_workout_session,
    update_workout_session,
    get_workout_session_by_id,
    list_workout_sessions_for_member,
    coach_verify_workout_session,
    create_fitness_progress_record,
    list_fitness_progress_records,
)

router = APIRouter(prefix="/workouts")


def _serialize_plan(plan: WorkoutPlan, db: Session, assigned_count: Optional[int] = None) -> WorkoutPlanResponse:
    if assigned_count is None:
        assigned_count = (
            db.query(WorkoutPlanAssignment)
            .filter(
                WorkoutPlanAssignment.workout_plan_id == plan.id,
                WorkoutPlanAssignment.is_active == True,
            )
            .count()
        )
    exercises = [
        WorkoutPlanExerciseResponse.model_validate(ex)
        for ex in sorted(plan.exercises or [], key=lambda e: (e.day_number, e.exercise_order))
    ]
    return WorkoutPlanResponse(
        id=plan.id,
        organization_id=plan.organization_id,
        branch_id=plan.branch_id,
        trainer_id=plan.trainer_id,
        trainer_name=plan.trainer.name if plan.trainer else None,
        name=plan.name,
        description=plan.description,
        goal=plan.goal,
        difficulty=plan.difficulty,
        duration_weeks=plan.duration_weeks,
        status=plan.status,
        start_date=plan.start_date,
        end_date=plan.end_date,
        exercises=exercises,
        assigned_member_count=assigned_count,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def _serialize_session(session: WorkoutSession, db: Session) -> WorkoutSessionResponse:
    points_val = (
        db.query(PointLedgerEntry.points)
        .filter(
            PointLedgerEntry.source_type == "workout_completed",
            PointLedgerEntry.source_id == session.id,
        )
        .scalar()
        or 0
    )
    exercises = [
        WorkoutSessionExerciseResponse.model_validate(ex)
        for ex in sorted(session.completed_exercises or [], key=lambda e: e.exercise_order)
    ]
    return WorkoutSessionResponse(
        id=session.id,
        workout_plan_id=session.workout_plan_id,
        plan_name=session.plan.name if session.plan else None,
        member_id=session.member_id,
        member_name=session.member.name if session.member else None,
        branch_id=session.branch_id,
        session_date=session.session_date,
        started_at=session.started_at,
        completed_at=session.completed_at,
        status=session.status,
        session_name=session.session_name,
        notes=session.notes,
        is_coach_verified=session.is_coach_verified,
        verified_by_id=session.verified_by_id,
        points_awarded=points_val,
        exercises=exercises,
    )


# ---------------------------------------------------------
# Workout Plan Endpoints
# ---------------------------------------------------------

@router.post(
    "/plans",
    response_model=WorkoutPlanResponse,
    dependencies=[Depends(require_roles("trainer", "branch_manager", "manager", "org_admin", "admin")), Depends(require_csrf)],
)
def create_plan_endpoint(
    plan_in: WorkoutPlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new workout plan prescription."""
    plan = create_workout_plan(db, plan_in, current_user)
    return _serialize_plan(plan, db)


@router.get("/plans", response_model=List[WorkoutPlanResponse])
def list_plans_endpoint(
    branch_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List workout plans with appropriate role and branch isolation."""
    plans = list_workout_plans(db, current_user, branch_id=branch_id, status_filter=status_filter)
    if not plans:
        return []

    plan_ids = [p.id for p in plans]
    counts_rows = (
        db.query(
            WorkoutPlanAssignment.workout_plan_id,
            func.count(WorkoutPlanAssignment.id),
        )
        .filter(
            WorkoutPlanAssignment.workout_plan_id.in_(plan_ids),
            WorkoutPlanAssignment.is_active == True,
        )
        .group_by(WorkoutPlanAssignment.workout_plan_id)
        .all()
    )
    counts_map = {pid: cnt for pid, cnt in counts_rows}
    return [_serialize_plan(p, db, assigned_count=counts_map.get(p.id, 0)) for p in plans]


@router.get("/plans/{plan_id}", response_model=WorkoutPlanResponse)
def get_plan_endpoint(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve details for a single workout plan."""
    plan = get_workout_plan_by_id(db, plan_id, current_user)
    return _serialize_plan(plan, db)


@router.put(
    "/plans/{plan_id}",
    response_model=WorkoutPlanResponse,
    dependencies=[Depends(require_roles("trainer", "branch_manager", "manager", "org_admin", "admin")), Depends(require_csrf)],
)
def update_plan_endpoint(
    plan_id: str,
    plan_in: WorkoutPlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update workout plan details."""
    plan = update_workout_plan(db, plan_id, plan_in, current_user)
    return _serialize_plan(plan, db)


@router.delete(
    "/plans/{plan_id}",
    response_model=WorkoutPlanResponse,
    dependencies=[Depends(require_roles("trainer", "branch_manager", "manager", "org_admin", "admin")), Depends(require_csrf)],
)
def archive_plan_endpoint(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Archive a workout plan without wiping session history."""
    plan = archive_workout_plan(db, plan_id, current_user)
    return _serialize_plan(plan, db)


@router.post(
    "/plans/{plan_id}/exercises",
    response_model=WorkoutPlanExerciseResponse,
    dependencies=[Depends(require_roles("trainer", "branch_manager", "manager", "org_admin", "admin")), Depends(require_csrf)],
)
def add_exercise_endpoint(
    plan_id: str,
    exercise_in: WorkoutPlanExerciseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add an exercise to a plan prescription."""
    exercise = add_exercise_to_plan(db, plan_id, exercise_in, current_user)
    return WorkoutPlanExerciseResponse.model_validate(exercise)


@router.delete(
    "/plans/{plan_id}/exercises/{exercise_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("trainer", "branch_manager", "manager", "org_admin", "admin")), Depends(require_csrf)],
)
def delete_exercise_endpoint(
    plan_id: str,
    exercise_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove an exercise from a plan prescription."""
    delete_exercise_from_plan(db, plan_id, exercise_id, current_user)
    return None


@router.post(
    "/plans/{plan_id}/assign",
    response_model=WorkoutPlanAssignmentResponse,
    dependencies=[Depends(require_roles("trainer", "branch_manager", "manager", "org_admin", "admin")), Depends(require_csrf)],
)
def assign_plan_endpoint(
    plan_id: str,
    req: WorkoutPlanAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Assign an active workout plan to a member."""
    assignment = assign_plan_to_member(db, plan_id, req.member_id, current_user, notes=req.notes)
    plan_resp = _serialize_plan(assignment.plan, db) if assignment.plan else None
    return WorkoutPlanAssignmentResponse(
        id=assignment.id,
        workout_plan_id=assignment.workout_plan_id,
        member_id=assignment.member_id,
        member_name=assignment.member.name if assignment.member else None,
        assigned_by_id=assignment.assigned_by_id,
        assigned_at=assignment.assigned_at,
        is_active=assignment.is_active,
        notes=assignment.notes,
        plan=plan_resp,
    )


@router.post(
    "/plans/{plan_id}/unassign",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("trainer", "branch_manager", "manager", "org_admin", "admin")), Depends(require_csrf)],
)
def unassign_plan_endpoint(
    plan_id: str,
    req: WorkoutPlanAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unassign a member from a workout plan."""
    unassign_plan_from_member(db, plan_id, req.member_id, current_user)
    return {"message": "Plan unassigned successfully."}


@router.get("/assigned", response_model=List[WorkoutPlanAssignmentResponse])
def get_my_assigned_plans(
    member_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List assigned workout plans for the authenticated member or requested member."""
    target_id = member_id or current_user.id
    assignments = get_member_assigned_plans(db, target_id, current_user)
    res = []
    for a in assignments:
        plan_resp = _serialize_plan(a.plan, db) if a.plan else None
        res.append(
            WorkoutPlanAssignmentResponse(
                id=a.id,
                workout_plan_id=a.workout_plan_id,
                member_id=a.member_id,
                member_name=a.member.name if a.member else None,
                assigned_by_id=a.assigned_by_id,
                assigned_at=a.assigned_at,
                is_active=a.is_active,
                notes=a.notes,
                plan=plan_resp,
            )
        )
    return res


# ---------------------------------------------------------
# Workout Session Endpoints
# ---------------------------------------------------------

@router.post(
    "/sessions",
    response_model=WorkoutSessionResponse,
    dependencies=[Depends(require_csrf)],
)
def start_session_endpoint(
    start_in: WorkoutSessionStartRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start or record a workout session."""
    session = start_workout_session(db, start_in, current_user)
    return _serialize_session(session, db)


@router.put(
    "/sessions/{session_id}",
    response_model=WorkoutSessionResponse,
    dependencies=[Depends(require_csrf)],
)
def update_session_endpoint(
    session_id: str,
    update_in: WorkoutSessionUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a workout session, log exercise sets, and complete session."""
    session = update_workout_session(db, session_id, update_in, current_user)
    return _serialize_session(session, db)


@router.get("/sessions/{session_id}", response_model=WorkoutSessionResponse)
def get_session_endpoint(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get workout session details."""
    session = get_workout_session_by_id(db, session_id, current_user)
    return _serialize_session(session, db)


@router.get("/sessions", response_model=List[WorkoutSessionResponse])
def list_sessions_endpoint(
    member_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List workout sessions for member."""
    target_id = member_id or current_user.id
    sessions = list_workout_sessions_for_member(db, target_id, current_user, limit=limit, offset=offset)
    return [_serialize_session(s, db) for s in sessions]


@router.post(
    "/sessions/{session_id}/verify",
    response_model=WorkoutSessionResponse,
    dependencies=[Depends(require_roles("trainer", "branch_manager", "manager", "org_admin", "admin")), Depends(require_csrf)],
)
def verify_session_endpoint(
    session_id: str,
    req: CoachVerifySessionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Coach verification of a completed workout session."""
    session = coach_verify_workout_session(db, session_id, current_user, notes=req.notes)
    return _serialize_session(session, db)


# ---------------------------------------------------------
# Fitness Progress Records
# ---------------------------------------------------------

@router.post(
    "/progress",
    response_model=FitnessProgressRecordResponse,
    dependencies=[Depends(require_csrf)],
)
def create_progress_endpoint(
    progress_in: FitnessProgressRecordCreate,
    member_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record private fitness progress (body weight, measurements, PR, notes)."""
    record = create_fitness_progress_record(db, progress_in, current_user, target_user_id=member_id)
    return FitnessProgressRecordResponse(
        id=record.id,
        user_id=record.user_id,
        user_name=record.user.name if record.user else None,
        record_type=record.record_type,
        value=record.value,
        unit=record.unit,
        text_value=record.text_value,
        recorded_date=record.recorded_date,
        is_private=record.is_private,
        notes=record.notes,
        created_at=record.created_at,
    )


@router.get("/progress", response_model=List[FitnessProgressRecordResponse])
def list_progress_endpoint(
    member_id: Optional[str] = Query(None),
    record_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List member fitness progress history.
    Strict privacy: only the member themselves or their actively assigned coach can view.
    """
    target_id = member_id or current_user.id
    records = list_fitness_progress_records(db, target_id, current_user, record_type=record_type)
    return [
        FitnessProgressRecordResponse(
            id=r.id,
            user_id=r.user_id,
            user_name=r.user.name if r.user else None,
            record_type=r.record_type,
            value=r.value,
            unit=r.unit,
            text_value=r.text_value,
            recorded_date=r.recorded_date,
            is_private=r.is_private,
            notes=r.notes,
            created_at=r.created_at,
        )
        for r in records
    ]
