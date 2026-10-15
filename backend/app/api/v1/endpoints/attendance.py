from datetime import date, datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from backend.app.core.database import get_db
from backend.app.core.auth import get_current_user, require_csrf, require_roles, verify_branch_access
from backend.app.core.rate_limit import rate_limit
from backend.app.models.user import User
from backend.app.models.attendance import AttendanceRecord, AttendanceAttempt
from backend.app.models.audit import AuditLog
from backend.app.services.attendance_service import (
    get_branch_local_date,
    resolve_member_identity,
    check_attendance_eligibility,
    generate_member_qr_token,
    process_qr_checkin,
    process_manual_checkin,
    process_manager_override,
    process_paper_backfill,
    lookup_members_for_desk,
    generate_branch_monthly_report,
    generate_member_monthly_report,
    export_branch_report_csv,
    export_branch_report_pdf,
    reconcile_member_identity_on_account_link,
)
from backend.app.schemas.attendance import (
    CheckInResponse,
    QRTokenResponse,
    QRCheckInRequest,
    ManualCheckInRequest,
    ManagerOverrideRequest,
    PaperBackfillRequest,
    MemberLookupResponse,
    MemberLookupItem,
    MonthlyAttendanceReportResponse,
    MemberMonthlyReportResponse,
)

router = APIRouter()


@router.post(
    "/attendance/check-in",
    response_model=CheckInResponse,
    dependencies=[Depends(require_csrf)],
    summary="Daily Member Floor Check-In (Portal)",
)
def check_in(
    branch_id: Optional[str] = Query(None, description="Branch facility ID where check-in occurs"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CheckInResponse:
    target_branch_id = branch_id or user.branch_id or "narsobawadi"
    branch_today = get_branch_local_date(target_branch_id)
    member_id_str = resolve_member_identity(
        user_id=user.id, membership_id=user.membership_id, member_phone=user.phone
    )

    # 1. Shared Eligibility Check
    if user.role == "member":
        eligible, reason_code, message = check_attendance_eligibility(
            db=db, user=user, branch_id=target_branch_id
        )
        if not eligible:
            attempt = AttendanceAttempt(
                member_identity=member_id_str,
                user_id=user.id,
                membership_id=user.membership_id,
                member_phone=user.phone,
                member_name=user.name,
                branch_id=target_branch_id,
                source="portal",
                failure_reason=reason_code,
                failure_detail=message,
            )
            db.add(attempt)
            db.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)

    # 2. Check for existing check-in today
    existing = (
        db.query(AttendanceRecord)
        .filter(
            or_(
                AttendanceRecord.member_identity == member_id_str,
                AttendanceRecord.user_id == user.id,
            ),
            AttendanceRecord.branch_id == target_branch_id,
            AttendanceRecord.check_in_date == branch_today,
        )
        .first()
    )
    if existing:
        attempt = AttendanceAttempt(
            member_identity=member_id_str,
            user_id=user.id,
            membership_id=user.membership_id,
            member_phone=user.phone,
            member_name=user.name,
            branch_id=target_branch_id,
            source="portal",
            failure_reason="already_checked_in",
            failure_detail="Duplicate portal check-in attempt on same date.",
        )
        db.add(attempt)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already checked in for today! Great dedication.",
        )

    # 3. Insert Attendance Record
    record = AttendanceRecord(
        member_identity=member_id_str,
        user_id=user.id,
        branch_id=target_branch_id,
        check_in_date=branch_today,
        source="portal",
        method="portal",
        member_name=user.name,
        member_phone=user.phone,
        membership_id=user.membership_id,
        notes=f"Daily floor check-in at branch {target_branch_id}",
    )
    db.add(record)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        attempt = AttendanceAttempt(
            member_identity=member_id_str,
            user_id=user.id,
            membership_id=user.membership_id,
            member_phone=user.phone,
            member_name=user.name,
            branch_id=target_branch_id,
            source="portal",
            failure_reason="already_checked_in",
            failure_detail="Duplicate check-in blocked by database uniqueness constraint.",
        )
        db.add(attempt)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already checked in for today! Great dedication.",
        )

    # 4. Streak Increment
    user.streak_days += 1

    # 5. Audit Trail
    audit = AuditLog(
        actor_id=user.id,
        action="attendance.checkin",
        resource_type="attendance_record",
        resource_id=record.id,
        details={
            "date": branch_today.isoformat(),
            "branch_id": target_branch_id,
            "new_streak": user.streak_days,
            "source": "portal",
        },
    )
    db.add(audit)
    db.commit()

    # Calculate month total
    first_of_month = date(branch_today.year, branch_today.month, 1)
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
        attendanceId=record.id,
        source="portal",
    )


@router.get(
    "/attendance/qr-token",
    response_model=QRTokenResponse,
    dependencies=[Depends(rate_limit(max_requests=60, window_seconds=60))],
    summary="Generate Dynamic Short-Lived QR Entry Token for Member",
)
def get_qr_token(user: User = Depends(get_current_user)) -> QRTokenResponse:
    token, expires_at, seconds_valid = generate_member_qr_token(user)
    return QRTokenResponse(
        qrToken=token,
        expiresAt=expires_at.isoformat(),
        secondsValid=seconds_valid,
    )


@router.post(
    "/attendance/qr-check-in",
    response_model=CheckInResponse,
    dependencies=[Depends(require_csrf), Depends(rate_limit(max_requests=60, window_seconds=60))],
    summary="Scan & Consume QR Code for Floor Check-In",
)
def scan_qr_checkin(
    payload: QRCheckInRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CheckInResponse:
    # Acting operator: if desk staff is scanning, record staff; if turnstile/kiosk member self-scans, record member
    staff = current_user if current_user.role != "member" else None
    try:
        record = process_qr_checkin(
            db=db,
            qr_token=payload.qrToken,
            branch_id=payload.branchId,
            staff=staff,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    branch_today = get_branch_local_date(payload.branchId)
    first_of_month = date(branch_today.year, branch_today.month, 1)
    month_count = (
        db.query(func.count(AttendanceRecord.id))
        .filter(
            AttendanceRecord.user_id == record.user_id,
            AttendanceRecord.check_in_date >= first_of_month,
        )
        .scalar()
        or 1
    )

    checked_time_str = record.check_in_time.strftime("%I:%M %p")
    member_name = record.user.name if record.user else (record.member_name or "Member")
    streak = record.user.streak_days if record.user else 1

    return CheckInResponse(
        success=True,
        message=f"QR check-in verified! Welcome to the gym, {member_name}.",
        streakDays=streak,
        attendanceThisMonth=month_count,
        checkedInAt=checked_time_str,
        attendanceId=record.id,
        source="qr",
    )


@router.post(
    "/attendance/manual-check-in",
    response_model=CheckInResponse,
    dependencies=[
        Depends(require_csrf),
        Depends(require_roles("org_admin", "admin", "branch_manager", "manager", "front_desk", "staff")),
    ],
    summary="Desk Staff Assisted Manual Check-In with Mandatory Reason Code",
)
def manual_checkin(
    payload: ManualCheckInRequest,
    staff: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CheckInResponse:
    verify_branch_access(staff, payload.branchId)
    try:
        record = process_manual_checkin(
            db=db,
            branch_id=payload.branchId,
            staff=staff,
            reason_code=payload.reasonCode,
            member_id=payload.memberId,
            phone=payload.phone,
            name=payload.name,
            notes=payload.notes,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    branch_today = get_branch_local_date(payload.branchId)
    first_of_month = date(branch_today.year, branch_today.month, 1)
    month_count = 1
    if record.user_id:
        month_count = (
            db.query(func.count(AttendanceRecord.id))
            .filter(
                AttendanceRecord.user_id == record.user_id,
                AttendanceRecord.check_in_date >= first_of_month,
            )
            .scalar()
            or 1
        )

    checked_time_str = record.check_in_time.strftime("%I:%M %p")
    member_name = record.user.name if record.user else (record.member_name or "Member")
    streak = record.user.streak_days if record.user else 1

    return CheckInResponse(
        success=True,
        message=f"Manual check-in recorded for {member_name} (Reason: {payload.reasonCode}).",
        streakDays=streak,
        attendanceThisMonth=month_count,
        checkedInAt=checked_time_str,
        attendanceId=record.id,
        source="manual",
    )


@router.post(
    "/attendance/override",
    response_model=CheckInResponse,
    dependencies=[
        Depends(require_csrf),
        Depends(require_roles("org_admin", "admin", "branch_manager", "manager")),
    ],
    summary="Manager-Only Override for Rejected Check-In Attempt",
)
@router.post(
    "/attendance/manager-override",
    response_model=CheckInResponse,
    dependencies=[
        Depends(require_csrf),
        Depends(require_roles("org_admin", "admin", "branch_manager", "manager")),
    ],
    summary="Manager-Only Override for Rejected Check-In Attempt (Alias)",
)
def manager_override(
    payload: ManagerOverrideRequest,
    manager: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CheckInResponse:
    try:
        attempt_id = payload.get_attempt_id()
        reason = payload.get_reason()
        record = process_manager_override(
            db=db,
            attempt_id=attempt_id,
            manager=manager,
            reason=reason,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    checked_time_str = record.check_in_time.strftime("%I:%M %p")
    member_name = record.user.name if record.user else (record.member_name or "Member")
    streak = record.user.streak_days if record.user else 1

    return CheckInResponse(
        success=True,
        message=f"Manager override approved for {member_name}. Attendance recorded.",
        streakDays=streak,
        attendanceThisMonth=1,
        checkedInAt=checked_time_str,
        attendanceId=record.id,
        source="override",
    )


@router.post(
    "/attendance/backfill",
    response_model=CheckInResponse,
    dependencies=[
        Depends(require_csrf),
        Depends(require_roles("org_admin", "admin", "branch_manager", "manager", "front_desk", "staff")),
    ],
    summary="Controlled Paper-Log Backfill for Facility Outages",
)
def paper_backfill(
    payload: PaperBackfillRequest,
    operator: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CheckInResponse:
    try:
        record = process_paper_backfill(
            db=db,
            branch_id=payload.branchId,
            operator=operator,
            visit_date=payload.visitDate,
            entry_operator=payload.entryOperator,
            reason=payload.reason,
            member_id=payload.memberId,
            phone=payload.phone,
            name=payload.name,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    member_name = record.user.name if record.user else (record.member_name or "Member")

    return CheckInResponse(
        success=True,
        message=f"Paper log backfill recorded for {member_name} on {payload.visitDate.isoformat()}.",
        streakDays=record.user.streak_days if record.user else 0,
        attendanceThisMonth=1,
        checkedInAt=record.check_in_time.strftime("%I:%M %p"),
        attendanceId=record.id,
        source="backfill",
    )


@router.get(
    "/attendance/members/lookup",
    response_model=MemberLookupResponse,
    dependencies=[
        Depends(require_roles("org_admin", "admin", "branch_manager", "manager", "front_desk", "staff")),
    ],
    summary="Desk Search by Member Number or Phone with Privacy Masking",
)
def desk_member_lookup(
    query: str = Query(..., min_length=2, description="Member ID, phone, or name search"),
    branch_id: str = Query("narsobawadi", description="Target branch ID for eligibility check"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MemberLookupResponse:
    verify_branch_access(user, branch_id)
    results = lookup_members_for_desk(db=db, query=query, branch_id=branch_id)
    return MemberLookupResponse(members=[MemberLookupItem(**r) for r in results])


@router.get(
    "/attendance/reports/branch/{branch_id}",
    response_model=MonthlyAttendanceReportResponse,
    dependencies=[
        Depends(require_roles("org_admin", "admin", "branch_manager", "manager")),
    ],
    summary="Branch Monthly Attendance Report",
)
def get_branch_monthly_report(
    branch_id: str,
    year: int = Query(2026, ge=2020, le=2050),
    month: int = Query(10, ge=1, le=12),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MonthlyAttendanceReportResponse:
    verify_branch_access(user, branch_id)
    report_data = generate_branch_monthly_report(db=db, branch_id=branch_id, year=year, month=month)
    return MonthlyAttendanceReportResponse(**report_data)


@router.get(
    "/attendance/reports/member/{user_id}",
    response_model=MemberMonthlyReportResponse,
    summary="Member Personal Monthly Attendance History",
)
def get_member_monthly_report(
    user_id: str,
    year: int = Query(2026, ge=2020, le=2050),
    month: int = Query(10, ge=1, le=12),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MemberMonthlyReportResponse:
    # Role isolation: members can only view their own history
    if user.role == "member" and user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only view your own monthly attendance report.",
        )
    try:
        report_data = generate_member_monthly_report(db=db, user_id=user_id, year=year, month=month)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return MemberMonthlyReportResponse(**report_data)


@router.get(
    "/attendance/reports/branch/{branch_id}/export",
    dependencies=[
        Depends(require_roles("org_admin", "admin", "branch_manager", "manager")),
        Depends(rate_limit(max_requests=10, window_seconds=60)),
    ],
    summary="Export Branch Attendance Report (CSV or PDF)",
)
def export_branch_report(
    branch_id: str,
    year: int = Query(2026, ge=2020, le=2050),
    month: int = Query(10, ge=1, le=12),
    format: str = Query("csv", description="csv | pdf"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    verify_branch_access(user, branch_id)
    report_data = generate_branch_monthly_report(db=db, branch_id=branch_id, year=year, month=month)

    clean_format = format.strip().lower()
    if clean_format == "csv":
        csv_str = export_branch_report_csv(report_data)
        filename = f"RVFitness_Attendance_{branch_id}_{year}_{month:02d}.csv"
        return Response(
            content=csv_str,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    elif clean_format == "pdf":
        pdf_bytes = export_branch_report_pdf(report_data)
        filename = f"RVFitness_Attendance_{branch_id}_{year}_{month:02d}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Export format must be 'csv' or 'pdf'.")


@router.post(
    "/attendance/members/{user_id}/reconcile",
    dependencies=[
        Depends(require_csrf),
        Depends(require_roles("org_admin", "admin", "branch_manager", "manager", "front_desk", "staff")),
    ],
    summary="Reconcile Unlinked Offline Attendance Records upon Account Linking",
)
def reconcile_member_attendance(
    user_id: str,
    membership_id: Optional[str] = Query(None, description="Optional offline card ID override"),
    staff: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member account not found.")
    verify_branch_access(staff, target_user.branch_id)
    result = reconcile_member_identity_on_account_link(
        db=db,
        user=target_user,
        membership_id=membership_id,
        acting_operator=staff,
    )
    return {"success": True, "data": result}

