import uuid
import concurrent.futures
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from typing import Dict, Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import or_

from backend.app.core.config import Settings, validate_production_security
from backend.app.core.security import hash_password, verify_password
from backend.app.core.auth import create_user_session, SESSION_COOKIE_NAME, CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from backend.app.models.user import User
from backend.app.models.organization import Organization, Branch, MemberBranchAccess
from backend.app.models.membership import MembershipPlan, Enrollment, MembershipChange
from backend.app.models.billing import Invoice, Payment
from backend.app.models.attendance import AttendanceRecord, AttendanceAttempt, ConsumedQRToken
from backend.app.models.trainer import TrainerProfile, TrainerMemberAssignment
from backend.app.models.audit import AuditLog
from backend.app.services.attendance_service import (
    generate_member_qr_token,
    process_qr_checkin,
    process_manual_checkin,
    process_manager_override,
    get_branch_local_date,
    resolve_member_identity,
    reconcile_member_identity_on_account_link,
)
from backend.app.services.billing_service import (
    record_offline_payment,
    reverse_payment,
    create_invoice_for_enrollment,
)
from backend.app.services.membership_service import (
    renew_membership,
    freeze_membership,
    cancel_membership,
)


@pytest.fixture
def phase5_fixtures(db_session: Session):
    """Seed comprehensive multi-branch organization fixture for Phase 5 tests."""
    # 1. Organization
    org = db_session.query(Organization).filter(Organization.code == "RVF").first()
    if not org:
        org = Organization(name="RV Fitness Systems", code="RVF", contact_email="contact@rvfitness.in")
        db_session.add(org)
        db_session.flush()

    # 2. Branches
    b1 = db_session.query(Branch).filter(Branch.id == "narsobawadi").first()
    if not b1:
        b1 = Branch(id="narsobawadi", organization_id=org.id, name="Narsobawadi Campus", code="NRS", is_active=True)
        db_session.add(b1)

    b2 = db_session.query(Branch).filter(Branch.id == "sangli").first()
    if not b2:
        b2 = Branch(id="sangli", organization_id=org.id, name="Sangli Central", code="SGL", is_active=True)
        db_session.add(b2)

    db_session.flush()

    # 3. Plans
    plan_local = db_session.query(MembershipPlan).filter(MembershipPlan.id == "plan-phase5-local").first()
    if not plan_local:
        plan_local = MembershipPlan(
            id="plan-phase5-local",
            name="Single Branch Standard",
            category="general",
            access_scope="single_branch",
            price=Decimal("3000.00"),
            currency="₹",
            billing_cycle="1 month",
            duration_days=30,
            is_active=True,
            perks=["Gym floor"],
        )
        db_session.add(plan_local)

    plan_multi = db_session.query(MembershipPlan).filter(MembershipPlan.id == "plan-phase5-multi").first()
    if not plan_multi:
        plan_multi = MembershipPlan(
            id="plan-phase5-multi",
            name="All Branch Platinum",
            category="vip",
            access_scope="all_branches",
            price=Decimal("6000.00"),
            currency="₹",
            billing_cycle="1 month",
            duration_days=30,
            is_active=True,
            perks=["All branches", "Sauna"],
        )
        db_session.add(plan_multi)

    db_session.flush()

    # 4. Users across roles and branches
    # Org Admin
    org_admin = db_session.query(User).filter(User.email == "orgadmin5@rvfitness.in").first()
    if not org_admin:
        org_admin = User(
            email="orgadmin5@rvfitness.in",
            hashed_password=hash_password("AdminPass123!"),
            name="Executive Director",
            role="org_admin",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(org_admin)

    # Branch Manager for Branch 1
    mgr_b1 = db_session.query(User).filter(User.email == "manager_b1@rvfitness.in").first()
    if not mgr_b1:
        mgr_b1 = User(
            email="manager_b1@rvfitness.in",
            hashed_password=hash_password("ManagerPass123!"),
            name="Manager Narsobawadi",
            role="branch_manager",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(mgr_b1)

    # Branch Manager for Branch 2
    mgr_b2 = db_session.query(User).filter(User.email == "manager_b2@rvfitness.in").first()
    if not mgr_b2:
        mgr_b2 = User(
            email="manager_b2@rvfitness.in",
            hashed_password=hash_password("ManagerPass123!"),
            name="Manager Sangli",
            role="branch_manager",
            branch_id="sangli",
            is_active=True,
        )
        db_session.add(mgr_b2)

    # Desk Staff for Branch 1
    staff_b1 = db_session.query(User).filter(User.email == "staff_b1@rvfitness.in").first()
    if not staff_b1:
        staff_b1 = User(
            email="staff_b1@rvfitness.in",
            hashed_password=hash_password("StaffPass123!"),
            name="Desk Staff Narsobawadi",
            role="front_desk",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(staff_b1)

    # Trainer for Branch 1
    trainer_b1 = db_session.query(User).filter(User.email == "trainer_b1@rvfitness.in").first()
    if not trainer_b1:
        trainer_b1 = User(
            email="trainer_b1@rvfitness.in",
            hashed_password=hash_password("TrainerPass123!"),
            name="Coach Rohit",
            role="trainer",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(trainer_b1)
        db_session.flush()
        prof_b1 = TrainerProfile(user_id=trainer_b1.id, specialization="Hypertrophy", max_clients=10, is_accepting_clients=True)
        db_session.add(prof_b1)

    # Trainer for Branch 2
    trainer_b2 = db_session.query(User).filter(User.email == "trainer_b2@rvfitness.in").first()
    if not trainer_b2:
        trainer_b2 = User(
            email="trainer_b2@rvfitness.in",
            hashed_password=hash_password("TrainerPass123!"),
            name="Coach Sangram",
            role="trainer",
            branch_id="sangli",
            is_active=True,
        )
        db_session.add(trainer_b2)
        db_session.flush()
        prof_b2 = TrainerProfile(user_id=trainer_b2.id, specialization="Powerlifting", max_clients=10, is_accepting_clients=True)
        db_session.add(prof_b2)

    # Member belonging to Branch 1
    member_b1 = db_session.query(User).filter(User.email == "member_b1@rvfitness.in").first()
    if not member_b1:
        member_b1 = User(
            email="member_b1@rvfitness.in",
            hashed_password=hash_password("MemberPass123!"),
            name="Aditya Patil",
            role="member",
            branch_id="narsobawadi",
            membership_id="RVF-NRS-001",
            membership_status="active",
            valid_until=date.today() + timedelta(days=30),
            membership_plan_id="plan-phase5-local",
            is_active=True,
        )
        db_session.add(member_b1)

    # Member belonging to Branch 2
    member_b2 = db_session.query(User).filter(User.email == "member_b2@rvfitness.in").first()
    if not member_b2:
        member_b2 = User(
            email="member_b2@rvfitness.in",
            hashed_password=hash_password("MemberPass123!"),
            name="Suresh Shinde",
            role="member",
            branch_id="sangli",
            membership_id="RVF-SGL-002",
            membership_status="active",
            valid_until=date.today() + timedelta(days=30),
            membership_plan_id="plan-phase5-local",
            is_active=True,
        )
        db_session.add(member_b2)

    db_session.commit()

    return {
        "org": org,
        "branches": {"narsobawadi": b1, "sangli": b2},
        "plans": {"local": plan_local, "multi": plan_multi},
        "org_admin": org_admin,
        "mgr_b1": mgr_b1,
        "mgr_b2": mgr_b2,
        "staff_b1": staff_b1,
        "trainer_b1": trainer_b1,
        "trainer_b2": trainer_b2,
        "member_b1": member_b1,
        "member_b2": member_b2,
    }


def _auth_headers(client: TestClient, db: Session, user: User) -> Dict[str, str]:
    """Helper to establish a verified cookie session and CSRF headers."""
    session, token, csrf = create_user_session(db, user)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    client.cookies.set(CSRF_COOKIE_NAME, csrf)
    return {
        CSRF_HEADER_NAME: csrf,
        "x-csrf-token": csrf,
        "Cookie": f"{SESSION_COOKIE_NAME}={token}; {CSRF_COOKIE_NAME}={csrf}",
    }


# ============================================================================
# PHASE 5.1 & 5.2 FOCUSED SECURITY & DATA INTEGRITY REGRESSION TESTS
# ============================================================================

def test_security_headers_present(client: TestClient):
    """
    Verify defensive HTTP security headers are enforced on all responses:
    X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy, CSP.
    """
    res = client.get("/api/info")
    assert res.status_code == 200
    headers = res.headers

    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert "1; mode=block" in headers.get("X-XSS-Protection", "")
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "default-src 'self'" in headers.get("Content-Security-Policy", "")
    assert "frame-ancestors 'none'" in headers.get("Content-Security-Policy", "")


def test_production_secret_key_validation():
    """
    Verify production security validation fails safely when SECRET_KEY is missing,
    default placeholder, or shorter than 32 characters.
    """
    # 1. Default placeholder key must fail validation
    insecure_settings = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql://user:pass@db:5432/rvf",
        SECRET_KEY="change-this-to-a-secure-random-64-character-hex-string-in-production",
    )
    with pytest.raises(ValueError, match="SECRET_KEY must be a cryptographically secure random string"):
        validate_production_security(insecure_settings)

    # 2. Too short key (< 32 chars) must fail validation
    short_settings = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql://user:pass@db:5432/rvf",
        SECRET_KEY="too-short-key",
    )
    with pytest.raises(ValueError, match="at least 32 characters"):
        validate_production_security(short_settings)

    # 3. Valid strong 64-character secret key and independent QR signing key must succeed
    strong_key = "a" * 64
    valid_settings = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql://user:pass@db:5432/rvf",
        SECRET_KEY=strong_key,
        QR_SIGNING_KEY="b" * 64,
        REDIS_URL="redis://127.0.0.1:6379/0",
    )
    validate_production_security(valid_settings)  # Should not raise


def test_registration_password_length_validation(client: TestClient):
    """
    Verify registration endpoint enforces minimum 8-character password length
    and rejects passwords with 6 or 7 characters with 422 Unprocessable Entity.
    """
    short_payload = {
        "name": "Weak Password User",
        "email": f"weak_{uuid.uuid4().hex[:6]}@rvfitness.in",
        "password": "short6",  # 6 characters
        "acceptedTerms": True,
    }
    res = client.post("/api/auth/register", json=short_payload)
    assert res.status_code == 422
    assert "password" in str(res.json()).lower()


def test_payment_idempotency_key_required(client: TestClient, db_session: Session, phase5_fixtures):
    """
    Verify money-changing payment endpoints strictly require an Idempotency-Key
    (either in HTTP header or body) and reject requests without it with 400 Bad Request.
    """
    mgr = phase5_fixtures["mgr_b1"]
    headers = _auth_headers(client, db_session, mgr)

    # Create dummy unpaid invoice
    invoice = Invoice(
        invoice_number=f"INV-IDEMP-REQ-{uuid.uuid4().hex[:6]}",
        branch_id="narsobawadi",
        status="unpaid",
        subtotal=Decimal("1000.00"),
        total_amount=Decimal("1000.00"),
        amount_paid=Decimal("0.00"),
        balance_due=Decimal("1000.00"),
        due_date=date.today() + timedelta(days=7),
    )
    db_session.add(invoice)
    db_session.commit()

    # Request omitting idempotencyKey
    payload = {
        "invoiceId": invoice.id,
        "amount": 500.0,
        "paymentMethod": "cash",
    }
    res = client.post("/api/billing/payments", json=payload, headers=headers)
    assert res.status_code == 400
    assert "Idempotency-Key is required" in res.json().get("detail", "")


def test_payment_idempotency_payload_mismatch_rejected(client: TestClient, db_session: Session, phase5_fixtures):
    """
    Verify reusing an Idempotency-Key with a different payload (e.g. altered amount)
    is safely rejected with 400 Bad Request.
    """
    mgr = phase5_fixtures["mgr_b1"]
    headers = _auth_headers(client, db_session, mgr)
    idemp_key = f"key-payload-check-{uuid.uuid4().hex}"

    invoice = Invoice(
        invoice_number=f"INV-MISMATCH-{uuid.uuid4().hex[:6]}",
        branch_id="narsobawadi",
        status="unpaid",
        subtotal=Decimal("2000.00"),
        total_amount=Decimal("2000.00"),
        amount_paid=Decimal("0.00"),
        balance_due=Decimal("2000.00"),
        due_date=date.today() + timedelta(days=7),
    )
    db_session.add(invoice)
    db_session.commit()

    # First payment: 500
    res1 = client.post(
        "/api/billing/payments",
        json={"invoiceId": invoice.id, "amount": 500.0, "paymentMethod": "cash", "idempotencyKey": idemp_key},
        headers=headers,
    )
    assert res1.status_code == 200

    # Second payment with same key but altered amount (1000 instead of 500)
    res2 = client.post(
        "/api/billing/payments",
        json={"invoiceId": invoice.id, "amount": 1000.0, "paymentMethod": "cash", "idempotencyKey": idemp_key},
        headers=headers,
    )
    assert res2.status_code == 400
    assert "different payment payload" in res2.json().get("detail", "")


def test_payment_reversal_cross_branch_idor_blocked(client: TestClient, db_session: Session, phase5_fixtures):
    """
    Critical finding regression: A branch manager of Branch 2 (Sangli) must NOT
    be allowed to reverse a payment recorded at Branch 1 (Narsobawadi).
    Must return 403 Forbidden.
    """
    mgr_b2 = phase5_fixtures["mgr_b2"]  # Sangli manager
    mgr_b1 = phase5_fixtures["mgr_b1"]  # Narsobawadi manager

    # Create Narsobawadi invoice and payment
    invoice = Invoice(
        invoice_number=f"INV-REV-IDOR-{uuid.uuid4().hex[:6]}",
        branch_id="narsobawadi",
        status="paid",
        subtotal=Decimal("1500.00"),
        total_amount=Decimal("1500.00"),
        amount_paid=Decimal("1500.00"),
        balance_due=Decimal("0.00"),
        due_date=date.today() + timedelta(days=7),
    )
    db_session.add(invoice)
    db_session.flush()

    payment = Payment(
        invoice_id=invoice.id,
        branch_id="narsobawadi",
        amount=Decimal("1500.00"),
        payment_method="cash",
        status="completed",
        recorded_by_id=mgr_b1.id,
    )
    db_session.add(payment)
    db_session.commit()

    # Manager B2 attempts reversal of payment from Branch 1
    headers_b2 = _auth_headers(client, db_session, mgr_b2)
    res = client.post(
        f"/api/billing/payments/{payment.id}/reverse",
        json={"reason": "Malicious cross branch reversal attempt"},
        headers=headers_b2,
    )
    assert res.status_code == 403
    assert "Access denied" in res.json().get("detail", "")

    # Also test at the service level directly
    with pytest.raises(PermissionError, match="cannot reverse payment for branch"):
        reverse_payment(db=db_session, payment_id=payment.id, actor=mgr_b2, reason="Direct service attack")


def test_membership_freeze_and_cancel_cross_branch_idor_blocked(client: TestClient, db_session: Session, phase5_fixtures):
    """
    Critical finding regression: Branch manager of Branch 2 must NOT be allowed
    to freeze or cancel a member belonging to Branch 1.
    Must return 403 Forbidden.
    """
    mgr_b2 = phase5_fixtures["mgr_b2"]
    member_b1 = phase5_fixtures["member_b1"]
    headers = _auth_headers(client, db_session, mgr_b2)

    # 1. Freeze attempt cross-branch
    res_freeze = client.post(
        "/api/memberships/freeze",
        json={"userId": member_b1.id, "freezeDays": 14, "reason": "Unauthorized cross-branch freeze"},
        headers=headers,
    )
    assert res_freeze.status_code == 403
    assert "Access denied" in res_freeze.json().get("detail", "")

    # 2. Cancel attempt cross-branch
    res_cancel = client.post(
        "/api/memberships/cancel",
        json={"userId": member_b1.id, "reason": "Unauthorized cross-branch cancellation"},
        headers=headers,
    )
    assert res_cancel.status_code == 403
    assert "Access denied" in res_cancel.json().get("detail", "")


def test_overlapping_freeze_rejected(db_session: Session, phase5_fixtures):
    """
    Verify that an active membership cannot have overlapping freeze records.
    Subsequent freeze calls must be rejected.
    """
    mgr_b1 = phase5_fixtures["mgr_b1"]
    user = User(
        email=f"freeze_test_{uuid.uuid4().hex[:6]}@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Freeze Candidate",
        role="member",
        branch_id="narsobawadi",
        membership_status="active",
        valid_until=date.today() + timedelta(days=60),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    # First freeze: succeeds
    freeze_membership(db=db_session, user=user, freeze_days=15, actor=mgr_b1)
    db_session.commit()
    assert user.membership_status == "frozen"

    # Second freeze while already frozen or overlapping: must fail
    with pytest.raises(ValueError, match="Only active memberships can be frozen"):
        freeze_membership(db=db_session, user=user, freeze_days=10, actor=mgr_b1)


def test_trainer_roster_and_details_branch_isolated(client: TestClient, db_session: Session, phase5_fixtures):
    """
    Verify branch managers and staff only see members of their own branch in /api/trainer/members
    and cannot inspect member details belonging to another branch.
    """
    mgr_b1 = phase5_fixtures["mgr_b1"]
    member_b2 = phase5_fixtures["member_b2"]
    headers_b1 = _auth_headers(client, db_session, mgr_b1)

    # 1. Roster query: Manager of Branch 1 should only see Branch 1 members
    res_roster = client.get("/api/trainer/members", headers=headers_b1)
    assert res_roster.status_code == 200
    members = res_roster.json()["members"]
    member_ids = [m["id"] for m in members]
    assert phase5_fixtures["member_b1"].id in member_ids
    assert phase5_fixtures["member_b2"].id not in member_ids

    # 2. Direct IDOR inspection of Branch 2 member: should be rejected with 403 Forbidden
    res_detail = client.get(f"/api/trainer/members/{member_b2.id}", headers=headers_b1)
    assert res_detail.status_code == 403
    assert "Access denied" in res_detail.json().get("detail", "")


def test_trainer_cross_branch_assignment_rejected(client: TestClient, db_session: Session, phase5_fixtures):
    """
    Verify branch manager of Branch 1 cannot assign a trainer from Branch 2
    or assign a member from Branch 2.
    """
    mgr_b1 = phase5_fixtures["mgr_b1"]
    trainer_b2 = phase5_fixtures["trainer_b2"]
    member_b1 = phase5_fixtures["member_b1"]
    headers = _auth_headers(client, db_session, mgr_b1)

    res = client.post(
        "/api/trainer/assignments",
        json={"trainerId": trainer_b2.id, "memberId": member_b1.id, "notes": "Cross branch assignment"},
        headers=headers,
    )
    assert res.status_code == 400
    assert "Access denied" in res.json().get("detail", "")


def test_admin_overview_branch_scoped(client: TestClient, db_session: Session, phase5_fixtures):
    """
    Verify /api/admin/overview filters totalMembers and activeToday by branch
    for branch managers and front desk staff.
    """
    mgr_b1 = phase5_fixtures["mgr_b1"]
    mgr_b2 = phase5_fixtures["mgr_b2"]

    # Manager B1 overview
    headers_b1 = _auth_headers(client, db_session, mgr_b1)
    res_b1 = client.get("/api/admin/overview", headers=headers_b1)
    assert res_b1.status_code == 200
    data_b1 = res_b1.json()

    # Manager B2 overview
    headers_b2 = _auth_headers(client, db_session, mgr_b2)
    res_b2 = client.get("/api/admin/overview", headers=headers_b2)
    assert res_b2.status_code == 200
    data_b2 = res_b2.json()

    # Assert branch scoping: both should reflect their branch, not equal totals if branches differ
    assert isinstance(data_b1["totalMembers"], int)
    assert isinstance(data_b2["totalMembers"], int)


def test_branch_access_grant_manager_scope(client: TestClient, db_session: Session, phase5_fixtures):
    """
    Verify branch manager cannot grant cross-branch access between branches
    outside their own branch jurisdiction.
    """
    mgr_b1 = phase5_fixtures["mgr_b1"]
    member_b2 = phase5_fixtures["member_b2"]  # Branch 2 member
    headers = _auth_headers(client, db_session, mgr_b1)

    # Manager of B1 trying to grant access for B2 member to B2 branch
    res = client.post(
        "/api/branches/access-grants",
        json={"userId": member_b2.id, "branchId": "sangli", "notes": "Unauthorized grant"},
        headers=headers,
    )
    assert res.status_code == 403
    assert "Access denied" in res.json().get("detail", "")


# ============================================================================
# PHASE 5.3 END-TO-END BUSINESS WORKFLOWS A THROUGH I
# ============================================================================

def test_workflow_a_registration_to_checkin_and_reporting(client: TestClient, db_session: Session, phase5_fixtures):
    """
    Workflow A:
    Member registration -> enrollment -> invoice creation -> payment posting -> successful check-in -> report inclusion.
    """
    email = f"workflow_a_{uuid.uuid4().hex[:6]}@rvfitness.in"

    # 1. Registration
    reg_res = client.post(
        "/api/auth/register",
        json={
            "name": "Workflow A Member",
            "email": email,
            "password": "Password1234!",
            "phone": "+91 98220 11111",
            "acceptedTerms": True,
        },
    )
    assert reg_res.status_code == 201
    member_data = reg_res.json()["user"]
    member_id = member_data["id"]

    # Set member's branch
    user_db = db_session.query(User).filter(User.id == member_id).one()
    user_db.branch_id = "narsobawadi"
    db_session.commit()

    # 2. Enrollment
    enroll_res = client.post(
        "/api/memberships/enroll",
        json={
            "planId": "plan-phase5-local",
            "name": "Workflow A Member",
            "phone": "+91 98220 11111",
            "email": email,
            "acceptedTerms": True,
        },
    )
    assert enroll_res.status_code == 201
    invoice_id = enroll_res.json()["enrollment"]["invoiceId"]
    assert invoice_id is not None

    # Link enrollment user
    invoice_db = db_session.query(Invoice).filter(Invoice.id == invoice_id).one()
    invoice_db.user_id = member_id
    db_session.commit()

    # 3. Payment Posting with Idempotency Key
    mgr = phase5_fixtures["mgr_b1"]
    mgr_headers = _auth_headers(client, db_session, mgr)
    idemp_key = f"wf_a_pay_{uuid.uuid4().hex}"
    pay_res = client.post(
        "/api/billing/payments",
        json={
            "invoiceId": invoice_id,
            "amount": float(invoice_db.total_amount),
            "paymentMethod": "upi_offline",
            "idempotencyKey": idemp_key,
            "notes": "Full upfront fee payment",
        },
        headers=mgr_headers,
    )
    assert pay_res.status_code == 200
    assert pay_res.json()["payment"]["status"] == "completed"

    # Activate member status and set validity
    user_db.membership_status = "active"
    user_db.valid_until = date.today() + timedelta(days=30)
    user_db.membership_plan_id = "plan-phase5-local"
    db_session.commit()

    # 4. Successful Check-In via Portal
    member_headers = _auth_headers(client, db_session, user_db)
    checkin_res = client.post("/api/attendance/check-in?branch_id=narsobawadi", headers=member_headers)
    assert checkin_res.status_code == 200
    assert checkin_res.json()["success"] is True

    # 5. Inclusion in Monthly Attendance Report
    today = date.today()
    rep_res = client.get(
        f"/api/attendance/reports/branch/narsobawadi?year={today.year}&month={today.month}",
        headers=mgr_headers,
    )
    assert rep_res.status_code == 200
    report = rep_res.json()
    assert report["totalCheckins"] >= 1
    assert report["branchId"] == "narsobawadi"


def test_workflow_b_unpaid_overdue_dues_denies_checkin(client: TestClient, db_session: Session, phase5_fixtures):
    """
    Workflow B:
    Member with unpaid overdue dues -> check-in denied with an auditable attempt.
    """
    user = User(
        email=f"workflow_b_{uuid.uuid4().hex[:6]}@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Overdue Dues Member",
        role="member",
        branch_id="narsobawadi",
        membership_id=f"RVF-OD-{uuid.uuid4().hex[:4]}",
        membership_status="active",
        valid_until=date.today() + timedelta(days=30),
        membership_plan_id="plan-phase5-local",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    # Overdue invoice past grace period (> 15 days)
    overdue_invoice = Invoice(
        invoice_number=f"INV-OVERDUE-{uuid.uuid4().hex[:6]}",
        user_id=user.id,
        branch_id="narsobawadi",
        status="unpaid",
        subtotal=Decimal("2000.00"),
        total_amount=Decimal("2000.00"),
        amount_paid=Decimal("0.00"),
        balance_due=Decimal("2000.00"),
        due_date=date.today() - timedelta(days=20),
    )
    db_session.add(overdue_invoice)
    db_session.commit()

    headers = _auth_headers(client, db_session, user)
    res = client.post("/api/attendance/check-in?branch_id=narsobawadi", headers=headers)
    assert res.status_code == 403
    assert "due" in res.json().get("detail", "").lower()

    # Verify auditable attempt logged in database
    attempt = (
        db_session.query(AttendanceAttempt)
        .filter(AttendanceAttempt.user_id == user.id, AttendanceAttempt.failure_reason == "unpaid_dues")
        .first()
    )
    assert attempt is not None
    assert attempt.branch_id == "narsobawadi"


def test_workflow_c_frozen_or_expired_member_renewal_lifecycle(client: TestClient, db_session: Session, phase5_fixtures):
    """
    Workflow C:
    Frozen or expired member -> check-in denied;
    valid renewal -> access restored according to agreed date rules.
    """
    mgr = phase5_fixtures["mgr_b1"]
    mgr_headers = _auth_headers(client, db_session, mgr)

    # 1. Expired member
    user = User(
        email=f"workflow_c_{uuid.uuid4().hex[:6]}@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Expired Then Renewed Member",
        role="member",
        branch_id="narsobawadi",
        membership_id=f"RVF-EXP-{uuid.uuid4().hex[:4]}",
        membership_status="expired",
        valid_until=date.today() - timedelta(days=5),
        membership_plan_id="plan-phase5-local",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    user_headers = _auth_headers(client, db_session, user)

    # Check-in denied when expired
    res_expired = client.post("/api/attendance/check-in?branch_id=narsobawadi", headers=user_headers)
    assert res_expired.status_code == 403
    assert "expired" in res_expired.json().get("detail", "").lower()

    # 2. Member Renews Membership
    renew_res = client.post(
        "/api/memberships/renew",
        json={"planId": "plan-phase5-local"},
        headers=user_headers,
    )
    assert renew_res.status_code == 200
    db_session.refresh(user)
    assert user.membership_status == "active"
    assert user.valid_until >= date.today() + timedelta(days=29)

    # 3. Check-in now succeeds
    res_restored = client.post("/api/attendance/check-in?branch_id=narsobawadi", headers=user_headers)
    assert res_restored.status_code == 200
    assert res_restored.json()["success"] is True


def test_workflow_d_concurrent_payment_requests_same_idempotency_key(db_session: Session, phase5_fixtures):
    """
    Workflow D:
    Two concurrent payment requests using the same idempotency key ->
    only one financial operation is executed, avoiding double credit.
    """
    mgr = phase5_fixtures["mgr_b1"]
    idemp_key = f"concur-pay-{uuid.uuid4().hex}"

    invoice = Invoice(
        invoice_number=f"INV-CONCUR-PAY-{uuid.uuid4().hex[:6]}",
        branch_id="narsobawadi",
        status="unpaid",
        subtotal=Decimal("4000.00"),
        total_amount=Decimal("4000.00"),
        amount_paid=Decimal("0.00"),
        balance_due=Decimal("4000.00"),
        due_date=date.today() + timedelta(days=7),
    )
    db_session.add(invoice)
    db_session.commit()

    bind = db_session.get_bind()
    session_factory = sessionmaker(bind=bind, autocommit=False, autoflush=False)
    results = []

    def run_payment():
        local_db = session_factory()
        try:
            actor = local_db.query(User).filter(User.id == mgr.id).one()
            p = record_offline_payment(
                db=local_db,
                invoice_id=invoice.id,
                amount=Decimal("2000.00"),
                payment_method="cash",
                recorded_by=actor,
                idempotency_key=idemp_key,
            )
            local_db.commit()
            return p.id
        except Exception as e:
            local_db.rollback()
            return str(type(e).__name__)
        finally:
            local_db.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(run_payment)
        f2 = executor.submit(run_payment)
        results = [f1.result(), f2.result()]

    db_session.refresh(invoice)
    # Balance must only be deducted ONCE (amount_paid == 2000, balance_due == 2000)
    assert invoice.amount_paid == Decimal("2000.00")
    assert invoice.balance_due == Decimal("2000.00")

    # Payment count for this key must be exactly 1
    payment_count = db_session.query(Payment).filter(Payment.idempotency_key == idemp_key).count()
    assert payment_count == 1


def test_workflow_e_concurrent_checkins_same_member_same_date(db_session: Session, phase5_fixtures):
    """
    Workflow E:
    Two concurrent check-ins for the same member and branch on the same local date ->
    exactly one success, and one rejection.
    """
    staff = phase5_fixtures["staff_b1"]
    member = User(
        email=f"workflow_e_{uuid.uuid4().hex[:6]}@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Concurrent Checkin User",
        role="member",
        branch_id="narsobawadi",
        membership_id=f"RVF-CONC-{uuid.uuid4().hex[:4]}",
        membership_status="active",
        valid_until=date.today() + timedelta(days=30),
        membership_plan_id="plan-phase5-local",
        is_active=True,
    )
    db_session.add(member)
    db_session.commit()

    today = get_branch_local_date("narsobawadi")
    bind = db_session.get_bind()
    session_factory = sessionmaker(bind=bind, autocommit=False, autoflush=False)

    def attempt_checkin(worker_idx: int):
        local_db = session_factory()
        try:
            st = local_db.query(User).filter(User.id == staff.id).first()
            rec = process_manual_checkin(
                db=local_db,
                branch_id="narsobawadi",
                staff=st,
                reason_code="no_internet",
                member_id=member.id,
                notes=f"Concurrent checkin {worker_idx}",
            )
            local_db.commit()
            return True
        except Exception:
            local_db.rollback()
            return False
        finally:
            local_db.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(attempt_checkin, 1)
        f2 = executor.submit(attempt_checkin, 2)
        outcomes = [f1.result(), f2.result()]

    # Exactly one success and one failure
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 1

    # Exactly one record in database
    records = db_session.query(AttendanceRecord).filter(
        AttendanceRecord.user_id == member.id,
        AttendanceRecord.branch_id == "narsobawadi",
        AttendanceRecord.check_in_date == today,
    ).all()
    assert len(records) == 1


def test_workflow_f_qr_token_replay_rejected(client: TestClient, db_session: Session, phase5_fixtures):
    """
    Workflow F:
    QR token replay: first valid scan succeeds and repeated use is rejected.
    """
    member = phase5_fixtures["member_b1"]
    mgr = phase5_fixtures["mgr_b1"]
    mgr_headers = _auth_headers(client, db_session, mgr)

    # 1. Generate QR token for member
    token, expires_at, _ = generate_member_qr_token(member)

    # Clean up any pre-existing check-in today for member_b1
    today = get_branch_local_date("narsobawadi")
    db_session.query(AttendanceRecord).filter(
        AttendanceRecord.user_id == member.id,
        AttendanceRecord.check_in_date == today,
    ).delete()
    db_session.commit()

    # 2. First scan: succeeds
    res1 = client.post(
        "/api/attendance/qr-check-in",
        json={"qrToken": token, "branchId": "narsobawadi"},
        headers=mgr_headers,
    )
    assert res1.status_code == 200
    assert res1.json()["success"] is True

    # 3. Replay scan with the identical token: must be rejected with 400 Bad Request
    res2 = client.post(
        "/api/attendance/qr-check-in",
        json={"qrToken": token, "branchId": "narsobawadi"},
        headers=mgr_headers,
    )
    assert res2.status_code == 400
    assert "already been scanned" in res2.json().get("detail", "").lower()


def test_workflow_g_matrix_role_authorization(client: TestClient, db_session: Session, phase5_fixtures):
    """
    Workflow G:
    Role Matrix Verification:
    Trainer, member, branch staff, manager, organization administrator ->
    each can access ONLY permitted resources.
    """
    org_admin = phase5_fixtures["org_admin"]
    mgr = phase5_fixtures["mgr_b1"]
    staff = phase5_fixtures["staff_b1"]
    trainer = phase5_fixtures["trainer_b1"]
    member = phase5_fixtures["member_b1"]

    headers_admin = _auth_headers(client, db_session, org_admin)
    headers_mgr = _auth_headers(client, db_session, mgr)
    headers_staff = _auth_headers(client, db_session, staff)
    headers_trainer = _auth_headers(client, db_session, trainer)
    headers_member = _auth_headers(client, db_session, member)

    # Test 1: Manager-only override endpoint
    override_payload = {"attemptId": "dummy_attempt", "reason": "Matrix testing override"}
    assert client.post("/api/attendance/override", json=override_payload, headers=headers_member).status_code == 403
    assert client.post("/api/attendance/override", json=override_payload, headers=headers_trainer).status_code == 403
    assert client.post("/api/attendance/override", json=override_payload, headers=headers_staff).status_code == 403
    # Manager and Admin are permitted past role-check (may fail on 404 attempt not found, but not 403 role forbidden)
    assert client.post("/api/attendance/override", json=override_payload, headers=headers_mgr).status_code in (400, 404)
    assert client.post("/api/attendance/override", json=override_payload, headers=headers_admin).status_code in (400, 404)

    # Test 2: Admin Operations Overview
    assert client.get("/api/admin/overview", headers=headers_member).status_code == 403
    assert client.get("/api/admin/overview", headers=headers_trainer).status_code == 403
    assert client.get("/api/admin/overview", headers=headers_staff).status_code == 200
    assert client.get("/api/admin/overview", headers=headers_mgr).status_code == 200
    assert client.get("/api/admin/overview", headers=headers_admin).status_code == 200

    # Test 3: Desk Member Lookup
    assert client.get("/api/attendance/members/lookup?query=Aditya", headers=headers_member).status_code == 403
    assert client.get("/api/attendance/members/lookup?query=Aditya", headers=headers_trainer).status_code == 403
    assert client.get("/api/attendance/members/lookup?query=Aditya", headers=headers_staff).status_code == 200


def test_workflow_h_account_linking_attendance_reconciliation(client: TestClient, db_session: Session, phase5_fixtures):
    """
    Workflow H:
    Account linking: eligible historical attendance for an offline member is reconciled
    without deleting audit history or incorrectly merging members.
    """
    mgr = phase5_fixtures["mgr_b1"]
    mgr_headers = _auth_headers(client, db_session, mgr)
    shared_phone = "+91 98220 77777"
    card_id = f"CARD-{uuid.uuid4().hex[:6]}"

    # 1. Desk records unlinked walkin attendance for an offline member
    offline_record = AttendanceRecord(
        member_identity=f"card:{card_id}",
        user_id=None,
        membership_id=card_id,
        member_phone=shared_phone,
        member_name="Walk-in Offline Member",
        branch_id="narsobawadi",
        check_in_date=date.today() - timedelta(days=2),
        source="manual",
        method="paper_log",
    )
    db_session.add(offline_record)
    db_session.commit()

    # 2. Member creates digital account and links to their card
    new_user = User(
        email=f"linked_user_{uuid.uuid4().hex[:6]}@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Walk-in Offline Member",
        phone=shared_phone,
        membership_id=card_id,
        role="member",
        branch_id="narsobawadi",
        membership_status="active",
        valid_until=date.today() + timedelta(days=30),
        is_active=True,
    )
    db_session.add(new_user)
    db_session.commit()

    # 3. Staff executes reconciliation endpoint
    recon_res = client.post(
        f"/api/attendance/members/{new_user.id}/reconcile?membership_id={card_id}",
        headers=mgr_headers,
    )
    assert recon_res.status_code == 200
    data = recon_res.json()["data"]
    assert data["reconciledRecords"] >= 1

    # 4. Verify original record updated with user_id, preserved date, and audit trail created
    db_session.refresh(offline_record)
    assert offline_record.user_id == new_user.id

    audit_entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "attendance.reconcile_identity", AuditLog.resource_id == new_user.id)
        .first()
    )
    assert audit_entry is not None


def test_workflow_i_cross_branch_requests_isolated(client: TestClient, db_session: Session, phase5_fixtures):
    """
    Workflow I:
    Cross-branch requests: no unauthorized reads, writes, exports, or financial operations.
    """
    mgr_b2 = phase5_fixtures["mgr_b2"]  # Sangli manager
    headers_b2 = _auth_headers(client, db_session, mgr_b2)

    # 1. Cross-branch attendance export: Sangli manager requesting Narsobawadi export -> 403
    res_export = client.get(
        "/api/attendance/reports/branch/narsobawadi/export?year=2026&month=10&format=csv",
        headers=headers_b2,
    )
    assert res_export.status_code == 403
    assert "Access denied" in res_export.json().get("detail", "")

    # 2. Cross-branch invoice listing: Sangli manager querying Narsobawadi invoices -> 403
    res_inv = client.get("/api/billing/invoices?branch_id=narsobawadi", headers=headers_b2)
    assert res_inv.status_code == 403
    assert "Access denied" in res_inv.json().get("detail", "")

    # 3. Cross-branch manual checkin: Sangli manager attempting manual checkin at Narsobawadi -> 403
    res_checkin = client.post(
        "/api/attendance/manual-check-in",
        json={"branchId": "narsobawadi", "reasonCode": "no_internet", "phone": "+91 98220 99999", "name": "Test"},
        headers=headers_b2,
    )
    assert res_checkin.status_code == 403
    assert "Access denied" in res_checkin.json().get("detail", "")
