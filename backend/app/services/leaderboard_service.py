import uuid
import re
from datetime import date, datetime, timezone
from typing import Optional, List, Tuple, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc, asc
from fastapi import HTTPException, status

from backend.app.models.user import User
from backend.app.models.leaderboard import PointLedgerEntry
from backend.app.models.attendance import AttendanceRecord
from backend.app.models.personal_record import PersonalRecord
from backend.app.models.organization import Branch
from backend.app.models.audit import AuditLog
from backend.app.schemas.leaderboard import (
    LeaderboardEntry,
    MemberSelfStandingResponse,
    ScoringRuleItem,
    ScoringRulesResponse,
)

# Configurable points values
POINTS_ATTENDANCE_VERIFIED = 10
POINTS_COACH_VERIFIED_PR = 25
POINTS_STREAK_MILESTONE = 20  # Awarded for each 7-day milestone
POINTS_WORKOUT_COMPLETED = 5
POINTS_COACH_VERIFIED_WORKOUT = 5


def get_default_alias_for_user(user: User) -> str:
    """Return a privacy-safe gaming alias for a user if none has been configured."""
    if user.leaderboard_alias and user.leaderboard_alias.strip():
        return user.leaderboard_alias.strip()
    clean_id = (user.id or "0000").replace("-", "")
    return f"Athlete_{clean_id[-4:]}"


def award_attendance_points(
    db: Session, attendance_record: AttendanceRecord
) -> Optional[PointLedgerEntry]:
    """
    Award points for a verified floor attendance check-in.
    Enforces idempotency and a strict daily cap of 1 attendance award per calendar date.
    Never awards points for rejected check-ins or records without a linked user.
    """
    if not attendance_record.user_id:
        # Desk check-in without an active web portal account; points await account linking.
        return None

    user = db.query(User).filter(User.id == attendance_record.user_id).first()
    if not user or not user.is_active:
        return None

    # Check for duplicate award for this specific attendance record
    existing_entry = (
        db.query(PointLedgerEntry)
        .filter(
            PointLedgerEntry.source_type == "attendance_verified",
            PointLedgerEntry.source_id == attendance_record.id,
        )
        .first()
    )
    if existing_entry:
        return existing_entry

    # Check daily cap: At most 1 attendance award per member per calendar date
    event_date = attendance_record.check_in_date
    daily_existing = (
        db.query(PointLedgerEntry)
        .filter(
            PointLedgerEntry.user_id == user.id,
            PointLedgerEntry.source_type == "attendance_verified",
            PointLedgerEntry.event_date == event_date,
        )
        .first()
    )
    if daily_existing:
        return daily_existing

    # Determine branch and org
    branch_id = attendance_record.branch_id or user.branch_id or "narsobawadi"
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    org_id = branch.organization_id if branch else "rvf-org-main"

    entry = PointLedgerEntry(
        id=str(uuid.uuid4()),
        user_id=user.id,
        organization_id=org_id,
        branch_id=branch_id,
        source_type="attendance_verified",
        source_id=attendance_record.id,
        points=POINTS_ATTENDANCE_VERIFIED,
        event_date=event_date,
        year=event_date.year,
        month=event_date.month,
        notes="Verified floor attendance check-in",
        created_by=getattr(attendance_record, "staff_id", None) or user.id,
    )
    db.add(entry)

    # Check for 7-day streak milestone award
    if user.streak_days > 0 and user.streak_days % 7 == 0:
        milestone_key = f"streak:{user.id}:{user.streak_days}:{event_date}"
        existing_streak_entry = (
            db.query(PointLedgerEntry)
            .filter(
                PointLedgerEntry.source_type == "streak_milestone",
                PointLedgerEntry.source_id == milestone_key,
            )
            .first()
        )
        if not existing_streak_entry:
            streak_entry = PointLedgerEntry(
                id=str(uuid.uuid4()),
                user_id=user.id,
                organization_id=org_id,
                branch_id=branch_id,
                source_type="streak_milestone",
                source_id=milestone_key,
                points=POINTS_STREAK_MILESTONE,
                event_date=event_date,
                year=event_date.year,
                month=event_date.month,
                notes=f"Discipline milestone: {user.streak_days}-day consecutive attendance",
                created_by=user.id,
            )
            db.add(streak_entry)

    db.flush()
    return entry


def award_pr_points(
    db: Session, pr: PersonalRecord, actor_id: Optional[str] = None
) -> Optional[PointLedgerEntry]:
    """Award points for a coach-verified Personal Record."""
    if not pr.is_coach_verified or not pr.user_id:
        return None

    source_key = f"pr:{pr.id}"
    existing = (
        db.query(PointLedgerEntry)
        .filter(
            PointLedgerEntry.source_type == "pr_verified",
            PointLedgerEntry.source_id == source_key,
        )
        .first()
    )
    if existing:
        return existing

    user = db.query(User).filter(User.id == pr.user_id).first()
    if not user:
        return None

    branch_id = user.branch_id or "narsobawadi"
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    org_id = branch.organization_id if branch else "rvf-org-main"
    event_date = pr.achieved_date or date.today()

    entry = PointLedgerEntry(
        id=str(uuid.uuid4()),
        user_id=user.id,
        organization_id=org_id,
        branch_id=branch_id,
        source_type="pr_verified",
        source_id=source_key,
        points=POINTS_COACH_VERIFIED_PR,
        event_date=event_date,
        year=event_date.year,
        month=event_date.month,
        notes=f"Coach-verified personal record: {pr.exercise_name} ({pr.value})",
        created_by=actor_id or getattr(pr, "verified_by_user_id", None) or user.id,
    )
    db.add(entry)
    db.flush()
    return entry


def reverse_attendance_points(
    db: Session, attendance_record_id: str, actor_id: Optional[str], reason: str
) -> Optional[PointLedgerEntry]:
    """
    Compensating reversal transaction for invalidated attendance.
    Preserves audit history by adding a negative ledger entry rather than deleting rows.
    """
    reversal_key = f"rev:{attendance_record_id}"
    existing_reversal = (
        db.query(PointLedgerEntry)
        .filter(
            PointLedgerEntry.source_type == "attendance_reversal",
            PointLedgerEntry.source_id == reversal_key,
        )
        .first()
    )
    if existing_reversal:
        return existing_reversal

    original_entry = (
        db.query(PointLedgerEntry)
        .filter(
            PointLedgerEntry.source_type == "attendance_verified",
            PointLedgerEntry.source_id == attendance_record_id,
        )
        .first()
    )
    if not original_entry:
        return None

    reversal_entry = PointLedgerEntry(
        id=str(uuid.uuid4()),
        user_id=original_entry.user_id,
        organization_id=original_entry.organization_id,
        branch_id=original_entry.branch_id,
        source_type="attendance_reversal",
        source_id=reversal_key,
        points=-original_entry.points,
        event_date=date.today(),
        year=original_entry.year,
        month=original_entry.month,
        notes=f"Attendance reversal: {reason}",
        created_by=actor_id,
    )
    db.add(reversal_entry)

    # Record in audit log
    audit = AuditLog(
        actor_id=actor_id,
        action="leaderboard.points_reversed",
        resource_type="attendance_record",
        resource_id=attendance_record_id,
        details={
            "reversedPoints": -original_entry.points,
            "reason": reason,
            "userId": original_entry.user_id,
        },
    )
    db.add(audit)
    db.flush()
    return reversal_entry


def award_workout_completion_points(
    db: Session, session: Any, actor_id: Optional[str] = None
) -> Optional[PointLedgerEntry]:
    """
    Award points for a completed workout session.
    Enforces idempotency and a strict daily cap of 1 workout completion award per member per calendar date.
    Never awards points for in-progress or abandoned sessions.
    """
    if getattr(session, "status", None) != "completed":
        return None

    user_id = getattr(session, "member_id", None)
    if not user_id:
        return None

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        return None

    # Idempotency check for this specific session
    existing_entry = (
        db.query(PointLedgerEntry)
        .filter(
            PointLedgerEntry.source_type == "workout_completed",
            PointLedgerEntry.source_id == session.id,
        )
        .first()
    )
    if existing_entry:
        return existing_entry

    # Strict daily cap: at most 1 workout completion award per member per calendar date
    event_date = getattr(session, "session_date", None) or date.today()
    daily_existing = (
        db.query(PointLedgerEntry)
        .filter(
            PointLedgerEntry.user_id == user.id,
            PointLedgerEntry.source_type == "workout_completed",
            PointLedgerEntry.event_date == event_date,
        )
        .first()
    )
    if daily_existing:
        return daily_existing

    branch_id = getattr(session, "branch_id", None) or user.branch_id or "narsobawadi"
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    org_id = branch.organization_id if branch else "rvf-org-main"

    entry = PointLedgerEntry(
        id=str(uuid.uuid4()),
        user_id=user.id,
        organization_id=org_id,
        branch_id=branch_id,
        source_type="workout_completed",
        source_id=session.id,
        points=POINTS_WORKOUT_COMPLETED,
        event_date=event_date,
        year=event_date.year,
        month=event_date.month,
        notes=f"Completed workout session ({getattr(session, 'session_name', None) or 'Custom Workout'})",
        created_by=actor_id or user.id,
    )
    db.add(entry)
    db.flush()
    return entry


def reverse_workout_points(
    db: Session, session_id: str, actor_id: Optional[str], reason: str
) -> Optional[PointLedgerEntry]:
    """
    Compensating reversal transaction for invalidated or abandoned workout completion.
    Preserves audit history by adding a negative ledger entry rather than deleting rows.
    """
    reversal_key = f"rev:workout:{session_id}"
    existing_reversal = (
        db.query(PointLedgerEntry)
        .filter(
            PointLedgerEntry.source_type == "workout_reversal",
            PointLedgerEntry.source_id == reversal_key,
        )
        .first()
    )
    if existing_reversal:
        return existing_reversal

    original_entry = (
        db.query(PointLedgerEntry)
        .filter(
            PointLedgerEntry.source_type == "workout_completed",
            PointLedgerEntry.source_id == session_id,
        )
        .first()
    )
    if not original_entry:
        return None

    reversal_entry = PointLedgerEntry(
        id=str(uuid.uuid4()),
        user_id=original_entry.user_id,
        organization_id=original_entry.organization_id,
        branch_id=original_entry.branch_id,
        source_type="workout_reversal",
        source_id=reversal_key,
        points=-original_entry.points,
        event_date=date.today(),
        year=original_entry.year,
        month=original_entry.month,
        notes=f"Workout points reversal: {reason}",
        created_by=actor_id,
    )
    db.add(reversal_entry)

    # Record in audit log
    audit = AuditLog(
        actor_id=actor_id,
        action="leaderboard.workout_points_reversed",
        resource_type="workout_session",
        resource_id=session_id,
        details={
            "reversedPoints": -original_entry.points,
            "reason": reason,
            "userId": original_entry.user_id,
        },
    )
    db.add(audit)
    db.flush()
    return reversal_entry


def record_admin_point_adjustment(
    db: Session,
    actor: User,
    target_user_id: str,
    points: int,
    reason: str,
    branch_id: Optional[str] = None,
) -> PointLedgerEntry:
    """
    Authorized administrative point adjustment.
    Enforces strict role-based access control and mandatory audit logging.
    """
    if actor.role not in ["org_admin", "admin", "branch_manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required to adjust member points.",
        )

    target_user = db.query(User).filter(User.id == target_user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target member does not exist.",
        )

    # Branch managers can only adjust points for members within their branch
    if actor.role == "branch_manager":
        if target_user.branch_id != actor.branch_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Branch managers can only adjust points for members in their assigned branch.",
            )

    if not reason or not reason.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A documented reason is mandatory for administrative score adjustments.",
        )

    target_branch_id = branch_id or target_user.branch_id or "narsobawadi"
    branch = db.query(Branch).filter(Branch.id == target_branch_id).first()
    org_id = branch.organization_id if branch else "rvf-org-main"
    today = date.today()

    adj_id = str(uuid.uuid4())
    entry = PointLedgerEntry(
        id=adj_id,
        user_id=target_user.id,
        organization_id=org_id,
        branch_id=target_branch_id,
        source_type="admin_adjustment",
        source_id=f"adj:{adj_id}",
        points=points,
        event_date=today,
        year=today.year,
        month=today.month,
        notes=reason.strip(),
        created_by=actor.id,
    )
    db.add(entry)

    # Append to durable audit log
    audit = AuditLog(
        actor_id=actor.id,
        action="leaderboard.admin_adjustment",
        resource_type="user",
        resource_id=target_user.id,
        details={
            "points": points,
            "reason": reason.strip(),
            "targetBranchId": target_branch_id,
            "ledgerEntryId": adj_id,
        },
    )
    db.add(audit)
    db.commit()
    db.refresh(entry)
    return entry


def get_monthly_leaderboard(
    db: Session,
    year: int,
    month: int,
    branch_id: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
) -> Tuple[List[LeaderboardEntry], int]:
    """
    Calculate privacy-safe monthly leaderboard standings with deterministic tie-breaking.
    Excludes opted-out members from public rankings.
    Tie-breaking:
    1. Total points (DESC)
    2. Distinct attendance days (DESC)
    3. Earliest point entry timestamp (ASC)
    4. User ID (ASC)
    """
    offset = max(0, (page - 1) * limit)

    # Base query for points and distinct days aggregated by user
    query_filters = [
        PointLedgerEntry.year == year,
        PointLedgerEntry.month == month,
        User.is_active == True,
        User.is_leaderboard_visible == True,  # Privacy filter: exclude opted-out members
    ]

    if branch_id and branch_id.lower() != "all":
        query_filters.append(PointLedgerEntry.branch_id == branch_id)

    # Aggregated query with tie-breaker columns
    ranked_query = (
        db.query(
            User.id.label("user_id"),
            User.leaderboard_alias.label("alias"),
            User.streak_days.label("streak_days"),
            User.branch_id.label("user_branch_id"),
            Branch.name.label("branch_name"),
            func.sum(PointLedgerEntry.points).label("total_points"),
            func.count(func.distinct(PointLedgerEntry.event_date)).label("distinct_days"),
            func.min(PointLedgerEntry.created_at).label("first_entry_time"),
        )
        .join(User, PointLedgerEntry.user_id == User.id)
        .outerjoin(Branch, User.branch_id == Branch.id)
        .filter(and_(*query_filters))
        .group_by(User.id, User.leaderboard_alias, User.streak_days, User.branch_id, Branch.name)
        .having(func.sum(PointLedgerEntry.points) > 0)
        .order_by(
            desc("total_points"),
            desc("distinct_days"),
            asc("first_entry_time"),
            asc(User.id),
        )
    )

    all_rows = ranked_query.all()
    total_count = len(all_rows)

    # Paginate
    paged_rows = all_rows[offset : offset + limit]

    entries: List[LeaderboardEntry] = []
    for idx, row in enumerate(paged_rows, start=offset + 1):
        alias = row.alias or f"Athlete_{row.user_id.replace('-', '')[-4:]}"
        points = int(row.total_points or 0)
        distinct_days = int(row.distinct_days or 0)

        # Tier assignment based on rank
        tier = "Gold" if idx <= 3 else ("Silver" if idx <= 10 else "Bronze")

        entries.append(
            LeaderboardEntry(
                rank=idx,
                name=alias,
                alias=alias,
                category="Points",
                score=f"{points} pts",
                points=points,
                distinctDays=distinct_days,
                streak=row.streak_days or 0,
                visitsThisMonth=distinct_days,
                tier=tier,
                branchName=row.branch_name or "RVFitness Campus",
            )
        )

    return entries, total_count


def get_member_self_standing(
    db: Session, user: User, year: int, month: int
) -> MemberSelfStandingResponse:
    """
    Return member's personal score, progress, and rank.
    Calculates member's rank even when their public visibility is disabled.
    """
    branch_id = user.branch_id or "narsobawadi"
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    branch_name = branch.name if branch else "RVFitness Campus"
    alias = get_default_alias_for_user(user)

    # Member's own points and distinct days
    user_totals = (
        db.query(
            func.sum(PointLedgerEntry.points).label("total_points"),
            func.count(func.distinct(PointLedgerEntry.event_date)).label("distinct_days"),
            func.min(PointLedgerEntry.created_at).label("first_entry_time"),
        )
        .filter(
            PointLedgerEntry.user_id == user.id,
            PointLedgerEntry.year == year,
            PointLedgerEntry.month == month,
        )
        .first()
    )

    my_points = int(user_totals.total_points or 0) if user_totals else 0
    my_distinct_days = int(user_totals.distinct_days or 0) if user_totals else 0
    my_first_time = user_totals.first_entry_time if user_totals else datetime.now(timezone.utc)

    # Determine rank among all members in member's branch
    all_branch_members = (
        db.query(
            PointLedgerEntry.user_id,
            func.sum(PointLedgerEntry.points).label("total_points"),
            func.count(func.distinct(PointLedgerEntry.event_date)).label("distinct_days"),
            func.min(PointLedgerEntry.created_at).label("first_entry_time"),
        )
        .filter(
            PointLedgerEntry.branch_id == branch_id,
            PointLedgerEntry.year == year,
            PointLedgerEntry.month == month,
        )
        .group_by(PointLedgerEntry.user_id)
        .having(func.sum(PointLedgerEntry.points) > 0)
        .order_by(
            desc("total_points"),
            desc("distinct_days"),
            asc("first_entry_time"),
            asc(PointLedgerEntry.user_id),
        )
        .all()
    )

    my_rank = None
    total_members = len(all_branch_members)

    for rank_idx, row in enumerate(all_branch_members, start=1):
        if row.user_id == user.id:
            my_rank = rank_idx
            break

    tier = "Bronze"
    if my_rank:
        tier = "Gold" if my_rank <= 3 else ("Silver" if my_rank <= 10 else "Bronze")

    return MemberSelfStandingResponse(
        rank=my_rank,
        totalMembers=total_members,
        points=my_points,
        distinctDays=my_distinct_days,
        streakDays=user.streak_days or 0,
        alias=alias,
        isLeaderboardVisible=user.is_leaderboard_visible,
        branchId=branch_id,
        branchName=branch_name,
        month=month,
        year=year,
        tier=tier,
    )


def update_member_preferences(
    db: Session,
    user: User,
    alias: Optional[str] = None,
    is_visible: Optional[bool] = None,
) -> User:
    """
    Update member's gaming alias and public leaderboard visibility.
    Validates alias format and case-insensitive uniqueness across members.
    """
    if alias is not None:
        clean_alias = alias.strip()
        if len(clean_alias) < 3 or len(clean_alias) > 30:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Alias must be between 3 and 30 characters in length.",
            )
        if not re.match(r"^[A-Za-z0-9_-]+$", clean_alias):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Alias may only contain alphanumeric characters, underscores, and hyphens.",
            )

        # Case-insensitive uniqueness check against other members
        existing = (
            db.query(User)
            .filter(
                func.lower(User.leaderboard_alias) == clean_alias.lower(),
                User.id != user.id,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This gaming alias is already claimed. Please select a different handle.",
            )
        user.leaderboard_alias = clean_alias

    if is_visible is not None:
        user.is_leaderboard_visible = is_visible

    db.commit()
    db.refresh(user)
    return user


def get_scoring_rules() -> ScoringRulesResponse:
    """Return transparent scoring rules and anti-abuse safeguards for member inspection."""
    rules = [
        ScoringRuleItem(
            activity="Verified Floor Check-In",
            points=POINTS_ATTENDANCE_VERIFIED,
            description="Awarded for verified gym entrance via desk RFID scan, entry QR token, or staff manual check-in.",
            frequencyLimit="Maximum 1 award per calendar date.",
        ),
        ScoringRuleItem(
            activity="Coach-Verified Personal Record (PR)",
            points=POINTS_COACH_VERIFIED_PR,
            description="Awarded when certified RVFitness strength coach verifies a benchmark lift or fitness achievement.",
            frequencyLimit="Per verified milestone submission.",
        ),
        ScoringRuleItem(
            activity="7-Day Discipline Streak Milestone",
            points=POINTS_STREAK_MILESTONE,
            description="Bonus awarded upon reaching every 7 consecutive days of consistent training discipline.",
            frequencyLimit="Awarded at each 7-day milestone (7, 14, 21, 28... days).",
        ),
        ScoringRuleItem(
            activity="Completed Workout Session",
            points=POINTS_WORKOUT_COMPLETED,
            description="Awarded upon recording a completed workout session from an assigned training plan.",
            frequencyLimit="Maximum 1 award per calendar date.",
        ),
        ScoringRuleItem(
            activity="Administrative Adjustment",
            points=0,
            description="Authorized adjustments by gym management with required justification and permanent audit record.",
            frequencyLimit="As determined by audit governance.",
        ),
    ]

    anti_abuse = (
        "Anti-abuse policy: Points are only awarded for successful, verified attendance records. "
        "Failed check-in attempts, QR scans without entrance, rejected attempts, and duplicate scans "
        "earn zero points. A strict daily cap prevents artificial point inflation. All manual score "
        "adjustments require authorized staff credentials, explicit justification, and immutable audit logs."
    )

    return ScoringRulesResponse(rules=rules, antiAbusePolicy=anti_abuse)
