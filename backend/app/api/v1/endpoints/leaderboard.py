from datetime import date, datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc

from backend.app.core.database import get_db
from backend.app.core.auth import (
    get_current_user,
    require_roles,
    require_csrf,
)
from backend.app.models.user import User
from backend.app.models.personal_record import PersonalRecord
from backend.app.models.attendance import AttendanceRecord
from backend.app.models.leaderboard import PointLedgerEntry
from backend.app.schemas.leaderboard import (
    LeaderboardResponse,
    LeaderboardEntry,
    MemberSelfStandingResponse,
    MemberPreferencesResponse,
    MemberPreferencesUpdate,
    PointLedgerItem,
    PointLedgerHistoryResponse,
    AdminPointAdjustmentRequest,
    AdminPointAdjustmentResponse,
    ScoringRulesResponse,
)
from backend.app.services.leaderboard_service import (
    get_monthly_leaderboard,
    get_member_self_standing,
    update_member_preferences,
    record_admin_point_adjustment,
    get_scoring_rules,
    get_default_alias_for_user,
)

router = APIRouter()


def mask_display_name(full_name: str) -> str:
    """Mask member surname to protect PII in public standings (e.g. 'Prathamesh Patil' -> 'Prathamesh P.')."""
    parts = full_name.strip().split()
    if len(parts) <= 1:
        return full_name
    return f"{parts[0]} {parts[1][0]}."


@router.get("/leaderboard", response_model=LeaderboardResponse, summary="Public Verified Standings")
def get_leaderboard(
    category: Optional[str] = Query(None, description="Category filter (e.g. 'Power Total', 'Points', or 'all')"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Target calendar month (1-12)"),
    year: Optional[int] = Query(None, ge=2020, le=2050, description="Target calendar year (e.g. 2026)"),
    branch_id: Optional[str] = Query(None, description="Branch filter (e.g. 'narsobawadi' or 'all')"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=100, description="Page size limit"),
    db: Session = Depends(get_db),
) -> LeaderboardResponse:
    """
    Retrieve public privacy-first leaderboard standings.
    Supports monthly points gamification, branch isolation, and legacy coach-verified PR totals.
    Opted-out members are strictly excluded from public rankings.
    """
    now_utc = datetime.now(timezone.utc)
    cur_year = year or now_utc.year
    cur_month = month or now_utc.month

    # Check whether caller explicitly requested legacy Power Total
    is_power_total_requested = category and category.lower() in ["power total", "powertotal"]

    # If Power Total requested, or if no point ledger entries exist and PR records exist with no explicit month/year filter, run legacy PR aggregator
    has_ledger_entries = db.query(PointLedgerEntry.id).filter(
        PointLedgerEntry.year == cur_year,
        PointLedgerEntry.month == cur_month,
    ).first() is not None

    if is_power_total_requested or (not has_ledger_entries and not month and not year and not branch_id):
        # 1. Query members with coach-verified PRs
        verified_prs = (
            db.query(
                PersonalRecord.user_id,
                PersonalRecord.exercise_name,
                func.max(PersonalRecord.value).label("max_val"),
            )
            .filter(PersonalRecord.is_coach_verified == True)
            .group_by(PersonalRecord.user_id, PersonalRecord.exercise_name)
            .all()
        )

        # Aggregate Power Total (Bench + Squat + Deadlift)
        user_totals = {}
        for user_id, exercise, max_val in verified_prs:
            if user_id not in user_totals:
                user_totals[user_id] = {"bench": 0, "squat": 0, "deadlift": 0}
            clean_ex = exercise.lower().replace("-", "_").replace(" ", "_")
            if "bench" in clean_ex:
                user_totals[user_id]["bench"] = float(max_val)
            elif "squat" in clean_ex:
                user_totals[user_id]["squat"] = float(max_val)
            elif "deadlift" in clean_ex:
                user_totals[user_id]["deadlift"] = float(max_val)

        # Compute total score and rank
        legacy_entries: List[LeaderboardEntry] = []
        candidates = []

        for user_id, lifts in user_totals.items():
            total = lifts["bench"] + lifts["squat"] + lifts["deadlift"]
            if total > 0:
                candidates.append((user_id, total))

        # Sort descending by total score
        candidates.sort(key=lambda x: x[1], reverse=True)

        first_of_month = date(cur_year, cur_month, 1)

        for rank_idx, (user_id, total_score) in enumerate(candidates, start=1):
            user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
            if not user:
                continue

            # Respect member opt-out for public standings
            if not user.is_leaderboard_visible:
                continue

            monthly_visits = (
                db.query(func.count(AttendanceRecord.id))
                .filter(
                    AttendanceRecord.user_id == user.id,
                    AttendanceRecord.check_in_date >= first_of_month,
                )
                .scalar()
                or 0
            )

            # Surname masked or gaming alias
            display_name = user.leaderboard_alias or mask_display_name(user.name)

            legacy_entries.append(
                LeaderboardEntry(
                    rank=rank_idx,
                    name=display_name,
                    alias=user.leaderboard_alias,
                    category="Power Total",
                    score=f"{int(total_score)} kg",
                    points=int(total_score),
                    streak=user.streak_days,
                    visitsThisMonth=monthly_visits,
                    tier="Gold" if rank_idx <= 3 else ("Silver" if rank_idx <= 10 else "Bronze"),
                    branchName=user.branch_id,
                )
            )

        if category and category.lower() != "all":
            legacy_entries = [e for e in legacy_entries if e.category.lower() == category.lower()]

        # If Power Total had results or was explicitly requested, return it
        if legacy_entries or is_power_total_requested:
            return LeaderboardResponse(
                leaderboard=legacy_entries,
                updatedAt=now_utc.isoformat(),
                total=len(legacy_entries),
                page=page,
                limit=limit,
                month=cur_month,
                year=cur_year,
                branchId=branch_id,
                scope="branch" if branch_id and branch_id != "all" else "organization",
            )

    # 2. Monthly Gamification Points Leaderboard (Phase 7 Core)
    entries, total_count = get_monthly_leaderboard(
        db=db,
        year=cur_year,
        month=cur_month,
        branch_id=branch_id,
        page=page,
        limit=limit,
    )

    scope_str = "branch" if branch_id and branch_id.lower() != "all" else "organization"
    return LeaderboardResponse(
        leaderboard=entries,
        updatedAt=now_utc.isoformat(),
        total=total_count,
        page=page,
        limit=limit,
        month=cur_month,
        year=cur_year,
        branchId=branch_id,
        scope=scope_str,
    )


@router.get("/leaderboard/me", response_model=MemberSelfStandingResponse, summary="Member Own Leaderboard Rank")
def get_my_standing(
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2020, le=2050),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MemberSelfStandingResponse:
    """
    Retrieve authenticated member's personal score, progress, and rank.
    Members can inspect their score even when opted out of public rankings.
    """
    now_utc = datetime.now(timezone.utc)
    target_year = year or now_utc.year
    target_month = month or now_utc.month

    return get_member_self_standing(
        db=db,
        user=current_user,
        year=target_year,
        month=target_month,
    )


@router.put("/leaderboard/preferences", response_model=MemberPreferencesResponse, summary="Update Privacy & Alias")
def update_preferences(
    req: MemberPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> MemberPreferencesResponse:
    """
    Update authenticated member's gaming alias and public leaderboard visibility.
    Members may change only their own preferences.
    """
    updated_user = update_member_preferences(
        db=db,
        user=current_user,
        alias=req.alias,
        is_visible=req.isLeaderboardVisible,
    )

    alias = get_default_alias_for_user(updated_user)
    return MemberPreferencesResponse(
        userId=updated_user.id,
        alias=alias,
        isLeaderboardVisible=updated_user.is_leaderboard_visible,
        branchId=updated_user.branch_id or "narsobawadi",
    )


@router.get("/leaderboard/rules", response_model=ScoringRulesResponse, summary="Scoring Rules & Policy")
def get_rules() -> ScoringRulesResponse:
    """Return transparent scoring rules and anti-abuse safeguards for member inspection."""
    return get_scoring_rules()


@router.get("/leaderboard/history", response_model=PointLedgerHistoryResponse, summary="Member Point History")
def get_point_history(
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2020, le=2050),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PointLedgerHistoryResponse:
    """
    Retrieve authenticated member's points ledger history.
    """
    query = db.query(PointLedgerEntry).filter(PointLedgerEntry.user_id == current_user.id)
    if year:
        query = query.filter(PointLedgerEntry.year == year)
    if month:
        query = query.filter(PointLedgerEntry.month == month)

    rows = query.order_by(desc(PointLedgerEntry.event_date), desc(PointLedgerEntry.created_at)).all()

    items = [
        PointLedgerItem(
            id=r.id,
            sourceType=r.source_type,
            sourceId=r.source_id,
            points=r.points,
            eventDate=r.event_date,
            year=r.year,
            month=r.month,
            notes=r.notes,
            createdAt=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]
    total_pts = sum(r.points for r in rows)

    return PointLedgerHistoryResponse(
        entries=items,
        totalPoints=total_pts,
        month=month,
        year=year,
    )


@router.post("/leaderboard/adjust", response_model=AdminPointAdjustmentResponse, summary="Admin Point Adjustment")
def adjust_points(
    req: AdminPointAdjustmentRequest,
    current_user: User = Depends(get_current_user),
    csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> AdminPointAdjustmentResponse:
    """
    Perform an authorized administrative point adjustment.
    Requires branch manager or organization administrator credentials.
    Mandatory reason is logged to the immutable audit log.
    """
    entry = record_admin_point_adjustment(
        db=db,
        actor=current_user,
        target_user_id=req.userId,
        points=req.points,
        reason=req.reason,
        branch_id=req.branchId,
    )

    # Compute new monthly total for the target user
    now_utc = datetime.now(timezone.utc)
    new_total = (
        db.query(func.sum(PointLedgerEntry.points))
        .filter(
            PointLedgerEntry.user_id == req.userId,
            PointLedgerEntry.year == now_utc.year,
            PointLedgerEntry.month == now_utc.month,
        )
        .scalar()
        or 0
    )

    return AdminPointAdjustmentResponse(
        success=True,
        ledgerId=entry.id,
        userId=req.userId,
        pointsAdjusted=req.points,
        newMonthlyTotal=int(new_total),
        reason=req.reason,
    )
