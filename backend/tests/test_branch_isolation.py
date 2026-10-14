from datetime import date, timedelta
from decimal import Decimal
import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from backend.app.models.user import User
from backend.app.models.organization import Organization, Branch, MemberBranchAccess
from backend.app.models.membership import MembershipPlan
from backend.app.models.billing import Invoice
from backend.app.core.security import hash_password
from backend.app.core.auth import create_user_session


def _setup_multi_branch_org(db: Session):
    org = Organization(name="RV Fitness Group", code="RVF", is_active=True)
    db.add(org)
    db.flush()

    branch_narsobawadi = Branch(
        id="narsobawadi",
        organization_id=org.id,
        name="Narsobawadi Main Campus",
        code="narsobawadi",
        city="Narsobawadi",
        state="Maharashtra",
        is_active=True,
    )
    branch_kolhapur = Branch(
        id="kolhapur",
        organization_id=org.id,
        name="Kolhapur Elite Branch",
        code="kolhapur",
        city="Kolhapur",
        state="Maharashtra",
        is_active=True,
    )
    db.add_all([branch_narsobawadi, branch_kolhapur])
    db.flush()

    return branch_narsobawadi, branch_kolhapur


def test_branch_manager_scope_restricted_to_assigned_branch(client: TestClient, db_session: Session):
    """
    Verify a Branch Manager of Branch A cannot access or manage invoices of Branch B.
    """
    branch_a, branch_b = _setup_multi_branch_org(db_session)

    manager_a = User(
        email="manager_narsobawadi@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Narsobawadi Manager",
        role="branch_manager",
        branch_id=branch_a.id,
    )
    db_session.add(manager_a)
    db_session.flush()

    # Invoice created at Branch B
    inv_b = Invoice(
        invoice_number="INV-KOL-001",
        branch_id=branch_b.id,
        status="unpaid",
        subtotal=Decimal("5000.00"),
        total_amount=Decimal("5000.00"),
        amount_paid=Decimal("0.00"),
        balance_due=Decimal("5000.00"),
        due_date=date.today() + timedelta(days=7),
    )
    db_session.add(inv_b)
    db_session.commit()

    # Authenticate as Manager of Branch A
    sess, token, csrf = create_user_session(db_session, manager_a, client)
    headers = {
        "x-csrf-token": csrf,
        "Cookie": f"rvf_session={token}; rvf_csrf_token={csrf}",
    }

    # Accessing invoice of Branch B should be rejected
    resp = client.get(f"/api/billing/invoices/{inv_b.id}", headers=headers)
    assert resp.status_code == 403
    assert "scope is restricted to your assigned branch" in resp.json()["detail"]


def test_cross_branch_checkin_eligibility(client: TestClient, db_session: Session):
    """
    Verify cross-branch check-in rules:
    1. Member with single-branch plan at Branch A cannot check in at Branch B.
    2. Explicit grant in member_branch_access allows check-in at Branch B.
    3. Multi-branch plan tier allows check-in at Branch B without special grant.
    """
    branch_a, branch_b = _setup_multi_branch_org(db_session)
    today = date.today()

    # Plan 1: Single-branch plan
    plan_single = MembershipPlan(
        id="plan_single",
        name="Single Branch Plan",
        access_scope="single_branch",
        price=Decimal("1500.00"),
        currency="₹",
        billing_cycle="per month",
        duration_days=30,
        is_active=True,
        perks=[],
    )
    # Plan 2: All-branches plan
    plan_all = MembershipPlan(
        id="plan_all",
        name="All Branches Passport",
        access_scope="all_branches",
        price=Decimal("12000.00"),
        currency="₹",
        billing_cycle="per year",
        duration_days=365,
        is_active=True,
        perks=[],
    )
    db_session.add_all([plan_single, plan_all])
    db_session.flush()

    # Member 1: Belongs to Branch A, single-branch plan
    member_single = User(
        email="member_single@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Single Branch Member",
        role="member",
        branch_id=branch_a.id,
        membership_plan_id=plan_single.id,
        membership_status="active",
        valid_until=today + timedelta(days=20),
    )
    # Member 2: Belongs to Branch A, all-branches plan
    member_passport = User(
        email="member_passport@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Passport Member",
        role="member",
        branch_id=branch_a.id,
        membership_plan_id=plan_all.id,
        membership_status="active",
        valid_until=today + timedelta(days=200),
    )
    db_session.add_all([member_single, member_passport])
    db_session.commit()

    # 1. Member 1 attempts check-in at Branch B (cross-branch attempt) -> Denied 403
    sess1, tok1, csrf1 = create_user_session(db_session, member_single, client)
    headers1 = {"x-csrf-token": csrf1, "Cookie": f"rvf_session={tok1}; rvf_csrf_token={csrf1}"}

    resp1 = client.post(f"/api/attendance/check-in?branch_id={branch_b.id}", headers=headers1)
    assert resp1.status_code == 403
    assert "does not grant access to branch facility" in resp1.json()["detail"]

    # 2. Grant explicit access for Member 1 to Branch B
    grant = MemberBranchAccess(
        user_id=member_single.id,
        branch_id=branch_b.id,
        granted_at=today,
        expires_at=today + timedelta(days=7),
        is_active=True,
    )
    db_session.add(grant)
    db_session.commit()

    # Check-in at Branch B now succeeds
    resp1_granted = client.post(f"/api/attendance/check-in?branch_id={branch_b.id}", headers=headers1)
    assert resp1_granted.status_code == 200
    assert resp1_granted.json()["success"] is True

    # 3. Member 2 with all-branches tier checks in at Branch B directly -> Succeeds 200
    sess2, tok2, csrf2 = create_user_session(db_session, member_passport, client)
    headers2 = {"x-csrf-token": csrf2, "Cookie": f"rvf_session={tok2}; rvf_csrf_token={csrf2}"}

    resp2 = client.post(f"/api/attendance/check-in?branch_id={branch_b.id}", headers=headers2)
    assert resp2.status_code == 200
    assert resp2.json()["success"] is True
