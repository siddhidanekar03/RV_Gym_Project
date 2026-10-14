from datetime import date, datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from backend.app.core.database import get_db
from backend.app.core.auth import get_current_user, require_csrf
from backend.app.models.user import User
from backend.app.models.attendance import AttendanceRecord
from backend.app.models.audit import AuditLog
from backend.app.services.membership_service import is_member_eligible_for_branch
from backend.app.schemas.attendance import CheckInResponse

router = APIRouter()


@router.post(
    "/attendance/check-in",
    response_model=CheckInResponse,
    dependencies=[Depends(require_csrf)],
    summary="Daily Member Floor Check-In",
)
def check_in(
    branch_id: Optional[str] = Query(None, description="Branch facility ID where check-in occurs"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CheckInResponse:
    today = date.today()
    target_branch_id = branch_id or user.branch_id or "narsobawadi"

    # 1. Eligibility Check: Status
    if user.role == "member":
        if user.membership_status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Check-in denied. Your membership status is currently '{user.membership_status}'. Active membership is required to access the gym floor.",
            )

        # 2. Eligibility Check: Expiration Date
        if user.valid_until and user.valid_until < today:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Check-in denied. Your membership expired on {user.valid_until.strftime('%B %d, %Y')}. Please visit the reception desk to renew.",
            )

        # 3. Cross-branch access eligibility
        if not is_member_eligible_for_branch(db, user, target_branch_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Check-in denied. Your membership does not grant access to branch facility '{target_branch_id}'.",
            )

    # 4. Check for existing check-in today
    existing = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.user_id == user.id,
            AttendanceRecord.check_in_date == today,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already checked in for today! Great dedication.",
        )

    # 5. Insert Attendance Record with Safe Concurrency Handling
    record = AttendanceRecord(
        user_id=user.id,
        branch_id=target_branch_id,
        check_in_date=today,
        method="portal",
        notes=f"Daily floor check-in at branch {target_branch_id}",
    )
    db.add(record)

    try:
        # Atomic flush to verify unique constraint at DB level
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already checked in for today! Great dedication.",
        )

    # 6. Streak Increment only after verified insert
    user.streak_days += 1

    # 7. Audit Trail
    audit = AuditLog(
        actor_id=user.id,
        action="attendance.checkin",
        resource_type="attendance_record",
        resource_id=record.id,
        details={
            "date": today.isoformat(),
            "branch_id": target_branch_id,
            "new_streak": user.streak_days,
        },
    )
    db.add(audit)
    db.commit()

    # Calculate month total
    first_of_month = date(today.year, today.month, 1)
    month_count = (
        db.query(func.count(AttendanceRecord.id))
        .filter(
            AttendanceRecord.user_id == user.id,
            AttendanceRecord.check_in_date >= first_of_month,
        )
        .scalar()
        or 1
    )

    checked_time_str = datetime.now().strftime("%I:%M %p")

    return CheckInResponse(
        success=True,
        message=f"Check-in recorded! Welcome to the gym today, {user.name}. Streak is now {user.streak_days} days!",
        streakDays=user.streak_days,
        attendanceThisMonth=month_count,
        checkedInAt=checked_time_str,
    )
