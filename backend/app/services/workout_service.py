import uuid
from datetime import date, datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, or_

from backend.app.models.user import User
from backend.app.models.workout import (
    WorkoutPlan,
    WorkoutPlanAssignment,
    WorkoutPlanExercise,
    WorkoutSession,
    WorkoutSessionExercise,
    FitnessProgressRecord,
)
from backend.app.models.audit import AuditLog
from backend.app.models.leaderboard import PointLedgerEntry
from backend.app.services.trainer_service import verify_trainer_access_to_member
from backend.app.services.leaderboard_service import (
    award_workout_completion_points,
    reverse_workout_points,
)
from backend.app.schemas.workout import (
    WorkoutPlanCreate,
    WorkoutPlanUpdate,
    WorkoutPlanExerciseCreate,
    WorkoutSessionStartRequest,
    WorkoutSessionUpdateRequest,
    WorkoutSessionExerciseRecord,
    FitnessProgressRecordCreate,
)


def _verify_plan_management_access(actor: User, plan: Optional[WorkoutPlan] = None, branch_id: Optional[str] = None) -> None:
    """
    Verify actor has permission to create or modify workout plans.
    Org admin: anywhere in org.
    Branch manager: within their branch.
    Trainer: within their branch and for plans they own.
    Members: forbidden.
    """
    if actor.role in ("org_admin", "admin"):
        return

    if actor.role in ("branch_manager", "manager"):
        target_branch = (plan.branch_id if plan else branch_id) or actor.branch_id
        if actor.branch_id and target_branch and actor.branch_id != target_branch:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: You can only manage plans for branch '{actor.branch_id}'.",
            )
        return

    if actor.role == "trainer":
        target_branch = (plan.branch_id if plan else branch_id) or actor.branch_id
        if actor.branch_id and target_branch and actor.branch_id != target_branch:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: You can only manage plans for branch '{actor.branch_id}'.",
            )
        if plan and plan.trainer_id and plan.trainer_id != actor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You can only modify workout plans created by you.",
            )
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied: Only trainers, branch managers, and administrators can manage workout plans.",
    )


def create_workout_plan(db: Session, plan_in: WorkoutPlanCreate, actor: User) -> WorkoutPlan:
    """Create a new workout plan with associated exercises and audit logging."""
    target_branch_id = plan_in.branch_id or actor.branch_id or "narsobawadi"
    _verify_plan_management_access(actor, branch_id=target_branch_id)

    target_trainer_id = plan_in.trainer_id
    if actor.role == "trainer":
        target_trainer_id = actor.id

    plan_id = str(uuid.uuid4())
    plan = WorkoutPlan(
        id=plan_id,
        organization_id=plan_in.organization_id or "rvf-org-main",
        branch_id=target_branch_id,
        trainer_id=target_trainer_id,
        name=plan_in.name.strip(),
        description=plan_in.description.strip() if plan_in.description else None,
        goal=plan_in.goal,
        difficulty=plan_in.difficulty,
        duration_weeks=plan_in.duration_weeks,
        status=plan_in.status,
        start_date=plan_in.start_date,
        end_date=plan_in.end_date,
    )
    db.add(plan)
    db.flush()

    if plan_in.exercises:
        for idx, ex_data in enumerate(plan_in.exercises, start=1):
            exercise = WorkoutPlanExercise(
                id=str(uuid.uuid4()),
                workout_plan_id=plan.id,
                day_number=ex_data.day_number,
                day_name=ex_data.day_name,
                exercise_order=ex_data.exercise_order or idx,
                name=ex_data.name.strip(),
                instructions=ex_data.instructions.strip() if ex_data.instructions else None,
                sets=ex_data.sets,
                reps=ex_data.reps,
                target_duration_seconds=ex_data.target_duration_seconds,
                target_distance_meters=ex_data.target_distance_meters,
                target_weight_kg=ex_data.target_weight_kg,
                rest_seconds=ex_data.rest_seconds,
                notes=ex_data.notes.strip() if ex_data.notes else None,
            )
            db.add(exercise)

    audit = AuditLog(
        actor_id=actor.id,
        action="workout_plan.create",
        resource_type="workout_plan",
        resource_id=plan.id,
        details={
            "plan_name": plan.name,
            "branch_id": plan.branch_id,
            "trainer_id": plan.trainer_id,
            "exercise_count": len(plan_in.exercises) if plan_in.exercises else 0,
        },
    )
    db.add(audit)
    db.commit()
    db.refresh(plan)
    return plan


def update_workout_plan(db: Session, plan_id: str, plan_in: WorkoutPlanUpdate, actor: User) -> WorkoutPlan:
    """Update workout plan metadata."""
    plan = db.query(WorkoutPlan).filter(WorkoutPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout plan not found.")

    _verify_plan_management_access(actor, plan=plan)

    if plan_in.name is not None:
        plan.name = plan_in.name.strip()
    if plan_in.description is not None:
        plan.description = plan_in.description.strip() if plan_in.description else None
    if plan_in.goal is not None:
        plan.goal = plan_in.goal
    if plan_in.difficulty is not None:
        plan.difficulty = plan_in.difficulty
    if plan_in.duration_weeks is not None:
        plan.duration_weeks = plan_in.duration_weeks
    if plan_in.status is not None:
        plan.status = plan_in.status
    if plan_in.start_date is not None:
        plan.start_date = plan_in.start_date
    if plan_in.end_date is not None:
        plan.end_date = plan_in.end_date

    audit = AuditLog(
        actor_id=actor.id,
        action="workout_plan.update",
        resource_type="workout_plan",
        resource_id=plan.id,
        details={"updated_fields": list(plan_in.model_dump(exclude_unset=True).keys())},
    )
    db.add(audit)
    db.commit()
    db.refresh(plan)
    return plan


def archive_workout_plan(db: Session, plan_id: str, actor: User) -> WorkoutPlan:
    """Archive a workout plan without deleting historical session data."""
    plan = db.query(WorkoutPlan).filter(WorkoutPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout plan not found.")

    _verify_plan_management_access(actor, plan=plan)

    plan.status = "archived"
    audit = AuditLog(
        actor_id=actor.id,
        action="workout_plan.archive",
        resource_type="workout_plan",
        resource_id=plan.id,
        details={"plan_name": plan.name, "status": "archived"},
    )
    db.add(audit)
    db.commit()
    db.refresh(plan)
    return plan


def get_workout_plan_by_id(db: Session, plan_id: str, actor: User) -> WorkoutPlan:
    """
    Retrieve workout plan details.
    Members can only view plans actively assigned to them.
    Trainers and staff are scoped by branch and trainer assignment.
    """
    plan = db.query(WorkoutPlan).filter(WorkoutPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout plan not found.")

    if actor.role == "member":
        assignment = (
            db.query(WorkoutPlanAssignment)
            .filter(
                WorkoutPlanAssignment.workout_plan_id == plan.id,
                WorkoutPlanAssignment.member_id == actor.id,
                WorkoutPlanAssignment.is_active == True,
            )
            .first()
        )
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not assigned to this workout plan.",
            )
        return plan

    if actor.role in ("branch_manager", "manager", "staff", "front_desk"):
        if actor.branch_id and plan.branch_id and actor.branch_id != plan.branch_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Plan belongs to branch '{plan.branch_id}'.",
            )
        return plan

    if actor.role == "trainer":
        if actor.branch_id and plan.branch_id and actor.branch_id != plan.branch_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Plan belongs to branch '{plan.branch_id}'.",
            )
        return plan

    if actor.role in ("org_admin", "admin"):
        return plan

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")


def list_workout_plans(
    db: Session,
    actor: User,
    branch_id: Optional[str] = None,
    status_filter: Optional[str] = None,
) -> List[WorkoutPlan]:
    """List workout plans with strict role and branch isolation."""
    query = db.query(WorkoutPlan)

    if actor.role == "member":
        # Member only sees plans assigned to them
        assigned_plan_ids = (
            db.query(WorkoutPlanAssignment.workout_plan_id)
            .filter(
                WorkoutPlanAssignment.member_id == actor.id,
                WorkoutPlanAssignment.is_active == True,
            )
            .subquery()
        )
        query = query.filter(WorkoutPlan.id.in_(assigned_plan_ids))
    elif actor.role in ("branch_manager", "manager"):
        target_branch = actor.branch_id or branch_id
        if target_branch:
            query = query.filter(WorkoutPlan.branch_id == target_branch)
    elif actor.role == "trainer":
        target_branch = actor.branch_id or branch_id
        if target_branch:
            query = query.filter(
                WorkoutPlan.branch_id == target_branch,
                or_(WorkoutPlan.trainer_id == actor.id, WorkoutPlan.trainer_id.is_(None)),
            )
    elif actor.role in ("org_admin", "admin"):
        if branch_id:
            query = query.filter(WorkoutPlan.branch_id == branch_id)

    if status_filter:
        query = query.filter(WorkoutPlan.status == status_filter)

    return query.order_by(desc(WorkoutPlan.created_at)).all()


def add_exercise_to_plan(
    db: Session,
    plan_id: str,
    exercise_in: WorkoutPlanExerciseCreate,
    actor: User,
) -> WorkoutPlanExercise:
    """Add an exercise to a workout plan."""
    plan = db.query(WorkoutPlan).filter(WorkoutPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout plan not found.")

    _verify_plan_management_access(actor, plan=plan)

    exercise = WorkoutPlanExercise(
        id=str(uuid.uuid4()),
        workout_plan_id=plan.id,
        day_number=exercise_in.day_number,
        day_name=exercise_in.day_name,
        exercise_order=exercise_in.exercise_order,
        name=exercise_in.name.strip(),
        instructions=exercise_in.instructions.strip() if exercise_in.instructions else None,
        sets=exercise_in.sets,
        reps=exercise_in.reps,
        target_duration_seconds=exercise_in.target_duration_seconds,
        target_distance_meters=exercise_in.target_distance_meters,
        target_weight_kg=exercise_in.target_weight_kg,
        rest_seconds=exercise_in.rest_seconds,
        notes=exercise_in.notes.strip() if exercise_in.notes else None,
    )
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    return exercise


def delete_exercise_from_plan(db: Session, plan_id: str, exercise_id: str, actor: User) -> None:
    """Remove an exercise from a workout plan."""
    plan = db.query(WorkoutPlan).filter(WorkoutPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout plan not found.")

    _verify_plan_management_access(actor, plan=plan)

    exercise = (
        db.query(WorkoutPlanExercise)
        .filter(
            WorkoutPlanExercise.id == exercise_id,
            WorkoutPlanExercise.workout_plan_id == plan.id,
        )
        .first()
    )
    if not exercise:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found in this plan.")

    db.delete(exercise)
    db.commit()


def assign_plan_to_member(
    db: Session,
    plan_id: str,
    member_id: str,
    actor: User,
    notes: Optional[str] = None,
) -> WorkoutPlanAssignment:
    """Assign a member to an active workout plan."""
    plan = db.query(WorkoutPlan).filter(WorkoutPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout plan not found.")

    if plan.status == "archived":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot assign members to an archived workout plan.",
        )

    member = db.query(User).filter(User.id == member_id, User.role == "member").first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    if not member.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot assign plan to inactive member.")

    # Verify actor access to member and plan
    _verify_plan_management_access(actor, plan=plan)
    try:
        verify_trainer_access_to_member(actor, member)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    assignment = (
        db.query(WorkoutPlanAssignment)
        .filter(
            WorkoutPlanAssignment.workout_plan_id == plan.id,
            WorkoutPlanAssignment.member_id == member.id,
        )
        .first()
    )

    if assignment:
        assignment.is_active = True
        assignment.assigned_by_id = actor.id
        assignment.assigned_at = datetime.now(timezone.utc)
        if notes:
            assignment.notes = notes.strip()
    else:
        assignment = WorkoutPlanAssignment(
            id=str(uuid.uuid4()),
            workout_plan_id=plan.id,
            member_id=member.id,
            assigned_by_id=actor.id,
            assigned_at=datetime.now(timezone.utc),
            is_active=True,
            notes=notes.strip() if notes else None,
        )
        db.add(assignment)

    audit = AuditLog(
        actor_id=actor.id,
        action="workout_plan.assign_member",
        resource_type="workout_plan_assignment",
        resource_id=assignment.id,
        details={
            "plan_id": plan.id,
            "plan_name": plan.name,
            "member_id": member.id,
            "member_name": member.name,
        },
    )
    db.add(audit)
    db.commit()
    db.refresh(assignment)
    return assignment


def unassign_plan_from_member(
    db: Session,
    plan_id: str,
    member_id: str,
    actor: User,
) -> None:
    """Deactivate member assignment to a workout plan."""
    assignment = (
        db.query(WorkoutPlanAssignment)
        .filter(
            WorkoutPlanAssignment.workout_plan_id == plan_id,
            WorkoutPlanAssignment.member_id == member_id,
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found.")

    plan = db.query(WorkoutPlan).filter(WorkoutPlan.id == plan_id).first()
    _verify_plan_management_access(actor, plan=plan)

    assignment.is_active = False
    audit = AuditLog(
        actor_id=actor.id,
        action="workout_plan.unassign_member",
        resource_type="workout_plan_assignment",
        resource_id=assignment.id,
        details={"plan_id": plan_id, "member_id": member_id},
    )
    db.add(audit)
    db.commit()


def get_member_assigned_plans(db: Session, member_id: str, actor: User) -> List[WorkoutPlanAssignment]:
    """List active workout plan assignments for a member."""
    member = db.query(User).filter(User.id == member_id).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    try:
        verify_trainer_access_to_member(actor, member)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    return (
        db.query(WorkoutPlanAssignment)
        .filter(
            WorkoutPlanAssignment.member_id == member_id,
            WorkoutPlanAssignment.is_active == True,
        )
        .order_by(desc(WorkoutPlanAssignment.assigned_at))
        .all()
    )


# ---------------------------------------------------------
# Workout Session Lifecycle
# ---------------------------------------------------------

def start_workout_session(
    db: Session,
    start_in: WorkoutSessionStartRequest,
    actor: User,
) -> WorkoutSession:
    """
    Start or record a workout session.
    Only the member themselves can start a workout session for their account.
    If linked to a plan, the plan must be actively assigned to this member.
    """
    if actor.role != "member":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only gym members can record personal workout sessions.",
        )

    plan = None
    if start_in.workout_plan_id:
        plan = db.query(WorkoutPlan).filter(WorkoutPlan.id == start_in.workout_plan_id).first()
        if not plan:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout plan not found.")

        if plan.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot start session for an archived workout plan.",
            )

        assignment = (
            db.query(WorkoutPlanAssignment)
            .filter(
                WorkoutPlanAssignment.workout_plan_id == plan.id,
                WorkoutPlanAssignment.member_id == actor.id,
                WorkoutPlanAssignment.is_active == True,
            )
            .first()
        )
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not assigned to this workout plan.",
            )

    now = datetime.now(timezone.utc)
    session_id = str(uuid.uuid4())
    session_name = start_in.session_name or (f"{plan.name} Session" if plan else "Free Training Session")

    session = WorkoutSession(
        id=session_id,
        workout_plan_id=plan.id if plan else None,
        member_id=actor.id,
        branch_id=actor.branch_id or (plan.branch_id if plan else "narsobawadi"),
        session_date=date.today(),
        started_at=now,
        completed_at=None,
        status="in_progress",
        session_name=session_name,
        notes=start_in.notes.strip() if start_in.notes else None,
        is_coach_verified=False,
    )
    db.add(session)
    db.flush()

    # Pre-populate session exercise entries from plan if available
    if plan and plan.exercises:
        for ex in plan.exercises:
            session_ex = WorkoutSessionExercise(
                id=str(uuid.uuid4()),
                session_id=session.id,
                plan_exercise_id=ex.id,
                exercise_name=ex.name,
                exercise_order=ex.exercise_order,
                sets_completed=None,
                reps_completed=None,
                weight_kg=None,
                duration_seconds=None,
                distance_meters=None,
                is_completed=False,
                notes=None,
            )
            db.add(session_ex)

    db.commit()
    db.refresh(session)
    return session


def update_workout_session(
    db: Session,
    session_id: str,
    update_in: WorkoutSessionUpdateRequest,
    actor: User,
) -> WorkoutSession:
    """
    Update session status, record actual exercise sets/reps, and award points on completion.
    Only the member who owns the session can update it.
    """
    session = db.query(WorkoutSession).filter(WorkoutSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout session not found.")

    if session.member_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You cannot modify another member's workout session.",
        )

    # Prevent re-completion or modification of already finalized sessions
    if session.status in ("completed", "abandoned") and update_in.status != session.status:
        # If moving away from completed, handle point reversal
        if session.status == "completed" and update_in.status in ("in_progress", "abandoned"):
            reverse_workout_points(db, session.id, actor_id=actor.id, reason=f"Session status changed to {update_in.status}")

    if update_in.session_name is not None:
        session.session_name = update_in.session_name.strip()
    if update_in.notes is not None:
        session.notes = update_in.notes.strip() if update_in.notes else None

    # Handle exercise logs
    if update_in.exercises is not None:
        for ex_data in update_in.exercises:
            # Match existing session exercise by plan_exercise_id or exercise_name
            existing_ex = (
                db.query(WorkoutSessionExercise)
                .filter(
                    WorkoutSessionExercise.session_id == session.id,
                    or_(
                        WorkoutSessionExercise.plan_exercise_id == ex_data.plan_exercise_id,
                        WorkoutSessionExercise.exercise_name == ex_data.exercise_name,
                    ),
                )
                .first()
            )
            if existing_ex:
                existing_ex.sets_completed = ex_data.sets_completed
                existing_ex.reps_completed = ex_data.reps_completed
                existing_ex.weight_kg = ex_data.weight_kg
                existing_ex.duration_seconds = ex_data.duration_seconds
                existing_ex.distance_meters = ex_data.distance_meters
                existing_ex.is_completed = ex_data.is_completed
                if ex_data.notes:
                    existing_ex.notes = ex_data.notes.strip()
            else:
                new_ex = WorkoutSessionExercise(
                    id=str(uuid.uuid4()),
                    session_id=session.id,
                    plan_exercise_id=ex_data.plan_exercise_id,
                    exercise_name=ex_data.exercise_name.strip(),
                    exercise_order=ex_data.exercise_order,
                    sets_completed=ex_data.sets_completed,
                    reps_completed=ex_data.reps_completed,
                    weight_kg=ex_data.weight_kg,
                    duration_seconds=ex_data.duration_seconds,
                    distance_meters=ex_data.distance_meters,
                    is_completed=ex_data.is_completed,
                    notes=ex_data.notes.strip() if ex_data.notes else None,
                )
                db.add(new_ex)

    # Check status transitions
    if update_in.status is not None:
        session.status = update_in.status
        if update_in.status == "completed":
            session.completed_at = update_in.completed_at or datetime.now(timezone.utc)
            # Idempotently award workout completion points (+5 points, max 1 award per day)
            award_workout_completion_points(db, session, actor_id=actor.id)
        elif update_in.status == "abandoned":
            session.completed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(session)
    return session


def get_workout_session_by_id(db: Session, session_id: str, actor: User) -> WorkoutSession:
    """Retrieve session details with strict authorization."""
    session = db.query(WorkoutSession).filter(WorkoutSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout session not found.")

    member = db.query(User).filter(User.id == session.member_id).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member record not found.")

    try:
        verify_trainer_access_to_member(actor, member)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    return session


def list_workout_sessions_for_member(
    db: Session,
    member_id: str,
    actor: User,
    limit: int = 50,
    offset: int = 0,
) -> List[WorkoutSession]:
    """List session history for a member."""
    member = db.query(User).filter(User.id == member_id).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    try:
        verify_trainer_access_to_member(actor, member)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    return (
        db.query(WorkoutSession)
        .filter(WorkoutSession.member_id == member_id)
        .order_by(desc(WorkoutSession.started_at))
        .offset(offset)
        .limit(limit)
        .all()
    )


def coach_verify_workout_session(
    db: Session,
    session_id: str,
    actor: User,
    notes: Optional[str] = None,
) -> WorkoutSession:
    """
    Coach verification of a completed workout session.
    Requires trainer or manager role with current assignment to the member.
    """
    session = db.query(WorkoutSession).filter(WorkoutSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout session not found.")

    if actor.role not in ("trainer", "branch_manager", "manager", "org_admin", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only authorized trainers and managers can verify workout sessions.",
        )

    member = db.query(User).filter(User.id == session.member_id).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    try:
        verify_trainer_access_to_member(actor, member)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    session.is_coach_verified = True
    session.verified_by_id = actor.id
    if notes:
        existing_notes = session.notes or ""
        session.notes = f"{existing_notes}\n[Coach Verification]: {notes.strip()}".strip()

    audit = AuditLog(
        actor_id=actor.id,
        action="workout_session.coach_verify",
        resource_type="workout_session",
        resource_id=session.id,
        details={
            "member_id": session.member_id,
            "session_name": session.session_name,
            "verified_by": actor.name,
        },
    )
    db.add(audit)
    db.commit()
    db.refresh(session)
    return session


# ---------------------------------------------------------
# Fitness Progress Tracking
# ---------------------------------------------------------

def create_fitness_progress_record(
    db: Session,
    progress_in: FitnessProgressRecordCreate,
    actor: User,
    target_user_id: Optional[str] = None,
) -> FitnessProgressRecord:
    """
    Record member fitness progress.
    Members record for themselves.
    Trainers can record for members assigned to them.
    """
    user_id = target_user_id or actor.id

    if actor.id != user_id:
        member = db.query(User).filter(User.id == user_id).first()
        if not member:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")
        try:
            verify_trainer_access_to_member(actor, member)
        except PermissionError as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    record = FitnessProgressRecord(
        id=str(uuid.uuid4()),
        user_id=user_id,
        record_type=progress_in.record_type,
        value=progress_in.value,
        unit=progress_in.unit.strip() if progress_in.unit else None,
        text_value=progress_in.text_value.strip() if progress_in.text_value else None,
        recorded_date=progress_in.recorded_date or date.today(),
        is_private=progress_in.is_private,
        notes=progress_in.notes.strip() if progress_in.notes else None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_fitness_progress_records(
    db: Session,
    target_user_id: str,
    actor: User,
    record_type: Optional[str] = None,
) -> List[FitnessProgressRecord]:
    """
    List member fitness progress history.
    Strict privacy:
    - Member sees all their records.
    - Trainer sees records only if actively assigned to the member.
    - If trainer assignment was removed, trainer access is blocked.
    - If not assigned, forbidden.
    - Public access is impossible.
    """
    member = db.query(User).filter(User.id == target_user_id).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    if actor.id != member.id:
        try:
            verify_trainer_access_to_member(actor, member)
        except PermissionError as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    query = db.query(FitnessProgressRecord).filter(FitnessProgressRecord.user_id == target_user_id)

    # If actor is trainer, only allow non-private or trainer-accessible records
    if actor.id != member.id and actor.role == "trainer":
        query = query.filter(FitnessProgressRecord.is_private == False)

    if record_type:
        query = query.filter(FitnessProgressRecord.record_type == record_type)

    return query.order_by(desc(FitnessProgressRecord.recorded_date), desc(FitnessProgressRecord.created_at)).all()
