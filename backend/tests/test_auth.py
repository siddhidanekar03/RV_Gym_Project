from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.core.security import hash_password, verify_password
from backend.app.models.user import User
from backend.app.models.session import UserSession
from backend.app.core.auth import SESSION_COOKIE_NAME, CSRF_COOKIE_NAME, CSRF_HEADER_NAME


def test_password_hashing_and_verification():
    """Verify bcrypt hashes passwords securely and constant-time check succeeds."""
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$2b$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_registration_flow_and_cookies(client: TestClient, db_session: Session):
    """Verify user registration hashes password, creates database session, and sets cookies."""
    payload = {
        "name": "Arjun Deshmukh",
        "email": "arjun@rvfitness.in",
        "password": "strongPassword2026",
        "phone": "+91 98220 55555",
        "acceptedTerms": True,
    }

    res = client.post("/api/auth/register", json=payload)
    assert res.status_code == 201
    data = res.json()

    assert data["user"]["email"] == "arjun@rvfitness.in"
    assert data["user"]["name"] == "Arjun Deshmukh"
    assert data["user"]["membershipId"].startswith("RVF-")
    assert "csrfToken" in data

    # Verify cookies
    assert SESSION_COOKIE_NAME in res.cookies
    assert CSRF_COOKIE_NAME in res.cookies

    # Verify user in database has hashed password
    user_db = db_session.query(User).filter(User.email == "arjun@rvfitness.in").one()
    assert user_db.hashed_password != "strongPassword2026"
    assert verify_password("strongPassword2026", user_db.hashed_password) is True


def test_login_success_and_failure(client: TestClient, db_session: Session):
    """Verify login authentication, password checking, and cookie creation."""
    # Seed user
    pw_hash = hash_password("memberPassword123")
    user = User(
        email="login_test@rvfitness.in",
        hashed_password=pw_hash,
        name="Login Test User",
        membership_id="RVF-2026-101",
        role="member",
    )
    db_session.add(user)
    db_session.commit()

    # 1. Invalid password
    bad_res = client.post(
        "/api/auth/login",
        json={"email": "login_test@rvfitness.in", "password": "WrongPassword"},
    )
    assert bad_res.status_code == 401
    assert "Invalid email or password" in bad_res.json()["error"]

    # 2. Correct password
    good_res = client.post(
        "/api/auth/login",
        json={"email": "login_test@rvfitness.in", "password": "memberPassword123"},
    )
    assert good_res.status_code == 200
    assert SESSION_COOKIE_NAME in good_res.cookies
    assert CSRF_COOKIE_NAME in good_res.cookies


def test_me_endpoint_and_session_expiry(client: TestClient, db_session: Session):
    """Verify /api/auth/me resolves active user and rejects expired sessions."""
    # Create user and active session
    pw_hash = hash_password("myPass123")
    user = User(
        email="me_test@rvfitness.in",
        hashed_password=pw_hash,
        name="Session Test User",
        membership_id="RVF-2026-102",
        role="member",
        membership_status="active",
    )
    db_session.add(user)
    db_session.commit()

    # Log in to get cookies
    login_res = client.post(
        "/api/auth/login",
        json={"email": "me_test@rvfitness.in", "password": "myPass123"},
    )
    session_token = login_res.cookies.get(SESSION_COOKIE_NAME)
    csrf_token = login_res.cookies.get(CSRF_COOKIE_NAME)

    # 1. Access /api/auth/me
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["user"]["email"] == "me_test@rvfitness.in"

    # 2. Expire session manually in database
    session_record = db_session.query(UserSession).filter(UserSession.user_id == user.id).first()
    session_record.expires_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db_session.commit()

    # 3. Access with expired session must be rejected with 401
    expired_res = client.get("/api/auth/me")
    assert expired_res.status_code == 401
    assert "Session has expired" in expired_res.json()["error"]


def test_logout_and_csrf_enforcement(client: TestClient, db_session: Session):
    """Verify logout requires CSRF and marks session revoked in database."""
    pw_hash = hash_password("logoutPass123")
    user = User(
        email="logout_test@rvfitness.in",
        hashed_password=pw_hash,
        name="Logout Test User",
        membership_id="RVF-2026-103",
        role="member",
    )
    db_session.add(user)
    db_session.commit()

    login_res = client.post(
        "/api/auth/login",
        json={"email": "logout_test@rvfitness.in", "password": "logoutPass123"},
    )
    session_token = login_res.cookies.get(SESSION_COOKIE_NAME)
    csrf_token = login_res.cookies.get(CSRF_COOKIE_NAME)

    # 1. Logout without CSRF header must fail with 403
    no_csrf_res = client.post("/api/auth/logout")
    assert no_csrf_res.status_code == 403
    assert "CSRF validation failed" in no_csrf_res.json()["error"]

    # 2. Logout with wrong CSRF token must fail with 403
    bad_csrf_res = client.post(
        "/api/auth/logout",
        headers={CSRF_HEADER_NAME: "invalid_csrf_token_value"},
    )
    assert bad_csrf_res.status_code == 403

    # 3. Logout with valid CSRF header succeeds
    logout_res = client.post(
        "/api/auth/logout",
        headers={CSRF_HEADER_NAME: csrf_token},
    )
    assert logout_res.status_code == 200

    # 4. Verify session is marked revoked in database
    session_record = db_session.query(UserSession).filter(UserSession.user_id == user.id).first()
    assert session_record.is_revoked is True

    # 5. Using revoked session must now be rejected
    client.cookies.set(SESSION_COOKIE_NAME, session_token)
    subsequent_res = client.get("/api/auth/me")
    assert subsequent_res.status_code == 401
