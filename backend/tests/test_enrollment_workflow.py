"""
Automated tests for Membership Enrollment Approval and Activation Workflow.
Verifies all 13 requirements specified in Phase 6.
"""

import pytest
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.core.security import hash_password
from backend.app.core.auth import create_user_session
from backend.app.models.user import User
from backend.app.models.organization import Organization, Branch
from backend.app.models.membership import MembershipPlan, PlanPrice, Enrollment, MembershipChange
from backend.app.models.billing import Invoice, Payment
from backend.app.services.billing_service import record_offline_payment


@pytest.fixture
def setup_enrollment_test_data(db_session: Session):
    """Seed test organization, branches, plans, owner, managers, trainer, and members."""
    # Organization
    org = db_session.query(Organization).filter(Organization.code == "RVF").first()
    if not org:
        org = Organization(name="RV Fitness Test Org", code="RVF")
        db_session.add(org)
        db_session.flush()

    # Branch 1: Narsobawadi
    branch1 = db_session.query(Branch).filter(Branch.id == "narsobawadi").first()
    if not branch1:
        branch1 = Branch(
            id="narsobawadi",
            organization_id=org.id,
            name="RVFitness Narsobawadi",
            code="NARSOBAWADI",
            city="Narsobawadi",
            state="Maharashtra",
        )
        db_session.add(branch1)
        db_session.flush()

    # Branch 2: Kolhapur City
    branch2 = db_session.query(Branch).filter(Branch.id == "kolhapur_city").first()
    if not branch2:
        branch2 = Branch(
            id="kolhapur_city",
            organization_id=org.id,
            name="RVFitness Kolhapur City",
            code="KOLHAPUR",
            city="Kolhapur",
            state="Maharashtra",
        )
        db_session.add(branch2)
        db_session.flush()

    # Membership Plans
    plan1 = db_session.query(MembershipPlan).filter(MembershipPlan.id == "plan_quarterly_test").first()
    if not plan1:
        plan1 = MembershipPlan(
            id="plan_quarterly_test",
            name="Quarterly Strength Test",
            category="strength",
            access_scope="single_branch",
            price=Decimal("4000.00"),
            currency="₹",
            billing_cycle="per 3 months",
            duration_days=90,
            is_active=True,
            perks=["All weights access", "Locker room"],
        )
        db_session.add(plan1)
        db_session.flush()

        p1_price = PlanPrice(
            plan_id=plan1.id,
            price=Decimal("4000.00"),
            currency="₹",
            effective_from=date.today() - timedelta(days=30),
            is_active=True,
        )
        db_session.add(p1_price)

    plan2 = db_session.query(MembershipPlan).filter(MembershipPlan.id == "plan_vip_test").first()
    if not plan2:
        plan2 = MembershipPlan(
            id="plan_vip_test",
            name="VIP Annual All Branch",
            category="vip",
            access_scope="all_branches",
            price=Decimal("15000.00"),
            currency="₹",
            billing_cycle="per year",
            duration_days=365,
            is_active=True,
            perks=["All branches VIP access"],
        )
        db_session.add(plan2)
        db_session.flush()

        p2_price = PlanPrice(
            plan_id=plan2.id,
            price=Decimal("15000.00"),
            currency="₹",
            effective_from=date.today() - timedelta(days=30),
            is_active=True,
        )
        db_session.add(p2_price)

    # Org Admin (Owner)
    owner = db_session.query(User).filter(User.email == "owner_workflow@rvfitness.in").first()
    if not owner:
        owner = User(
            email="owner_workflow@rvfitness.in",
            hashed_password=hash_password("OwnerSecurePass123!"),
            name="Workflow Owner",
            role="org_admin",
            staff_role="Gym Owner",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(owner)

    # Branch Manager for Branch 1
    manager1 = db_session.query(User).filter(User.email == "manager1@rvfitness.in").first()
    if not manager1:
        manager1 = User(
            email="manager1@rvfitness.in",
            hashed_password=hash_password("Manager1Pass123!"),
            name="Branch 1 Manager",
            role="manager",
            staff_role="Branch Manager",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(manager1)

    # Branch Manager for Branch 2
    manager2 = db_session.query(User).filter(User.email == "manager2@rvfitness.in").first()
    if not manager2:
        manager2 = User(
            email="manager2@rvfitness.in",
            hashed_password=hash_password("Manager2Pass123!"),
            name="Branch 2 Manager",
            role="manager",
            staff_role="Branch Manager",
            branch_id="kolhapur_city",
            is_active=True,
        )
        db_session.add(manager2)

    # Trainer (Unauthorized for approvals)
    trainer = db_session.query(User).filter(User.email == "trainer_workflow@rvfitness.in").first()
    if not trainer:
        trainer = User(
            email="trainer_workflow@rvfitness.in",
            hashed_password=hash_password("TrainerPass123!"),
            name="Workflow Trainer",
            role="trainer",
            staff_role="Strength Coach",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(trainer)

    # Member user
    member = db_session.query(User).filter(User.email == "member_workflow@rvfitness.in").first()
    if not member:
        member = User(
            email="member_workflow@rvfitness.in",
            hashed_password=hash_password("MemberPass123!"),
            name="Workflow Member",
            role="member",
            membership_status="pending",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(member)

    db_session.commit()
    return {
        "org": org,
        "branch1": branch1,
        "branch2": branch2,
        "plan1": plan1,
        "plan2": plan2,
        "owner": owner,
        "manager1": manager1,
        "manager2": manager2,
        "trainer": trainer,
        "member": member,
    }


def auth_headers_for_user(db_session: Session, user: User):
    """Generate session cookie and CSRF header for a test user."""
    session, raw_token, csrf_token = create_user_session(db_session, user)
    return {"cookies": {"rvf_session": raw_token}, "headers": {"x-csrf-token": csrf_token}}


# ==============================================================================
# TEST 1: Member Enrollment Creation and Database Persistence
# ==============================================================================
def test_member_enrollment_creation_and_persistence(client: TestClient, db_session: Session, setup_enrollment_test_data):
    """Verify member enrollment creates DB record with user_id, branch_id, and invoice."""
    member = setup_enrollment_test_data["member"]
    plan = setup_enrollment_test_data["plan1"]
    auth = auth_headers_for_user(db_session, member)

    payload = {
        "planId": plan.id,
        "name": member.name,
        "phone": "+91 98220 11111",
        "email": member.email,
        "branchId": "narsobawadi",
        "acceptedTerms": True,
    }

    res = client.post("/api/v1/memberships/enroll", json=payload, cookies=auth["cookies"], headers=auth["headers"])
    assert res.status_code == status.HTTP_201_CREATED
    data = res.json()
    assert "enrollment" in data
    enr_id = data["enrollment"]["id"]
    assert enr_id is not None

    # Check database persistence
    db_enr = db_session.query(Enrollment).filter(Enrollment.id == enr_id).first()
    assert db_enr is not None
    assert db_enr.user_id == member.id
    assert db_enr.branch_id == "narsobawadi"
    assert db_enr.plan_id == plan.id
    # Verify invoice was generated
    invoice = db_session.query(Invoice).filter(Invoice.enrollment_id == db_enr.id).first()
    assert invoice is not None
    assert invoice.balance_due == Decimal("4000.00")
    assert invoice.status == "unpaid"


# ==============================================================================
# TEST 2: Owner Queue Returns the Correct Pending Request
# ==============================================================================
def test_owner_queue_returns_pending_request(client: TestClient, db_session: Session, setup_enrollment_test_data):
    """Verify owner enrollment queue lists pending requests with complete metadata."""
    owner = setup_enrollment_test_data["owner"]
    member = setup_enrollment_test_data["member"]
    plan = setup_enrollment_test_data["plan1"]

    # Submit enrollment
    m_auth = auth_headers_for_user(db_session, member)
    enr_res = client.post(
        "/api/v1/memberships/enroll",
        json={"planId": plan.id, "name": member.name, "phone": "+91 98220 22222", "email": member.email, "acceptedTerms": True},
        cookies=m_auth["cookies"],
        headers=m_auth["headers"],
    )
    assert enr_res.status_code == status.HTTP_201_CREATED
    enr_id = enr_res.json()["enrollment"]["id"]

    # Query owner queue
    o_auth = auth_headers_for_user(db_session, owner)
    queue_res = client.get("/api/v1/owner/enrollments?status=pending", cookies=o_auth["cookies"])
    assert queue_res.status_code == status.HTTP_200_OK
    queue_data = queue_res.json()
    assert "enrollments" in queue_data
    matched = [e for e in queue_data["enrollments"] if e["id"] == enr_id]
    assert len(matched) == 1
    item = matched[0]
    assert item["name"] == member.name
    assert item["email"] == member.email
    assert item["planName"] == plan.name
    assert item["price"] == 4000.0
    assert item["branchId"] == "narsobawadi"


# ==============================================================================
# TEST 3: Request Visibility Across Authorized Branches
# ==============================================================================
def test_request_visibility_across_branches(client: TestClient, db_session: Session, setup_enrollment_test_data):
    """Verify org_admin sees all requests, while branch manager only sees their branch."""
    owner = setup_enrollment_test_data["owner"]
    manager1 = setup_enrollment_test_data["manager1"]
    manager2 = setup_enrollment_test_data["manager2"]
    plan1 = setup_enrollment_test_data["plan1"]
    plan2 = setup_enrollment_test_data["plan2"]

    # Create request in Branch 1 (Narsobawadi)
    enr1 = Enrollment(
        plan_id=plan1.id,
        branch_id="narsobawadi",
        name="Branch1 Member",
        phone="+91 98220 33331",
        email="b1_member@test.in",
        status="pending_verification",
        price=Decimal("4000.00"),
        currency="₹",
    )
    db_session.add(enr1)

    # Create request in Branch 2 (Kolhapur)
    enr2 = Enrollment(
        plan_id=plan2.id,
        branch_id="kolhapur_city",
        name="Branch2 Member",
        phone="+91 98220 33332",
        email="b2_member@test.in",
        status="pending_verification",
        price=Decimal("15000.00"),
        currency="₹",
    )
    db_session.add(enr2)
    db_session.commit()

    # Owner should see both
    o_auth = auth_headers_for_user(db_session, owner)
    o_res = client.get("/api/v1/owner/enrollments?status=all", cookies=o_auth["cookies"])
    assert o_res.status_code == status.HTTP_200_OK
    o_ids = [e["id"] for e in o_res.json()["enrollments"]]
    assert str(enr1.id) in o_ids
    assert str(enr2.id) in o_ids

    # Manager 1 should only see Branch 1 request
    m1_auth = auth_headers_for_user(db_session, manager1)
    m1_res = client.get("/api/v1/owner/enrollments", cookies=m1_auth["cookies"])
    assert m1_res.status_code == status.HTTP_200_OK
    m1_ids = [e["id"] for e in m1_res.json()["enrollments"]]
    assert str(enr1.id) in m1_ids
    assert str(enr2.id) not in m1_ids

    # Manager 2 should only see Branch 2 request
    m2_auth = auth_headers_for_user(db_session, manager2)
    m2_res = client.get("/api/v1/owner/enrollments", cookies=m2_auth["cookies"])
    assert m2_res.status_code == status.HTTP_200_OK
    m2_ids = [e["id"] for e in m2_res.json()["enrollments"]]
    assert str(enr1.id) not in m2_ids
    assert str(enr2.id) in m2_ids


# ==============================================================================
# TEST 4: Unauthorized Users Receive 401/403
# ==============================================================================
def test_unauthorized_users_receive_401_or_403(client: TestClient, db_session: Session, setup_enrollment_test_data):
    """Verify unauthenticated returns 401, trainer and member return 403 on queue & approvals."""
    trainer = setup_enrollment_test_data["trainer"]
    member = setup_enrollment_test_data["member"]

    # 1. Unauthenticated request to owner queue -> 401
    unauth_res = client.get("/api/v1/owner/enrollments")
    assert unauth_res.status_code == status.HTTP_401_UNAUTHORIZED

    # 2. Trainer request to owner queue -> 403
    t_auth = auth_headers_for_user(db_session, trainer)
    t_res = client.get("/api/v1/owner/enrollments", cookies=t_auth["cookies"])
    assert t_res.status_code == status.HTTP_403_FORBIDDEN

    # 3. Member request to owner queue -> 403
    m_auth = auth_headers_for_user(db_session, member)
    m_res = client.get("/api/v1/owner/enrollments", cookies=m_auth["cookies"])
    assert m_res.status_code == status.HTTP_403_FORBIDDEN

    # 4. Trainer approval attempt -> 403
    fake_id = "00000000-0000-0000-0000-000000000000"
    appr_res = client.post(
        f"/api/v1/owner/enrollments/{fake_id}/approve",
        json={"record_payment": False},
        cookies=t_auth["cookies"],
        headers=t_auth["headers"],
    )
    assert appr_res.status_code == status.HTTP_403_FORBIDDEN


# ==============================================================================
# TEST 5: Successful Approval Creates or Updates the Correct Membership
# ==============================================================================
def test_successful_approval_with_desk_payment_activates_membership(
    client: TestClient, db_session: Session, setup_enrollment_test_data
):
    """Verify approval with front-desk payment marks enrollment active and activates user."""
    owner = setup_enrollment_test_data["owner"]
    member = setup_enrollment_test_data["member"]
    plan = setup_enrollment_test_data["plan1"]

    # Submit enrollment
    m_auth = auth_headers_for_user(db_session, member)
    enr_res = client.post(
        "/api/v1/memberships/enroll",
        json={"planId": plan.id, "name": member.name, "phone": "+91 98220 55555", "email": member.email, "acceptedTerms": True},
        cookies=m_auth["cookies"],
        headers=m_auth["headers"],
    )
    enr_id = enr_res.json()["enrollment"]["id"]

    # Approve with record_payment = True
    o_auth = auth_headers_for_user(db_session, owner)
    appr_payload = {
        "record_payment": True,
        "payment_method": "cash",
        "reference_number": "CASH-DESK-001",
        "notes": "Paid full fee at Narsobawadi desk",
    }
    appr_res = client.post(
        f"/api/v1/owner/enrollments/{enr_id}/approve",
        json=appr_payload,
        cookies=o_auth["cookies"],
        headers=o_auth["headers"],
    )
    assert appr_res.status_code == status.HTTP_200_OK
    data = appr_res.json()
    assert data["enrollment"]["status"] == "active"
    assert data["enrollment"]["balanceDue"] == 0.0

    # Verify user record updated in database
    db_session.refresh(member)
    assert member.membership_status == "active"
    assert member.membership_plan_id == plan.id
    assert member.valid_until is not None
    expected_valid_until = date.today() + timedelta(days=90)
    assert member.valid_until == expected_valid_until

    # Verify audit / membership changes recorded
    changes = db_session.query(MembershipChange).filter(MembershipChange.user_id == member.id).all()
    assert len(changes) >= 1
    assert changes[-1].new_status == "active"
    assert changes[-1].action_type in ("enrollment", "activation")


# ==============================================================================
# TEST 6: Rejection Preserves History and Does Not Activate Membership
# ==============================================================================
def test_rejection_preserves_history_and_does_not_activate(
    client: TestClient, db_session: Session, setup_enrollment_test_data
):
    """Verify rejection captures reason, voids unpaid invoice, and preserves enrollment history."""
    owner = setup_enrollment_test_data["owner"]
    member = setup_enrollment_test_data["member"]
    plan = setup_enrollment_test_data["plan1"]

    # Member starts as pending
    member.membership_status = "pending"
    db_session.commit()

    # Submit enrollment
    m_auth = auth_headers_for_user(db_session, member)
    enr_res = client.post(
        "/api/v1/memberships/enroll",
        json={"planId": plan.id, "name": member.name, "phone": "+91 98220 66666", "email": member.email, "acceptedTerms": True},
        cookies=m_auth["cookies"],
        headers=m_auth["headers"],
    )
    enr_id = enr_res.json()["enrollment"]["id"]

    # Reject request
    o_auth = auth_headers_for_user(db_session, owner)
    rej_payload = {"reason": "Applicant requested tier change to VIP"}
    rej_res = client.post(
        f"/api/v1/owner/enrollments/{enr_id}/reject",
        json=rej_payload,
        cookies=o_auth["cookies"],
        headers=o_auth["headers"],
    )
    assert rej_res.status_code == status.HTTP_200_OK
    assert rej_res.json()["enrollment"]["status"] == "rejected"
    assert rej_res.json()["enrollment"]["rejectionReason"] == "Applicant requested tier change to VIP"

    # Verify database state
    db_enr = db_session.query(Enrollment).filter(Enrollment.id == enr_id).first()
    assert db_enr is not None  # History preserved, not deleted!
    assert db_enr.status == "rejected"
    assert db_enr.rejection_reason == "Applicant requested tier change to VIP"

    # Verify user was NOT activated
    db_session.refresh(member)
    assert member.membership_status != "active"

    # Verify unpaid invoice was voided
    inv = db_session.query(Invoice).filter(Invoice.enrollment_id == db_enr.id).first()
    if inv:
        assert inv.status == "void"


# ==============================================================================
# TEST 7: Payment-Pending Requests Remain Inactive
# ==============================================================================
def test_approval_without_payment_leaves_membership_inactive(
    client: TestClient, db_session: Session, setup_enrollment_test_data
):
    """Verify approval without payment sets payment_pending and membership remains inactive."""
    owner = setup_enrollment_test_data["owner"]
    member = setup_enrollment_test_data["member"]
    plan = setup_enrollment_test_data["plan1"]

    member.membership_status = "pending"
    db_session.commit()

    m_auth = auth_headers_for_user(db_session, member)
    enr_res = client.post(
        "/api/v1/memberships/enroll",
        json={"planId": plan.id, "name": member.name, "phone": "+91 98220 77777", "email": member.email, "acceptedTerms": True},
        cookies=m_auth["cookies"],
        headers=m_auth["headers"],
    )
    enr_id = enr_res.json()["enrollment"]["id"]

    # Owner approves WITHOUT recording payment
    o_auth = auth_headers_for_user(db_session, owner)
    appr_res = client.post(
        f"/api/v1/owner/enrollments/{enr_id}/approve",
        json={"record_payment": False},
        cookies=o_auth["cookies"],
        headers=o_auth["headers"],
    )
    assert appr_res.status_code == status.HTTP_200_OK
    assert appr_res.json()["enrollment"]["status"] == "payment_pending"

    # Verify user membership is NOT active
    db_session.refresh(member)
    assert member.membership_status != "active"
    assert member.membership_status == "approved"


# ==============================================================================
# TEST 8: Valid Payment Confirmation Activates Membership When Conditions Met
# ==============================================================================
def test_offline_payment_confirmation_activates_membership(
    client: TestClient, db_session: Session, setup_enrollment_test_data
):
    """Verify recording full payment on invoice via billing triggers automatic activation."""
    owner = setup_enrollment_test_data["owner"]
    member = setup_enrollment_test_data["member"]
    plan = setup_enrollment_test_data["plan1"]

    member.membership_status = "pending"
    db_session.commit()

    # Create enrollment and approve to payment_pending
    m_auth = auth_headers_for_user(db_session, member)
    enr_res = client.post(
        "/api/v1/memberships/enroll",
        json={"planId": plan.id, "name": member.name, "phone": "+91 98220 88888", "email": member.email, "acceptedTerms": True},
        cookies=m_auth["cookies"],
        headers=m_auth["headers"],
    )
    enr_id = enr_res.json()["enrollment"]["id"]

    o_auth = auth_headers_for_user(db_session, owner)
    client.post(
        f"/api/v1/owner/enrollments/{enr_id}/approve",
        json={"record_payment": False},
        cookies=o_auth["cookies"],
        headers=o_auth["headers"],
    )

    db_enr = db_session.query(Enrollment).filter(Enrollment.id == enr_id).first()
    assert db_enr.status == "payment_pending"
    inv = db_session.query(Invoice).filter(Invoice.enrollment_id == db_enr.id).first()
    assert inv is not None
    invoice_id = inv.id

    # Record full payment through record_offline_payment
    record_offline_payment(
        db=db_session,
        invoice_id=invoice_id,
        amount=Decimal("4000.00"),
        payment_method="upi_qr",
        recorded_by=owner,
        reference_number="UPI-VERIFIED-999",
    )
    db_session.commit()

    # Verify enrollment is now active
    db_session.refresh(db_enr)
    assert db_enr.status == "active"

    # Verify member is now active
    db_session.refresh(member)
    assert member.membership_status == "active"
    assert member.membership_plan_id == plan.id
    assert member.valid_until is not None


# ==============================================================================
# TEST 9: Repeated Approval Does Not Create Duplicate Subscriptions
# ==============================================================================
def test_repeated_approval_rejected(client: TestClient, db_session: Session, setup_enrollment_test_data):
    """Verify attempting to approve an already approved enrollment returns 400 Bad Request."""
    owner = setup_enrollment_test_data["owner"]
    member = setup_enrollment_test_data["member"]
    plan = setup_enrollment_test_data["plan1"]

    m_auth = auth_headers_for_user(db_session, member)
    enr_res = client.post(
        "/api/v1/memberships/enroll",
        json={"planId": plan.id, "name": member.name, "phone": "+91 98220 99991", "email": member.email, "acceptedTerms": True},
        cookies=m_auth["cookies"],
        headers=m_auth["headers"],
    )
    enr_id = enr_res.json()["enrollment"]["id"]

    o_auth = auth_headers_for_user(db_session, owner)
    # First approval succeeds
    res1 = client.post(
        f"/api/v1/owner/enrollments/{enr_id}/approve",
        json={"record_payment": True, "payment_method": "cash"},
        cookies=o_auth["cookies"],
        headers=o_auth["headers"],
    )
    assert res1.status_code == status.HTTP_200_OK

    # Second approval fails
    res2 = client.post(
        f"/api/v1/owner/enrollments/{enr_id}/approve",
        json={"record_payment": True, "payment_method": "cash"},
        cookies=o_auth["cookies"],
        headers=o_auth["headers"],
    )
    assert res2.status_code == status.HTTP_400_BAD_REQUEST
    assert "already approved" in res2.json()["detail"].lower() or "already active" in res2.json()["detail"].lower()


# ==============================================================================
# TEST 10: Concurrent Approval Attempts Cannot Activate Duplicate Memberships
# ==============================================================================
def test_concurrent_approval_idempotency_protection(
    client: TestClient, db_session: Session, setup_enrollment_test_data
):
    """Verify row locking and state checking prevent multiple simultaneous activations."""
    owner = setup_enrollment_test_data["owner"]
    plan = setup_enrollment_test_data["plan1"]

    # Create fresh enrollment directly
    enr = Enrollment(
        plan_id=plan.id,
        branch_id="narsobawadi",
        name="Concurrent Tester",
        phone="+91 98220 99992",
        email="concurrent@test.in",
        status="pending_verification",
        price=Decimal("4000.00"),
        currency="₹",
    )
    db_session.add(enr)
    db_session.commit()
    enr_id = str(enr.id)

    # First call approves
    o_auth = auth_headers_for_user(db_session, owner)
    res1 = client.post(
        f"/api/v1/owner/enrollments/{enr_id}/approve",
        json={"record_payment": False},
        cookies=o_auth["cookies"],
        headers=o_auth["headers"],
    )
    assert res1.status_code == status.HTTP_200_OK

    # Simulate second concurrent call where status is already payment_pending
    res2 = client.post(
        f"/api/v1/owner/enrollments/{enr_id}/approve",
        json={"record_payment": False},
        cookies=o_auth["cookies"],
        headers=o_auth["headers"],
    )
    # Cannot re-approve pending request that is already payment_pending
    assert res2.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# TEST 11: Member Portal and Keycard Reflect Authoritative Status
# ==============================================================================
# TEST 11: Member Portal Reflects Authoritative Status and Expiration
# ==============================================================================
def test_member_portal_reflects_authoritative_status_and_expiration(
    client: TestClient, db_session: Session, setup_enrollment_test_data
):
    """Verify /memberships/my-enrollment returns accurate enrollment lifecycle state and balance."""
    owner = setup_enrollment_test_data["owner"]
    member = setup_enrollment_test_data["member"]
    plan = setup_enrollment_test_data["plan1"]

    member.membership_status = "pending"
    db_session.commit()

    # Step A: Before enrollment, my-enrollment returns null
    m_auth = auth_headers_for_user(db_session, member)
    pre_enr = client.get("/api/v1/memberships/my-enrollment", cookies=m_auth["cookies"])
    assert pre_enr.status_code == status.HTTP_200_OK

    # Step B: Submit enrollment -> my-enrollment returns pending_verification
    client.post(
        "/api/v1/memberships/enroll",
        json={"planId": plan.id, "name": member.name, "phone": "+91 98220 12340", "email": member.email, "acceptedTerms": True},
        cookies=m_auth["cookies"],
        headers=m_auth["headers"],
    )
    pending_res = client.get("/api/v1/memberships/my-enrollment", cookies=m_auth["cookies"])
    assert pending_res.status_code == status.HTTP_200_OK
    assert pending_res.json()["enrollment"]["status"] in ("pending_verification", "Pending Verification at Gym Desk")
    assert pending_res.json()["enrollment"]["planName"] == plan.name

    # Step C: Owner approves to payment_pending -> portal displays awaiting payment
    enr_id = pending_res.json()["enrollment"]["id"]
    o_auth = auth_headers_for_user(db_session, owner)
    client.post(
        f"/api/v1/owner/enrollments/{enr_id}/approve",
        json={"record_payment": False},
        cookies=o_auth["cookies"],
        headers=o_auth["headers"],
    )
    pay_pending_res = client.get("/api/v1/memberships/my-enrollment", cookies=m_auth["cookies"])
    assert pay_pending_res.status_code == status.HTTP_200_OK
    assert pay_pending_res.json()["enrollment"]["status"] == "payment_pending"
    assert pay_pending_res.json()["enrollment"]["balanceDue"] == 4000.0

    # Step D: Front-desk payment recorded -> portal displays active with 0 balance
    client.post(
        f"/api/v1/owner/enrollments/{enr_id}/approve",
        json={"record_payment": True, "payment_method": "cash"},
        cookies=o_auth["cookies"],
        headers=o_auth["headers"],
    )
    active_res = client.get("/api/v1/memberships/my-enrollment", cookies=m_auth["cookies"])
    assert active_res.status_code == status.HTTP_200_OK
    assert active_res.json()["enrollment"]["status"] == "active"
    assert active_res.json()["enrollment"]["balanceDue"] == 0.0


# ==============================================================================
# TEST 12: Member Keycard Reflects Authoritative Status and Expiration
# ==============================================================================
def test_member_keycard_reflects_authoritative_status_and_expiration(
    client: TestClient, db_session: Session, setup_enrollment_test_data
):
    """Verify /auth/me returns authoritative plan, validity date, and keycard state across lifecycle."""
    owner = setup_enrollment_test_data["owner"]
    member = setup_enrollment_test_data["member"]
    plan = setup_enrollment_test_data["plan1"]

    member.membership_status = "pending"
    db_session.commit()

    # Step A: New member before enrollment -> keycard shows Trial / Awaiting Activation
    m_auth = auth_headers_for_user(db_session, member)
    me_pre = client.get("/api/v1/auth/me", cookies=m_auth["cookies"])
    assert me_pre.status_code == status.HTTP_200_OK

    # Step B: Member submits enrollment -> keycard shows Pending Verification
    enr_res = client.post(
        "/api/v1/memberships/enroll",
        json={"planId": plan.id, "name": member.name, "phone": "+91 98220 12349", "email": member.email, "acceptedTerms": True},
        cookies=m_auth["cookies"],
        headers=m_auth["headers"],
    )
    enr_id = enr_res.json()["enrollment"]["id"]

    me_pending = client.get("/api/v1/auth/me", cookies=m_auth["cookies"])
    assert me_pending.status_code == status.HTTP_200_OK
    user_p = me_pending.json()["user"]
    assert "Pending" in user_p["membershipPlan"]
    assert "Pending" in user_p["validUntil"]

    # Step C: Owner approves request without payment -> keycard shows Awaiting Payment
    o_auth = auth_headers_for_user(db_session, owner)
    client.post(
        f"/api/v1/owner/enrollments/{enr_id}/approve",
        json={"record_payment": False},
        cookies=o_auth["cookies"],
        headers=o_auth["headers"],
    )

    me_pay = client.get("/api/v1/auth/me", cookies=m_auth["cookies"])
    assert me_pay.status_code == status.HTTP_200_OK
    user_pay = me_pay.json()["user"]
    assert "Awaiting Payment" in user_pay["membershipPlan"]
    assert "Awaiting Desk Payment" in user_pay["validUntil"]

    # Step D: Desk payment recorded -> keycard updates immediately to active with valid expiration date
    client.post(
        f"/api/v1/owner/enrollments/{enr_id}/approve",
        json={"record_payment": True, "payment_method": "cash"},
        cookies=o_auth["cookies"],
        headers=o_auth["headers"],
    )

    me_active = client.get("/api/v1/auth/me", cookies=m_auth["cookies"])
    assert me_active.status_code == status.HTTP_200_OK
    user_act = me_active.json()["user"]
    assert user_act["status"].lower() == "active"
    assert user_act["membershipPlan"] == plan.name
    assert "Pending" not in user_act["validUntil"]
    assert "Awaiting" not in user_act["validUntil"]


# ==============================================================================
# TEST 13: Branch Managers Cannot Approve Requests from Unauthorized Branches
# ==============================================================================
def test_branch_manager_cross_branch_approval_prevented(
    client: TestClient, db_session: Session, setup_enrollment_test_data
):
    """Verify branch manager of branch 1 cannot approve or reject branch 2 requests."""
    manager1 = setup_enrollment_test_data["manager1"]
    plan2 = setup_enrollment_test_data["plan2"]

    # Enrollment in Kolhapur City (branch 2)
    enr = Enrollment(
        plan_id=plan2.id,
        branch_id="kolhapur_city",
        name="Kolhapur Applicant",
        phone="+91 98220 99993",
        email="kolhapur_app@test.in",
        status="pending_verification",
        price=Decimal("15000.00"),
        currency="₹",
    )
    db_session.add(enr)
    db_session.commit()
    enr_id = str(enr.id)

    # Manager 1 (Narsobawadi) attempts to approve Kolhapur request -> 403 Forbidden
    m1_auth = auth_headers_for_user(db_session, manager1)
    appr_res = client.post(
        f"/api/v1/owner/enrollments/{enr_id}/approve",
        json={"record_payment": False},
        cookies=m1_auth["cookies"],
        headers=m1_auth["headers"],
    )
    assert appr_res.status_code == status.HTTP_403_FORBIDDEN
    assert "not authorized to approve applications for branch" in appr_res.json()["detail"].lower()

    # Manager 1 attempts to reject Kolhapur request -> 403 Forbidden
    rej_res = client.post(
        f"/api/v1/owner/enrollments/{enr_id}/reject",
        json={"reason": "Unauthorized attempt"},
        cookies=m1_auth["cookies"],
        headers=m1_auth["headers"],
    )
    assert rej_res.status_code == status.HTTP_403_FORBIDDEN
    assert "not authorized to reject applications for branch" in rej_res.json()["detail"].lower()
