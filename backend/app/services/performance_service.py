import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc
from fastapi import HTTPException, status

from backend.app.models.user import User
from backend.app.models.member_profile import MemberProfile, MemberBodyMeasurement
from backend.app.models.workout import (
    WorkoutSession,
    WorkoutSessionExercise,
    WorkoutPlanAssignment,
    FitnessProgressRecord,
)
from backend.app.models.personal_record import PersonalRecord
from backend.app.models.attendance import AttendanceRecord
from backend.app.models.audit import AuditLog
from backend.app.schemas.performance import (
    PerformanceSummaryResponse,
    WeightHistoryItem,
    PersonalRecordItem,
    WorkoutCompletionRequest,
    CoachMemberProgressItem,
)
from backend.app.services.member_profile_service import get_or_create_member_profile


def get_performance_summary(
    db: Session,
    user_id: str,
    viewer: User,
) -> PerformanceSummaryResponse:
    """
    Compute comprehensive member performance summary including baseline vs latest weight,
    goal progress, workout completion, attendance consistency, and personal records.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member account not found.")

    is_self = user.id == viewer.id
    is_admin = viewer.role in ("org_admin", "admin")
    is_branch_mgr = viewer.role in ("branch_manager", "manager") and viewer.branch_id == user.branch_id
    is_assigned_coach = viewer.role == "trainer" and user.assigned_trainer_id == viewer.id

    if not (is_self or is_admin or is_branch_mgr or is_assigned_coach):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    profile = get_or_create_member_profile(db, user)

    # 1. Resolve weight history (from member_measurements or legacy fitness_progress_records)
    measurements = (
        db.query(MemberBodyMeasurement)
        .filter(MemberBodyMeasurement.user_id == user.id, MemberBodyMeasurement.weight_kg != None)
        .order_by(asc(MemberBodyMeasurement.recorded_date), asc(MemberBodyMeasurement.created_at))
        .all()
    )

    baseline_weight: Optional[float] = None
    current_weight: Optional[float] = None
    last_m_date: Optional[str] = None
    latest_measurements_dict: Optional[Dict[str, Any]] = None

    if measurements:
        baseline_weight = float(measurements[0].weight_kg)
        current_weight = float(measurements[-1].weight_kg)
        last_m_date = measurements[-1].recorded_date.isoformat()
        latest = measurements[-1]
        latest_measurements_dict = {
            "weightKg": float(latest.weight_kg) if latest.weight_kg is not None else None,
            "heightCm": float(latest.height_cm) if latest.height_cm is not None else None,
            "bodyFatPct": float(latest.body_fat_pct) if latest.body_fat_pct is not None else None,
            "chestCm": float(latest.chest_cm) if latest.chest_cm is not None else None,
            "waistCm": float(latest.waist_cm) if latest.waist_cm is not None else None,
            "hipsCm": float(latest.hips_cm) if latest.hips_cm is not None else None,
            "armsCm": float(latest.arms_cm) if latest.arms_cm is not None else None,
        }
    else:
        # Check fallback legacy fitness progress records
        legacy = (
            db.query(FitnessProgressRecord)
            .filter(FitnessProgressRecord.user_id == user.id, FitnessProgressRecord.record_type == "body_weight")
            .order_by(asc(FitnessProgressRecord.recorded_date), asc(FitnessProgressRecord.created_at))
            .all()
        )
        if legacy:
            baseline_weight = float(legacy[0].value) if legacy[0].value else None
            current_weight = float(legacy[-1].value) if legacy[-1].value else None
            last_m_date = legacy[-1].recorded_date.isoformat()

    # 2. Net weight change & goal progress calculation
    net_change: Optional[float] = None
    if current_weight is not None and baseline_weight is not None:
        net_change = round(current_weight - baseline_weight, 2)

    target_weight = float(profile.target_weight_kg) if profile.target_weight_kg is not None else None
    goal_type = (profile.primary_goal or "general_fitness").lower()
    goal_progress_pct: Optional[float] = None
    goal_status_msg = "No baseline measurements recorded yet. Log your first check-in to begin progress tracking."

    if current_weight is not None and baseline_weight is not None:
        if target_weight is not None:
            if "fat_loss" in goal_type or "weight_loss" in goal_type or target_weight < baseline_weight:
                total_to_lose = baseline_weight - target_weight
                lost = baseline_weight - current_weight
                if total_to_lose > 0:
                    goal_progress_pct = round(max(0.0, min(100.0, (lost / total_to_lose) * 100.0)), 1)
                else:
                    goal_progress_pct = 100.0 if current_weight <= target_weight else 0.0
                goal_status_msg = f"{abs(net_change)} kg {'lost' if net_change <= 0 else 'gained'} toward target of {target_weight} kg."
            elif "gain" in goal_type or "hypertrophy" in goal_type or target_weight > baseline_weight:
                total_to_gain = target_weight - baseline_weight
                gained = current_weight - baseline_weight
                if total_to_gain > 0:
                    goal_progress_pct = round(max(0.0, min(100.0, (gained / total_to_gain) * 100.0)), 1)
                else:
                    goal_progress_pct = 100.0 if current_weight >= target_weight else 0.0
                goal_status_msg = f"{abs(net_change)} kg {'gained' if net_change >= 0 else 'lost'} toward target of {target_weight} kg."
            else:
                goal_status_msg = f"Current weight: {current_weight} kg (Target: {target_weight} kg)."
        else:
            diff_sign = "+" if (net_change or 0) > 0 else ""
            goal_status_msg = f"Net change from baseline: {diff_sign}{net_change} kg over recorded sessions."

    # 3. Workouts completed (this week, this month, all-time)
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = date(today.year, today.month, 1)

    workouts_week = (
        db.query(func.count(WorkoutSession.id))
        .filter(
            WorkoutSession.member_id == user.id,
            WorkoutSession.status == "completed",
            WorkoutSession.session_date >= start_of_week,
        )
        .scalar()
        or 0
    )

    workouts_month = (
        db.query(func.count(WorkoutSession.id))
        .filter(
            WorkoutSession.member_id == user.id,
            WorkoutSession.status == "completed",
            WorkoutSession.session_date >= start_of_month,
        )
        .scalar()
        or 0
    )

    total_workouts = (
        db.query(func.count(WorkoutSession.id))
        .filter(
            WorkoutSession.member_id == user.id,
            WorkoutSession.status == "completed",
        )
        .scalar()
        or 0
    )

    # 4. Attendance sessions this month
    attendance_month = (
        db.query(func.count(AttendanceRecord.id))
        .filter(
            AttendanceRecord.user_id == user.id,
            AttendanceRecord.check_in_date >= start_of_month,
        )
        .scalar()
        or 0
    )

    # 5. Recent Personal Records
    prs = (
        db.query(PersonalRecord)
        .filter(PersonalRecord.user_id == user.id)
        .order_by(desc(PersonalRecord.recorded_at))
        .limit(10)
        .all()
    )
    pr_items = [
        PersonalRecordItem(
            exerciseName=p.exercise_name,
            value=float(p.value),
            unit=p.unit,
            reps=p.reps,
            recordedAt=p.recorded_at.strftime("%B %d, %Y") if p.recorded_at else "",
            isCoachVerified=p.is_coach_verified,
        )
        for p in prs
    ]

    return PerformanceSummaryResponse(
        userId=user.id,
        userName=user.name,
        primaryGoal=profile.primary_goal or "general_fitness",
        currentWeightKg=current_weight,
        baselineWeightKg=baseline_weight,
        netWeightChangeKg=net_change,
        goalWeightKg=target_weight,
        goalProgressPct=goal_progress_pct,
        goalStatusMessage=goal_status_msg,
        workoutsCompletedThisWeek=workouts_week,
        workoutsCompletedThisMonth=workouts_month,
        totalCompletedWorkouts=total_workouts,
        attendanceThisMonth=attendance_month,
        streakDays=user.streak_days,
        recentPRs=pr_items,
        latestMeasurements=latest_measurements_dict,
        lastMeasurementDate=last_m_date,
    )


def get_weight_history(
    db: Session,
    user_id: str,
    viewer: User,
) -> List[WeightHistoryItem]:
    """Retrieve chronological dated weight records for progress chart rendering."""
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
        .filter(MemberBodyMeasurement.user_id == user_id, MemberBodyMeasurement.weight_kg != None)
        .order_by(asc(MemberBodyMeasurement.recorded_date), asc(MemberBodyMeasurement.created_at))
        .all()
    )

    history = [
        WeightHistoryItem(
            date=m.recorded_date.isoformat(),
            weightKg=float(m.weight_kg),
            recordedBy=m.recorded_by.name if m.recorded_by else "Self",
            recordedByRole=m.recorded_by_role,
            notes=m.notes,
        )
        for m in items
    ]

    # If no member_measurements exist, check legacy fitness_progress_records
    if not history:
        legacy = (
            db.query(FitnessProgressRecord)
            .filter(FitnessProgressRecord.user_id == user_id, FitnessProgressRecord.record_type == "body_weight")
            .order_by(asc(FitnessProgressRecord.recorded_date))
            .all()
        )
        history = [
            WeightHistoryItem(
                date=r.recorded_date.isoformat(),
                weightKg=float(r.value),
                recordedBy=r.user.name if r.user else "Self",
                recordedByRole="member",
                notes=r.notes,
            )
            for r in legacy
            if r.value is not None
        ]

    return history


def log_completed_workout_session(
    db: Session,
    user: User,
    req: WorkoutCompletionRequest,
    actor: User,
) -> WorkoutSession:
    """
    Record an authentic completed workout session with exercise performance logs,
    personal record recognition, and audit trail.
    """
    is_self = user.id == actor.id
    is_admin = actor.role in ("org_admin", "admin", "branch_manager", "manager")
    is_coach = actor.role == "trainer" and user.assigned_trainer_id == actor.id

    if not (is_self or is_admin or is_coach):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    now = datetime.now(timezone.utc)
    target_branch = user.branch_id or "narsobawadi"
    is_coach_verified = actor.role == "trainer"

    session = WorkoutSession(
        id=str(uuid.uuid4()),
        workout_plan_id=req.workoutPlanId,
        member_id=user.id,
        branch_id=target_branch,
        session_date=req.sessionDate or date.today(),
        started_at=now - timedelta(minutes=req.durationMinutes or 45),
        completed_at=now,
        status="completed",
        session_name=req.sessionName.strip(),
        notes=req.notes.strip() if req.notes else None,
        duration_minutes=req.durationMinutes,
        rpe=req.rpe,
        is_coach_verified=is_coach_verified,
        verified_by_id=actor.id if is_coach_verified else None,
    )
    db.add(session)
    db.flush()

    # Add exercise logs and evaluate potential new personal records
    for idx, ex in enumerate(req.exercises, start=1):
        clean_name = ex.exerciseName.strip()
        weight_dec = Decimal(str(ex.weightKg)) if ex.weightKg is not None else None
        dist_dec = Decimal(str(ex.distanceMeters)) if ex.distanceMeters is not None else None

        ex_log = WorkoutSessionExercise(
            id=str(uuid.uuid4()),
            session_id=session.id,
            exercise_name=clean_name,
            exercise_order=idx,
            sets_completed=ex.sets,
            reps_completed=ex.reps,
            weight_kg=weight_dec,
            duration_seconds=ex.durationSeconds,
            distance_meters=dist_dec,
            is_completed=True,
            notes=ex.notes,
        )
        db.add(ex_log)

        # Check for new PR on heaviest lift
        if weight_dec and weight_dec > Decimal("0.00"):
            existing_pr = (
                db.query(PersonalRecord)
                .filter(
                    PersonalRecord.user_id == user.id,
                    func.lower(PersonalRecord.exercise_name) == clean_name.lower(),
                )
                .first()
            )
            if not existing_pr:
                new_pr = PersonalRecord(
                    id=str(uuid.uuid4()),
                    user_id=user.id,
                    exercise_name=clean_name,
                    value=weight_dec,
                    unit="kg",
                    reps=ex.reps or 1,
                    is_coach_verified=is_coach_verified,
                    verified_by_id=actor.id if is_coach_verified else None,
                )
                db.add(new_pr)
            elif weight_dec > existing_pr.value:
                existing_pr.value = weight_dec
                existing_pr.reps = ex.reps or 1
                existing_pr.recorded_at = now
                if is_coach_verified:
                    existing_pr.is_coach_verified = True
                    existing_pr.verified_by_id = actor.id

    # Award workout points for gamification
    try:
        from backend.app.services.leaderboard_service import award_completed_workout_points
        award_completed_workout_points(db, session)
    except Exception:
        pass

    db.commit()
    db.refresh(session)
    return session


def get_coach_assigned_members_progress(
    db: Session,
    coach: User,
) -> List[CoachMemberProgressItem]:
    """Retrieve training and goal progress overview for members assigned to coach."""
    members = (
        db.query(User)
        .filter(User.assigned_trainer_id == coach.id, User.is_active == True)
        .order_by(User.name.asc())
        .all()
    )

    results = []
    today = date.today()
    start_of_month = date(today.year, today.month, 1)

    for m in members:
        profile = get_or_create_member_profile(db, m)

        # Latest weight
        latest_meas = (
            db.query(MemberBodyMeasurement)
            .filter(MemberBodyMeasurement.user_id == m.id, MemberBodyMeasurement.weight_kg != None)
            .order_by(desc(MemberBodyMeasurement.recorded_date), desc(MemberBodyMeasurement.created_at))
            .first()
        )
        first_meas = (
            db.query(MemberBodyMeasurement)
            .filter(MemberBodyMeasurement.user_id == m.id, MemberBodyMeasurement.weight_kg != None)
            .order_by(asc(MemberBodyMeasurement.recorded_date), asc(MemberBodyMeasurement.created_at))
            .first()
        )

        curr_wt = float(latest_meas.weight_kg) if latest_meas else None
        base_wt = float(first_meas.weight_kg) if first_meas else None
        net_wt = round(curr_wt - base_wt, 2) if (curr_wt is not None and base_wt is not None) else None

        # Workouts this month
        w_count = (
            db.query(func.count(WorkoutSession.id))
            .filter(
                WorkoutSession.member_id == m.id,
                WorkoutSession.status == "completed",
                WorkoutSession.session_date >= start_of_month,
            )
            .scalar()
            or 0
        )

        # Last workout session
        last_w = (
            db.query(WorkoutSession)
            .filter(WorkoutSession.member_id == m.id, WorkoutSession.status == "completed")
            .order_by(desc(WorkoutSession.session_date))
            .first()
        )

        # Active assigned plan
        active_assign = (
            db.query(WorkoutPlanAssignment)
            .filter(WorkoutPlanAssignment.member_id == m.id, WorkoutPlanAssignment.is_active == True)
            .first()
        )

        results.append(
            CoachMemberProgressItem(
                memberId=m.id,
                memberName=m.name,
                memberEmail=m.email,
                memberPhone=m.phone,
                membershipStatus=m.membership_status,
                membershipPlan=m.membership_plan.name if m.membership_plan else "None",
                streakDays=m.streak_days,
                primaryGoal=profile.primary_goal or "general_fitness",
                currentWeightKg=curr_wt,
                baselineWeightKg=base_wt,
                netWeightChangeKg=net_wt,
                goalWeightKg=float(profile.target_weight_kg) if profile.target_weight_kg else None,
                workoutsCompletedThisMonth=w_count,
                lastWorkoutDate=last_w.session_date.isoformat() if last_w else None,
                lastMeasurementDate=latest_meas.recorded_date.isoformat() if latest_meas else None,
                hasHealthRestrictions=bool(profile.exercise_restrictions or profile.current_injuries),
                movementRestrictions=profile.exercise_restrictions,
                activeAssignedPlanName=active_assign.plan.name if active_assign and active_assign.plan else None,
            )
        )

    return results
