import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.core.security import hash_password
from backend.app.core.auth import create_user_session
from backend.app.models.user import User
from backend.app.models.organization import Organization, Branch
from backend.app.models.attendance import AttendanceRecord, ConsumedQRToken
from backend.app.models.member_profile import MemberProfile, MemberBodyMeasurement
from backend.app.models.workout import WorkoutSession, WorkoutSessionExercise
from backend.app.models.personal_record import PersonalRecord
from backend.app.services.attendance_service import generate_member_qr_token


def _get_or_create_branches(db: Session):
    org = db.query(Organization).filter(Organization.code == "RVF").first()
    if not org:
        org = Organization(name="RV Fitness", code="RVF", is_active=True)
        db.add(org)
        db.flush()

    branch1 = db.query(Branch).filter(Branch.id == "narsobawadi").first()
    if not branch1:
        branch1 = Branch(
            id="narsobawadi",
            organization_id=org.id,
            name="Narsobawadi Main Campus",
            code="narsobawadi",
            is_active=True,
        )
        db.add(branch1)

    branch2 = db.query(Branch).filter(Branch.id == "kolhapur").first()
    if not branch2:
        branch2 = Branch(
            id="kolhapur",
            organization_id=org.id,
            name="Kolhapur Center",
            code="kolhapur",
            is_active=True,
        )
        db.add(branch2)

    db.flush()
    return branch1, branch2


def _auth_headers(db: Session, user: User, client: TestClient):
    _, token, csrf = create_user_session(db, user, client)
    return {
        "x-csrf-token": csrf,
        "Cookie": f"rvf_session={token}; rvf_csrf_token={csrf}",
    }


def _create_user(db: Session, email: str, role: str = "member", branch_id: str = "narsobawadi", **kwargs):
    u = User(
        email=email,
        hashed_password=hash_password("TestSecurePass123!"),
        name=kwargs.get("name", "Test User"),
        phone=kwargs.get("phone", "+919822012345"),
        role=role,
        branch_id=branch_id,
        is_active=True,
        membership_status=kwargs.get("membership_status", "active"),
        streak_days=kwargs.get("streak_days", 5),
        assigned_trainer_id=kwargs.get("assigned_trainer_id", None),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ==============================================================================
# PART A: QR ATTENDANCE REPAIR & SECURITY TESTS
# ==============================================================================

def test_qr_checkin_hardened_rejects_regular_member(db_session: Session, client: TestClient):
    """
    Vulnerability check: A regular member cannot call /attendance/qr-check-in directly
    to self-check-in remotely. It must return HTTP 403 Forbidden.
    """
    _get_or_create_branches(db_session)
    member = _create_user(db_session, "remote_member@test.com", role="member")
    headers = _auth_headers(db_session, member, client)

    # Member generates QR token
    qr_token, _, _ = generate_member_qr_token(member)

    # Member attempts self-check-in via endpoint
    resp = client.post(
        "/api/v1/attendance/qr-check-in",
        json={"qrToken": qr_token, "branchId": "narsobawadi"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert "Forbidden" in resp.json()["detail"] or "Access denied" in resp.json()["detail"]


def test_qr_checkin_staff_end_to_end_persists_record(db_session: Session, client: TestClient):
    """
    Valid QR scanning by authorized staff records attendance and persists to database.
    """
    _get_or_create_branches(db_session)
    staff = _create_user(db_session, "staff_scanner@test.com", role="front_desk", branch_id="narsobawadi")
    member = _create_user(db_session, "valid_member@test.com", role="member", branch_id="narsobawadi")

    staff_headers = _auth_headers(db_session, staff, client)
    qr_token, _, _ = generate_member_qr_token(member)

    # Staff scans member token
    resp = client.post(
        "/api/v1/attendance/qr-check-in",
        json={"qrToken": qr_token, "branchId": "narsobawadi"},
        headers=staff_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "QR check-in verified" in data["message"] or "Welcome to the gym" in data["message"]

    # Verify database persistence
    record = (
        db_session.query(AttendanceRecord)
        .filter(AttendanceRecord.user_id == member.id, AttendanceRecord.check_in_date == date.today())
        .first()
    )
    assert record is not None
    assert record.branch_id == "narsobawadi"
    assert record.source == "qr"


def test_qr_checkin_rejects_replay_token(db_session: Session, client: TestClient):
    """
    Replaying an already consumed QR token fails immediately.
    """
    _get_or_create_branches(db_session)
    staff = _create_user(db_session, "staff_replay@test.com", role="front_desk", branch_id="narsobawadi")
    member = _create_user(db_session, "member_replay@test.com", role="member", branch_id="narsobawadi")

    staff_headers = _auth_headers(db_session, staff, client)
    qr_token, _, _ = generate_member_qr_token(member)

    # First scan succeeds
    resp1 = client.post(
        "/api/v1/attendance/qr-check-in",
        json={"qrToken": qr_token, "branchId": "narsobawadi"},
        headers=staff_headers,
    )
    assert resp1.status_code == 200

    # Second scan with exact same token must fail
    resp2 = client.post(
        "/api/v1/attendance/qr-check-in",
        json={"qrToken": qr_token, "branchId": "narsobawadi"},
        headers=staff_headers,
    )
    assert resp2.status_code == 400
    assert "already been scanned" in resp2.json()["detail"] or "already checked in" in resp2.json()["detail"] or "Replay rejected" in resp2.json()["detail"]


def test_qr_checkin_rejects_cross_branch_access(db_session: Session, client: TestClient):
    """
    Staff from branch B cannot scan members at branch A without authorization.
    """
    _get_or_create_branches(db_session)
    staff_kolhapur = _create_user(db_session, "staff_kp@test.com", role="front_desk", branch_id="kolhapur")
    member_narso = _create_user(db_session, "member_narso@test.com", role="member", branch_id="narsobawadi")

    headers = _auth_headers(db_session, staff_kolhapur, client)
    qr_token, _, _ = generate_member_qr_token(member_narso)

    # Staff from Kolhapur tries to check in member for Narsobawadi
    resp = client.post(
        "/api/v1/attendance/qr-check-in",
        json={"qrToken": qr_token, "branchId": "narsobawadi"},
        headers=headers,
    )
    assert resp.status_code in (400, 403)


# ==============================================================================
# PART B: MEMBER PROFILE & SENSITIVE HEALTH DATA TESTS
# ==============================================================================

def test_member_profile_crud_and_age_calculation(db_session: Session, client: TestClient):
    """
    Member can retrieve and update their personal profile.
    Age is dynamically computed from date of birth.
    """
    _get_or_create_branches(db_session)
    member = _create_user(db_session, "profile_member@test.com", role="member")
    headers = _auth_headers(db_session, member, client)

    # Get my profile
    resp = client.get("/api/v1/profile/me", headers=headers)
    assert resp.status_code == 200
    p = resp.json()
    assert p["email"] == "profile_member@test.com"
    assert p["accessScope"] == "full"

    # Update personal details and DOB (e.g. member born 2000-05-15)
    update_payload = {
        "personal": {
            "name": "Updated Name Patil",
            "phone": "+919822099999",
            "date_of_birth": "2000-05-15",
            "gender": "male",
            "emergency_contact_name": "Emergency Relative",
            "emergency_contact_phone": "+919822088888",
        },
        "targets": {
            "height_cm": 178.5,
            "target_weight_kg": 75.0,
            "primary_goal": "strength",
        },
    }
    resp_update = client.put("/api/v1/profile/me", json=update_payload, headers=headers)
    assert resp_update.status_code == 200
    data = resp_update.json()
    assert data["name"] == "Updated Name Patil"
    assert data["calculatedAge"] is not None
    assert data["calculatedAge"] >= 25
    assert data["targetWeightKg"] == 75.0


def test_member_profile_validation_rejects_invalid_inputs(db_session: Session, client: TestClient):
    """
    Invalid dates of birth (future or < 12 years) and invalid phone numbers are rejected.
    """
    _get_or_create_branches(db_session)
    member = _create_user(db_session, "valid_test_user@test.com", role="member")
    headers = _auth_headers(db_session, member, client)

    # Future date of birth
    resp = client.put(
        "/api/v1/profile/me",
        json={"personal": {"date_of_birth": "2030-01-01"}},
        headers=headers,
    )
    assert resp.status_code == 422

    # Under 12 years old
    resp2 = client.put(
        "/api/v1/profile/me",
        json={"personal": {"date_of_birth": (date.today() - timedelta(days=365 * 5)).isoformat()}},
        headers=headers,
    )
    assert resp2.status_code == 422

    # Out of range body weight
    resp3 = client.post(
        "/api/v1/profile/measurements",
        json={"recorded_date": date.today().isoformat(), "weight_kg": 999.0},
        headers=headers,
    )
    assert resp3.status_code == 422


def test_member_cannot_read_another_members_profile(db_session: Session, client: TestClient):
    """
    A member cannot access another member's profile via /profile/member/{id}.
    Returns HTTP 403.
    """
    _get_or_create_branches(db_session)
    member1 = _create_user(db_session, "member1@test.com", role="member")
    member2 = _create_user(db_session, "member2@test.com", role="member")

    headers1 = _auth_headers(db_session, member1, client)
    resp = client.get(f"/api/v1/profile/member/{member2.id}", headers=headers1)
    assert resp.status_code == 403


def test_least_privilege_health_data_scoping_by_role(db_session: Session, client: TestClient):
    """
    Privacy verification:
    - Member gets full health details.
    - Assigned coach gets only training-relevant restrictions (conditions & confidential notes redacted).
    - Front desk staff has health details fully redacted.
    - Unassigned coach is forbidden (HTTP 403).
    """
    _get_or_create_branches(db_session)
    coach = _create_user(db_session, "assigned_coach@test.com", role="trainer")
    unassigned_coach = _create_user(db_session, "unassigned_coach@test.com", role="trainer")
    front_desk = _create_user(db_session, "front_desk_staff@test.com", role="front_desk")
    member = _create_user(
        db_session,
        "health_member@test.com",
        role="member",
        assigned_trainer_id=coach.id,
    )

    # Member sets health disclosures
    member_headers = _auth_headers(db_session, member, client)
    health_payload = {
        "health": {
            "exercise_restrictions": "No heavy deadlifts due to disc bulge",
            "current_injuries": "L4-L5 lumbar strain",
            "health_conditions": "Private cardiac condition",
            "health_notes": "Confidential member note",
        }
    }
    client.put("/api/v1/profile/me", json=health_payload, headers=member_headers)

    # 1. Assigned coach access: receives training restrictions, sensitive conditions are None
    coach_headers = _auth_headers(db_session, coach, client)
    coach_resp = client.get(f"/api/v1/profile/member/{member.id}", headers=coach_headers)
    assert coach_resp.status_code == 200
    coach_data = coach_resp.json()
    assert coach_data["accessScope"] == "coach_training"
    assert coach_data["exerciseRestrictions"] == "No heavy deadlifts due to disc bulge"
    assert coach_data["healthConditions"] is None  # Redacted
    assert coach_data["healthNotes"] is None  # Redacted

    # 2. Front desk access: health notes are completely redacted
    fd_headers = _auth_headers(db_session, front_desk, client)
    fd_resp = client.get(f"/api/v1/profile/member/{member.id}", headers=fd_headers)
    assert fd_resp.status_code == 200
    fd_data = fd_resp.json()
    assert fd_data["accessScope"] == "front_desk_reception"
    assert fd_data["exerciseRestrictions"] is None  # Redacted for reception
    assert fd_data["healthConditions"] is None
    # But front desk has emergency contact
    assert "emergencyContactName" in fd_data

    # 3. Unassigned coach: HTTP 403 Forbidden
    unassigned_headers = _auth_headers(db_session, unassigned_coach, client)
    unassigned_resp = client.get(f"/api/v1/profile/member/{member.id}", headers=unassigned_headers)
    assert unassigned_resp.status_code == 403


# ==============================================================================
# PART C: TIME-SERIES MEASUREMENTS & FITNESS PERFORMANCE TRACKING TESTS
# ==============================================================================

def test_time_series_measurements_preserves_history(db_session: Session, client: TestClient):
    """
    Logging multiple dated body measurements preserves historical records
    without overwriting past weigh-ins.
    """
    _get_or_create_branches(db_session)
    member = _create_user(db_session, "metrics_member@test.com", role="member")
    headers = _auth_headers(db_session, member, client)

    # Baseline measurement 30 days ago
    client.post(
        "/api/v1/profile/measurements",
        json={
            "recorded_date": (date.today() - timedelta(days=30)).isoformat(),
            "weight_kg": 80.0,
            "height_cm": 178.0,
            "notes": "Initial baseline",
        },
        headers=headers,
    )

    # Second measurement today
    client.post(
        "/api/v1/profile/measurements",
        json={
            "recorded_date": date.today().isoformat(),
            "weight_kg": 76.5,
            "notes": "Progress check",
        },
        headers=headers,
    )

    # Verify both records exist in chronological order
    resp = client.get("/api/v1/profile/measurements", headers=headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    assert items[0]["weightKg"] == 76.5
    assert items[1]["weightKg"] == 80.0


def test_performance_summary_weight_change_calculation(db_session: Session, client: TestClient):
    """
    Performance summary correctly calculates net weight change (latest - baseline).
    """
    _get_or_create_branches(db_session)
    member = _create_user(db_session, "perf_member@test.com", role="member")
    headers = _auth_headers(db_session, member, client)

    # Baseline: 85.0 kg, Target: 75.0 kg
    client.put(
        "/api/v1/profile/me",
        json={"targets": {"target_weight_kg": 75.0, "primary_goal": "fat_loss"}},
        headers=headers,
    )

    client.post(
        "/api/v1/profile/measurements",
        json={"recorded_date": (date.today() - timedelta(days=20)).isoformat(), "weight_kg": 85.0},
        headers=headers,
    )
    client.post(
        "/api/v1/profile/measurements",
        json={"recorded_date": date.today().isoformat(), "weight_kg": 82.0},
        headers=headers,
    )

    summary_resp = client.get("/api/v1/performance/summary", headers=headers)
    assert summary_resp.status_code == 200
    s = summary_resp.json()
    assert s["baselineWeightKg"] == 85.0
    assert s["currentWeightKg"] == 82.0
    # Net change: 82.0 - 85.0 = -3.0 kg
    assert s["netWeightChangeKg"] == -3.0
    assert s["goalWeightKg"] == 75.0
    assert s["goalProgressPct"] is not None
    assert s["goalProgressPct"] == 30.0  # 3kg lost out of 10kg goal = 30%


def test_log_completed_workout_session_and_pr_recognition(db_session: Session, client: TestClient):
    """
    Recording completed workout persists the session with exercise sets/reps,
    and automatically recognizes new personal best records.
    """
    _get_or_create_branches(db_session)
    member = _create_user(db_session, "workout_member@test.com", role="member")
    headers = _auth_headers(db_session, member, client)

    workout_payload = {
        "sessionName": "Heavy Leg Day",
        "sessionDate": date.today().isoformat(),
        "durationMinutes": 60,
        "rpe": 9,
        "exercises": [
            {"exerciseName": "Barbell Squat", "sets": 5, "reps": 5, "weightKg": 140.0},
            {"exerciseName": "Romanian Deadlift", "sets": 4, "reps": 8, "weightKg": 110.0},
        ],
    }

    resp = client.post("/api/v1/performance/workouts/complete", json=workout_payload, headers=headers)
    assert resp.status_code == 200
    session_data = resp.json()
    assert session_data["status"] == "completed"
    assert session_data["duration_minutes"] == 60
    assert len(session_data["exercises"]) == 2

    # Check that a Personal Record was automatically recorded for Barbell Squat @ 140kg
    pr = (
        db_session.query(PersonalRecord)
        .filter(PersonalRecord.user_id == member.id, PersonalRecord.exercise_name == "Barbell Squat")
        .first()
    )
    assert pr is not None
    assert float(pr.value) == 140.0


def test_coach_assigned_members_progress_overview(db_session: Session, client: TestClient):
    """
    Coach can retrieve progress overview for assigned members including weight change,
    workouts this month, and movement restrictions.
    """
    _get_or_create_branches(db_session)
    coach = _create_user(db_session, "head_coach@test.com", role="trainer")
    athlete = _create_user(
        db_session,
        "athlete1@test.com",
        role="member",
        assigned_trainer_id=coach.id,
    )

    coach_headers = _auth_headers(db_session, coach, client)

    # Add a measurement for athlete
    athlete_headers = _auth_headers(db_session, athlete, client)
    client.post(
        "/api/v1/profile/measurements",
        json={"recorded_date": date.today().isoformat(), "weight_kg": 72.0},
        headers=athlete_headers,
    )

    resp = client.get("/api/v1/performance/coach/members", headers=coach_headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    target = next((item for item in items if item["memberId"] == athlete.id), None)
    assert target is not None
    assert target["currentWeightKg"] == 72.0
