from datetime import date, datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.app.core.database import get_db
from backend.app.models.user import User
from backend.app.models.personal_record import PersonalRecord
from backend.app.models.attendance import AttendanceRecord
from backend.app.schemas.leaderboard import LeaderboardResponse, LeaderboardEntry

router = APIRouter()


def mask_display_name(full_name: str) -> str:
    """Mask member surname to protect PII in public standings (e.g. 'Prathamesh Patil' -> 'Prathamesh P.')."""
    parts = full_name.strip().split()
    if len(parts) <= 1:
        return full_name
    return f"{parts[0]} {parts[1][0]}."


@router.get("/leaderboard", response_model=LeaderboardResponse, summary="Public Verified Standings")
def get_leaderboard(
    category: Optional[str] = Query(None, description="Category filter (e.g. 'Power Total' or 'all')"),
    db: Session = Depends(get_db),
) -> LeaderboardResponse:
    today = date.today()
    first_of_month = date(today.year, today.month, 1)

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
    entries: List[LeaderboardEntry] = []
    candidates = []

    for user_id, lifts in user_totals.items():
        total = lifts["bench"] + lifts["squat"] + lifts["deadlift"]
        if total > 0:
            candidates.append((user_id, total))

    # Sort descending by total score
    candidates.sort(key=lambda x: x[1], reverse=True)

    for rank_idx, (user_id, total_score) in enumerate(candidates, start=1):
        user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
        if not user:
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

        entries.append(
            LeaderboardEntry(
                rank=rank_idx,
                name=mask_display_name(user.name),
                category="Power Total",
                score=f"{int(total_score)} kg",
                streak=user.streak_days,
                visitsThisMonth=monthly_visits,
            )
        )

    # Apply category filter if requested
    if category and category.lower() != "all":
        entries = [e for e in entries if e.category.lower() == category.lower()]

    now_iso = datetime.now(timezone.utc).isoformat()
    return LeaderboardResponse(leaderboard=entries, updatedAt=now_iso)
