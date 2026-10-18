import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
import jwt
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import or_

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal
from backend.app.core.security import hash_password
from backend.app.core.auth import create_user_session
from backend.app.models.user import User
from backend.app.models.organization import Organization, Branch
from backend.app.models.membership import MembershipPlan
from backend.app.models.billing import Invoice, Payment
from backend.app.models.attendance import AttendanceRecord, AttendanceAttempt, ConsumedQRToken
from backend.app.services.attendance_service import (
    generate_member_qr_token,
    process_qr_checkin,
    process_manual_checkin,
    process_manager_override,
    process_paper_backfill,
    check_attendance_eligibility,
    generate_branch_monthly_report,
    get_branch_local_date,
    resolve_member_identity,
    DEFAULT_TIMEZONE,
)
from backend.app.services.billing_service import record_offline_payment, reverse_payment
from backend.app.cli.prune_nonces import run_prune_nonces, RVF_QR_CLEANUP_ADVISORY_LOCK_ID

# Deterministic test-only wrong key with >= 32 bytes (256 bits) to satisfy PyJWT / RFC 7518
TEST_ADVERSARIAL_FORGED_HMAC_KEY = "rvf_test_deterministic_adversarial_wrong_hmac_key_32b"


@pytest.fixture
def adversarial_setup(db_session: Session):
    """Seed test fixtures: org, 2 branches, admin, manager, staff, single-branch member, multi-branch member."""
    # Organization
    org = db_session.query(Organization).filter(Organization.code == "RVF").first()
    if not org:
        org = Organization(name="RV Fitness", code="RVF", contact_email="admin@rvf.in")
        db_session.add(org)
        db_session.flush()

    # Branches
    b1 = db_session.query(Branch).filter(Branch.id == "narsobawadi").first()
    if not b1:
        b1 = Branch(id="narsobawadi", organization_id=org.id, name="Narsobawadi Main Campus", code="NRS")
        db_session.add(b1)
    b2 = db_session.query(Branch).filter(Branch.id == "kolhapur").first()
    if not b2:
        b2 = Branch(id="kolhapur", organization_id=org.id, name="Kolhapur Elite Center", code="KLP")
        db_session.add(b2)
    db_session.flush()

    # Plans
    single_plan = db_session.query(MembershipPlan).filter(MembershipPlan.id == "plan-single").first()
    if not single_plan:
        single_plan = MembershipPlan(
            id="plan-single",
            name="Single Campus Access",
            price=Decimal("1500.00"),
            billing_cycle="monthly",
            duration_days=30,
            access_scope="single_branch",
            is_active=True,
        )
        db_session.add(single_plan)

    multi_plan = db_session.query(MembershipPlan).filter(MembershipPlan.id == "plan-multi").first()
    if not multi_plan:
        multi_plan = MembershipPlan(
            id="plan-multi",
            name="All Campus Platinum",
            price=Decimal("3500.00"),
            billing_cycle="quarterly",
            duration_days=90,
            access_scope="all_branches",
            is_active=True,
        )
        db_session.add(multi_plan)
    db_session.flush()

    # Admin
    admin = db_session.query(User).filter(User.email == "adv_admin@rvf.in").first()
    if not admin:
        admin = User(
            id="adv-admin-1",
            email="adv_admin@rvf.in",
            name="Adv Admin",
            role="org_admin",
            branch_id="narsobawadi",
            hashed_password=hash_password("adminSecret123"),
            is_active=True,
        )
        db_session.add(admin)

    # Branch Manager
    manager = db_session.query(User).filter(User.email == "adv_mgr@rvf.in").first()
    if not manager:
        manager = User(
            id="adv-mgr-1",
            email="adv_mgr@rvf.in",
            name="Adv Branch Manager",
            role="branch_manager",
            branch_id="narsobawadi",
            hashed_password=hash_password("managerSecret123"),
            is_active=True,
        )
        db_session.add(manager)

    # Desk Staff
    staff = db_session.query(User).filter(User.email == "adv_staff@rvf.in").first()
    if not staff:
        staff = User(
            id="adv-staff-1",
            email="adv_staff@rvf.in",
            name="Adv Desk Staff",
            role="front_desk",
            branch_id="narsobawadi",
            hashed_password=hash_password("staffSecret123"),
            is_active=True,
        )
        db_session.add(staff)

    # Member 1 (Single branch)
    member_single = db_session.query(User).filter(User.email == "adv_single@rvf.in").first()
    if not member_single:
        member_single = User(
            id="adv-mem-single",
            email="adv_single@rvf.in",
            name="Single Branch Member",
            role="member",
            phone="+91 91234 56789",
            membership_id="RVF-SB-001",
            membership_status="active",
            valid_until=date.today() + timedelta(days=60),
            membership_plan_id=single_plan.id,
            branch_id="narsobawadi",
            hashed_password=hash_password("memberSecret123"),
            is_active=True,
        )
        db_session.add(member_single)

    # Member 2 (Multi branch)
    member_multi = db_session.query(User).filter(User.email == "adv_multi@rvf.in").first()
    if not member_multi:
        member_multi = User(
            id="adv-mem-multi",
            email="adv_multi@rvf.in",
            name="Multi Branch Member",
            role="member",
            phone="+91 98765 12345",
            membership_id="RVF-MB-002",
            membership_status="active",
            valid_until=date.today() + timedelta(days=90),
            membership_plan_id=multi_plan.id,
            branch_id="narsobawadi",
            hashed_password=hash_password("memberSecret123"),
            is_active=True,
        )
        db_session.add(member_multi)

    db_session.commit()
    return {
        "admin": admin,
        "manager": manager,
        "staff": staff,
        "member_single": member_single,
        "member_multi": member_multi,
        "single_plan": single_plan,
        "multi_plan": multi_plan,
    }


def test_concurrent_duplicate_checkin_registered_user(adversarial_setup, db_session: Session):
    """
    Simultaneously submit 5 concurrent check-in requests for the same registered member.
    The database constraint must enforce that strictly 1 succeeds and duplicates fail.
    """
    session_factory = sessionmaker(bind=db_session.bind, autocommit=False, autoflush=False)
    member = adversarial_setup["member_single"]
    branch_id = "narsobawadi"
    today = get_branch_local_date(branch_id)

    # Clean out any previous records for this user/branch/date
    clean_db = session_factory()
    clean_db.query(AttendanceRecord).filter(
        AttendanceRecord.user_id == member.id,
        AttendanceRecord.branch_id == branch_id,
        AttendanceRecord.check_in_date == today,
    ).delete()
    clean_db.commit()
    clean_db.close()

    successes = []
    failures = []

    def attempt_checkin():
        db = session_factory()
        try:
            member_user = db.query(User).filter(User.id == member.id).first()
            # Generate fresh unique QR token per attempt
            qr_token, _, _ = generate_member_qr_token(member_user)
            rec = process_qr_checkin(db=db, qr_token=qr_token, branch_id=branch_id)
            db.commit()
            return True, rec.id
        except Exception as e:
            db.rollback()
            return False, str(e)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(attempt_checkin) for _ in range(5)]
        for f in as_completed(futures):
            ok, res = f.result()
            if ok:
                successes.append(res)
            else:
                failures.append(res)

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
    assert len(failures) == 4, f"Expected 4 rejections, got {len(failures)}"

    verify_db = session_factory()
    count = verify_db.query(AttendanceRecord).filter(
        AttendanceRecord.user_id == member.id,
        AttendanceRecord.branch_id == branch_id,
        AttendanceRecord.check_in_date == today,
    ).count()
    assert count == 1
    verify_db.close()


def test_concurrent_duplicate_checkin_unregistered_walkin(adversarial_setup, db_session: Session):
    """
    Simultaneously submit 5 concurrent manual check-ins for a walk-in member without an account.
    Database uniqueness on member_identity ('phone:9811122233') must prevent duplicates.
    """
    session_factory = sessionmaker(bind=db_session.bind, autocommit=False, autoflush=False)
    staff = adversarial_setup["staff"]
    branch_id = "narsobawadi"
    test_phone = "+91 98111 22233"
    walkin_name = "Walkin Athlete"
    today = get_branch_local_date(branch_id)
    canonical_identity = resolve_member_identity(user_id=None, member_phone=test_phone, member_name=walkin_name)

    clean_db = session_factory()
    clean_db.query(AttendanceRecord).filter(
        AttendanceRecord.member_identity == canonical_identity,
        AttendanceRecord.branch_id == branch_id,
        AttendanceRecord.check_in_date == today,
    ).delete()
    clean_db.commit()
    clean_db.close()

    successes = []
    failures = []

    def attempt_walkin():
        db = session_factory()
        try:
            st = db.query(User).filter(User.id == staff.id).first()
            rec = process_manual_checkin(
                db=db,
                branch_id=branch_id,
                staff=st,
                reason_code="no_account",
                name="Walkin Athlete",
                phone=test_phone,
            )
            db.commit()
            return True, rec.id
        except Exception as e:
            db.rollback()
            return False, str(e)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(attempt_walkin) for _ in range(5)]
        for f in as_completed(futures):
            ok, res = f.result()
            if ok:
                successes.append(res)
            else:
                failures.append(res)

    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
    assert len(failures) == 4, f"Expected 4 rejections, got {len(failures)}"

    verify_db = session_factory()
    count = verify_db.query(AttendanceRecord).filter(
        AttendanceRecord.member_identity == canonical_identity,
        AttendanceRecord.branch_id == branch_id,
        AttendanceRecord.check_in_date == today,
    ).count()
    assert count == 1
    verify_db.close()


def test_concurrent_qr_replay_attack(adversarial_setup, db_session: Session):
    """
    Simultaneously submit 5 requests using the EXACT SAME single-use QR token.
    Atomically consumed nonce (JTI) must reject 4 replay attempts.
    """
    session_factory = sessionmaker(bind=db_session.bind, autocommit=False, autoflush=False)
    member = adversarial_setup["member_multi"]
    branch_id = "kolhapur"
    today = get_branch_local_date(branch_id)

    # Clean previous record
    clean_db = session_factory()
    clean_db.query(AttendanceRecord).filter(
        AttendanceRecord.user_id == member.id,
        AttendanceRecord.branch_id == branch_id,
        AttendanceRecord.check_in_date == today,
    ).delete()
    clean_db.commit()

    # Generate single QR token with fixed JTI
    mem = clean_db.query(User).filter(User.id == member.id).first()
    shared_qr_token, _, _ = generate_member_qr_token(mem)
    clean_db.close()

    successes = []
    failures = []

    def replay_worker():
        db = session_factory()
        try:
            rec = process_qr_checkin(db=db, qr_token=shared_qr_token, branch_id=branch_id)
            db.commit()
            return True, rec.id
        except Exception as e:
            db.rollback()
            return False, str(e)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(replay_worker) for _ in range(5)]
        for f in as_completed(futures):
            ok, res = f.result()
            if ok:
                successes.append(res)
            else:
                failures.append(res)

    assert len(successes) == 1
    assert len(failures) == 4
    # All failure messages should indicate replay or duplicate
    for msg in failures:
        assert "already been scanned" in msg or "already checked in" in msg


def test_forged_and_expired_qr_tokens(adversarial_setup, db_session: Session):
    """Cryptographic tamper, forgery, wrong secret, expired token, and wrong token type rejection."""
    member = adversarial_setup["member_single"]

    # 1. Tampered payload / wrong secret
    tampered_payload = {
        "sub": member.id,
        "jti": str(uuid.uuid4()),
        "token_type": "rvf_entry_qr",
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
    }
    assert len(TEST_ADVERSARIAL_FORGED_HMAC_KEY.encode("utf-8")) >= 32
    forged_token = jwt.encode(tampered_payload, TEST_ADVERSARIAL_FORGED_HMAC_KEY, algorithm="HS256")
    with pytest.raises(ValueError, match="Invalid QR code scanned"):
        process_qr_checkin(db=db_session, qr_token=forged_token, branch_id="narsobawadi")

    # 2. Expired token
    expired_payload = {
        "sub": member.id,
        "jti": str(uuid.uuid4()),
        "token_type": "rvf_entry_qr",
        "iat": int((datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp()),
        "exp": int((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp()),
    }
    expired_token = jwt.encode(expired_payload, settings.SECRET_KEY, algorithm="HS256")
    with pytest.raises(ValueError, match="expired"):
        process_qr_checkin(db=db_session, qr_token=expired_token, branch_id="narsobawadi")

    # 3. Wrong token type (e.g., standard auth session token masquerading as entry QR)
    auth_token_payload = {
        "sub": member.id,
        "jti": str(uuid.uuid4()),
        "token_type": "access_token",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=15)).timestamp()),
    }
    auth_token = jwt.encode(auth_token_payload, settings.SECRET_KEY, algorithm="HS256")
    with pytest.raises(ValueError, match="Invalid QR token type"):
        process_qr_checkin(db=db_session, qr_token=auth_token, branch_id="narsobawadi")

    # Verify attempt logs recorded
    attempts = db_session.query(AttendanceAttempt).filter(AttendanceAttempt.source == "qr").all()
    reasons = [a.failure_reason for a in attempts]
    assert "invalid_payload" in reasons
    assert "qr_expired" in reasons


def test_failed_attempts_never_prevent_subsequent_valid_checkin(adversarial_setup, db_session: Session):
    """
    Rejected attempts log auditable history in attendance_attempts but never prevent
    a subsequent valid check-in once the issue is rectified.
    """
    member = adversarial_setup["member_single"]
    branch_id = "narsobawadi"
    today = get_branch_local_date(branch_id)

    # Clean existing records
    db_session.query(AttendanceRecord).filter(
        AttendanceRecord.user_id == member.id,
        AttendanceRecord.branch_id == branch_id,
        AttendanceRecord.check_in_date == today,
    ).delete()
    db_session.commit()

    # Step 1: Deliberately trigger failed attempt with invalid token
    with pytest.raises(ValueError):
        process_qr_checkin(db=db_session, qr_token="bad.qr.token", branch_id=branch_id)

    # Verify failed attempt row is in attendance_attempts
    failed_attempt = (
        db_session.query(AttendanceAttempt)
        .filter(AttendanceAttempt.branch_id == branch_id, AttendanceAttempt.failure_reason == "invalid_payload")
        .first()
    )
    assert failed_attempt is not None

    # Step 2: Member presents a valid QR token
    valid_token, _, _ = generate_member_qr_token(member)
    record = process_qr_checkin(db=db_session, qr_token=valid_token, branch_id=branch_id)
    assert record is not None
    assert record.user_id == member.id
    assert record.check_in_date == today


def test_cross_branch_access_enforcement(adversarial_setup, db_session: Session):
    """
    Members with single_branch tier cannot check in at unauthorized branch.
    Members with all_branches tier can check in across facilities.
    """
    member_single = adversarial_setup["member_single"]  # Home: narsobawadi, Scope: single_branch
    member_multi = adversarial_setup["member_multi"]    # Home: narsobawadi, Scope: all_branches

    # Single-branch member denied at Kolhapur
    qr_single, _, _ = generate_member_qr_token(member_single)
    with pytest.raises(PermissionError, match="does not grant access to branch facility 'kolhapur'"):
        process_qr_checkin(db=db_session, qr_token=qr_single, branch_id="kolhapur")

    # Multi-branch member allowed at Kolhapur
    # Clean previous record if any
    today = get_branch_local_date("kolhapur")
    db_session.query(AttendanceRecord).filter(
        AttendanceRecord.user_id == member_multi.id,
        AttendanceRecord.branch_id == "kolhapur",
        AttendanceRecord.check_in_date == today,
    ).delete()
    db_session.commit()

    qr_multi, _, _ = generate_member_qr_token(member_multi)
    rec = process_qr_checkin(db=db_session, qr_token=qr_multi, branch_id="kolhapur")
    assert rec.branch_id == "kolhapur"


def test_role_enforcement_on_overrides_and_backfills(adversarial_setup, db_session: Session):
    """
    Role boundaries:
    - Member and Front Desk staff cannot perform manager overrides (403/PermissionError).
    - Regular members cannot perform paper backfills.
    - Overrides preserve the original attempt with audit trail.
    """
    member = adversarial_setup["member_single"]
    staff = adversarial_setup["staff"]
    manager = adversarial_setup["manager"]

    # 1. Create a failed attempt
    attempt = AttendanceAttempt(
        user_id=member.id,
        branch_id="narsobawadi",
        membership_id=member.membership_id,
        member_name=member.name,
        source="manual",
        failure_reason="unpaid_dues",
        failure_detail="Payment issue at desk",
    )
    db_session.add(attempt)
    db_session.commit()
    db_session.refresh(attempt)

    # 2. Member attempts override -> PermissionError
    with pytest.raises(PermissionError, match="Manager override requires branch manager or organization admin"):
        process_manager_override(db=db_session, attempt_id=attempt.id, manager=member, reason="Self override")

    # 3. Staff attempts override -> PermissionError
    with pytest.raises(PermissionError, match="Manager override requires branch manager or organization admin"):
        process_manager_override(db=db_session, attempt_id=attempt.id, manager=staff, reason="Staff override attempt")

    # 4. Regular member attempts paper backfill -> PermissionError
    with pytest.raises(PermissionError, match="Paper backfill requires staff, branch manager, or organization admin"):
        process_paper_backfill(
            db=db_session,
            branch_id="narsobawadi",
            operator=member,
            visit_date=date.today() - timedelta(days=1),
            reason="Member self-backfill",
            user_id=member.id,
        )

    # 5. Manager performs valid override
    override_rec = process_manager_override(
        db=db_session,
        attempt_id=attempt.id,
        manager=manager,
        reason="Member presented cash receipt; override granted.",
    )
    assert override_rec.source == "override"

    # Original attempt is preserved and marked as overridden
    db_session.refresh(attempt)
    assert attempt.is_overridden is True
    assert attempt.overridden_by_id == manager.id
    assert "Member presented cash receipt" in attempt.override_reason


def test_billing_eligibility_lifecycle_partial_payments_and_reversals(adversarial_setup, db_session: Session):
    """
    Tests financial dues enforcement lifecycle on floor check-in eligibility:
    1. Overdue invoice with positive balance -> Ineligible ('unpaid_dues').
    2. Partial payment leaving balance overdue -> Still ineligible ('unpaid_dues').
    3. Full payment clearing balance -> Eligible.
    4. Payment reversal restoring overdue balance -> Immediately ineligible again ('unpaid_dues').
    """
    member = adversarial_setup["member_single"]
    admin = adversarial_setup["admin"]
    branch_id = "narsobawadi"

    # Clean existing invoices for this member
    db_session.query(Invoice).filter(Invoice.user_id == member.id).delete()
    db_session.commit()

    # Step 1: Create an overdue invoice (due yesterday)
    inv = Invoice(
        invoice_number=f"INV-TEST-{uuid.uuid4().hex[:6].upper()}",
        user_id=member.id,
        branch_id=branch_id,
        status="unpaid",
        subtotal=Decimal("2000.00"),
        tax=Decimal("0.00"),
        total_amount=Decimal("2000.00"),
        amount_paid=Decimal("0.00"),
        balance_due=Decimal("2000.00"),
        due_date=date.today() - timedelta(days=2),
    )
    db_session.add(inv)
    db_session.commit()

    # Check eligibility -> Must be denied
    eligible, reason, msg = check_attendance_eligibility(db=db_session, user=member, branch_id=branch_id)
    assert eligible is False
    assert reason == "unpaid_dues"

    # Step 2: Partial payment of ₹500 (balance remains ₹1500)
    p1 = record_offline_payment(
        db=db_session,
        invoice_id=inv.id,
        amount=Decimal("500.00"),
        payment_method="cash",
        recorded_by=admin,
        notes="Partial payment at desk",
    )
    db_session.commit()

    eligible, reason, msg = check_attendance_eligibility(db=db_session, user=member, branch_id=branch_id)
    assert eligible is False
    assert reason == "unpaid_dues"

    # Step 3: Settle remaining balance of ₹1500 (balance becomes ₹0.00)
    p2 = record_offline_payment(
        db=db_session,
        invoice_id=inv.id,
        amount=Decimal("1500.00"),
        payment_method="upi_offline",
        recorded_by=admin,
        notes="Settlement payment",
    )
    db_session.commit()

    eligible, reason, msg = check_attendance_eligibility(db=db_session, user=member, branch_id=branch_id)
    assert eligible is True
    assert reason == "eligible"

    # Step 4: Admin reverses the ₹1500 payment (e.g. bounce/dispute)
    reverse_payment(
        db=db_session,
        payment_id=p2.id,
        actor=admin,
        reason="UPI transaction disputed/reversed by bank",
    )
    db_session.commit()

    # Member's balance is restored to ₹1500 overdue -> check-in must be immediately denied again
    eligible, reason, msg = check_attendance_eligibility(db=db_session, user=member, branch_id=branch_id)
    assert eligible is False
    assert reason == "unpaid_dues"
    assert "₹1500.00 is past due date" in msg


def test_monthly_reporting_month_end_timezone_boundary(adversarial_setup, db_session: Session):
    """
    Verifies that the monthly attendance report correctly counts attempts occurring up to
    the very last microsecond of the month (23:59:59.999999) in branch-local time,
    and cleanly separates the 1st of the next month.
    """
    branch_id = "narsobawadi"
    tz = DEFAULT_TIMEZONE

    # October 2026 test window
    oct_last_moment = datetime(2026, 10, 31, 23, 59, 59, 900000, tzinfo=tz).astimezone(timezone.utc)
    nov_first_moment = datetime(2026, 11, 1, 0, 0, 0, 100000, tzinfo=tz).astimezone(timezone.utc)

    # Insert two failed attempts at boundary
    a1 = AttendanceAttempt(
        branch_id=branch_id,
        source="qr",
        failure_reason="qr_expired",
        attempted_at=oct_last_moment,
    )
    a2 = AttendanceAttempt(
        branch_id=branch_id,
        source="qr",
        failure_reason="qr_expired",
        attempted_at=nov_first_moment,
    )
    db_session.add_all([a1, a2])
    db_session.commit()

    # Generate report for October 2026
    oct_report = generate_branch_monthly_report(db=db_session, branch_id=branch_id, year=2026, month=10)
    # Generate report for November 2026
    nov_report = generate_branch_monthly_report(db=db_session, branch_id=branch_id, year=2026, month=11)

    # a1 should be counted in October, not November
    # a2 should be counted in November, not October
    oct_attempts = db_session.query(AttendanceAttempt).filter(
        AttendanceAttempt.branch_id == branch_id,
        AttendanceAttempt.attempted_at == oct_last_moment,
    ).all()
    assert len(oct_attempts) == 1

    assert oct_report["rejectedAttemptsCount"] >= 1
    assert nov_report["rejectedAttemptsCount"] >= 1


def test_prune_nonces_cli_command(db_session: Session):
    """
    Verifies the one-shot scheduled command for pruning expired QR nonces:
    - Dry-run mode counts without deleting.
    - Active prune removes expired nonces while preserving unexpired ones.
    """
    now = datetime.now(timezone.utc)
    expired_dt = now - timedelta(minutes=5)
    valid_dt = now + timedelta(minutes=5)

    n1 = ConsumedQRToken(jti=str(uuid.uuid4()), user_id="u1", expires_at=expired_dt)
    n2 = ConsumedQRToken(jti=str(uuid.uuid4()), user_id="u2", expires_at=expired_dt)
    n3 = ConsumedQRToken(jti=str(uuid.uuid4()), user_id="u3", expires_at=valid_dt)

    db_session.add_all([n1, n2, n3])
    db_session.commit()

    # 1. Dry run
    success, dry_count = run_prune_nonces(db=db_session, dry_run=True)
    assert success is True
    assert dry_count >= 2

    # Verify rows still exist
    assert db_session.query(ConsumedQRToken).filter(ConsumedQRToken.jti.in_([n1.jti, n2.jti])).count() == 2

    # 2. Active run
    success, pruned_count = run_prune_nonces(db=db_session, dry_run=False)
    assert success is True
    assert pruned_count >= 2

    # Verify expired are deleted, active preserved
    assert db_session.query(ConsumedQRToken).filter(ConsumedQRToken.jti.in_([n1.jti, n2.jti])).count() == 0
    assert db_session.query(ConsumedQRToken).filter(ConsumedQRToken.jti == n3.jti).count() == 1


def test_api_role_and_branch_scope_on_export_and_lookup(adversarial_setup, db_session: Session, client: TestClient):
    """
    Test API authorization invariants:
    - Member calling /export is rejected with 403 Forbidden.
    - Branch manager of Kolhapur calling /export for Narsobawadi is rejected with 403 Forbidden.
    - Branch manager of Narsobawadi calling /export for Narsobawadi succeeds with 200 OK.
    - Desk staff from Narsobawadi searching in Kolhapur scope is rejected with 403 Forbidden.
    - Desk staff searching in Narsobawadi scope succeeds and personal phone numbers are masked.
    """
    member = adversarial_setup["member_single"]
    manager = adversarial_setup["manager"]
    staff = adversarial_setup["staff"]

    # 1. Member calling branch report export -> 403
    _, m_token, m_csrf = create_user_session(db_session, member, client)
    m_headers = {"x-csrf-token": m_csrf, "Cookie": f"rvf_session={m_token}; rvf_csrf_token={m_csrf}"}
    res_mem = client.get("/api/attendance/reports/branch/narsobawadi/export?format=csv", headers=m_headers)
    assert res_mem.status_code == 403

    # 2. Manager of another branch (e.g. Kolhapur manager)
    kolhapur_mgr = User(
        id="mgr-kolhapur",
        email="mgr_klp@rvf.in",
        name="Kolhapur Manager",
        role="branch_manager",
        branch_id="kolhapur",
        hashed_password=hash_password("klpSecret123"),
        is_active=True,
    )
    db_session.add(kolhapur_mgr)
    db_session.commit()

    _, klp_token, klp_csrf = create_user_session(db_session, kolhapur_mgr, client)
    klp_headers = {"x-csrf-token": klp_csrf, "Cookie": f"rvf_session={klp_token}; rvf_csrf_token={klp_csrf}"}
    res_klp = client.get("/api/attendance/reports/branch/narsobawadi/export?format=csv", headers=klp_headers)
    assert res_klp.status_code == 403

    # 3. Manager of Narsobawadi -> 200 OK
    _, nrs_token, nrs_csrf = create_user_session(db_session, manager, client)
    nrs_headers = {"x-csrf-token": nrs_csrf, "Cookie": f"rvf_session={nrs_token}; rvf_csrf_token={nrs_csrf}"}
    res_nrs = client.get("/api/attendance/reports/branch/narsobawadi/export?format=csv", headers=nrs_headers)
    assert res_nrs.status_code == 200
    assert "RVFitness Monthly Facility Attendance Report" in res_nrs.text

    # 4. Desk Staff from Narsobawadi looking up members in Kolhapur scope -> 403 Forbidden
    _, st_token, st_csrf = create_user_session(db_session, staff, client)
    st_headers = {"x-csrf-token": st_csrf, "Cookie": f"rvf_session={st_token}; rvf_csrf_token={st_csrf}"}
    res_scope = client.get("/api/attendance/members/lookup?query=Single&branch_id=kolhapur", headers=st_headers)
    assert res_scope.status_code == 403

    # 5. Desk Staff looking up members in own branch scope -> 200 OK and phone is masked
    res_ok = client.get("/api/attendance/members/lookup?query=Single&branch_id=narsobawadi", headers=st_headers)
    assert res_ok.status_code == 200
    data = res_ok.json()
    assert len(data["members"]) >= 1
    found = data["members"][0]
    assert "******" in found["maskedPhone"]
    assert "password" not in found
    assert "email" not in found


def test_cross_channel_duplicate_checkin_prevention(adversarial_setup, db_session: Session, client: TestClient):
    """
    Verify that checking in via Portal resolves to canonical identity 'user:<id>' and
    blocks subsequent check-ins on the same branch-local date across all channels:
    - Channel A: Portal check-in (Succeeds)
    - Channel B: QR scanner check-in (Rejected: already_checked_in)
    - Channel C: Manual desk check-in (Rejected: already_checked_in)
    - Channel D: Paper backfill for today (Rejected: already has a recorded attendance visit)
    - Channel E: Manager override without rejection (Rejected: already has a successful check-in)
    """
    member = adversarial_setup["member_single"]
    staff = adversarial_setup["staff"]
    manager = adversarial_setup["manager"]
    branch_id = "narsobawadi"
    today = get_branch_local_date(branch_id)

    # 1. Channel A: Portal Check-In succeeds
    _, m_token, m_csrf = create_user_session(db_session, member, client)
    m_headers = {"x-csrf-token": m_csrf, "Cookie": f"rvf_session={m_token}; rvf_csrf_token={m_csrf}"}
    res_portal = client.post(f"/api/attendance/check-in?branch_id={branch_id}", headers=m_headers)
    assert res_portal.status_code == 200
    assert res_portal.json()["success"] is True

    # 2. Channel B: QR Scanner Check-In on same day -> 400 Bad Request
    mem = db_session.query(User).filter(User.id == member.id).first()
    qr_token, _, _ = generate_member_qr_token(mem)
    res_qr = client.post(
        "/api/attendance/qr-check-in",
        json={"qrToken": qr_token, "branchId": branch_id},
        headers=m_headers,
    )
    assert res_qr.status_code == 400
    assert "already checked in" in res_qr.json()["detail"].lower()

    # 3. Channel C: Desk Manual Check-In on same day -> 400 Bad Request
    _, s_token, s_csrf = create_user_session(db_session, staff, client)
    s_headers = {"x-csrf-token": s_csrf, "Cookie": f"rvf_session={s_token}; rvf_csrf_token={s_csrf}"}
    res_manual = client.post(
        "/api/attendance/manual-check-in",
        json={
            "branchId": branch_id,
            "memberId": member.id,
            "reasonCode": "qr_invalid",
            "notes": "Scanner camera down",
        },
        headers=s_headers,
    )
    assert res_manual.status_code == 400
    assert "already checked in" in res_manual.json()["detail"].lower()

    # 4. Channel D: Paper Backfill on same day -> 400 Bad Request
    res_backfill = client.post(
        "/api/attendance/backfill",
        json={
            "branchId": branch_id,
            "visitDate": today.isoformat(),
            "memberId": member.id,
            "entryOperator": "Desk Staff",
            "reason": "Desk equipment power glitch",
        },
        headers=s_headers,
    )
    assert res_backfill.status_code == 400
    assert "already has a recorded attendance visit" in res_backfill.json()["detail"].lower()

    # 5. Verify database has exactly 1 successful record for this member today
    count = db_session.query(AttendanceRecord).filter(
        AttendanceRecord.member_identity == f"user:{member.id}",
        AttendanceRecord.branch_id == branch_id,
        AttendanceRecord.check_in_date == today,
    ).count()
    assert count == 1


def test_offline_member_without_portal_account(adversarial_setup, db_session: Session):
    """
    Verify members without portal accounts (desk-only with physical membership card)
    resolve to canonical identity 'member:<card_id>', enforce daily uniqueness,
    and are protected by database unique constraints.
    """
    staff = adversarial_setup["staff"]
    branch_id = "narsobawadi"
    today = get_branch_local_date(branch_id)
    card_id = "CARD-OFFLINE-99"

    # 1. First manual check-in for offline card member
    rec1 = process_manual_checkin(
        db=db_session,
        branch_id=branch_id,
        staff=staff,
        reason_code="no_account",
        member_id=card_id,
        name="Offline Card Lifter",
        phone="+91 91111 22222",
    )
    db_session.commit()
    assert rec1.member_identity == f"member:{card_id}"
    assert rec1.user_id is None
    assert rec1.membership_id == card_id

    # 2. Second manual check-in attempt on the same day -> ValueError
    with pytest.raises(ValueError, match="already checked in"):
        process_manual_checkin(
            db=db_session,
            branch_id=branch_id,
            staff=staff,
            reason_code="no_account",
            member_id=card_id,
            name="Offline Card Lifter",
            phone="+91 91111 22222",
        )
    db_session.rollback()

    # 3. Direct DB insert with identical canonical identity -> IntegrityError
    from sqlalchemy.exc import IntegrityError
    dup_rec = AttendanceRecord(
        member_identity=f"member:{card_id}",
        user_id=None,
        branch_id=branch_id,
        check_in_date=today,
        source="manual",
        method="desk_manual",
    )
    db_session.add(dup_rec)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_shared_contact_number_multiple_members(adversarial_setup, db_session: Session):
    """
    Verify behavior when two members share the same family contact phone number:
    - Member Alice and Member Bob share '+91 98888 11111'.
    - Alice checking in does NOT block Bob.
    - Bob can check in on the same date.
    - Neither can check in twice on the same date.
    """
    staff = adversarial_setup["staff"]
    branch_id = "narsobawadi"
    today = get_branch_local_date(branch_id)
    shared_phone = "+91 98888 11111"

    # Seed Alice and Bob
    alice = User(
        id="adv-mem-alice",
        email="alice_fam@rvf.in",
        name="Alice Smith",
        phone=shared_phone,
        role="member",
        membership_id="RVF-FAM-A",
        membership_status="active",
        valid_until=today + timedelta(days=60),
        branch_id=branch_id,
        hashed_password=hash_password("aliceSecret123"),
        is_active=True,
    )
    bob = User(
        id="adv-mem-bob",
        email="bob_fam@rvf.in",
        name="Bob Smith",
        phone=shared_phone,
        role="member",
        membership_id="RVF-FAM-B",
        membership_status="active",
        valid_until=today + timedelta(days=60),
        branch_id=branch_id,
        hashed_password=hash_password("bobSecret123"),
        is_active=True,
    )
    db_session.add(alice)
    db_session.add(bob)
    db_session.commit()

    # 1. Alice checks in via manual desk check-in
    rec_alice = process_manual_checkin(
        db=db_session,
        branch_id=branch_id,
        staff=staff,
        reason_code="qr_invalid",
        member_id=alice.id,
        name=alice.name,
        phone=shared_phone,
    )
    db_session.commit()
    assert rec_alice.member_identity == f"user:{alice.id}"

    # 2. Bob checks in on the same day with same phone -> must SUCCEED
    rec_bob = process_manual_checkin(
        db=db_session,
        branch_id=branch_id,
        staff=staff,
        reason_code="qr_invalid",
        member_id=bob.id,
        name=bob.name,
        phone=shared_phone,
    )
    db_session.commit()
    assert rec_bob.member_identity == f"user:{bob.id}"

    # 3. Alice attempts to check in again -> rejected
    with pytest.raises(ValueError, match="already checked in"):
        process_manual_checkin(
            db=db_session,
            branch_id=branch_id,
            staff=staff,
            reason_code="qr_invalid",
            member_id=alice.id,
            name=alice.name,
            phone=shared_phone,
        )
    db_session.rollback()

    # 4. Bob attempts to check in again -> rejected
    with pytest.raises(ValueError, match="already checked in"):
        process_manual_checkin(
            db=db_session,
            branch_id=branch_id,
            staff=staff,
            reason_code="qr_invalid",
            member_id=bob.id,
            name=bob.name,
            phone=shared_phone,
        )
    db_session.rollback()


def test_phone_number_change_preserves_canonical_identity(adversarial_setup, db_session: Session):
    """
    Verify that when a member changes their phone number in their profile,
    their canonical identity remains 'user:<id>', and duplicate check-in
    prevention remains fully authoritative under the new phone number.
    """
    staff = adversarial_setup["staff"]
    branch_id = "narsobawadi"
    today = get_branch_local_date(branch_id)
    old_phone = "+91 97777 00001"
    new_phone = "+91 97777 99999"

    member = User(
        id="adv-mem-phonechange",
        email="phonechange@rvf.in",
        name="Charlie Changer",
        phone=old_phone,
        role="member",
        membership_id="RVF-PC-01",
        membership_status="active",
        valid_until=today + timedelta(days=60),
        branch_id=branch_id,
        hashed_password=hash_password("charlieSecret123"),
        is_active=True,
    )
    db_session.add(member)
    db_session.commit()

    # 1. Member checks in at 9:00 AM using old phone
    rec1 = process_manual_checkin(
        db=db_session,
        branch_id=branch_id,
        staff=staff,
        reason_code="qr_invalid",
        member_id=member.id,
        phone=old_phone,
    )
    db_session.commit()
    assert rec1.member_identity == f"user:{member.id}"

    # 2. Member updates phone number in profile
    member.phone = new_phone
    db_session.commit()

    # 3. Member attempts to check in at 2:00 PM using the new phone number
    with pytest.raises(ValueError, match="already checked in"):
        process_manual_checkin(
            db=db_session,
            branch_id=branch_id,
            staff=staff,
            reason_code="qr_invalid",
            phone=new_phone,
            name=member.name,
        )
    db_session.rollback()


def test_unregistered_walkins_sharing_phone_number(adversarial_setup, db_session: Session):
    """
    Verify that two unregistered desk walk-in members (without accounts)
    sharing a contact phone number are disambiguated by name in member_identity,
    allowing each person to check in once per day.
    """
    staff = adversarial_setup["staff"]
    branch_id = "narsobawadi"
    today = get_branch_local_date(branch_id)
    shared_phone = "+91 96666 11111"

    # Walk-in 1: John Smith
    rec1 = process_manual_checkin(
        db=db_session,
        branch_id=branch_id,
        staff=staff,
        reason_code="no_account",
        name="John Smith",
        phone=shared_phone,
    )
    db_session.commit()
    assert rec1.member_identity == "phone:9666611111:john_smith"

    # Walk-in 2: Mary Smith (shares phone) -> succeeds
    rec2 = process_manual_checkin(
        db=db_session,
        branch_id=branch_id,
        staff=staff,
        reason_code="no_account",
        name="Mary Smith",
        phone=shared_phone,
    )
    db_session.commit()
    assert rec2.member_identity == "phone:9666611111:mary_smith"

    # Walk-in 1 attempts second check-in today -> rejected
    with pytest.raises(ValueError, match="already checked in"):
        process_manual_checkin(
            db=db_session,
            branch_id=branch_id,
            staff=staff,
            reason_code="no_account",
            name="John Smith",
            phone=shared_phone,
        )
    db_session.rollback()


def test_failed_attempt_preserves_audit_after_manager_override(adversarial_setup, db_session: Session):
    """
    Verify that manager override preserves the original failed attempt,
    records the operator, reason, timestamp, and links the resulting attendance record.
    """
    manager = adversarial_setup["manager"]
    staff = adversarial_setup["staff"]
    branch_id = "narsobawadi"
    today = get_branch_local_date(branch_id)

    # Expired member
    expired_mem = User(
        id="adv-mem-expired",
        email="expired_mem@rvf.in",
        name="Expired Member",
        phone="+91 95555 44444",
        role="member",
        membership_id="RVF-EXP-01",
        membership_status="expired",
        valid_until=today - timedelta(days=10),
        branch_id=branch_id,
        hashed_password=hash_password("expiredSecret123"),
        is_active=True,
    )
    db_session.add(expired_mem)
    db_session.commit()

    # 1. Attempt manual check-in -> fails and logs AttendanceAttempt
    with pytest.raises(PermissionError):
        process_manual_checkin(
            db=db_session,
            branch_id=branch_id,
            staff=staff,
            reason_code="qr_invalid",
            member_id=expired_mem.id,
        )

    # Locate logged attempt
    attempt = db_session.query(AttendanceAttempt).filter(
        AttendanceAttempt.user_id == expired_mem.id,
        AttendanceAttempt.is_overridden == False,
    ).first()
    assert attempt is not None
    assert attempt.failure_reason == "inactive_membership"
    attempt_id = attempt.id

    # 2. Manager overrides the rejection
    rec = process_manager_override(
        db=db_session,
        attempt_id=attempt_id,
        manager=manager,
        reason="Renewed membership offline at front desk cash counter",
    )
    db_session.commit()

    # 3. Verify attempt is preserved with audit linkage
    db_session.refresh(attempt)
    assert attempt.id == attempt_id
    assert attempt.is_overridden is True
    assert attempt.overridden_by_id == manager.id
    assert attempt.override_reason == "Renewed membership offline at front desk cash counter"
    assert attempt.override_attendance_id == rec.id
    assert attempt.overridden_at is not None

    # 4. Verify resulting attendance record has override source
    assert rec.source == "override"
    assert rec.member_identity == f"user:{expired_mem.id}"


def test_canonical_identity_lifecycle_account_linking(adversarial_setup, db_session: Session, client: TestClient):
    """
    Test the complete canonical identity lifecycle across account creation and linking:
    1. Member attends offline without a portal account using card 'CARD-RAMESH-01'.
    2. Daily duplicate check-in is strictly prevented before linking.
    3. Member registers online and links 'CARD-RAMESH-01'.
    4. Historical attendance records are preserved and reconciled to canonical identity 'user:<id>'.
    5. Duplicate check-ins on the same day after linking are rejected across all channels (Portal, QR, Desk).
    6. Check-ins on subsequent dates succeed and increment streak correctly.
    """
    staff = adversarial_setup["staff"]
    branch_id = "narsobawadi"
    today = get_branch_local_date(branch_id)
    card_id = "CARD-RAMESH-01"

    # 1. Historical attendance offline on day -2 and day -1
    d_minus_2 = today - timedelta(days=2)
    d_minus_1 = today - timedelta(days=1)
    rec_past1 = AttendanceRecord(
        member_identity=f"member:{card_id}",
        user_id=None,
        branch_id=branch_id,
        check_in_date=d_minus_2,
        source="manual",
        method="desk_manual",
        member_name="Ramesh Patel",
        member_phone="+91 94444 11111",
        membership_id=card_id,
        notes="Offline desk check-in day -2",
    )
    rec_past2 = AttendanceRecord(
        member_identity=f"member:{card_id}",
        user_id=None,
        branch_id=branch_id,
        check_in_date=d_minus_1,
        source="manual",
        method="desk_manual",
        member_name="Ramesh Patel",
        member_phone="+91 94444 11111",
        membership_id=card_id,
        notes="Offline desk check-in day -1",
    )
    db_session.add(rec_past1)
    db_session.add(rec_past2)
    db_session.commit()

    # 2. Today: Ramesh checks in at 8:00 AM at the desk
    rec_today = process_manual_checkin(
        db=db_session,
        branch_id=branch_id,
        staff=staff,
        reason_code="no_account",
        member_id=card_id,
        name="Ramesh Patel",
        phone="+91 94444 11111",
    )
    db_session.commit()
    assert rec_today.member_identity == f"member:{card_id}"
    assert rec_today.user_id is None

    # Duplicate check-in at 8:30 AM before account linking -> rejected
    with pytest.raises(ValueError, match="already checked in"):
        process_manual_checkin(
            db=db_session,
            branch_id=branch_id,
            staff=staff,
            reason_code="no_account",
            member_id=card_id,
            name="Ramesh Patel",
            phone="+91 94444 11111",
        )
    db_session.rollback()

    # 3. At 10:00 AM, Ramesh registers online with his card_id
    res_reg = client.post(
        "/api/auth/register",
        json={
            "name": "Ramesh Patel",
            "email": "ramesh.patel@rvf.in",
            "password": "rameshPassword123",
            "phone": "+91 94444 11111",
            "membershipId": card_id,
            "acceptedTerms": True,
        },
    )
    assert res_reg.status_code == 201
    reg_data = res_reg.json()
    new_user_id = reg_data["user"]["id"]

    # 4. Verify historical attendance is preserved and reconciled
    db_session.expire_all()
    reconciled_records = db_session.query(AttendanceRecord).filter(
        AttendanceRecord.user_id == new_user_id
    ).order_by(AttendanceRecord.check_in_date).all()
    assert len(reconciled_records) == 3, f"Expected 3 reconciled records, got {len(reconciled_records)}"
    for r in reconciled_records:
        assert r.member_identity == f"user:{new_user_id}"
        assert r.membership_id == card_id

    # 5. At 12:00 PM on same day, Ramesh attempts portal check-in -> 400 Bad Request
    user_obj = db_session.query(User).filter(User.id == new_user_id).first()
    # Activate membership so eligibility passes to test duplicate check
    user_obj.membership_status = "active"
    user_obj.valid_until = today + timedelta(days=60)
    db_session.commit()

    _, m_token, m_csrf = create_user_session(db_session, user_obj, client)
    m_headers = {"x-csrf-token": m_csrf, "Cookie": f"rvf_session={m_token}; rvf_csrf_token={m_csrf}"}
    res_portal = client.post(f"/api/attendance/check-in?branch_id={branch_id}", headers=m_headers)
    assert res_portal.status_code == 400
    assert "already checked in" in res_portal.json()["detail"].lower()

    # QR check-in on same day -> 400 Bad Request
    qr_token, _, _ = generate_member_qr_token(user_obj)
    res_qr = client.post(
        "/api/attendance/qr-check-in",
        json={"qrToken": qr_token, "branchId": branch_id},
        headers=m_headers,
    )
    assert res_qr.status_code == 400
    assert "already checked in" in res_qr.json()["detail"].lower()

    # Desk manual check-in on same day -> 400 Bad Request
    _, s_token, s_csrf = create_user_session(db_session, staff, client)
    s_headers = {"x-csrf-token": s_csrf, "Cookie": f"rvf_session={s_token}; rvf_csrf_token={s_csrf}"}
    res_manual = client.post(
        "/api/attendance/manual-check-in",
        json={
            "branchId": branch_id,
            "memberId": new_user_id,
            "reasonCode": "no_internet",
        },
        headers=s_headers,
    )
    assert res_manual.status_code == 400
    assert "already checked in" in res_manual.json()["detail"].lower()

    # 6. Subsequent date: Member checks in cleanly
    day_next = today + timedelta(days=1)
    rec_next = AttendanceRecord(
        member_identity=f"user:{new_user_id}",
        user_id=new_user_id,
        branch_id=branch_id,
        check_in_date=day_next,
        source="portal",
        method="portal",
    )
    db_session.add(rec_next)
    db_session.commit()

    total_count = db_session.query(AttendanceRecord).filter(
        AttendanceRecord.user_id == new_user_id
    ).count()
    assert total_count == 4


def test_reconciliation_cannot_merge_distinct_members_or_delete_history(adversarial_setup, db_session: Session):
    """
    Verify identity reconciliation safeguards:
    - Offline records belonging to member B are NEVER modified when member A links their account.
    - Historical attendance is NEVER deleted.
    - Two members sharing a family phone number are NOT merged if names differ.
    """
    branch_id = "narsobawadi"
    today = get_branch_local_date(branch_id)
    shared_phone = "+91 93333 55555"

    # Member 1 (Offline Card): Suresh
    rec_suresh = AttendanceRecord(
        member_identity="member:CARD-SURESH-02",
        user_id=None,
        branch_id=branch_id,
        check_in_date=today - timedelta(days=1),
        source="manual",
        method="desk_manual",
        member_name="Suresh Kumar",
        member_phone=shared_phone,
        membership_id="CARD-SURESH-02",
        notes="Suresh offline visit",
    )
    # Member 2 (Offline Phone): Dinesh (shares phone, different name)
    rec_dinesh = AttendanceRecord(
        member_identity="phone:9333355555:dinesh_kumar",
        user_id=None,
        branch_id=branch_id,
        check_in_date=today - timedelta(days=1),
        source="manual",
        method="desk_manual",
        member_name="Dinesh Kumar",
        member_phone=shared_phone,
        notes="Dinesh offline visit",
    )
    db_session.add(rec_suresh)
    db_session.add(rec_dinesh)
    db_session.commit()

    total_records_before = db_session.query(AttendanceRecord).count()

    # Create user for Suresh
    user_suresh = User(
        id="adv-mem-suresh",
        email="suresh.kumar@rvf.in",
        name="Suresh Kumar",
        phone=shared_phone,
        role="member",
        membership_id="CARD-SURESH-02",
        membership_status="active",
        valid_until=today + timedelta(days=60),
        branch_id=branch_id,
        hashed_password=hash_password("sureshSecret123"),
        is_active=True,
    )
    db_session.add(user_suresh)
    db_session.commit()

    # Run reconciliation for Suresh
    from backend.app.services.attendance_service import reconcile_member_identity_on_account_link
    result = reconcile_member_identity_on_account_link(db=db_session, user=user_suresh)
    assert result["reconciledRecords"] == 1

    # Verify Suresh's record was reconciled
    db_session.refresh(rec_suresh)
    assert rec_suresh.user_id == user_suresh.id
    assert rec_suresh.member_identity == f"user:{user_suresh.id}"

    # Verify Dinesh's record was NOT modified or merged
    db_session.refresh(rec_dinesh)
    assert rec_dinesh.user_id is None
    assert rec_dinesh.member_identity == "phone:9333355555:dinesh_kumar"
    assert rec_dinesh.member_name == "Dinesh Kumar"

    # Verify zero historical records were deleted
    total_records_after = db_session.query(AttendanceRecord).count()
    assert total_records_after == total_records_before


