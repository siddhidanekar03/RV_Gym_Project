import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.security import hash_password
from backend.app.core.auth import create_user_session
from backend.app.models.user import User
from backend.app.models.organization import Organization, Branch
from backend.app.models.billing import Invoice
from backend.app.models.attendance import (
    AttendanceRecord,
    AttendanceAttempt,
    ConsumedQRToken,
)
from backend.app.services.attendance_service import (
    generate_member_qr_token,
    consume_qr_token,
    process_qr_checkin,
    process_manual_checkin,
    process_manager_override,
    process_paper_backfill,
    generate_branch_monthly_report,
    export_branch_report_csv,
    export_branch_report_pdf,
    lookup_members_for_desk,
)


def _setup_org_and_branch(db: Session) -> Branch:
    org = db.query(Organization).filter(Organization.code == "RVF").first()
    if not org:
        org = Organization(name="RV Fitness", code="RVF", is_active=True)
        db.add(org)
        db.flush()

    branch = db.query(Branch).filter(Branch.id == "narsobawadi").first()
    if not branch:
        branch = Branch(
            id="narsobawadi",
            organization_id=org.id,
            name="Narsobawadi Main Campus",
            code="narsobawadi",
            is_active=True,
        )
        db.add(branch)
        db.flush()
    return branch


def _auth_headers(db: Session, user: User, client: TestClient):
    _, token, csrf = create_user_session(db, user, client)
    return {
        "x-csrf-token": csrf,
        "Cookie": f"rvf_session={token}; rvf_csrf_token={csrf}",
    }


def test_qr_token_generation_and_consumption(db_session: Session):
    """
    Verify QR token is generated with a valid signed payload, expiration within 120s,
    and can be consumed once.
    """
    branch = _setup_org_and_branch(db_session)
    member = User(
        email="qr_member@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="QR Member",
        role="member",
        branch_id=branch.id,
        membership_id="RVF-QR-001",
        membership_status="active",
        valid_until=date.today() + timedelta(days=30),
    )
    db_session.add(member)
    db_session.commit()

    token, expires_at, ttl = generate_member_qr_token(member)
    assert ttl == 120
    assert token is not None

    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    assert payload["sub"] == member.id
    assert "jti" in payload
    assert payload["token_type"] == "rvf_entry_qr"

    # Consume token
    success = consume_qr_token(
        db_session,
        jti=payload["jti"],
        user_id=member.id,
        expires_at=expires_at,
    )
    assert success is True

    # Check consumed record exists
    consumed = db_session.query(ConsumedQRToken).filter(ConsumedQRToken.jti == payload["jti"]).first()
    assert consumed is not None
    assert consumed.user_id == member.id


def test_qr_replay_rejection(db_session: Session):
    """
    Verify that consuming the same QR token nonce twice is strictly rejected
    and logs a qr_replay attempt.
    """
    branch = _setup_org_and_branch(db_session)
    member = User(
        email="replay_member@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Replay Member",
        role="member",
        branch_id=branch.id,
        membership_id="RVF-REPLAY-001",
        membership_status="active",
        valid_until=date.today() + timedelta(days=30),
    )
    db_session.add(member)
    db_session.commit()

    token, expires_at, _ = generate_member_qr_token(member)

    # First check-in succeeds
    rec1 = process_qr_checkin(
        db=db_session,
        qr_token=token,
        branch_id=branch.id,
    )
    assert rec1 is not None
    assert rec1.source == "qr"

    # Second check-in with exact same token is rejected as replay
    with pytest.raises(Exception) as exc_info:
        process_qr_checkin(
            db=db_session,
            qr_token=token,
            branch_id=branch.id,
        )
    assert "replay" in str(exc_info.value).lower()

    # Verify attempt logged in attendance_attempts
    attempt = (
        db_session.query(AttendanceAttempt)
        .filter(AttendanceAttempt.user_id == member.id, AttendanceAttempt.failure_reason == "qr_replay")
        .first()
    )
    assert attempt is not None


def test_expired_qr_token_rejection(db_session: Session):
    """
    Verify expired QR token is rejected by the decoder and logged as qr_expired.
    """
    branch = _setup_org_and_branch(db_session)
    member = User(
        email="expired_qr@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Expired QR Member",
        role="member",
        branch_id=branch.id,
        membership_id="RVF-EXP-001",
        membership_status="active",
        valid_until=date.today() + timedelta(days=30),
    )
    db_session.add(member)
    db_session.commit()

    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": member.id,
        "jti": str(uuid.uuid4()),
        "name": member.name,
        "membership_id": member.membership_id,
        "branch_id": branch.id,
        "iat": int((now - timedelta(seconds=200)).timestamp()),
        "exp": int((now - timedelta(seconds=10)).timestamp()),  # Expired 10s ago
        "token_type": "rvf_entry_qr",
    }
    expired_token = jwt.encode(expired_payload, settings.SECRET_KEY, algorithm="HS256")

    with pytest.raises(Exception) as exc_info:
        process_qr_checkin(
            db=db_session,
            qr_token=expired_token,
            branch_id=branch.id,
        )
    assert "expired" in str(exc_info.value).lower()

    # Verify attempt logged
    attempt = (
        db_session.query(AttendanceAttempt)
        .filter(AttendanceAttempt.failure_reason == "qr_expired")
        .first()
    )
    assert attempt is not None


def test_failed_attempt_does_not_block_later_successful_checkin(db_session: Session):
    """
    Verify that an append-only failed attendance attempt does NOT block
    a subsequent valid check-in on the same day.
    """
    branch = _setup_org_and_branch(db_session)
    member = User(
        email="recovery_member@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Recovery Member",
        role="member",
        branch_id=branch.id,
        membership_id="RVF-REC-001",
        membership_status="active",
        valid_until=date.today() + timedelta(days=30),
    )
    db_session.add(member)
    db_session.commit()

    # 1. Fail check-in with invalid token
    with pytest.raises(Exception):
        process_qr_checkin(
            db=db_session,
            qr_token="invalid.jwt.token",
            branch_id=branch.id,
        )

    attempts = db_session.query(AttendanceAttempt).all()
    assert len(attempts) >= 1

    # 2. Member tries again with valid freshly minted QR token
    valid_token, _, _ = generate_member_qr_token(member)
    rec = process_qr_checkin(
        db=db_session,
        qr_token=valid_token,
        branch_id=branch.id,
    )
    assert rec is not None
    assert rec.user_id == member.id


def test_duplicate_checkin_prevented_by_database_constraint(db_session: Session):
    """
    Verify at most one successful visit per member, branch, and branch-local calendar date.
    Subsequent check-in attempts on the same day must raise an error.
    """
    branch = _setup_org_and_branch(db_session)
    member = User(
        email="daily_member@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Daily Member",
        role="member",
        branch_id=branch.id,
        membership_id="RVF-DAILY-001",
        membership_status="active",
        valid_until=date.today() + timedelta(days=30),
    )
    staff = User(
        email="staff_desk@rvfitness.in",
        hashed_password=hash_password("StaffPass123"),
        name="Desk Staff",
        role="front_desk",
        branch_id=branch.id,
    )
    db_session.add_all([member, staff])
    db_session.commit()

    # First manual check-in succeeds
    rec1 = process_manual_checkin(
        db=db_session,
        branch_id=branch.id,
        staff=staff,
        user_id=member.id,
        reason_code="no_internet",
    )
    assert rec1 is not None

    # Second check-in on the same day fails with duplicate_daily
    with pytest.raises(Exception) as exc_info:
        process_manual_checkin(
            db=db_session,
            branch_id=branch.id,
            staff=staff,
            user_id=member.id,
            reason_code="qr_invalid",
        )
    assert "already checked in" in str(exc_info.value).lower()


def test_manual_checkin_reason_code_validation(db_session: Session):
    """
    Verify manual check-ins strictly require a recognized reason code:
    no_account, no_internet, qr_invalid, other.
    """
    branch = _setup_org_and_branch(db_session)
    member = User(
        email="reason_member@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Reason Member",
        role="member",
        branch_id=branch.id,
        membership_id="RVF-RSN-001",
        membership_status="active",
        valid_until=date.today() + timedelta(days=30),
    )
    staff = User(
        email="reason_staff@rvfitness.in",
        hashed_password=hash_password("StaffPass123"),
        name="Desk Staff",
        role="front_desk",
        branch_id=branch.id,
    )
    db_session.add_all([member, staff])
    db_session.commit()

    # Invalid reason code rejected
    with pytest.raises(Exception) as exc_info:
        process_manual_checkin(
            db=db_session,
            branch_id=branch.id,
            staff=staff,
            user_id=member.id,
            reason_code="forgot_phone_invalid",
        )
    assert "invalid manual check-in reason" in str(exc_info.value).lower()

    # Valid reason code succeeds
    rec = process_manual_checkin(
        db=db_session,
        branch_id=branch.id,
        staff=staff,
        user_id=member.id,
        reason_code="qr_invalid",
        notes="Member screen cracked",
    )
    assert rec.manual_reason == "qr_invalid"
    assert rec.source == "manual"
    assert rec.staff_id == staff.id


def test_desk_checkin_for_member_without_portal_account(db_session: Session):
    """
    Verify walk-in members who have not registered a portal account (user_id=None)
    can be checked in at the desk with name, phone, and membership ID.
    """
    branch = _setup_org_and_branch(db_session)
    staff = User(
        email="portal_staff@rvfitness.in",
        hashed_password=hash_password("StaffPass123"),
        name="Desk Staff",
        role="front_desk",
        branch_id=branch.id,
    )
    db_session.add(staff)
    db_session.commit()

    rec = process_manual_checkin(
        db=db_session,
        branch_id=branch.id,
        staff=staff,
        member_name="Offline Ramesh Patil",
        member_phone="+91 98220 99887",
        membership_id="RVF-OFFLINE-789",
        reason_code="no_account",
        notes="Paper card presented",
    )
    assert rec.user_id is None
    assert rec.member_name == "Offline Ramesh Patil"
    assert rec.member_phone == "+91 98220 99887"
    assert rec.membership_id == "RVF-OFFLINE-789"
    assert rec.manual_reason == "no_account"


def test_manager_override_workflow(client: TestClient, db_session: Session):
    """
    Verify:
    1. Regular staff cannot perform an override (role isolation).
    2. Manager can perform an override with mandatory reason.
    3. Original rejected attempt is preserved in attendance_attempts and linked to override.
    """
    branch = _setup_org_and_branch(db_session)
    member = User(
        email="override_member@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Override Member",
        role="member",
        branch_id=branch.id,
        membership_id="RVF-OVR-001",
        membership_status="frozen",  # Frozen status causes check-in rejection
        valid_until=date.today() + timedelta(days=30),
    )
    staff = User(
        email="desk_override@rvfitness.in",
        hashed_password=hash_password("StaffPass123"),
        name="Regular Desk Staff",
        role="front_desk",
        branch_id=branch.id,
    )
    manager = User(
        email="manager_override@rvfitness.in",
        hashed_password=hash_password("ManagerPass123"),
        name="Branch Manager",
        role="branch_manager",
        branch_id=branch.id,
    )
    db_session.add_all([member, staff, manager])
    db_session.commit()

    # Step 1: Attempt check-in which fails due to frozen status
    token, _, _ = generate_member_qr_token(member)
    with pytest.raises(Exception):
        process_qr_checkin(
            db=db_session,
            qr_token=token,
            branch_id=branch.id,
        )

    # Failed attempt logged
    attempt = (
        db_session.query(AttendanceAttempt)
        .filter(AttendanceAttempt.user_id == member.id)
        .first()
    )
    assert attempt is not None
    assert attempt.failure_reason == "frozen_membership"
    assert attempt.is_overridden is False

    # Step 2: Front desk staff attempts override -> Rejected (403 via API)
    staff_headers = _auth_headers(db_session, staff, client)
    resp_staff = client.post(
        "/api/attendance/override",
        headers=staff_headers,
        json={
            "attemptId": attempt.id,
            "reason": "Desk staff trying to override",
        },
    )
    assert resp_staff.status_code == 403

    # Step 3: Manager override via domain service without reason -> Rejected
    with pytest.raises(ValueError) as val_err:
        process_manager_override(
            db=db_session,
            attempt_id=attempt.id,
            manager=manager,
            reason="",  # Blank reason
        )
    assert "mandatory" in str(val_err.value).lower()

    # Step 4: Manager override with valid reason -> Success
    rec = process_manager_override(
        db=db_session,
        attempt_id=attempt.id,
        manager=manager,
        reason="Member unfreeze form signed in person at counter",
    )
    assert rec is not None
    assert rec.source == "override"
    assert rec.user_id == member.id

    # Verify attempt is updated and NEVER deleted
    db_session.refresh(attempt)
    assert attempt.is_overridden is True
    assert attempt.overridden_by_id == manager.id
    assert attempt.override_reason == "Member unfreeze form signed in person at counter"
    assert attempt.override_attendance_id == rec.id


def test_paper_backfill_for_desk_outage(db_session: Session):
    """
    Verify controlled paper-log backfill for desk outages:
    records past visit date, entry operator, backfill operator, and reason.
    Prevents duplicate backfill for the same date.
    """
    branch = _setup_org_and_branch(db_session)
    member = User(
        email="backfill_member@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Backfill Member",
        role="member",
        branch_id=branch.id,
        membership_id="RVF-BKF-001",
        membership_status="active",
        valid_until=date.today() + timedelta(days=60),
    )
    manager = User(
        email="backfill_mgr@rvfitness.in",
        hashed_password=hash_password("MgrPass123"),
        name="Operations Manager",
        role="branch_manager",
        branch_id=branch.id,
    )
    db_session.add_all([member, manager])
    db_session.commit()

    outage_date = date.today() - timedelta(days=2)

    # 1. Successful backfill
    rec = process_paper_backfill(
        db=db_session,
        branch_id=branch.id,
        backfill_operator=manager,
        user_id=member.id,
        visit_date=outage_date,
        entry_operator="Operator Sandeep (Desk Logbook)",
        backfill_reason="Power outage and ISP downtime on October 12",
        notes="Verified against physical entry register #4",
    )
    assert rec.is_backfill is True
    assert rec.check_in_date == outage_date
    assert rec.source == "backfill"
    assert rec.backfill_entry_operator == "Operator Sandeep (Desk Logbook)"
    assert rec.backfill_operator_id == manager.id
    assert rec.backfill_reason == "Power outage and ISP downtime on October 12"

    # 2. Duplicate backfill on same date prevented
    with pytest.raises(Exception) as exc_info:
        process_paper_backfill(
            db=db_session,
            branch_id=branch.id,
            backfill_operator=manager,
            user_id=member.id,
            visit_date=outage_date,
            entry_operator="Operator Sandeep",
            backfill_reason="Duplicate attempt",
        )
    assert "already has a recorded attendance visit" in str(exc_info.value).lower()


def test_shared_eligibility_overdue_dues_rejection(db_session: Session):
    """
    Verify member with overdue unpaid invoice balance is rejected at check-in.
    """
    branch = _setup_org_and_branch(db_session)
    member = User(
        email="dues_member@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Dues Member",
        role="member",
        branch_id=branch.id,
        membership_id="RVF-DUES-001",
        membership_status="active",
        valid_until=date.today() + timedelta(days=30),
    )
    db_session.add(member)
    db_session.flush()

    # Add overdue invoice
    overdue_inv = Invoice(
        invoice_number="INV-DUE-TEST-001",
        user_id=member.id,
        branch_id=branch.id,
        due_date=date.today() - timedelta(days=5),  # 5 days past due
        status="unpaid",
        subtotal=Decimal("2500.00"),
        tax=Decimal("0.00"),
        total_amount=Decimal("2500.00"),
        amount_paid=Decimal("0.00"),
        balance_due=Decimal("2500.00"),
    )
    db_session.add(overdue_inv)
    db_session.commit()

    token, _, _ = generate_member_qr_token(member)

    with pytest.raises(Exception) as exc_info:
        process_qr_checkin(
            db=db_session,
            qr_token=token,
            branch_id=branch.id,
        )
    assert "outstanding invoice balance" in str(exc_info.value).lower()

    # Settle balance
    overdue_inv.status = "paid"
    overdue_inv.amount_paid = Decimal("2500.00")
    overdue_inv.balance_due = Decimal("0.00")
    db_session.commit()

    # New check-in now succeeds
    token2, _, _ = generate_member_qr_token(member)
    rec = process_qr_checkin(
        db=db_session,
        qr_token=token2,
        branch_id=branch.id,
    )
    assert rec is not None
    assert rec.user_id == member.id


def test_member_lookup_pii_masking_and_disambiguation(db_session: Session):
    """
    Verify desk member search returns masked phone numbers and supports disambiguation.
    """
    branch = _setup_org_and_branch(db_session)
    m1 = User(
        email="ramesh1@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Ramesh Patil",
        phone="+91 98221 12345",
        role="member",
        branch_id=branch.id,
        membership_id="RVF-DIS-001",
        membership_status="active",
        valid_until=date.today() + timedelta(days=30),
    )
    m2 = User(
        email="ramesh2@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Ramesh Kulkarni",
        phone="+91 98221 67890",
        role="member",
        branch_id=branch.id,
        membership_id="RVF-DIS-002",
        membership_status="active",
        valid_until=date.today() + timedelta(days=30),
    )
    db_session.add_all([m1, m2])
    db_session.commit()

    results = lookup_members_for_desk(db=db_session, query="Ramesh")
    assert len(results) >= 2

    for r in results:
        # PII masking verification
        assert "******" in r["phone_masked"]
        assert r["is_eligible"] is True


def test_monthly_attendance_report_and_exports(db_session: Session):
    """
    Verify monthly report:
    1. Computes distinct attendance days, qr_count, manual_count, backfilled_count, manager_overrides.
    2. Calculates operator manual check-in ratio percentage.
    3. Produces valid CSV and PDF byte payloads.
    """
    branch = _setup_org_and_branch(db_session)
    staff = User(
        email="report_staff@rvfitness.in",
        hashed_password=hash_password("StaffPass123"),
        name="Report Staff Priya",
        role="front_desk",
        branch_id=branch.id,
    )
    member = User(
        email="report_member@rvfitness.in",
        hashed_password=hash_password("MemberPass123"),
        name="Report Member Sachin",
        role="member",
        branch_id=branch.id,
        membership_id="RVF-RPT-001",
        membership_status="active",
        valid_until=date.today() + timedelta(days=60),
    )
    db_session.add_all([staff, member])
    db_session.commit()

    today = date.today()
    year = today.year
    month = today.month

    # Insert 1 QR record and 1 Manual record on distinct dates in current month
    d1 = date(year, month, 1)
    d2 = date(year, month, 2)

    rec_qr = AttendanceRecord(
        user_id=member.id,
        branch_id=branch.id,
        check_in_date=d1,
        source="qr",
        method="qr",
    )
    rec_man = AttendanceRecord(
        user_id=member.id,
        branch_id=branch.id,
        check_in_date=d2,
        source="manual",
        method="manual",
        staff_id=staff.id,
        manual_reason="no_internet",
    )
    db_session.add_all([rec_qr, rec_man])
    db_session.commit()

    report = generate_branch_monthly_report(
        db=db_session,
        branch_id=branch.id,
        year=year,
        month=month,
    )
    assert report["distinct_attendance_days"] >= 2
    assert report["qr_count"] >= 1
    assert report["manual_count"] >= 1
    assert "average_visit_duration" not in report  # No fabricated duration

    # Operator ratio check
    op_ratios = report["operator_ratios"]
    assert len(op_ratios) >= 1
    priya_op = next((op for op in op_ratios if op["operatorId"] == staff.id), None)
    assert priya_op is not None
    assert priya_op["manualCount"] >= 1

    # CSV export
    csv_bytes = export_branch_report_csv(report)
    if isinstance(csv_bytes, str):
        csv_str = csv_bytes
    else:
        csv_str = csv_bytes.decode("utf-8")
    assert "Executive Attendance Summary" in csv_str
    assert "Report Staff Priya" in csv_str

    # PDF export
    pdf_bytes = export_branch_report_pdf(report)
    assert pdf_bytes.startswith(b"%PDF-")
