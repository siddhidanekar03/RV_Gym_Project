import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.core.security import hash_password
from backend.app.models.user import User
from backend.app.core.auth import SESSION_COOKIE_NAME


def test_admin_route_authorization_by_role(client: TestClient, db_session: Session):
    """Verify that administrative routes are strictly protected by role."""
    # 1. Unauthenticated request -> 401
    unauth_res = client.get("/api/admin/overview")
    assert unauth_res.status_code == 401

    # 2. Member role -> 403 Forbidden
    member = User(
        email="member_authz@rvfitness.in",
        hashed_password=hash_password("pw123456"),
        name="Regular Member",
        role="member",
    )
    db_session.add(member)
    db_session.commit()

    login_mem = client.post(
        "/api/auth/login",
        json={"email": "member_authz@rvfitness.in", "password": "pw123456"},
    )
    mem_cookie = login_mem.cookies.get(SESSION_COOKIE_NAME)

    forbidden_res = client.get("/api/admin/overview", cookies={SESSION_COOKIE_NAME: mem_cookie})
    assert forbidden_res.status_code == 403
    assert "Access denied" in forbidden_res.json()["error"]

    # 3. Staff / Admin role -> 200 OK
    admin_user = User(
        email="admin_authz@rvfitness.in",
        hashed_password=hash_password("adminpw123"),
        name="Coach Rohit (Admin)",
        role="admin",
        staff_role="Head Coach",
    )
    db_session.add(admin_user)
    db_session.commit()

    login_admin = client.post(
        "/api/auth/login",
        json={"email": "admin_authz@rvfitness.in", "password": "adminpw123"},
    )
    admin_cookie = login_admin.cookies.get(SESSION_COOKIE_NAME)

    allowed_res = client.get("/api/admin/overview", cookies={SESSION_COOKIE_NAME: admin_cookie})
    assert allowed_res.status_code == 200
    assert "totalMembers" in allowed_res.json()
    assert "activeTodayInGym" in allowed_res.json()


def test_trainer_and_member_isolation(db_session: Session):
    """Verify trainer assignment relationships and member data isolation at domain level."""
    trainer = User(
        email="trainer_sneha@rvfitness.in",
        hashed_password=hash_password("coachPass123"),
        name="Sneha P.",
        role="trainer",
    )
    db_session.add(trainer)
    db_session.flush()

    member_assigned = User(
        email="assigned_athlete@rvfitness.in",
        hashed_password=hash_password("athletePass123"),
        name="Assigned Athlete",
        role="member",
        assigned_trainer_id=trainer.id,
    )
    member_other = User(
        email="unassigned_athlete@rvfitness.in",
        hashed_password=hash_password("athletePass123"),
        name="Other Athlete",
        role="member",
        assigned_trainer_id=None,
    )
    db_session.add_all([member_assigned, member_other])
    db_session.commit()

    # Query trainer's assigned members
    assigned_list = (
        db_session.query(User)
        .filter(User.assigned_trainer_id == trainer.id)
        .all()
    )
    assert len(assigned_list) == 1
    assert assigned_list[0].email == "assigned_athlete@rvfitness.in"
