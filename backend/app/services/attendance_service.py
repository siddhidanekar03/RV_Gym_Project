import csv
import io
import uuid
import calendar
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal
from typing import Optional, Tuple, Dict, Any, List

import jwt
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, distinct
from sqlalchemy.exc import IntegrityError

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from backend.app.core.config import settings
from backend.app.models.attendance import AttendanceRecord, AttendanceAttempt, ConsumedQRToken
from backend.app.models.user import User
from backend.app.models.organization import Branch
from backend.app.models.billing import Invoice
from backend.app.models.audit import AuditLog
from backend.app.services.membership_service import is_member_eligible_for_branch
from backend.app.core.auth import verify_branch_access

DEFAULT_TIMEZONE = ZoneInfo("Asia/Kolkata")


def get_branch_timezone(branch_id: str = "narsobawadi") -> ZoneInfo:
    """Return local timezone for the specified gym facility."""
    return DEFAULT_TIMEZONE


def get_branch_local_now(branch_id: str = "narsobawadi") -> datetime:
    """Return current timezone-aware timestamp in branch-local time."""
    tz = get_branch_timezone(branch_id)
    return datetime.now(timezone.utc).astimezone(tz)


def get_branch_local_date(branch_id: str = "narsobawadi") -> date:
    """Return today's calendar date in branch-local time."""
    return get_branch_local_now(branch_id).date()


def mask_phone(phone: Optional[str]) -> str:
    """Mask telephone number for privacy display (e.g. +91 ******1234)."""
    if not phone:
        return "No phone on file"
    clean = phone.strip()
    if len(clean) <= 4:
        return clean
    last_four = clean[-4:]
    prefix = clean[:3] if clean.startswith("+91") else ""
    return f"{prefix} ******{last_four}"


def resolve_member_identity(
    user_id: Optional[str] = None,
    membership_id: Optional[str] = None,
    member_phone: Optional[str] = None,
    member_name: Optional[str] = None,
) -> str:
    """
    Computes a canonical non-null member identity string for attendance uniqueness.
    Priority:
    1. Registered User ID: 'user:<id>' (immutable across phone changes)
    2. Membership Card ID: 'member:<id>' (stable for members without web portal accounts)
    3. Phone + Normalized Name: 'phone:<digits>:<norm_name>' (for walk-in guests sharing contact phones)
    4. Normalized Phone: 'phone:<digits>' (fallback walk-in guest)
    """
    if user_id and str(user_id).strip():
        return f"user:{str(user_id).strip()}"
    if membership_id and str(membership_id).strip():
        return f"member:{str(membership_id).strip().upper()}"
    if member_phone and str(member_phone).strip():
        digits = "".join(c for c in str(member_phone) if c.isdigit())
        phone_key = digits[-10:] if len(digits) >= 10 else (digits or str(member_phone).strip())
        if member_name and str(member_name).strip():
            norm_name = "_".join(str(member_name).strip().lower().split())
            return f"phone:{phone_key}:{norm_name}"
        return f"phone:{phone_key}"
    raise ValueError("A stable member identity (user_id, membership_id, or phone) is required.")


def check_attendance_eligibility(
    db: Session,
    user: Optional[User],
    branch_id: str,
    phone: Optional[str] = None,
    membership_id: Optional[str] = None,
) -> Tuple[bool, str, Optional[str]]:
    """
    Shared eligibility service for QR and manual check-ins.
    Validates membership status and dates, freeze/cancellation state,
    applicable dues policy, and membership plan's branch-access rules.
    Returns: (is_eligible, failure_reason_code, detail_message)
    """
    if not user:
        if phone:
            user = db.query(User).filter(User.phone == phone.strip()).first()
        elif membership_id:
            user = db.query(User).filter(User.membership_id == membership_id.strip()).first()

    if not user:
        return (False, "user_not_found", "No registered member account found.")

    if not user.is_active:
        return (False, "inactive_account", "Account has been suspended or deactivated.")

    # 1. Freeze check
    if user.membership_status == "frozen":
        return (
            False,
            "frozen_membership",
            f"Check-in denied. Membership status is currently 'frozen' until {user.valid_until.strftime('%B %d, %Y') if user.valid_until else 'further notice'}. Visit desk to unfreeze.",
        )

    # 2. Cancellation check
    if user.membership_status == "cancelled":
        return (
            False,
            "cancelled_membership",
            "Check-in denied. Your membership has been cancelled.",
        )

    # 3. Active status check
    if user.membership_status != "active":
        return (
            False,
            "inactive_membership",
            f"Check-in denied. Your membership status is '{user.membership_status}'. Active membership is required.",
        )

    branch_today = get_branch_local_date(branch_id)

    # 4. Expiration check
    if user.valid_until and user.valid_until < branch_today:
        return (
            False,
            "expired_membership",
            f"Check-in denied. Your membership expired on {user.valid_until.strftime('%B %d, %Y')}. Please renew at the reception desk.",
        )

    # 5. Branch eligibility (multi-branch tier, home branch, or explicit grant)
    if not is_member_eligible_for_branch(db, user, branch_id):
        return (
            False,
            "branch_ineligible",
            f"Check-in denied. Your membership plan does not grant access to branch facility '{branch_id}'.",
        )

    # 6. Dues Policy: Check for overdue invoices with positive balance
    overdue_invoices = (
        db.query(Invoice)
        .filter(
            Invoice.user_id == user.id,
            Invoice.due_date < branch_today,
            Invoice.balance_due > Decimal("0.00"),
            Invoice.status.in_(["unpaid", "partially_paid"]),
        )
        .all()
    )
    if overdue_invoices:
        total_overdue = sum(inv.balance_due for inv in overdue_invoices)
        return (
            False,
            "unpaid_dues",
            f"Check-in denied. Outstanding invoice balance of ₹{total_overdue} is past due date. Please settle balance at reception.",
        )

    return (True, "eligible", None)


def generate_member_qr_token(user: User) -> Tuple[str, datetime, int]:
    """
    Generate a signed, short-lived QR token containing a jti nonce.
    Default validity: 120 seconds.
    """
    now = datetime.now(timezone.utc)
    seconds_valid = 120
    expires_at = now + timedelta(seconds=seconds_valid)
    jti = str(uuid.uuid4())

    payload = {
        "sub": user.id,
        "jti": jti,
        "name": user.name,
        "membership_id": user.membership_id,
        "branch_id": user.branch_id,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "token_type": "rvf_entry_qr",
    }
    token = jwt.encode(payload, settings.get_qr_signing_key(), algorithm="HS256")
    return token, expires_at, seconds_valid


def consume_qr_token(db: Session, jti: str, user_id: str, expires_at: datetime) -> bool:
    """
    Consume nonce through conflict detection.
    Returns True if successfully consumed, False if already consumed (replay attack).
    """
    nonce = ConsumedQRToken(
        jti=jti,
        user_id=user_id,
        consumed_at=datetime.now(timezone.utc),
        expires_at=expires_at,
    )
    db.add(nonce)
    try:
        db.flush()
        return True
    except IntegrityError:
        db.rollback()
        return False


def process_qr_checkin(
    db: Session,
    qr_token: str,
    branch_id: str = "narsobawadi",
    staff: Optional[User] = None,
) -> AttendanceRecord:
    """
    Validate and consume a dynamic QR entry token, enforcing signature,
    expiration, single-use nonce consumption, shared eligibility,
    and daily branch attendance uniqueness.
    """
    clean_token = (qr_token or "").strip().strip('"').strip("'")
    target_branch = branch_id if branch_id and branch_id.strip() and branch_id.strip() != "all" else (staff.branch_id if staff and staff.branch_id else "narsobawadi")
    branch_today = get_branch_local_date(target_branch)

    # 1. Decode and verify JWT signature
    try:
        payload = jwt.decode(
            clean_token,
            settings.get_qr_signing_key(),
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except jwt.ExpiredSignatureError:
        attempt = AttendanceAttempt(
            branch_id=branch_id,
            source="qr",
            failure_reason="qr_expired",
            failure_detail="QR token has expired. Member must generate a fresh code.",
            staff_id=staff.id if staff else None,
        )
        db.add(attempt)
        db.commit()
        raise ValueError("QR entry token has expired. Please refresh your membership card QR.")
    except Exception as e:
        attempt = AttendanceAttempt(
            branch_id=branch_id,
            source="qr",
            failure_reason="invalid_payload",
            failure_detail=f"QR cryptographic verification failed: {str(e)}",
            staff_id=staff.id if staff else None,
        )
        db.add(attempt)
        db.commit()
        raise ValueError("Invalid QR code scanned.")

    user_id = payload["sub"]
    jti = payload["jti"]
    exp_dt = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

    # Validate token type specifically for gym floor entry
    if payload.get("token_type") != "rvf_entry_qr":
        attempt = AttendanceAttempt(
            branch_id=branch_id,
            source="qr",
            failure_reason="invalid_payload",
            failure_detail="Scanned token is not an RVFitness gym entry QR code.",
            staff_id=staff.id if staff else None,
        )
        db.add(attempt)
        db.commit()
        raise ValueError("Invalid QR token type. Only RVFitness entry QR codes are accepted.")

    # 2. Replay Attack Prevention: consume nonce atomically
    consumed = consume_qr_token(db=db, jti=jti, user_id=user_id, expires_at=exp_dt)
    if not consumed:
        attempt = AttendanceAttempt(
            user_id=user_id,
            branch_id=branch_id,
            source="qr",
            failure_reason="qr_replay",
            failure_detail=f"Replay detected: JTI '{jti}' already consumed.",
            staff_id=staff.id if staff else None,
        )
        db.add(attempt)
        db.commit()
        raise ValueError("This QR code has already been scanned. Replay rejected.")

    # 3. User lookup
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        attempt = AttendanceAttempt(
            user_id=user_id,
            branch_id=branch_id,
            source="qr",
            failure_reason="user_not_found",
            failure_detail="Subject ID in QR payload does not exist in users table.",
            staff_id=staff.id if staff else None,
        )
        db.add(attempt)
        db.commit()
        raise ValueError("Member profile associated with QR code was not found.")

    member_id_str = resolve_member_identity(
        user_id=user.id, membership_id=user.membership_id, member_phone=user.phone
    )

    # 4. Shared Eligibility Verification
    eligible, reason_code, message = check_attendance_eligibility(
        db=db, user=user, branch_id=branch_id
    )
    if not eligible:
        attempt = AttendanceAttempt(
            member_identity=member_id_str,
            user_id=user.id,
            membership_id=user.membership_id,
            member_phone=user.phone,
            member_name=user.name,
            branch_id=branch_id,
            source="qr",
            failure_reason=reason_code,
            failure_detail=message,
            staff_id=staff.id if staff else None,
        )
        db.add(attempt)
        db.commit()
        raise PermissionError(message)

    # 5. Check duplicate check-in today for this user and branch
    existing = (
        db.query(AttendanceRecord)
        .filter(
            or_(
                AttendanceRecord.member_identity == member_id_str,
                AttendanceRecord.user_id == user.id,
            ),
            AttendanceRecord.branch_id == branch_id,
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
            branch_id=branch_id,
            source="qr",
            failure_reason="already_checked_in",
            failure_detail="Duplicate check-in attempt on the same calendar date.",
            staff_id=staff.id if staff else None,
        )
        db.add(attempt)
        db.commit()
        raise ValueError("Member has already checked in for today at this branch.")

    # 6. Record verified attendance
    record = AttendanceRecord(
        member_identity=member_id_str,
        user_id=user.id,
        branch_id=branch_id,
        check_in_date=branch_today,
        source="qr",
        method="qr",
        staff_id=staff.id if staff else None,
        member_name=user.name,
        member_phone=user.phone,
        membership_id=user.membership_id,
        notes="Verified QR scanner check-in",
    )
    db.add(record)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        try:
            attempt = AttendanceAttempt(
                member_identity=user.id,
                user_id=user.id,
                membership_id=user.membership_id,
                member_phone=user.phone,
                member_name=user.name,
                branch_id=branch_id,
                source="qr",
                failure_reason="already_checked_in",
                failure_detail="Duplicate QR check-in attempt caught by unique constraint.",
                staff_id=staff.id if staff else None,
            )
            db.add(attempt)
            db.commit()
        except Exception:
            db.rollback()
        raise ValueError("Member has already checked in for today at this branch.")

    # 7. Increment streak
    user.streak_days += 1

    # 8. Audit log
    audit = AuditLog(
        actor_id=staff.id if staff else user.id,
        action="attendance.qr_checkin",
        resource_type="attendance_record",
        resource_id=record.id,
        details={
            "branch_id": branch_id,
            "check_in_date": branch_today.isoformat(),
            "streak_days": user.streak_days,
            "jti": jti,
        },
    )
    db.add(audit)
    from backend.app.services.leaderboard_service import award_attendance_points
    award_attendance_points(db, record)
    db.commit()
    db.refresh(record)

    return record


VALID_MANUAL_REASONS = {"no_account", "no_internet", "qr_invalid", "other"}


def process_manual_checkin(
    db: Session,
    branch_id: str,
    staff: User,
    reason_code: str,
    member_id: Optional[str] = None,
    phone: Optional[str] = None,
    name: Optional[str] = None,
    notes: Optional[str] = None,
    user_id: Optional[str] = None,
    member_name: Optional[str] = None,
    member_phone: Optional[str] = None,
    membership_id: Optional[str] = None,
) -> AttendanceRecord:
    """
    Facilitates front-desk manual check-in with mandatory reason code tracking.
    Supports members with existing portal accounts and desk walk-ins without web accounts.
    """
    member_id = member_id or user_id or membership_id
    phone = phone or member_phone
    name = name or member_name

    authorized_roles = {"org_admin", "admin", "branch_manager", "manager", "front_desk", "staff"}
    if staff.role not in authorized_roles:
        raise PermissionError("Access denied: Manual check-in requires staff, manager, or admin privileges.")

    if reason_code not in VALID_MANUAL_REASONS:
        raise ValueError(
            f"Invalid manual check-in reason code '{reason_code}'. Must be one of: {sorted(list(VALID_MANUAL_REASONS))}"
        )

    if reason_code == "other" and not (notes and notes.strip()):
        raise ValueError("Detailed explanation notes are mandatory when reason code is 'other'.")

    branch_today = get_branch_local_date(branch_id)

    # 1. Lookup member
    user = None
    if member_id:
        user = (
            db.query(User)
            .filter(or_(User.id == member_id.strip(), User.membership_id == member_id.strip()))
            .first()
        )
    elif phone:
        # If multiple users share this contact phone, disambiguate with name if provided
        phone_q = db.query(User).filter(User.phone == phone.strip())
        if name and name.strip():
            matched_user = phone_q.filter(func.lower(User.name) == name.strip().lower()).first()
            user = matched_user or phone_q.first()
        else:
            user = phone_q.first()

    # 2. Member exists in system
    if user:
        member_id_str = resolve_member_identity(
            user_id=user.id, membership_id=user.membership_id, member_phone=user.phone
        )
        eligible, failure_reason, message = check_attendance_eligibility(
            db=db, user=user, branch_id=branch_id
        )
        if not eligible:
            attempt = AttendanceAttempt(
                member_identity=member_id_str,
                user_id=user.id,
                membership_id=user.membership_id,
                member_phone=user.phone,
                member_name=user.name,
                branch_id=branch_id,
                source="manual",
                failure_reason=failure_reason,
                failure_detail=message,
                staff_id=staff.id,
            )
            db.add(attempt)
            db.commit()
            raise PermissionError(message)

        # Check duplicate
        existing = (
            db.query(AttendanceRecord)
            .filter(
                or_(
                    AttendanceRecord.member_identity == member_id_str,
                    AttendanceRecord.user_id == user.id,
                ),
                AttendanceRecord.branch_id == branch_id,
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
                branch_id=branch_id,
                source="manual",
                failure_reason="already_checked_in",
                failure_detail="Duplicate manual check-in attempt on the same calendar date.",
                staff_id=staff.id,
            )
            db.add(attempt)
            db.commit()
            raise ValueError("Member has already checked in for today at this branch.")

        record = AttendanceRecord(
            member_identity=member_id_str,
            user_id=user.id,
            branch_id=branch_id,
            check_in_date=branch_today,
            source="manual",
            method="desk_manual",
            manual_reason=reason_code,
            staff_id=staff.id,
            member_name=user.name,
            member_phone=user.phone,
            membership_id=user.membership_id,
            notes=notes or f"Manual check-in: reason={reason_code}",
        )
        db.add(record)
        user.streak_days += 1

    else:
        # 3. Desk walk-in without online portal account
        if not name or not name.strip():
            raise ValueError("Member name is required for manual desk check-in without an account.")
        if not phone or not phone.strip():
            raise ValueError("Contact phone number is required for manual desk check-in without an account.")

        clean_name = name.strip()
        clean_phone = phone.strip()
        member_id_str = resolve_member_identity(
            user_id=None,
            membership_id=member_id.strip() if member_id else None,
            member_phone=clean_phone,
            member_name=clean_name,
        )

        # Duplicate check by canonical member_identity for this branch and date
        existing_walkin = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.member_identity == member_id_str,
                AttendanceRecord.branch_id == branch_id,
                AttendanceRecord.check_in_date == branch_today,
            )
            .first()
        )
        if existing_walkin:
            attempt = AttendanceAttempt(
                member_identity=member_id_str,
                member_name=clean_name,
                member_phone=clean_phone,
                membership_id=member_id.strip() if member_id else None,
                branch_id=branch_id,
                source="manual",
                failure_reason="already_checked_in",
                failure_detail="Duplicate manual check-in attempt on the same calendar date.",
                staff_id=staff.id,
            )
            db.add(attempt)
            db.commit()
            raise ValueError("Member has already checked in for today at this branch.")

        record = AttendanceRecord(
            member_identity=member_id_str,
            user_id=None,
            branch_id=branch_id,
            check_in_date=branch_today,
            source="manual",
            method="desk_manual",
            manual_reason=reason_code,
            staff_id=staff.id,
            member_name=clean_name,
            member_phone=clean_phone,
            membership_id=member_id.strip() if member_id else None,
            notes=notes or f"Manual check-in (unregistered): reason={reason_code}",
        )
        db.add(record)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        try:
            attempt = AttendanceAttempt(
                member_identity=member_id_str,
                user_id=user.id if user else None,
                membership_id=user.membership_id if user else (member_id.strip() if member_id else None),
                member_phone=user.phone if user else clean_phone,
                member_name=user.name if user else clean_name,
                branch_id=branch_id,
                source="manual",
                failure_reason="already_checked_in",
                failure_detail="Duplicate manual check-in attempt caught by unique constraint.",
                staff_id=staff.id,
            )
            db.add(attempt)
            db.commit()
        except Exception:
            db.rollback()
        raise ValueError("Member has already checked in for today at this branch.")

    audit = AuditLog(
        actor_id=staff.id,
        action="attendance.manual_checkin",
        resource_type="attendance_record",
        resource_id=record.id,
        details={
            "branch_id": branch_id,
            "check_in_date": branch_today.isoformat(),
            "reason_code": reason_code,
            "member_name": record.member_name,
        },
    )
    db.add(audit)
    from backend.app.services.leaderboard_service import award_attendance_points
    award_attendance_points(db, record)
    db.commit()
    db.refresh(record)

    return record


def process_manager_override(
    db: Session,
    attempt_id: str,
    manager: User,
    reason: Optional[str] = None,
    override_reason: Optional[str] = None,
) -> AttendanceRecord:
    """
    Manager-only override for rejected check-in attempts.
    Never erases the original failed attempt.
    Requires branch manager or organization admin privileges.
    """
    reason = override_reason if override_reason is not None else reason
    if reason is None:
        reason = ""

    authorized_roles = {"org_admin", "admin", "branch_manager", "manager"}
    if manager.role not in authorized_roles:
        raise PermissionError("Access denied: Manager override requires branch manager or organization admin role.")

    if not reason or len(reason.strip()) < 5:
        raise ValueError("A detailed mandatory reason (at least 5 characters) is required for manager overrides.")

    attempt = db.query(AttendanceAttempt).filter(AttendanceAttempt.id == attempt_id).first()
    if not attempt:
        raise ValueError(f"Attendance attempt '{attempt_id}' not found.")

    if attempt.is_overridden:
        raise ValueError("This rejected attempt has already been overridden.")

    # Branch scope verification
    verify_branch_access(manager, attempt.branch_id)

    attempt_date = attempt.attempted_at.astimezone(get_branch_timezone(attempt.branch_id)).date()
    member_id_str = attempt.member_identity or resolve_member_identity(
        user_id=attempt.user_id,
        membership_id=attempt.membership_id,
        member_phone=attempt.member_phone,
        member_name=attempt.member_name,
    )

    # Prevent duplicate successful check-in if one already exists
    existing = (
        db.query(AttendanceRecord)
        .filter(
            or_(
                AttendanceRecord.member_identity == member_id_str,
                AttendanceRecord.user_id == attempt.user_id if attempt.user_id else False,
            ),
            AttendanceRecord.branch_id == attempt.branch_id,
            AttendanceRecord.check_in_date == attempt_date,
        )
        .first()
    )
    if existing:
        raise ValueError("Member already has a successful check-in recorded for this date and branch.")

    # Create successful override attendance record
    record = AttendanceRecord(
        member_identity=member_id_str,
        user_id=attempt.user_id,
        branch_id=attempt.branch_id,
        check_in_date=attempt_date,
        source="override",
        method="manager_override",
        staff_id=manager.id,
        member_name=attempt.member_name,
        member_phone=attempt.member_phone,
        membership_id=attempt.membership_id,
        notes=f"Manager Override by {manager.name}: {reason.strip()}",
    )
    db.add(record)
    db.flush()

    # Update attempt record with override metadata without deleting original failure
    attempt.is_overridden = True
    attempt.overridden_by_id = manager.id
    attempt.override_reason = reason.strip()
    attempt.overridden_at = datetime.now(timezone.utc)
    attempt.override_attendance_id = record.id

    if attempt.user_id:
        u = db.query(User).filter(User.id == attempt.user_id).first()
        if u:
            u.streak_days += 1

    audit = AuditLog(
        actor_id=manager.id,
        action="attendance.manager_override",
        resource_type="attendance_attempt",
        resource_id=attempt.id,
        details={
            "override_attendance_id": record.id,
            "failure_reason": attempt.failure_reason,
            "manager_reason": reason.strip(),
            "branch_id": attempt.branch_id,
        },
    )
    db.add(audit)
    from backend.app.services.leaderboard_service import award_attendance_points
    award_attendance_points(db, record)
    db.commit()
    db.refresh(record)

    return record


def process_paper_backfill(
    db: Session,
    branch_id: str = "narsobawadi",
    operator: Optional[User] = None,
    visit_date: Optional[date] = None,
    entry_operator: Optional[str] = None,
    reason: Optional[str] = None,
    member_id: Optional[str] = None,
    phone: Optional[str] = None,
    name: Optional[str] = None,
    backfill_operator: Optional[User] = None,
    backfill_reason: Optional[str] = None,
    user_id: Optional[str] = None,
    member_name: Optional[str] = None,
    member_phone: Optional[str] = None,
    membership_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> AttendanceRecord:
    """
    Controlled paper-log backfill for facility outages (power, internet, desk equipment).
    Retains original visit date, entry operator, backfill operator, and reason.
    """
    operator = backfill_operator or operator
    if not operator:
        raise ValueError("Backfill operator is required.")

    authorized_roles = {"org_admin", "admin", "branch_manager", "manager", "front_desk", "staff"}
    if operator.role not in authorized_roles:
        raise PermissionError("Access denied: Paper backfill requires staff, branch manager, or organization admin privileges.")

    reason = backfill_reason or reason
    if not reason or not reason.strip():
        raise ValueError("Reason for paper backfill is required (e.g. 'Power outage at front desk').")
    if not visit_date:
        raise ValueError("Visit date is required for paper backfill.")
    member_id = member_id or user_id or membership_id
    phone = phone or member_phone
    name = name or member_name

    verify_branch_access(operator, branch_id)

    # Member lookup
    user = None
    if member_id:
        user = (
            db.query(User)
            .filter(or_(User.id == member_id.strip(), User.membership_id == member_id.strip()))
            .first()
        )
    elif phone:
        user = db.query(User).filter(User.phone == phone.strip()).first()

    if user:
        member_id_str = resolve_member_identity(
            user_id=user.id, membership_id=user.membership_id, member_phone=user.phone
        )
        # Check duplicate for that date
        existing = (
            db.query(AttendanceRecord)
            .filter(
                or_(
                    AttendanceRecord.member_identity == member_id_str,
                    AttendanceRecord.user_id == user.id,
                ),
                AttendanceRecord.branch_id == branch_id,
                AttendanceRecord.check_in_date == visit_date,
            )
            .first()
        )
        if existing:
            raise ValueError(
                f"Member '{user.name}' already has a recorded attendance visit on {visit_date.isoformat()}."
            )

        record = AttendanceRecord(
            member_identity=member_id_str,
            user_id=user.id,
            branch_id=branch_id,
            check_in_date=visit_date,
            source="backfill",
            method="paper_backfill",
            is_backfill=True,
            backfill_operator_id=operator.id,
            backfill_entry_operator=entry_operator.strip() if entry_operator else "Staff Desk",
            backfill_reason=reason.strip(),
            staff_id=operator.id,
            member_name=user.name,
            member_phone=user.phone,
            membership_id=user.membership_id,
            notes=f"Paper log backfill. Original operator: {entry_operator.strip() if entry_operator else 'Staff Desk'}. Reason: {reason.strip()}",
        )
        db.add(record)
    else:
        if not name or not name.strip():
            raise ValueError("Member name is required for backfill when no account is found.")
        if not phone or not phone.strip():
            raise ValueError("Contact phone number is required for paper backfill without an account.")

        clean_name = name.strip()
        clean_phone = phone.strip()
        member_id_str = resolve_member_identity(
            user_id=None,
            membership_id=member_id.strip() if member_id else None,
            member_phone=clean_phone,
            member_name=clean_name,
        )

        existing_backfill = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.member_identity == member_id_str,
                AttendanceRecord.branch_id == branch_id,
                AttendanceRecord.check_in_date == visit_date,
            )
            .first()
        )
        if existing_backfill:
            raise ValueError(f"Attendance already recorded for '{clean_name}' on {visit_date.isoformat()}.")

        record = AttendanceRecord(
            member_identity=member_id_str,
            user_id=None,
            branch_id=branch_id,
            check_in_date=visit_date,
            source="backfill",
            method="paper_backfill",
            is_backfill=True,
            backfill_operator_id=operator.id,
            backfill_entry_operator=entry_operator.strip() if entry_operator else "Staff Desk",
            backfill_reason=reason.strip(),
            staff_id=operator.id,
            member_name=clean_name,
            member_phone=clean_phone,
            membership_id=member_id.strip() if member_id else None,
            notes=f"Paper log backfill (unregistered). Original operator: {entry_operator.strip() if entry_operator else 'Staff Desk'}. Reason: {reason.strip()}",
        )
        db.add(record)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ValueError(f"Duplicate attendance detected for date {visit_date.isoformat()}.")

    audit = AuditLog(
        actor_id=operator.id,
        action="attendance.paper_backfill",
        resource_type="attendance_record",
        resource_id=record.id,
        details={
            "visit_date": visit_date.isoformat(),
            "branch_id": branch_id,
            "entry_operator": entry_operator.strip(),
            "reason": reason.strip(),
        },
    )
    db.add(audit)
    from backend.app.services.leaderboard_service import award_attendance_points
    award_attendance_points(db, record)
    db.commit()
    db.refresh(record)

    return record


def reconcile_member_identity_on_account_link(
    db: Session,
    user: User,
    membership_id: Optional[str] = None,
    acting_operator: Optional[User] = None,
) -> Dict[str, Any]:
    """
    Reconciles unlinked offline attendance records and rejected attempts when an offline
    card-holder or walk-in member establishes or links a web portal account.

    Invariants:
    1. Zero deletions: Historical attendance records are NEVER deleted.
    2. Strict attribution: Records already belonging to another user are NEVER altered.
    3. Shared phone safety: Members sharing contact numbers are only merged if names match.
    4. Database uniqueness preservation: If an unlinked record collides on (branch_id, date)
       with an existing record for this user, the existing record is authoritative and
       the duplicate is safely retained without violating uq_member_branch_attendance_daily.
    5. Audit integrity: An immutable audit log records operator, timestamp, and counts.
    """
    card_id = (membership_id or user.membership_id or "").strip().upper()
    user_phone = (user.phone or "").strip()
    user_name = user.name.strip().lower()

    if not card_id and not user_phone:
        return {"reconciled_records": 0, "reconciled_attempts": 0, "status": "no_identifiers"}

    # Find unlinked records where user_id IS NULL
    query_filters = []
    if card_id:
        query_filters.append(func.upper(AttendanceRecord.membership_id) == card_id)
        query_filters.append(func.upper(AttendanceRecord.member_identity) == f"MEMBER:{card_id}")
        query_filters.append(func.upper(AttendanceRecord.member_identity) == f"CARD:{card_id}")
    if user_phone:
        # Match phone only when no conflicting card is set and names match
        phone_digits = "".join(c for c in user_phone if c.isdigit())
        phone_key = phone_digits[-10:] if len(phone_digits) >= 10 else phone_digits
        if phone_key:
            query_filters.append(
                and_(
                    AttendanceRecord.member_phone.ilike(f"%{phone_key}%"),
                    AttendanceRecord.membership_id.is_(None),
                    func.lower(AttendanceRecord.member_name) == user_name,
                )
            )

    unlinked_records = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.user_id.is_(None),
            or_(*query_filters),
        )
        .all()
    )

    reconciled_records_count = 0
    new_canonical_id = f"user:{user.id}"

    # Get set of dates where user already has a check-in per branch to avoid constraint collision
    existing_checkins = (
        db.query(AttendanceRecord.branch_id, AttendanceRecord.check_in_date)
        .filter(AttendanceRecord.user_id == user.id)
        .all()
    )
    existing_date_branch_pairs = set(existing_checkins)

    for rec in unlinked_records:
        pair = (rec.branch_id, rec.check_in_date)
        if pair in existing_date_branch_pairs:
            # User already has an authoritative record for this branch and date
            continue
        rec.user_id = user.id
        rec.member_identity = new_canonical_id
        if not rec.membership_id and card_id:
            rec.membership_id = card_id
        rec.notes = (rec.notes or "") + f" [Reconciled to user {user.id}]"
        existing_date_branch_pairs.add(pair)
        reconciled_records_count += 1
        from backend.app.services.leaderboard_service import award_attendance_points
        award_attendance_points(db, rec)

    # Reconcile unlinked attendance_attempts as well
    attempt_filters = []
    if card_id:
        attempt_filters.append(func.upper(AttendanceAttempt.membership_id) == card_id)
        attempt_filters.append(func.upper(AttendanceAttempt.member_identity) == f"MEMBER:{card_id}")
        attempt_filters.append(func.upper(AttendanceAttempt.member_identity) == f"CARD:{card_id}")
    if user_phone:
        phone_digits = "".join(c for c in user_phone if c.isdigit())
        phone_key = phone_digits[-10:] if len(phone_digits) >= 10 else phone_digits
        if phone_key:
            attempt_filters.append(
                and_(
                    AttendanceAttempt.member_phone.ilike(f"%{phone_key}%"),
                    AttendanceAttempt.membership_id.is_(None),
                    func.lower(AttendanceAttempt.member_name) == user_name,
                )
            )

    unlinked_attempts = (
        db.query(AttendanceAttempt)
        .filter(
            AttendanceAttempt.user_id.is_(None),
            or_(*attempt_filters),
        )
        .all()
    )

    reconciled_attempts_count = 0
    for att in unlinked_attempts:
        att.user_id = user.id
        att.member_identity = new_canonical_id
        if not att.membership_id and card_id:
            att.membership_id = card_id
        reconciled_attempts_count += 1

    # Recalculate streak
    total_distinct_days = (
        db.query(func.count(distinct(AttendanceRecord.check_in_date)))
        .filter(AttendanceRecord.user_id == user.id)
        .scalar()
        or 0
    )
    if total_distinct_days > user.streak_days:
        user.streak_days = total_distinct_days

    # Audit log entry
    operator_id = acting_operator.id if acting_operator else user.id
    audit = AuditLog(
        actor_id=operator_id,
        action="attendance.reconcile_identity",
        resource_type="user",
        resource_id=user.id,
        details={
            "reconciled_records": reconciled_records_count,
            "reconciled_attempts": reconciled_attempts_count,
            "membership_id": card_id,
            "canonical_identity": new_canonical_id,
        },
    )
    db.add(audit)
    db.commit()

    return {
        "userId": user.id,
        "canonicalIdentity": new_canonical_id,
        "reconciledRecords": reconciled_records_count,
        "reconciledAttempts": reconciled_attempts_count,
        "totalAttendanceDays": total_distinct_days,
    }


def lookup_members_for_desk(
    db: Session, query: str, branch_id: str = "narsobawadi"
) -> List[Dict[str, Any]]:
    """
    Search active membership roster by member number, phone, or name.
    Masks phone numbers and provides real-time branch eligibility evaluation.
    """
    clean_q = query.strip()
    if not clean_q:
        return []

    users = (
        db.query(User)
        .filter(
            User.role == "member",
            or_(
                User.name.ilike(f"%{clean_q}%"),
                User.phone.ilike(f"%{clean_q}%"),
                User.membership_id.ilike(f"%{clean_q}%"),
                User.email.ilike(f"%{clean_q}%"),
            ),
        )
        .limit(20)
        .all()
    )

    results = []
    for u in users:
        eligible, reason_code, message = check_attendance_eligibility(db=db, user=u, branch_id=branch_id)
        results.append({
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "branchId": u.branch_id,
            "branchName": u.branch.name if u.branch else "Narsobawadi Main Campus",
            "membershipId": u.membership_id or "Pending ID",
            "membership_id": u.membership_id or "Pending ID",
            "maskedPhone": mask_phone(u.phone),
            "phone_masked": mask_phone(u.phone),
            "phone": u.phone,
            "status": u.membership_status,
            "validUntil": u.valid_until.strftime("%B %d, %Y") if u.valid_until else "Pending",
            "planId": u.membership_plan_id,
            "planName": u.membership_plan.name if u.membership_plan else "No Plan Assigned",
            "isEligible": eligible,
            "is_eligible": eligible,
            "ineligibilityReason": message if not eligible else None,
            "streakDays": u.streak_days,
        })
    return results


def generate_branch_monthly_report(
    db: Session,
    branch_id: str,
    year: int,
    month: int,
) -> Dict[str, Any]:
    """
    Produce truthful branch-level monthly attendance report using branch-local timezone boundaries.
    Reports distinct attendance days, source breakdown, operator manual ratios, and rejected attempt tallies.
    Does NOT report redundant total visits or unverified checkout durations.
    """
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    branch_name = branch.name if branch else "Narsobawadi Main Campus"

    # Timezone boundaries
    tz = get_branch_timezone(branch_id)
    _, last_day = calendar.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)

    # 1. Attendance Records in window
    records = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.branch_id == branch_id,
            AttendanceRecord.check_in_date >= start_date,
            AttendanceRecord.check_in_date <= end_date,
        )
        .all()
    )

    distinct_days = len(set(r.check_in_date for r in records))
    total_checkins = len(records)
    qr_count = sum(1 for r in records if r.source == "qr")
    manual_count = sum(1 for r in records if r.source == "manual")
    backfill_count = sum(1 for r in records if r.source == "backfill")
    override_count = sum(1 for r in records if r.source == "override")

    # 2. Operator manual check-in ratio analysis
    operator_totals: Dict[str, int] = {}
    operator_manual: Dict[str, int] = {}
    operator_names: Dict[str, str] = {}

    for r in records:
        op_id = r.staff_id or "self_service"
        operator_totals[op_id] = operator_totals.get(op_id, 0) + 1
        if r.source == "manual":
            operator_manual[op_id] = operator_manual.get(op_id, 0) + 1
        if r.staff and r.staff.id not in operator_names:
            operator_names[r.staff.id] = r.staff.name

    operator_metrics = []
    for op_id, total in operator_totals.items():
        if op_id == "self_service":
            continue
        m_count = operator_manual.get(op_id, 0)
        ratio = round((m_count / total * 100), 1) if total > 0 else 0.0
        operator_metrics.append({
            "operatorId": op_id,
            "operatorName": operator_names.get(op_id, f"Staff ({op_id[:8]})"),
            "manualCount": m_count,
            "totalCount": total,
            "manualRatioPercent": ratio,
        })

    # 3. Rejected Attempts in month
    # Convert dates to UTC bounds for attempted_at timestamp comparison (half-open interval)
    start_dt = datetime(year, month, 1, 0, 0, 0, tzinfo=tz).astimezone(timezone.utc)
    next_year, next_month = (year, month + 1) if month < 12 else (year + 1, 1)
    next_month_start_dt = datetime(next_year, next_month, 1, 0, 0, 0, tzinfo=tz).astimezone(timezone.utc)

    attempts = (
        db.query(AttendanceAttempt)
        .filter(
            AttendanceAttempt.branch_id == branch_id,
            AttendanceAttempt.attempted_at >= start_dt,
            AttendanceAttempt.attempted_at < next_month_start_dt,
        )
        .all()
    )
    rejected_count = len(attempts)
    rejected_by_reason: Dict[str, int] = {}
    for a in attempts:
        rejected_by_reason[a.failure_reason] = rejected_by_reason.get(a.failure_reason, 0) + 1

    # 4. Daily breakdown
    daily_map: Dict[date, Dict[str, int]] = {}
    for r in records:
        d = r.check_in_date
        if d not in daily_map:
            daily_map[d] = {"total": 0, "qr": 0, "manual": 0, "override": 0, "backfill": 0}
        daily_map[d]["total"] += 1
        if r.source in daily_map[d]:
            daily_map[d][r.source] += 1

    daily_breakdown = []
    for day_num in range(1, last_day + 1):
        cur_date = date(year, month, day_num)
        stats = daily_map.get(cur_date, {"total": 0, "qr": 0, "manual": 0, "override": 0, "backfill": 0})
        daily_breakdown.append({
            "date": cur_date.isoformat(),
            "totalCount": stats["total"],
            "qrCount": stats["qr"],
            "manualCount": stats["manual"],
            "overrideCount": stats["override"],
            "backfillCount": stats["backfill"],
        })

    month_name = calendar.month_name[month]

    return {
        "branchId": branch_id,
        "branch_id": branch_id,
        "branchName": branch_name,
        "branch_name": branch_name,
        "year": year,
        "month": month,
        "monthName": month_name,
        "timezone": str(tz),
        "distinctAttendanceDays": distinct_days,
        "distinct_attendance_days": distinct_days,
        "totalCheckins": total_checkins,
        "total_checkins": total_checkins,
        "qrCheckins": qr_count,
        "qr_count": qr_count,
        "manualCheckins": manual_count,
        "manual_count": manual_count,
        "backfilledCheckins": backfill_count,
        "backfilled_count": backfill_count,
        "managerOverrides": override_count,
        "manager_overrides": override_count,
        "operatorMetrics": operator_metrics,
        "operator_ratios": operator_metrics,
        "rejectedAttemptsCount": rejected_count,
        "rejected_count": rejected_count,
        "rejectedAttemptsByReason": rejected_by_reason,
        "dailyBreakdown": daily_breakdown,
    }


def generate_member_monthly_report(
    db: Session,
    user_id: str,
    year: int,
    month: int,
) -> Dict[str, Any]:
    """Produce truthful member-level monthly attendance history."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("Member not found.")

    _, last_day = calendar.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)

    records = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.user_id == user.id,
            AttendanceRecord.check_in_date >= start_date,
            AttendanceRecord.check_in_date <= end_date,
        )
        .order_by(AttendanceRecord.check_in_date.asc())
        .all()
    )

    distinct_days = len(set(r.check_in_date for r in records))
    checkin_dates = [r.check_in_date.isoformat() for r in records]

    return {
        "userId": user.id,
        "userName": user.name,
        "membershipId": user.membership_id,
        "year": year,
        "month": month,
        "monthName": calendar.month_name[month],
        "distinctAttendanceDays": distinct_days,
        "checkinDates": checkin_dates,
        "streakDays": user.streak_days,
    }


def export_branch_report_csv(report: Dict[str, Any]) -> str:
    """Export monthly branch attendance report into clean CSV format."""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["RVFitness Monthly Facility Attendance Report"])
    writer.writerow(["Branch", report["branchName"], "Branch ID", report["branchId"]])
    writer.writerow(["Period", f"{report['monthName']} {report['year']}", "Timezone", report["timezone"]])
    writer.writerow([])

    writer.writerow(["Executive Attendance Summary"])
    writer.writerow(["Metric", "Count"])
    writer.writerow(["Distinct Attendance Days", report["distinctAttendanceDays"]])
    writer.writerow(["Total Verified Check-ins", report["totalCheckins"]])
    writer.writerow(["Dynamic QR Check-ins", report["qrCheckins"]])
    writer.writerow(["Desk Manual Check-ins", report["manualCheckins"]])
    writer.writerow(["Outage Paper Backfills", report["backfilledCheckins"]])
    writer.writerow(["Manager Authorized Overrides", report["managerOverrides"]])
    writer.writerow(["Rejected Check-in Attempts", report["rejectedAttemptsCount"]])
    writer.writerow([])

    writer.writerow(["Staff Operator Manual Check-in Ratios"])
    writer.writerow(["Operator Name", "Operator ID", "Manual Check-ins", "Total Handled", "Manual Ratio %"])
    for op in report["operatorMetrics"]:
        writer.writerow([op["operatorName"], op["operatorId"], op["manualCount"], op["totalCount"], f"{op['manualRatioPercent']}%"])
    writer.writerow([])

    writer.writerow(["Daily Attendance Breakdown"])
    writer.writerow(["Date", "Total Check-ins", "QR", "Manual", "Override", "Backfill"])
    for d in report["dailyBreakdown"]:
        writer.writerow([d["date"], d["totalCount"], d["qrCount"], d["manualCount"], d["overrideCount"], d["backfillCount"]])

    return output.getvalue()


def export_branch_report_pdf(report: Dict[str, Any]) -> bytes:
    """
    Generate an executive PDF report using ReportLab with black-and-gold aesthetic tokens.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()

    # Custom styling tokens
    gold = colors.HexColor("#d4af37")
    dark_bg = colors.HexColor("#08090b")
    card_bg = colors.HexColor("#11141a")
    text_light = colors.HexColor("#f8fafc")
    text_muted = colors.HexColor("#94a3b8")

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=gold,
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=text_muted,
    )
    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=gold,
        spaceBefore=12,
        spaceAfter=6,
    )

    story = []

    # Title & Metadata
    story.append(Paragraph("RV FITNESS · OFFICIAL ATTENDANCE AUDIT REPORT", title_style))
    story.append(Spacer(1, 4))
    meta_text = (
        f"Facility: <b>{report['branchName']}</b> ({report['branchId']}) | "
        f"Period: <b>{report['monthName']} {report['year']}</b> | "
        f"Timezone: {report['timezone']}"
    )
    story.append(Paragraph(meta_text, subtitle_style))
    story.append(Spacer(1, 14))

    # Metric Table
    story.append(Paragraph("Facility Operations Summary", heading_style))
    summary_data = [
        ["Metric", "Verified Count", "Operational Notes"],
        ["Distinct Attendance Days", str(report["distinctAttendanceDays"]), "Calendar dates with verified floor access"],
        ["Total Verified Check-ins", str(report["totalCheckins"]), "Total successful entry transactions"],
        ["Dynamic QR Scans", str(report["qrCheckins"]), "Cryptographically signed QR entries"],
        ["Desk Manual Entries", str(report["manualCheckins"]), "Staff-assisted desk check-ins with reason tracking"],
        ["Outage Paper Backfills", str(report["backfilledCheckins"]), "Controlled recovery for power/internet outages"],
        ["Manager Authorized Overrides", str(report["managerOverrides"]), "Supervisor authorized access exceptions"],
        ["Unsuccessful Attempts", str(report["rejectedAttemptsCount"]), "Logged in append-only attempts audit table"],
    ]
    summary_table = Table(summary_data, colWidths=[200, 100, 240])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), card_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), gold),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#2a2d36")),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 14))

    # Operator Metrics Table
    if report["operatorMetrics"]:
        story.append(Paragraph("Desk Operator Manual Check-in Ratios", heading_style))
        op_data = [["Operator Name", "Operator ID", "Manual Entries", "Total Handled", "Manual Ratio %"]]
        for op in report["operatorMetrics"]:
            op_data.append([
                op["operatorName"],
                op["operatorId"][:12] + "...",
                str(op["manualCount"]),
                str(op["totalCount"]),
                f"{op['manualRatioPercent']}%",
            ])
        op_table = Table(op_data, colWidths=[160, 110, 90, 90, 90])
        op_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), card_bg),
            ("TEXTCOLOR", (0, 0), (-1, 0), gold),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#2a2d36")),
        ]))
        story.append(op_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def purge_expired_qr_tokens(db: Session) -> int:
    """Purge expired QR nonce records from the consumed_qr_tokens table."""
    now = datetime.now(timezone.utc)
    deleted = db.query(ConsumedQRToken).filter(ConsumedQRToken.expires_at < now).delete()
    db.commit()
    return deleted
