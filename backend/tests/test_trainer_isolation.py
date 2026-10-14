import pytest
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from backend.app.models.user import User
from backend.app.models.organization import Organization, Branch
from backend.app.models.trainer import TrainerProfile
from backend.app.services.trainer_service import assign_member_to_trainer
from backend.app.core.security import hash_password
from backend.app.core.auth import create_user_session


def _setup_branch(db: Session) -> Branch:
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


def test_trainer_can_only_view_assigned_members(client: TestClient, db_session: Session):
    """
    Verify server-side isolation prevents Coach A from accessing Coach B's private members.
    Coach A querying Coach B's member must receive HTTP 403 Forbidden.
    """
    branch = _setup_branch(db_session)
    today = date.today()

    # Create two trainers
    coach_rohit = User(
        email="rohit_coach@rvfitness.in",
        hashed_password=hash_password("CoachPass123"),
        name="Rohit V.",
        role="trainer",
        branch_id=branch.id,
    )
    coach_sneha = User(
        email="sneha_coach@rvfitness.in",
        hashed_password=hash_password("CoachPass123"),
        name="Sneha P.",
        role="trainer",
        branch_id=branch.id,
    )
    db_session.add_all([coach_rohit, coach_sneha])
    db_session.flush()

    # Create members
    member_rohit = User(
        email="member_rohit@rvfitness.in",
        hashed_password=hash_password("MemberPass123"),
        name="Rohit Client",
        role="member",
        branch_id=branch.id,
        assigned_trainer_id=coach_rohit.id,
        membership_status="active",
        valid_until=today + timedelta(days=30),
    )
    member_sneha = User(
        email="member_sneha@rvfitness.in",
        hashed_password=hash_password("MemberPass123"),
        name="Sneha Client",
        role="member",
        branch_id=branch.id,
        assigned_trainer_id=coach_sneha.id,
        membership_status="active",
        valid_until=today + timedelta(days=30),
    )
    db_session.add_all([member_rohit, member_sneha])
    db_session.commit()

    # Session for Coach Rohit
    sess, token_rohit, csrf_rohit = create_user_session(db_session, coach_rohit, client)
    headers = {
        "x-csrf-token": csrf_rohit,
        "Cookie": f"rvf_session={token_rohit}; rvf_csrf_token={csrf_rohit}",
    }

    # 1. Coach Rohit views their assigned member -> 200 OK
    resp_assigned = client.get(f"/api/trainer/members/{member_rohit.id}", headers=headers)
    assert resp_assigned.status_code == 200
    assert resp_assigned.json()["name"] == "Rohit Client"

    # 2. Coach Rohit attempts to view Sneha's member -> 403 Forbidden
    resp_unassigned = client.get(f"/api/trainer/members/{member_sneha.id}", headers=headers)
    assert resp_unassigned.status_code == 403
    assert "not assigned to coach this member" in resp_unassigned.json()["detail"]


def test_trainer_member_assignment_capacity(db_session: Session):
    """
    Verify coach capacity limits (max_clients) are enforced when assigning members.
    """
    branch = _setup_branch(db_session)
    admin = User(
        email="admin_assign@rvfitness.in",
        hashed_password=hash_password("AdminPass123"),
        name="Admin User",
        role="org_admin",
        branch_id=branch.id,
    )
    coach = User(
        email="capacity_coach@rvfitness.in",
        hashed_password=hash_password("CoachPass123"),
        name="Capacity Coach",
        role="trainer",
        branch_id=branch.id,
    )
    db_session.add_all([admin, coach])
    db_session.flush()

    # Give coach a max capacity of 2 clients
    profile = TrainerProfile(
        user_id=coach.id,
        specialization="Strength",
        max_clients=2,
    )
    db_session.add(profile)
    db_session.flush()

    m1 = User(email="m1@rvfitness.in", hashed_password="pw", name="M1", role="member", branch_id=branch.id)
    m2 = User(email="m2@rvfitness.in", hashed_password="pw", name="M2", role="member", branch_id=branch.id)
    m3 = User(email="m3@rvfitness.in", hashed_password="pw", name="M3", role="member", branch_id=branch.id)
    db_session.add_all([m1, m2, m3])
    db_session.commit()

    # Assign 1 and 2 successfully
    assign_member_to_trainer(db=db_session, trainer_id=coach.id, member_id=m1.id, actor=admin)
    assign_member_to_trainer(db=db_session, trainer_id=coach.id, member_id=m2.id, actor=admin)
    db_session.commit()

    # Attempting to assign 3 exceeds capacity
    with pytest.raises(ValueError, match="at maximum client capacity"):
        assign_member_to_trainer(db=db_session, trainer_id=coach.id, member_id=m3.id, actor=admin)
