import pytest
from decimal import Decimal
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.core.security import hash_password, generate_csrf_token
from backend.app.models.user import User
from backend.app.models.organization import Organization, Branch
from backend.app.models.membership import MembershipPlan, PlanPrice, Enrollment
from backend.app.models.website_content import WebsiteContent, EquipmentItem, GalleryItem
from backend.app.models.session import UserSession
from backend.app.core.auth import create_user_session


@pytest.fixture
def seed_test_org_and_users(db_session: Session):
    """Seed test organization, branch, and role accounts for testing."""
    org = db_session.query(Organization).filter(Organization.code == "RVF").first()
    if not org:
        org = Organization(name="RV Fitness Organization", code="RVF")
        db_session.add(org)
        db_session.flush()

    branch = db_session.query(Branch).filter(Branch.id == "narsobawadi").first()
    if not branch:
        branch = Branch(
            id="narsobawadi",
            organization_id=org.id,
            name="RVFitness Narsobawadi",
            code="NARSOBAWADI",
            city="Narsobawadi",
            state="Maharashtra",
        )
        db_session.add(branch)
        db_session.flush()

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

    # Owner user
    owner = db_session.query(User).filter(User.email == "owner_test@rvfitness.in").first()
    if not owner:
        owner = User(
            email="owner_test@rvfitness.in",
            hashed_password=hash_password("OwnerPassword123!"),
            name="Test Gym Owner",
            role="org_admin",
            staff_role="Gym Owner",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(owner)

    # Trainer user
    trainer = db_session.query(User).filter(User.email == "trainer_test@rvfitness.in").first()
    if not trainer:
        trainer = User(
            email="trainer_test@rvfitness.in",
            hashed_password=hash_password("TrainerPassword123!"),
            name="Test Coach Amit",
            role="trainer",
            staff_role="Strength Coach",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(trainer)

    # Member user
    member = db_session.query(User).filter(User.email == "member_test@rvfitness.in").first()
    if not member:
        member = User(
            email="member_test@rvfitness.in",
            hashed_password=hash_password("MemberPassword123!"),
            name="Test Member Rahul",
            role="member",
            membership_status="active",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(member)

    db_session.commit()
    return {"org": org, "branch": branch, "owner": owner, "trainer": trainer, "member": member}


# ==============================================================================
# PHASE 1: REGISTRATION VALIDATION TESTS
# ==============================================================================

def test_registration_short_password_validation(client: TestClient):
    """Verify that password under 8 characters returns 422 with structured field error."""
    payload = {
        "name": "Validation Tester",
        "email": "shortpw@rvfitness.in",
        "password": "short",
        "phone": "+91 98220 99999",
        "acceptedTerms": True,
    }
    res = client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    data = res.json()
    assert "field_errors" in data
    assert "password" in data["field_errors"]
    assert "at least 8 characters" in data["field_errors"]["password"]


def test_registration_invalid_email_validation(client: TestClient):
    """Verify that malformed email returns 422 with email field error."""
    payload = {
        "name": "Validation Tester",
        "email": "not-an-email",
        "password": "ValidPassword123!",
        "acceptedTerms": True,
    }
    res = client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    data = res.json()
    assert "field_errors" in data
    assert "email" in data["field_errors"]


def test_registration_terms_not_accepted(client: TestClient):
    """Verify that unchecked terms returns 400 Bad Request."""
    payload = {
        "name": "Validation Tester",
        "email": "noterms@rvfitness.in",
        "password": "ValidPassword123!",
        "acceptedTerms": False,
    }
    res = client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    data = res.json()
    assert "Terms of Service" in data["detail"]


def test_registration_successful_and_duplicate(client: TestClient, db_session: Session, seed_test_org_and_users):
    """Verify that valid registration returns 201 and duplicate email returns 409."""
    email = "new_member_reg@rvfitness.in"
    payload = {
        "name": "Fresh Member",
        "email": email,
        "password": "SecurePassword123!",
        "phone": "+91 98220 11223",
        "acceptedTerms": True,
    }
    res1 = client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == status.HTTP_201_CREATED
    data1 = res1.json()
    assert data1["user"]["email"] == email
    assert "rvf_session" in res1.cookies

    # Duplicate attempt
    res2 = client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == status.HTTP_409_CONFLICT
    assert "already exists" in res2.json()["detail"]


# ==============================================================================
# PHASE 2: AUTHENTICATION AND SESSION PERSISTENCE TESTS
# ==============================================================================

def test_login_session_cookie_and_csrf_persistence(client: TestClient, seed_test_org_and_users):
    """Verify login sets HttpOnly session and readable CSRF cookies."""
    login_payload = {
        "email": "owner_test@rvfitness.in",
        "password": "OwnerPassword123!",
    }
    res = client.post("/api/v1/auth/login", json=login_payload)
    assert res.status_code == status.HTTP_200_OK
    assert "rvf_session" in res.cookies
    assert "rvf_csrf_token" in res.cookies

    # Access current user profile using the active cookie
    me_res = client.get("/api/v1/auth/me", cookies=res.cookies)
    assert me_res.status_code == status.HTTP_200_OK
    assert me_res.json()["user"]["email"] == "owner_test@rvfitness.in"


def test_attendance_reports_with_authenticated_session(client: TestClient, seed_test_org_and_users):
    """Verify Monthly Attendance Reports can be fetched after authenticating."""
    login_payload = {
        "email": "owner_test@rvfitness.in",
        "password": "OwnerPassword123!",
    }
    login_res = client.post("/api/v1/auth/login", json=login_payload)
    assert login_res.status_code == status.HTTP_200_OK

    report_res = client.get(
        "/api/v1/attendance/reports/branch/narsobawadi?year=2026&month=10",
        cookies=login_res.cookies,
    )
    assert report_res.status_code == status.HTTP_200_OK
    data = report_res.json()
    assert "dailyBreakdown" in data
    assert data["branchId"] == "narsobawadi"


def test_unauthenticated_request_rejected(client: TestClient):
    """Verify request without session credentials returns 401."""
    res = client.get("/api/v1/attendance/reports/branch/narsobawadi?year=2026&month=10")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Missing session credentials" in res.json()["detail"]


def test_revoked_session_rejected(client: TestClient, db_session: Session, seed_test_org_and_users):
    """Verify that a revoked session token cannot access protected endpoints."""
    owner = seed_test_org_and_users["owner"]
    session, raw_token, csrf_token = create_user_session(db_session, owner)
    session.is_revoked = True
    db_session.commit()

    cookies = {"rvf_session": raw_token}
    res = client.get("/api/v1/auth/me", cookies=cookies)
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


def test_logout_invalidates_session(client: TestClient, seed_test_org_and_users):
    """Verify logout revokes the server-side session and clears cookies."""
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "owner_test@rvfitness.in", "password": "OwnerPassword123!"},
    )
    csrf_token = login_res.cookies.get("rvf_csrf_token")
    logout_res = client.post(
        "/api/v1/auth/logout",
        cookies=login_res.cookies,
        headers={"x-csrf-token": csrf_token},
    )
    assert logout_res.status_code == status.HTTP_200_OK

    # Subsequent request with old cookies must fail with 401
    me_res = client.get("/api/v1/auth/me", cookies=login_res.cookies)
    assert me_res.status_code == status.HTTP_401_UNAUTHORIZED


# ==============================================================================
# PHASE 3 & 4: GYM OWNER MANAGEMENT PANEL ENDPOINTS & AUTHORIZATION
# ==============================================================================

def test_owner_website_content_management(client: TestClient, seed_test_org_and_users):
    """Verify owner can read and update website content sections."""
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "owner_test@rvfitness.in", "password": "OwnerPassword123!"},
    )
    csrf_token = login_res.cookies.get("rvf_csrf_token")
    cookies = login_res.cookies

    # 1. Update Hero section
    hero_payload = {
        "data": {
            "headline": "CHAMPIONS TRAIN HERE.\nNARSOBAWADI STRENGTH.",
            "subtitle": "Updated customized description for public website testing.",
            "badgeText": "RVFITNESS · VERIFIED",
            "ctaPrimary": "Join Today",
        }
    }
    update_res = client.put(
        "/api/v1/owner/website-content/homepage_hero",
        json=hero_payload,
        cookies=cookies,
        headers={"x-csrf-token": csrf_token},
    )
    assert update_res.status_code == status.HTTP_200_OK
    assert update_res.json()["success"] is True

    # 2. Verify public gym info reflects the change
    info_res = client.get("/api/v1/gym/info")
    assert info_res.status_code == status.HTTP_200_OK
    info_data = info_res.json()
    assert "hero" in info_data
    assert info_data["hero"]["headline"] == "CHAMPIONS TRAIN HERE.\nNARSOBAWADI STRENGTH."


def test_owner_equipment_management(client: TestClient, seed_test_org_and_users):
    """Verify owner can add, update, and remove equipment items."""
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "owner_test@rvfitness.in", "password": "OwnerPassword123!"},
    )
    csrf_token = login_res.cookies.get("rvf_csrf_token")
    cookies = login_res.cookies

    # 1. Add equipment
    create_payload = {
        "name": "Precision Deadlift Platform 3000",
        "category": "Powerlifting",
        "spec": "Heavy duty commercial hardwood platform with band pegs and rubber drop pads.",
        "brand_model": "Rogue Monster",
        "branch_id": "narsobawadi",
        "primary_image_url": "/uploads/equipment/sample_deadlift.jpg",
        "is_published": True,
    }
    create_res = client.post(
        "/api/v1/owner/equipment",
        json=create_payload,
        cookies=cookies,
        headers={"x-csrf-token": csrf_token},
    )
    assert create_res.status_code == status.HTTP_200_OK
    equip_id = create_res.json()["id"]

    # 2. Verify equipment is returned in public list
    public_res = client.get("/api/v1/gym/equipment")
    assert public_res.status_code == status.HTTP_200_OK
    items = public_res.json()["equipment"]
    assert any(i["id"] == equip_id and i["name"] == "Precision Deadlift Platform 3000" for i in items)

    # 3. Update equipment
    update_res = client.put(
        f"/api/v1/owner/equipment/{equip_id}",
        json={"name": "Precision Deadlift Platform 3000 (Updated)"},
        cookies=cookies,
        headers={"x-csrf-token": csrf_token},
    )
    assert update_res.status_code == status.HTTP_200_OK

    # 4. Delete equipment
    del_res = client.delete(
        f"/api/v1/owner/equipment/{equip_id}",
        cookies=cookies,
        headers={"x-csrf-token": csrf_token},
    )
    assert del_res.status_code == status.HTTP_200_OK


def test_owner_coaches_management(client: TestClient, seed_test_org_and_users):
    """Verify owner can add and update coach records with hashed passwords."""
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "owner_test@rvfitness.in", "password": "OwnerPassword123!"},
    )
    csrf_token = login_res.cookies.get("rvf_csrf_token")
    cookies = login_res.cookies

    coach_payload = {
        "name": "Coach Mahesh Jadhav",
        "email": "mahesh.coach@rvfitness.in",
        "password": "CoachSecurePass123!",
        "phone": "+91 98220 77777",
        "branch_id": "narsobawadi",
        "specialization": "Hypertrophy and Bodybuilding Coach",
        "bio": "Certified physique coach with 7 years of competitive training experience.",
        "certifications": ["K11 Academy Diploma", "ISSA CPT"],
        "experience_years": 7,
        "max_clients": 25,
        "is_accepting_clients": True,
    }
    create_res = client.post(
        "/api/v1/owner/coaches",
        json=coach_payload,
        cookies=cookies,
        headers={"x-csrf-token": csrf_token},
    )
    assert create_res.status_code == status.HTTP_200_OK
    coach_id = create_res.json()["id"]

    # Verify coach can log in with their created password
    coach_login = client.post(
        "/api/v1/auth/login",
        json={"email": "mahesh.coach@rvfitness.in", "password": "CoachSecurePass123!"},
    )
    assert coach_login.status_code == status.HTTP_200_OK
    assert coach_login.json()["user"]["role"] == "trainer"


def test_owner_plan_management_and_dependency_guard(client: TestClient, db_session: Session, seed_test_org_and_users):
    """Verify owner can manage plans and cannot delete plan with active subscribers."""
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "owner_test@rvfitness.in", "password": "OwnerPassword123!"},
    )
    csrf_token = login_res.cookies.get("rvf_csrf_token")
    cookies = login_res.cookies

    plan_payload = {
        "id": "plan_monsoon_special",
        "name": "Monsoon Strength Pass",
        "category": "strength",
        "access_scope": "single_branch",
        "price": 3200.00,
        "currency": "₹",
        "billing_cycle": "per 3 months",
        "duration_days": 90,
        "is_featured": True,
        "is_active": True,
        "description": "Special 90-day monsoon strength conditioning pass.",
        "perks": ["Full floor access", "Complimentary diet review"],
    }
    create_res = client.post(
        "/api/v1/owner/plans",
        json=plan_payload,
        cookies=cookies,
        headers={"x-csrf-token": csrf_token},
    )
    assert create_res.status_code == status.HTTP_200_OK

    # Link member to this plan to simulate an active subscription dependency
    member = seed_test_org_and_users["member"]
    member.membership_plan_id = "plan_monsoon_special"
    db_session.commit()

    # Attempting to delete must be blocked with 400 Bad Request
    del_res = client.delete(
        "/api/v1/owner/plans/plan_monsoon_special",
        cookies=cookies,
        headers={"x-csrf-token": csrf_token},
    )
    assert del_res.status_code == status.HTTP_400_BAD_REQUEST
    assert "Cannot delete plan" in del_res.json()["detail"]
    assert "archive the plan instead" in del_res.json()["detail"]


def test_member_and_trainer_forbidden_from_owner_endpoints(client: TestClient, seed_test_org_and_users):
    """Verify non-owner users (members and trainers) are strictly forbidden (403)."""
    # 1. Member attempt
    member_login = client.post(
        "/api/v1/auth/login",
        json={"email": "member_test@rvfitness.in", "password": "MemberPassword123!"},
    )
    member_cookies = member_login.cookies
    member_res = client.get("/api/v1/owner/equipment", cookies=member_cookies)
    assert member_res.status_code == status.HTTP_403_FORBIDDEN

    # 2. Trainer attempt
    trainer_login = client.post(
        "/api/v1/auth/login",
        json={"email": "trainer_test@rvfitness.in", "password": "TrainerPassword123!"},
    )
    trainer_cookies = trainer_login.cookies
    trainer_res = client.get("/api/v1/owner/plans", cookies=trainer_cookies)
    assert trainer_res.status_code == status.HTTP_403_FORBIDDEN


def test_csrf_protection_on_owner_mutations(client: TestClient, seed_test_org_and_users):
    """Verify mutating owner endpoints require valid CSRF token."""
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "owner_test@rvfitness.in", "password": "OwnerPassword123!"},
    )
    cookies = login_res.cookies

    # Calling POST without x-csrf-token header must fail with 403 Forbidden
    res = client.post(
        "/api/v1/owner/equipment",
        json={"name": "CSRF Test Dumbbell", "category": "Free Weights", "spec": "Spec"},
        cookies=cookies,
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN
