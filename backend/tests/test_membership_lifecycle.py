from datetime import date, timedelta
from decimal import Decimal
import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from backend.app.models.user import User
from backend.app.models.organization import Organization, Branch
from backend.app.models.membership import MembershipPlan, PlanPrice, MembershipChange
from backend.app.services.membership_service import (
    get_effective_plan_price,
    renew_membership,
    freeze_membership,
    unfreeze_membership,
    cancel_membership,
    calculate_expiry,
)
from backend.app.core.security import hash_password
from backend.app.core.auth import create_user_session


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


def test_effective_dated_pricing_history(db_session: Session):
    """
    Verify pricing history resolves the exact price active on a target date,
    supporting scheduled future price changes and historical audit fidelity.
    """
    _setup_org_and_branch(db_session)
    plan = MembershipPlan(
        id="plan_strength_tier",
        name="Strength Tier",
        category="strength",
        access_scope="single_branch",
        price=Decimal("4000.00"),
        currency="₹",
        billing_cycle="3 months",
        duration_days=90,
        is_active=True,
        perks=["Floor access"],
    )
    db_session.add(plan)
    db_session.flush()

    # Historical price: Jan 1 2025 to Dec 31 2025 at 3500
    p2025 = PlanPrice(
        plan_id=plan.id,
        price=Decimal("3500.00"),
        currency="₹",
        effective_from=date(2025, 1, 1),
        effective_to=date(2025, 12, 31),
        is_active=True,
    )
    # Current price: Jan 1 2026 onwards at 4000
    p2026 = PlanPrice(
        plan_id=plan.id,
        price=Decimal("4000.00"),
        currency="₹",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        is_active=True,
    )
    db_session.add_all([p2025, p2026])
    db_session.commit()

    # Historical query
    price_2025 = get_effective_plan_price(db_session, plan.id, as_of=date(2025, 6, 15))
    assert price_2025 == Decimal("3500.00")

    # Current query
    price_current = get_effective_plan_price(db_session, plan.id, as_of=date(2026, 6, 15))
    assert price_current == Decimal("4000.00")


def test_membership_renewal_date_calculations(db_session: Session):
    """
    Verify renewal extends from current valid_until if active,
    or from today if expired, and generates renewal invoice.
    """
    branch = _setup_org_and_branch(db_session)
    plan = MembershipPlan(
        id="plan_monthly_test",
        name="Monthly",
        category="general",
        price=Decimal("1500.00"),
        currency="₹",
        billing_cycle="per month",
        duration_days=30,
        is_active=True,
        perks=[],
    )
    db_session.add(plan)
    db_session.flush()

    today = date.today()

    # 1. Active member with 10 days left
    active_member = User(
        email="active_renewal@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Active Renewing Member",
        role="member",
        branch_id=branch.id,
        membership_plan_id=plan.id,
        membership_status="active",
        valid_until=today + timedelta(days=10),
    )
    db_session.add(active_member)
    db_session.flush()

    updated_member, inv1 = renew_membership(db=db_session, user=active_member)
    db_session.commit()

    # Should extend by 30 days starting from current valid_until
    expected_new_date = today + timedelta(days=10 + 30)
    assert updated_member.valid_until == expected_new_date
    assert inv1.total_amount == Decimal("1500.00")

    # 2. Expired member renewal
    expired_member = User(
        email="expired_renewal@rvfitness.in",
        hashed_password=hash_password("Pass123!"),
        name="Expired Renewing Member",
        role="member",
        branch_id=branch.id,
        membership_plan_id=plan.id,
        membership_status="expired",
        valid_until=today - timedelta(days=20),
    )
    db_session.add(expired_member)
    db_session.flush()

    updated_expired, inv2 = renew_membership(db=db_session, user=expired_member)
    db_session.commit()

    # Should extend starting from today
    assert updated_expired.valid_until == today + timedelta(days=30)
    assert updated_expired.membership_status == "active"
    assert inv2.total_amount == Decimal("1500.00")


def test_membership_freeze_and_unfreeze(client: TestClient, db_session: Session):
    """
    Verify freezing extends valid_until by freeze days,
    blocks floor check-in while frozen, and unfreezing restores access.
    """
    branch = _setup_org_and_branch(db_session)
    admin = User(
        email="admin_freeze@rvfitness.in",
        hashed_password=hash_password("AdminPass123"),
        name="Org Administrator",
        role="org_admin",
        branch_id=branch.id,
    )
    today = date.today()
    member = User(
        email="freeze_member@rvfitness.in",
        hashed_password=hash_password("MemberPass123"),
        name="Freezable Member",
        role="member",
        branch_id=branch.id,
        membership_status="active",
        valid_until=today + timedelta(days=40),
    )
    db_session.add_all([admin, member])
    db_session.commit()

    # Freeze member for 14 days
    freeze_membership(db=db_session, user=member, freeze_days=14, actor=admin, reason="Vacation travel")
    db_session.commit()

    assert member.membership_status == "frozen"
    assert member.valid_until == today + timedelta(days=40 + 14)

    # Attempt check-in while frozen should be denied
    sess, raw_session, raw_csrf = create_user_session(db_session, member, client)
    headers = {
        "x-csrf-token": raw_csrf,
        "Cookie": f"rvf_session={raw_session}; rvf_csrf_token={raw_csrf}",
    }
    resp = client.post("/api/attendance/check-in", headers=headers)
    assert resp.status_code == 403
    assert "currently 'frozen'" in resp.json()["detail"]

    # Unfreeze member
    unfreeze_membership(db=db_session, user=member, actor=admin)
    db_session.commit()
    assert member.membership_status == "active"

    # Check-in should now succeed
    resp_unfrozen = client.post("/api/attendance/check-in", headers=headers)
    assert resp_unfrozen.status_code == 200
    assert resp_unfrozen.json()["success"] is True


def test_membership_cancellation(db_session: Session):
    """
    Verify cancelling a membership marks it cancelled, terminates future access,
    and logs the action in membership_changes.
    """
    branch = _setup_org_and_branch(db_session)
    admin = User(
        email="admin_cancel@rvfitness.in",
        hashed_password=hash_password("AdminPass123"),
        name="Org Administrator",
        role="org_admin",
        branch_id=branch.id,
    )
    today = date.today()
    member = User(
        email="cancel_member@rvfitness.in",
        hashed_password=hash_password("MemberPass123"),
        name="Cancellable Member",
        role="member",
        branch_id=branch.id,
        membership_status="active",
        valid_until=today + timedelta(days=60),
    )
    db_session.add_all([admin, member])
    db_session.commit()

    cancel_membership(db=db_session, user=member, actor=admin, reason="Relocation out of area")
    db_session.commit()

    assert member.membership_status == "cancelled"
    assert member.valid_until <= today

    change = (
        db_session.query(MembershipChange)
        .filter(MembershipChange.user_id == member.id, MembershipChange.action_type == "cancellation")
        .first()
    )
    assert change is not None
    assert change.reason == "Relocation out of area"
