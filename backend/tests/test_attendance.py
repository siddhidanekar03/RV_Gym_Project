from datetime import date, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from unittest.mock import patch

from backend.app.core.security import hash_password
from backend.app.models.user import User
from backend.app.models.attendance import AttendanceRecord
from backend.app.core.auth import SESSION_COOKIE_NAME, CSRF_COOKIE_NAME, CSRF_HEADER_NAME


def test_active_member_checkin_success(client: TestClient, db_session: Session):
    """Verify an active member with valid membership can check in and increment streak."""
    today = date.today()
    user = User(
        email="active_checkin@rvfitness.in",
        hashed_password=hash_password("pwActive123"),
        name="Active Checkin Member",
        role="member",
        membership_status="active",
        valid_until=today + timedelta(days=60),
        streak_days=5,
    )
    db_session.add(user)
    db_session.commit()

    login_res = client.post(
        "/api/auth/login",
        json={"email": "active_checkin@rvfitness.in", "password": "pwActive123"},
    )
    session_token = login_res.cookies.get(SESSION_COOKIE_NAME)
    csrf_token = login_res.cookies.get(CSRF_COOKIE_NAME)

    checkin_res = client.post(
        "/api/attendance/check-in",
        headers={CSRF_HEADER_NAME: csrf_token},
    )
    assert checkin_res.status_code == 200
    data = checkin_res.json()

    assert data["success"] is True
    assert data["streakDays"] == 6
    assert data["attendanceThisMonth"] >= 1
    assert "Check-in recorded" in data["message"]

    # Verify database record
    record = (
        db_session.query(AttendanceRecord)
        .filter(AttendanceRecord.user_id == user.id, AttendanceRecord.check_in_date == today)
        .first()
    )
    assert record is not None


def test_checkin_denied_for_pending_membership(client: TestClient, db_session: Session):
    """Verify check-in is rejected when member status is 'pending'."""
    user = User(
        email="pending_checkin@rvfitness.in",
        hashed_password=hash_password("pwPending123"),
        name="Pending Member",
        role="member",
        membership_status="pending",
        streak_days=0,
    )
    db_session.add(user)
    db_session.commit()

    login_res = client.post(
        "/api/auth/login",
        json={"email": "pending_checkin@rvfitness.in", "password": "pwPending123"},
    )
    session_token = login_res.cookies.get(SESSION_COOKIE_NAME)
    csrf_token = login_res.cookies.get(CSRF_COOKIE_NAME)

    res = client.post(
        "/api/attendance/check-in",
        headers={CSRF_HEADER_NAME: csrf_token},
    )
    assert res.status_code == 403
    assert "Active membership is required" in res.json()["error"]


def test_checkin_denied_for_expired_membership(client: TestClient, db_session: Session):
    """Verify check-in is rejected when valid_until is in the past."""
    today = date.today()
    user = User(
        email="expired_checkin@rvfitness.in",
        hashed_password=hash_password("pwExpired123"),
        name="Expired Member",
        role="member",
        membership_status="active",
        valid_until=today - timedelta(days=1),  # Expired yesterday
        streak_days=10,
    )
    db_session.add(user)
    db_session.commit()

    login_res = client.post(
        "/api/auth/login",
        json={"email": "expired_checkin@rvfitness.in", "password": "pwExpired123"},
    )
    session_token = login_res.cookies.get(SESSION_COOKIE_NAME)
    csrf_token = login_res.cookies.get(CSRF_COOKIE_NAME)

    res = client.post(
        "/api/attendance/check-in",
        headers={CSRF_HEADER_NAME: csrf_token},
    )
    assert res.status_code == 403
    assert "Your membership expired" in res.json()["error"]


def test_duplicate_checkin_rejected_same_day(client: TestClient, db_session: Session):
    """Verify second check-in attempt on the same day is rejected with HTTP 400."""
    today = date.today()
    user = User(
        email="dup_checkin@rvfitness.in",
        hashed_password=hash_password("pwDup1234"),
        name="Dup Member",
        role="member",
        membership_status="active",
        valid_until=today + timedelta(days=30),
        streak_days=2,
    )
    db_session.add(user)
    db_session.commit()

    login_res = client.post(
        "/api/auth/login",
        json={"email": "dup_checkin@rvfitness.in", "password": "pwDup1234"},
    )
    session_token = login_res.cookies.get(SESSION_COOKIE_NAME)
    csrf_token = login_res.cookies.get(CSRF_COOKIE_NAME)

    # 1. First checkin succeeds
    first_res = client.post(
        "/api/attendance/check-in",
        headers={CSRF_HEADER_NAME: csrf_token},
    )
    assert first_res.status_code == 200

    # 2. Second checkin on same day is rejected
    second_res = client.post(
        "/api/attendance/check-in",
        headers={CSRF_HEADER_NAME: csrf_token},
    )
    assert second_res.status_code == 400
    assert "already checked in for today" in second_res.json()["error"]
