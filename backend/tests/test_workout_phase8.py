import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.core.auth import (
    create_user_session,
    SESSION_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
)
from backend.app.core.security import hash_password
from backend.app.models.user import User
from backend.app.models.organization import Organization, Branch
from backend.app.models.attendance import AttendanceRecord
from backend.app.models.audit import AuditLog
from backend.app.models.leaderboard import PointLedgerEntry
from backend.app.models.workout import (
    WorkoutPlan,
    WorkoutPlanAssignment,
    WorkoutPlanExercise,
    WorkoutSession,
    WorkoutSessionExercise,
    FitnessProgressRecord,
)
from backend.app.services.workout_service import (
    create_workout_plan,
    update_workout_session,
)
from backend.app.services.leaderboard_service import (
    award_attendance_points,
    reverse_workout_points,
)


@pytest.fixture
def workout_fixtures(db_session: Session):
    """Seed multi-branch fixtures and roles for Phase 8 workout testing."""
    # Organization
    org = db_session.query(Organization).filter(Organization.code == "RVF").first()
    if not org:
        org = Organization(name="RV Fitness Systems", code="RVF", contact_email="contact@rvfitness.in")
        db_session.add(org)
        db_session.flush()

    # Branches
    b1 = db_session.query(Branch).filter(Branch.id == "narsobawadi").first()
    if not b1:
        b1 = Branch(id="narsobawadi", organization_id=org.id, name="Narsobawadi Campus", code="NRS", is_active=True)
        db_session.add(b1)

    b2 = db_session.query(Branch).filter(Branch.id == "sangli").first()
    if not b2:
        b2 = Branch(id="sangli", organization_id=org.id, name="Sangli Campus", code="SGL", is_active=True)
        db_session.add(b2)

    db_session.flush()

    # Users
    admin = db_session.query(User).filter(User.email == "w_admin@rvf.in").first()
    if not admin:
        admin = User(
            email="w_admin@rvf.in",
            hashed_password=hash_password("AdminSecret123!"),
            name="Executive Director",
            role="org_admin",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(admin)

    mgr_nrs = db_session.query(User).filter(User.email == "w_mgr_nrs@rvf.in").first()
    if not mgr_nrs:
        mgr_nrs = User(
            email="w_mgr_nrs@rvf.in",
            hashed_password=hash_password("ManagerSecret123!"),
            name="Manager Narsobawadi",
            role="branch_manager",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(mgr_nrs)

    trainer_nrs = db_session.query(User).filter(User.email == "w_coach_nrs@rvf.in").first()
    if not trainer_nrs:
        trainer_nrs = User(
            email="w_coach_nrs@rvf.in",
            hashed_password=hash_password("CoachSecret123!"),
            name="Coach Vikram",
            role="trainer",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(trainer_nrs)

    trainer_sgl = db_session.query(User).filter(User.email == "w_coach_sgl@rvf.in").first()
    if not trainer_sgl:
        trainer_sgl = User(
            email="w_coach_sgl@rvf.in",
            hashed_password=hash_password("CoachSecret123!"),
            name="Coach Rohan",
            role="trainer",
            branch_id="sangli",
            is_active=True,
        )
        db_session.add(trainer_sgl)

    member_nrs_1 = db_session.query(User).filter(User.email == "w_mem_nrs1@rvf.in").first()
    if not member_nrs_1:
        member_nrs_1 = User(
            email="w_mem_nrs1@rvf.in",
            hashed_password=hash_password("MemberSecret123!"),
            name="Arjun Kulkarni",
            role="member",
            branch_id="narsobawadi",
            assigned_trainer_id=None,
            membership_id="RVF-W-001",
            membership_status="active",
            valid_until=date.today() + timedelta(days=90),
            is_active=True,
        )
        db_session.add(member_nrs_1)

    member_nrs_2 = db_session.query(User).filter(User.email == "w_mem_nrs2@rvf.in").first()
    if not member_nrs_2:
        member_nrs_2 = User(
            email="w_mem_nrs2@rvf.in",
            hashed_password=hash_password("MemberSecret123!"),
            name="Rohit Patil",
            role="member",
            branch_id="narsobawadi",
            assigned_trainer_id=None,
            membership_id="RVF-W-002",
            membership_status="active",
            valid_until=date.today() + timedelta(days=90),
            is_active=True,
        )
        db_session.add(member_nrs_2)

    member_sgl_1 = db_session.query(User).filter(User.email == "w_mem_sgl1@rvf.in").first()
    if not member_sgl_1:
        member_sgl_1 = User(
            email="w_mem_sgl1@rvf.in",
            hashed_password=hash_password("MemberSecret123!"),
            name="Pradnya Joshi",
            role="member",
            branch_id="sangli",
            assigned_trainer_id=None,
            membership_id="RVF-W-SGL1",
            membership_status="active",
            valid_until=date.today() + timedelta(days=90),
            is_active=True,
        )
        db_session.add(member_sgl_1)

    db_session.commit()

    return {
        "org": org,
        "branches": {"narsobawadi": b1, "sangli": b2},
        "admin": admin,
        "mgr_nrs": mgr_nrs,
        "trainer_nrs": trainer_nrs,
        "trainer_sgl": trainer_sgl,
        "member_nrs_1": member_nrs_1,
        "member_nrs_2": member_nrs_2,
        "member_sgl_1": member_sgl_1,
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


def test_01_authorized_workout_plan_creation_and_editing(client: TestClient, db_session: Session, workout_fixtures):
    """1. Authorized workout plan creation and editing by assigned coach."""
    fx = workout_fixtures
    coach = fx["trainer_nrs"]
    headers = _auth_headers(client, db_session, coach)

    payload = {
        "name": "Hypertrophy Foundations A",
        "description": "4-week introductory hypertrophy plan targeting full body compound movements.",
        "goal": "strength",
        "difficulty": "intermediate",
        "duration_weeks": 4,
        "status": "active",
        "exercises": [
            {
                "day_number": 1,
                "day_name": "Push Day",
                "exercise_order": 1,
                "name": "Barbell Bench Press",
                "instructions": "Retract scapulae and maintain arch.",
                "sets": 4,
                "reps": 8,
                "target_weight_kg": 70.0,
                "rest_seconds": 90,
            },
            {
                "day_number": 1,
                "day_name": "Push Day",
                "exercise_order": 2,
                "name": "Overhead Barbell Press",
                "instructions": "Strict standing press with core locked.",
                "sets": 3,
                "reps": 10,
                "target_weight_kg": 40.0,
                "rest_seconds": 60,
            },
        ],
    }

    res = client.post("/api/workouts/plans", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["name"] == "Hypertrophy Foundations A"
    assert data["difficulty"] == "intermediate"
    assert len(data["exercises"]) == 2
    assert data["trainer_id"] == coach.id
    plan_id = data["id"]

    # Edit plan details
    update_payload = {
        "name": "Hypertrophy Foundations Alpha",
        "duration_weeks": 6,
    }
    update_res = client.put(f"/api/workouts/plans/{plan_id}", json=update_payload, headers=headers)
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["name"] == "Hypertrophy Foundations Alpha"
    assert updated_data["duration_weeks"] == 6


def test_02_rejection_of_unauthorized_plan_modifications(client: TestClient, db_session: Session, workout_fixtures):
    """2. Rejection of unauthorized plan creation and modification attempts."""
    fx = workout_fixtures
    mem = fx["member_nrs_1"]
    coach_sgl = fx["trainer_sgl"]
    coach_nrs = fx["trainer_nrs"]

    # Member cannot create plans
    mem_headers = _auth_headers(client, db_session, mem)
    res_mem = client.post(
        "/api/workouts/plans",
        json={"name": "Member Illegal Plan", "goal": "general_fitness"},
        headers=mem_headers,
    )
    assert res_mem.status_code == 403

    # Create plan with Coach NRS
    nrs_headers = _auth_headers(client, db_session, coach_nrs)
    plan_res = client.post(
        "/api/workouts/plans",
        json={"name": "Coach NRS Plan", "goal": "strength", "difficulty": "intermediate"},
        headers=nrs_headers,
    )
    assert plan_res.status_code == 200
    plan_id = plan_res.json()["id"]

    # Coach from Sangli cannot modify Coach NRS's plan
    sgl_headers = _auth_headers(client, db_session, coach_sgl)
    res_unauth = client.put(
        f"/api/workouts/plans/{plan_id}",
        json={"name": "Hijacked Plan"},
        headers=sgl_headers,
    )
    assert res_unauth.status_code == 403


def test_03_trainer_assignment_and_cross_branch_isolation(client: TestClient, db_session: Session, workout_fixtures):
    """3. Trainer assignment and cross-branch isolation rules."""
    fx = workout_fixtures
    coach_nrs = fx["trainer_nrs"]
    mem_nrs = fx["member_nrs_1"]
    mem_sgl = fx["member_sgl_1"]

    # Assign member_nrs to coach_nrs
    mem_nrs.assigned_trainer_id = coach_nrs.id
    db_session.commit()

    nrs_headers = _auth_headers(client, db_session, coach_nrs)

    # Coach NRS creates plan
    plan_res = client.post(
        "/api/workouts/plans",
        json={"name": "NRS Branch Plan", "goal": "strength", "difficulty": "intermediate"},
        headers=nrs_headers,
    )
    assert plan_res.status_code == 200
    plan_id = plan_res.json()["id"]

    # Coach NRS assigns plan to their assigned member
    assign_res = client.post(
        f"/api/workouts/plans/{plan_id}/assign",
        json={"member_id": mem_nrs.id, "notes": "Follow 3x weekly."},
        headers=nrs_headers,
    )
    assert assign_res.status_code == 200
    assert assign_res.json()["is_active"] is True

    # Coach NRS attempts to assign plan to Sangli member (cross-branch IDOR)
    cross_res = client.post(
        f"/api/workouts/plans/{plan_id}/assign",
        json={"member_id": mem_sgl.id},
        headers=nrs_headers,
    )
    assert cross_res.status_code == 403


def test_04_members_viewing_only_their_assigned_plans(client: TestClient, db_session: Session, workout_fixtures):
    """4. Members can view only plans assigned to them."""
    fx = workout_fixtures
    coach_nrs = fx["trainer_nrs"]
    mem_assigned = fx["member_nrs_1"]
    mem_unassigned = fx["member_nrs_2"]

    # Create plan and assign only to member_nrs_1
    nrs_headers = _auth_headers(client, db_session, coach_nrs)
    mem_assigned.assigned_trainer_id = coach_nrs.id
    db_session.commit()

    plan_res = client.post(
        "/api/workouts/plans",
        json={"name": "Exclusive Athlete Plan", "goal": "endurance", "difficulty": "beginner"},
        headers=nrs_headers,
    )
    plan_id = plan_res.json()["id"]

    client.post(f"/api/workouts/plans/{plan_id}/assign", json={"member_id": mem_assigned.id}, headers=nrs_headers)

    # Assigned member checks assigned plans
    assigned_headers = _auth_headers(client, db_session, mem_assigned)
    list_res = client.get("/api/workouts/assigned", headers=assigned_headers)
    assert list_res.status_code == 200
    plan_ids = [p["workout_plan_id"] for p in list_res.json()]
    assert plan_id in plan_ids

    # Unassigned member checks assigned plans: does not see the plan
    unassigned_headers = _auth_headers(client, db_session, mem_unassigned)
    list_unassigned = client.get("/api/workouts/assigned", headers=unassigned_headers)
    assert list_unassigned.status_code == 200
    unassigned_ids = [p["workout_plan_id"] for p in list_unassigned.json()]
    assert plan_id not in unassigned_ids

    # Unassigned member attempts direct access to plan ID: forbidden
    direct_res = client.get(f"/api/workouts/plans/{plan_id}", headers=unassigned_headers)
    assert direct_res.status_code == 403


def test_05_nested_exercise_endpoint_authorization(client: TestClient, db_session: Session, workout_fixtures):
    """5. Nested exercise endpoint authorization and validation."""
    fx = workout_fixtures
    coach_nrs = fx["trainer_nrs"]
    coach_sgl = fx["trainer_sgl"]
    mem = fx["member_nrs_1"]

    nrs_headers = _auth_headers(client, db_session, coach_nrs)
    plan_res = client.post(
        "/api/workouts/plans",
        json={"name": "Exercise Mod Plan", "goal": "mobility", "difficulty": "beginner"},
        headers=nrs_headers,
    )
    plan_id = plan_res.json()["id"]

    # Coach adds exercise
    ex_payload = {
        "day_number": 2,
        "day_name": "Mobility Session",
        "exercise_order": 1,
        "name": "Hip Flexor Flow",
        "target_duration_seconds": 600,
        "rest_seconds": 30,
    }
    ex_res = client.post(f"/api/workouts/plans/{plan_id}/exercises", json=ex_payload, headers=nrs_headers)
    assert ex_res.status_code == 200
    ex_id = ex_res.json()["id"]

    # Member attempts to add exercise: 403 Forbidden
    mem_headers = _auth_headers(client, db_session, mem)
    mem_add = client.post(f"/api/workouts/plans/{plan_id}/exercises", json=ex_payload, headers=mem_headers)
    assert mem_add.status_code == 403

    # Coach SGL attempts to delete exercise: 403 Forbidden
    sgl_headers = _auth_headers(client, db_session, coach_sgl)
    sgl_del = client.delete(f"/api/workouts/plans/{plan_id}/exercises/{ex_id}", headers=sgl_headers)
    assert sgl_del.status_code == 403

    # Coach NRS deletes exercise: 204 No Content
    nrs_del = client.delete(f"/api/workouts/plans/{plan_id}/exercises/{ex_id}", headers=nrs_headers)
    assert nrs_del.status_code == 204


def test_06_valid_and_invalid_exercise_prescription_values(client: TestClient, db_session: Session, workout_fixtures):
    """6. Valid and invalid exercise prescription numeric values."""
    fx = workout_fixtures
    coach = fx["trainer_nrs"]
    headers = _auth_headers(client, db_session, coach)

    # Invalid difficulty
    bad_diff = client.post(
        "/api/workouts/plans",
        json={"name": "Bad Diff Plan", "difficulty": "impossible"},
        headers=headers,
    )
    assert bad_diff.status_code == 422

    # Plan with invalid exercise reps (> 500 reps)
    bad_reps = client.post(
        "/api/workouts/plans",
        json={
            "name": "Excessive Reps Plan",
            "exercises": [{"name": "Crunches", "reps": 1000}],
        },
        headers=headers,
    )
    assert bad_reps.status_code == 422


def test_07_session_lifecycle_and_duplicate_completion_prevention(client: TestClient, db_session: Session, workout_fixtures):
    """7. Session lifecycle and duplicate completion points prevention."""
    fx = workout_fixtures
    coach = fx["trainer_nrs"]
    mem = fx["member_nrs_1"]
    mem.assigned_trainer_id = coach.id
    db_session.commit()

    coach_headers = _auth_headers(client, db_session, coach)
    plan_res = client.post(
        "/api/workouts/plans",
        json={"name": "Lifecycle Plan", "goal": "strength", "difficulty": "beginner"},
        headers=coach_headers,
    )
    plan_id = plan_res.json()["id"]
    client.post(f"/api/workouts/plans/{plan_id}/assign", json={"member_id": mem.id}, headers=coach_headers)

    mem_headers = _auth_headers(client, db_session, mem)

    # Start session
    start_res = client.post("/api/workouts/sessions", json={"workout_plan_id": plan_id}, headers=mem_headers)
    assert start_res.status_code == 200
    session_data = start_res.json()
    assert session_data["status"] == "in_progress"
    session_id = session_data["id"]

    # Record actual sets and complete session
    complete_payload = {
        "status": "completed",
        "notes": "Solid workout, feeling energetic.",
        "exercises": [
            {
                "exercise_name": "Back Squat",
                "sets_completed": 3,
                "reps_completed": 8,
                "weight_kg": 80.0,
                "is_completed": True,
            }
        ],
    }
    comp_res = client.put(f"/api/workouts/sessions/{session_id}", json=complete_payload, headers=mem_headers)
    assert comp_res.status_code == 200
    data = comp_res.json()
    assert data["status"] == "completed"
    assert data["points_awarded"] == 5

    # Re-submitting completion does not duplicate points
    comp_again = client.put(f"/api/workouts/sessions/{session_id}", json=complete_payload, headers=mem_headers)
    assert comp_again.status_code == 200
    assert comp_again.json()["points_awarded"] == 5

    # Check database points ledger entries count for this session
    entries = (
        db_session.query(PointLedgerEntry)
        .filter(
            PointLedgerEntry.source_type == "workout_completed",
            PointLedgerEntry.source_id == session_id,
        )
        .all()
    )
    assert len(entries) == 1
    assert entries[0].points == 5


def test_08_members_cannot_modify_another_members_workout_history(client: TestClient, db_session: Session, workout_fixtures):
    """8. Members cannot modify or hijack another member's workout history."""
    fx = workout_fixtures
    mem1 = fx["member_nrs_1"]
    mem2 = fx["member_nrs_2"]

    mem1_headers = _auth_headers(client, db_session, mem1)
    s_res = client.post("/api/workouts/sessions", json={"session_name": "Arjun Solo Workout"}, headers=mem1_headers)
    session_id = s_res.json()["id"]

    # Member 2 attempts to update Member 1's session
    mem2_headers = _auth_headers(client, db_session, mem2)
    tamper_res = client.put(
        f"/api/workouts/sessions/{session_id}",
        json={"status": "completed", "notes": "Tampered by Rohit"},
        headers=mem2_headers,
    )
    assert tamper_res.status_code == 403


def test_09_private_fitness_records_and_sharing_permissions(client: TestClient, db_session: Session, workout_fixtures):
    """9. Sensitive fitness records are private to member and hidden from public endpoints."""
    fx = workout_fixtures
    mem1 = fx["member_nrs_1"]
    mem2 = fx["member_nrs_2"]

    mem1_headers = _auth_headers(client, db_session, mem1)
    record_payload = {
        "record_type": "body_weight",
        "value": 74.5,
        "unit": "kg",
        "is_private": True,
        "notes": "Target: cut to 72 kg.",
    }
    rec_res = client.post("/api/workouts/progress", json=record_payload, headers=mem1_headers)
    assert rec_res.status_code == 200
    assert rec_res.json()["is_private"] is True

    # Member 1 views their own progress
    get_res = client.get("/api/workouts/progress", headers=mem1_headers)
    assert get_res.status_code == 200
    assert len(get_res.json()) >= 1

    # Member 2 attempts to view Member 1's progress: 403 Forbidden
    mem2_headers = _auth_headers(client, db_session, mem2)
    snoop_res = client.get(f"/api/workouts/progress?member_id={mem1.id}", headers=mem2_headers)
    assert snoop_res.status_code == 403

    # Public leaderboard standings do not leak body weight
    lb_res = client.get("/api/leaderboard")
    assert lb_res.status_code == 200
    lb_text = lb_res.text
    assert "74.5" not in lb_text
    assert "body_weight" not in lb_text


def test_10_trainer_access_after_assignment_removal(client: TestClient, db_session: Session, workout_fixtures):
    """10. Trainer access to member progress is revoked when assignment is removed."""
    fx = workout_fixtures
    coach = fx["trainer_nrs"]
    mem = fx["member_nrs_1"]

    # Assign coach to member
    mem.assigned_trainer_id = coach.id
    db_session.commit()

    # Member creates shared fitness record
    mem_headers = _auth_headers(client, db_session, mem)
    client.post(
        "/api/workouts/progress",
        json={"record_type": "personal_record", "value": 120.0, "unit": "kg", "is_private": False},
        headers=mem_headers,
    )

    coach_headers = _auth_headers(client, db_session, coach)
    # Coach can view member progress while assigned
    view_res = client.get(f"/api/workouts/progress?member_id={mem.id}", headers=coach_headers)
    assert view_res.status_code == 200

    # Remove trainer assignment
    mem.assigned_trainer_id = None
    db_session.commit()

    # Coach is now blocked from viewing member's progress
    blocked_res = client.get(f"/api/workouts/progress?member_id={mem.id}", headers=coach_headers)
    assert blocked_res.status_code == 403


def test_11_self_reported_completion_vs_coach_verified(client: TestClient, db_session: Session, workout_fixtures):
    """11. Self-reported workout completion remains distinct from coach-verified status."""
    fx = workout_fixtures
    coach = fx["trainer_nrs"]
    mem = fx["member_nrs_1"]
    mem.assigned_trainer_id = coach.id
    db_session.commit()

    mem_headers = _auth_headers(client, db_session, mem)
    s_res = client.post("/api/workouts/sessions", json={"session_name": "Self Logged Run"}, headers=mem_headers)
    session_id = s_res.json()["id"]

    # Member completes session
    client.put(f"/api/workouts/sessions/{session_id}", json={"status": "completed"}, headers=mem_headers)

    s_check = client.get(f"/api/workouts/sessions/{session_id}", headers=mem_headers)
    assert s_check.json()["is_coach_verified"] is False
    assert s_check.json()["verified_by_id"] is None

    # Coach verifies session
    coach_headers = _auth_headers(client, db_session, coach)
    v_res = client.post(
        f"/api/workouts/sessions/{session_id}/verify",
        json={"is_coach_verified": True, "notes": "Good technique observed in squat."},
        headers=coach_headers,
    )
    assert v_res.status_code == 200
    assert v_res.json()["is_coach_verified"] is True
    assert v_res.json()["verified_by_id"] == coach.id


def test_12_duplicate_workout_point_awards_and_daily_cap(client: TestClient, db_session: Session, workout_fixtures):
    """12. Strict daily frequency limit: maximum 1 workout point award per calendar date."""
    fx = workout_fixtures
    mem = fx["member_nrs_1"]
    mem_headers = _auth_headers(client, db_session, mem)

    # Session 1 on today
    s1 = client.post("/api/workouts/sessions", json={"session_name": "Morning Session"}, headers=mem_headers).json()
    c1 = client.put(f"/api/workouts/sessions/{s1['id']}", json={"status": "completed"}, headers=mem_headers).json()
    assert c1["points_awarded"] == 5

    # Session 2 on today
    s2 = client.post("/api/workouts/sessions", json={"session_name": "Evening Session"}, headers=mem_headers).json()
    c2 = client.put(f"/api/workouts/sessions/{s2['id']}", json={"status": "completed"}, headers=mem_headers).json()
    # Daily cap prevents second award on same calendar date
    assert c2["points_awarded"] == 0

    # Total points from workout_completed for this member today must be exactly 5
    total = (
        db_session.query(PointLedgerEntry)
        .filter(
            PointLedgerEntry.user_id == mem.id,
            PointLedgerEntry.source_type == "workout_completed",
            PointLedgerEntry.event_date == date.today(),
        )
        .count()
    )
    assert total == 1


def test_13_point_reversals_and_audit_history(db_session: Session, workout_fixtures):
    """13. Reversals create compensating negative entries without deleting history."""
    fx = workout_fixtures
    mem = fx["member_nrs_1"]
    session_id = str(uuid.uuid4())

    # Create dummy completed session and ledger entry
    entry = PointLedgerEntry(
        id=str(uuid.uuid4()),
        user_id=mem.id,
        organization_id="rvf-org-main",
        branch_id="narsobawadi",
        source_type="workout_completed",
        source_id=session_id,
        points=5,
        event_date=date.today(),
        year=date.today().year,
        month=date.today().month,
        notes="Session completed",
        created_by=mem.id,
    )
    db_session.add(entry)
    db_session.commit()

    # Reversal
    rev_entry = reverse_workout_points(db_session, session_id, actor_id=fx["admin"].id, reason="Member logged bogus data")
    assert rev_entry is not None
    assert rev_entry.points == -5
    assert rev_entry.source_type == "workout_reversal"

    # Both rows exist in ledger
    rows = (
        db_session.query(PointLedgerEntry)
        .filter(
            PointLedgerEntry.user_id == mem.id,
            PointLedgerEntry.source_id.in_([session_id, f"rev:workout:{session_id}"]),
        )
        .all()
    )
    assert len(rows) == 2


def test_14_existing_attendance_and_leaderboard_scores_remain_unchanged(db_session: Session, workout_fixtures):
    """14. Existing attendance scoring (10 points) remains completely intact alongside workout points."""
    fx = workout_fixtures
    mem = fx["member_nrs_2"]

    # Attendance check-in on today
    att = AttendanceRecord(
        user_id=mem.id,
        branch_id="narsobawadi",
        check_in_date=date.today(),
        source="kiosk",
        method="rfid",
    )
    db_session.add(att)
    db_session.flush()

    att_entry = award_attendance_points(db_session, att)
    assert att_entry is not None
    assert att_entry.points == 10
    assert att_entry.source_type == "attendance_verified"


def test_15_plan_archival_preserves_historical_sessions(client: TestClient, db_session: Session, workout_fixtures):
    """15. Archiving a plan prevents new sessions but preserves existing session history."""
    fx = workout_fixtures
    coach = fx["trainer_nrs"]
    mem = fx["member_nrs_1"]
    mem.assigned_trainer_id = coach.id
    db_session.commit()

    coach_headers = _auth_headers(client, db_session, coach)
    plan_res = client.post(
        "/api/workouts/plans",
        json={"name": "Temporary Summer Blitz", "goal": "general_fitness"},
        headers=coach_headers,
    )
    plan_id = plan_res.json()["id"]
    client.post(f"/api/workouts/plans/{plan_id}/assign", json={"member_id": mem.id}, headers=coach_headers)

    mem_headers = _auth_headers(client, db_session, mem)
    # Start and complete session before archive
    s_res = client.post("/api/workouts/sessions", json={"workout_plan_id": plan_id}, headers=mem_headers)
    session_id = s_res.json()["id"]
    client.put(f"/api/workouts/sessions/{session_id}", json={"status": "completed"}, headers=mem_headers)

    # Coach archives the plan
    arch_res = client.delete(f"/api/workouts/plans/{plan_id}", headers=coach_headers)
    assert arch_res.status_code == 200
    assert arch_res.json()["status"] == "archived"

    # Historical session is still viewable
    hist_res = client.get(f"/api/workouts/sessions/{session_id}", headers=mem_headers)
    assert hist_res.status_code == 200
    assert hist_res.json()["id"] == session_id

    # Starting a new session for the archived plan is rejected
    new_res = client.post("/api/workouts/sessions", json={"workout_plan_id": plan_id}, headers=mem_headers)
    assert new_res.status_code == 400


def test_16_regression_auth_csrf_and_leaderboard_rules(client: TestClient, db_session: Session, workout_fixtures):
    """16. Mutating workout endpoints require valid CSRF and scoring rules list workout awards."""
    fx = workout_fixtures
    mem = fx["member_nrs_1"]
    session, token, csrf = create_user_session(db_session, mem)
    # Auth cookie provided, but NO CSRF header or cookie
    client.cookies.set(SESSION_COOKIE_NAME, token)
    client.cookies.delete(CSRF_COOKIE_NAME)
    bad_req = client.post("/api/workouts/sessions", json={})
    assert bad_req.status_code == 403

    # Transparent scoring rules endpoint includes Completed Workout Session
    rules_res = client.get("/api/leaderboard/rules")
    assert rules_res.status_code == 200
    rules = rules_res.json()["rules"]
    rule_activities = [r["activity"] for r in rules]
    assert "Completed Workout Session" in rule_activities
