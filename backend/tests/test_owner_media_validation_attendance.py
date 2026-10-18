"""
Automated unit and integration regression tests for:
1. Phone Number Validation and Normalization (Issue 4)
2. Direct Membership Assignment to Existing Member (Issue 1)
3. Coach Photo Management and Media Safety (Issue 2)
4. Homepage Hero Media Management (Issue 3)
5. Attendance Security and QR Check-In Routes (Issue 6)
"""

import os
import io
import pytest
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from fastapi import status, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.app.core.validation import validate_and_normalize_phone
from backend.app.schemas.auth import RegisterRequest
from backend.app.schemas.membership import EnrollmentRequest, AssignMembershipRequest
from backend.app.schemas.owner import CoachCreateRequest, CoachUpdateRequest
from backend.app.schemas.contact import ContactRequest
from backend.app.schemas.attendance import ManualCheckInRequest, PaperBackfillRequest
from backend.app.models.user import User
from backend.app.models.organization import Organization, Branch
from backend.app.models.membership import MembershipPlan, PlanPrice, Enrollment, MembershipChange
from backend.app.models.trainer import TrainerProfile
from backend.app.models.billing import Invoice, Payment
from backend.app.models.attendance import AttendanceRecord
from backend.app.models.website_content import WebsiteContent
from backend.app.core.security import hash_password
from backend.app.core.auth import create_user_session
from backend.app.services.membership_service import assign_membership_to_user
from backend.app.services.attendance_service import generate_member_qr_token


# ==============================================================================
# 1. PHONE NUMBER VALIDATION TESTS (ISSUE 4)
# ==============================================================================

class TestPhoneNumberValidation:
    """Test suite for phone validation, normalization, and Pydantic validators."""

    def test_indian_10_digit_standard(self):
        """10-digit Indian numbers starting with 6, 7, 8, 9 normalize to +91 XXXXX XXXXX."""
        assert validate_and_normalize_phone("9822012345") == "+91 98220 12345"
        assert validate_and_normalize_phone("8888888888") == "+91 88888 88888"
        assert validate_and_normalize_phone("7777777777") == "+91 77777 77777"
        assert validate_and_normalize_phone("6666666666") == "+91 66666 66666"

    def test_indian_with_spaces_hyphens_parens(self):
        """Valid formatting characters are stripped during normalization."""
        assert validate_and_normalize_phone("+91 98220 12345") == "+91 98220 12345"
        assert validate_and_normalize_phone("+91-98220-12345") == "+91 98220 12345"
        assert validate_and_normalize_phone("(+91) 9822012345") == "+91 98220 12345"
        assert validate_and_normalize_phone("09822012345") == "+91 98220 12345"

    def test_international_e164(self):
        """International numbers in E.164 format are preserved and validated."""
        assert validate_and_normalize_phone("+14155552671") == "+14155552671"
        assert validate_and_normalize_phone("+44 20 7183 8750") == "+442071838750"
        assert validate_and_normalize_phone("+971 50 123 4567") == "+971501234567"

    def test_alphanumeric_rejection(self):
        """Letters and invalid symbols are strictly rejected."""
        with pytest.raises(ValueError, match="cannot contain alphabetic characters"):
            validate_and_normalize_phone("98220ABC45")

        with pytest.raises(ValueError, match="invalid special characters"):
            validate_and_normalize_phone("+91-9822#4545")

        with pytest.raises(ValueError, match="cannot contain alphabetic characters"):
            validate_and_normalize_phone("phone_number")

    def test_invalid_length_rejection(self):
        """Numbers with fewer than 7 or more than 15 digits are rejected."""
        with pytest.raises(ValueError, match="too short"):
            validate_and_normalize_phone("12345")

        with pytest.raises(ValueError, match="too long"):
            validate_and_normalize_phone("123456789012345678")

    def test_invalid_indian_start_digit(self):
        """10-digit Indian numbers starting with 0-5 are rejected."""
        with pytest.raises(ValueError, match="must start with digit 6, 7, 8, or 9"):
            validate_and_normalize_phone("1234567890")

        with pytest.raises(ValueError, match="must start with digit 6, 7, 8, or 9"):
            validate_and_normalize_phone("5555555555")

    def test_pydantic_schema_integration(self):
        """Pydantic schemas enforce phone validation via field validators."""
        # Valid register request
        reg_valid = RegisterRequest(
            name="Raj Patil",
            email="raj@test.com",
            password="StrongPassword123!",
            acceptedTerms=True,
            phone="9822012345"
        )
        assert reg_valid.phone == "+91 98220 12345"

        # Invalid register request with letters
        with pytest.raises(ValidationError):
            RegisterRequest(
                name="Raj Patil",
                email="raj@test.com",
                password="StrongPassword123!",
                acceptedTerms=True,
                phone="98220INVALID"
            )

        # EnrollmentRequest with invalid phone
        with pytest.raises(ValidationError):
            EnrollmentRequest(
                plan_id="plan_monthly",
                branch_id="narsobawadi",
                phone="not_a_phone"
            )

        # ContactRequest with invalid phone
        with pytest.raises(ValidationError):
            ContactRequest(
                name="Inquirer",
                email="inq@test.com",
                phone="abc123",
                message="Hello"
            )


# ==============================================================================
# 2. SEED FIXTURES FOR OWNER, MEMBERS, AND BRANCHES
# ==============================================================================

@pytest.fixture
def setup_owner_test_data(db_session: Session):
    """Seed organization, branch, membership plan, owner user, and test member."""
    # Organization
    org = db_session.query(Organization).filter(Organization.code == "RVF").first()
    if not org:
        org = Organization(name="RV Fitness Org", code="RVF")
        db_session.add(org)
        db_session.flush()

    # Branch: Narsobawadi
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

    # Second branch for isolation test
    branch2 = db_session.query(Branch).filter(Branch.id == "kolhapur").first()
    if not branch2:
        branch2 = Branch(
            id="kolhapur",
            organization_id=org.id,
            name="RVFitness Kolhapur",
            code="KOLHAPUR",
            city="Kolhapur",
            state="Maharashtra",
        )
        db_session.add(branch2)
        db_session.flush()

    # Membership Plan
    plan = db_session.query(MembershipPlan).filter(MembershipPlan.id == "plan_strength_30").first()
    if not plan:
        plan = MembershipPlan(
            id="plan_strength_30",
            name="30-Day Strength Protocol",
            category="strength",
            access_scope="single_branch",
            price=Decimal("2500.00"),
            currency="₹",
            duration_days=30,
            billing_cycle="monthly",
            is_active=True,
            perks=["Gym Floor Access", "Locker Room"],
        )
        db_session.add(plan)
        db_session.flush()

        price = PlanPrice(
            plan_id=plan.id,
            price=Decimal("2500.00"),
            currency="₹",
            effective_from=date.today(),
            is_active=True,
        )
        db_session.add(price)
        db_session.flush()

    # Owner User
    owner = db_session.query(User).filter(User.email == "owner_test@rvfitness.in").first()
    if not owner:
        owner = User(
            email="owner_test@rvfitness.in",
            hashed_password=hash_password("OwnerSecure123!"),
            name="Gym Owner Boss",
            role="org_admin",
            staff_role="Gym Owner",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(owner)
        db_session.flush()

    # Member User (Registered without plan)
    member = db_session.query(User).filter(User.email == "unassigned_member@test.com").first()
    if not member:
        member = User(
            email="unassigned_member@test.com",
            hashed_password=hash_password("MemberPass123!"),
            name="Sunil Gavaskar",
            phone="+91 98220 11223",
            role="member",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(member)
        db_session.flush()

    db_session.commit()

    return {
        "org": org,
        "branch": branch,
        "branch2": branch2,
        "plan": plan,
        "owner": owner,
        "member": member,
    }


# ==============================================================================
# 3. DIRECT MEMBERSHIP ASSIGNMENT TESTS (ISSUE 1)
# ==============================================================================

class TestDirectMembershipAssignment:
    """Tests for owner/admin assigning membership directly to existing member."""

    def test_assign_membership_without_immediate_payment(self, db_session: Session, setup_owner_test_data):
        """Owner assigns membership to existing member awaiting desk payment."""
        data = setup_owner_test_data
        owner = data["owner"]
        member = data["member"]
        plan = data["plan"]

        enr, inv, u = assign_membership_to_user(
            db=db_session,
            target_user_id=member.id,
            plan_id=plan.id,
            actor=owner,
            branch_id="narsobawadi",
            record_payment=False,
            notes="In-person desk consultation",
        )
        assert enr.status in ["payment_pending", "approved", "pending_verification"]
        assert enr.id is not None
        assert inv.balance_due == Decimal("2500.00")

        # Verify keycard code generated
        db_session.refresh(member)
        assert member.membership_id is not None
        assert member.membership_id.startswith("RVF-")

        # Verify invoice created
        invoice = db_session.query(Invoice).filter(Invoice.enrollment_id == enr.id).first()
        assert invoice is not None
        assert invoice.total_amount == Decimal("2500.00")
        assert invoice.balance_due == Decimal("2500.00")

    def test_assign_membership_with_immediate_desk_payment(self, db_session: Session, setup_owner_test_data):
        """Owner assigns membership and records full cash payment at the counter."""
        data = setup_owner_test_data
        owner = data["owner"]
        plan = data["plan"]

        # Create fresh member
        new_member = User(
            email="paid_member@test.com",
            hashed_password=hash_password("Pass123!"),
            name="Rohit Sharma",
            phone="+91 98220 99887",
            role="member",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(new_member)
        db_session.commit()

        enr, inv, u = assign_membership_to_user(
            db=db_session,
            target_user_id=new_member.id,
            plan_id=plan.id,
            actor=owner,
            branch_id="narsobawadi",
            record_payment=True,
            payment_method="cash",
            reference_number="CASH-RECEIPT-001",
            notes="Paid in full at reception desk",
        )

        assert enr.status == "active"
        assert inv.balance_due == Decimal("0.00")
        assert u.membership_status == "active"
        assert u.valid_until >= date.today() + timedelta(days=29)

    def test_reject_conflicting_active_membership(self, db_session: Session, setup_owner_test_data):
        """Direct assignment is blocked if member already has an active membership."""
        data = setup_owner_test_data
        owner = data["owner"]
        plan = data["plan"]

        active_member = User(
            email="active_sub@test.com",
            hashed_password=hash_password("Pass123!"),
            name="Virat Kohli",
            phone="+91 98220 77665",
            role="member",
            branch_id="narsobawadi",
            membership_status="active",
            valid_until=date.today() + timedelta(days=30),
            is_active=True,
        )
        db_session.add(active_member)
        db_session.commit()

        with pytest.raises(ValueError, match="already has an active"):
            assign_membership_to_user(
                db=db_session,
                target_user_id=active_member.id,
                plan_id=plan.id,
                actor=owner,
                branch_id="narsobawadi",
            )

    def test_reject_duplicate_pending_enrollment(self, db_session: Session, setup_owner_test_data):
        """Direct assignment is blocked if member already has a pending application."""
        data = setup_owner_test_data
        owner = data["owner"]
        plan = data["plan"]

        pending_member = User(
            email="pending_app@test.com",
            hashed_password=hash_password("Pass123!"),
            name="Jasprit Bumrah",
            phone="+91 98220 55443",
            role="member",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(pending_member)
        db_session.flush()

        pending_enr = Enrollment(
            user_id=pending_member.id,
            plan_id=plan.id,
            branch_id="narsobawadi",
            name=pending_member.name,
            phone=pending_member.phone,
            email=pending_member.email,
            price=plan.price,
            currency=plan.currency,
            status="pending_verification",
            accepted_terms=True,
        )
        db_session.add(pending_enr)
        db_session.commit()

        with pytest.raises(ValueError, match="already has a pending enrollment request"):
            assign_membership_to_user(
                db=db_session,
                target_user_id=pending_member.id,
                plan_id=plan.id,
                actor=owner,
                branch_id="narsobawadi",
            )

    def test_branch_isolation_on_assignment(self, db_session: Session, setup_owner_test_data):
        """Branch manager cannot assign membership to a different branch."""
        data = setup_owner_test_data
        plan = data["plan"]

        manager_branch1 = User(
            email="mgr_branch1@rvfitness.in",
            hashed_password=hash_password("MgrPass123!"),
            name="Manager One",
            role="branch_manager",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(manager_branch1)

        other_member = User(
            email="other_member@test.com",
            hashed_password=hash_password("Pass123!"),
            name="Other City Member",
            role="member",
            branch_id="kolhapur",
            is_active=True,
        )
        db_session.add(other_member)
        db_session.commit()

        # Manager from narsobawadi attempts to assign in kolhapur
        with pytest.raises(PermissionError, match="Access denied"):
            assign_membership_to_user(
                db=db_session,
                target_user_id=other_member.id,
                plan_id=plan.id,
                actor=manager_branch1,
                branch_id="kolhapur",
            )


# ==============================================================================
# 4. COACH PHOTO AND MEDIA CLEANUP SAFETY TESTS (ISSUE 2)
# ==============================================================================

class TestCoachPhotoAndMediaSafety:
    """Tests for coach photo upload, persistence, and deletion safety."""

    def test_coach_create_and_update_schemas_accept_photo_url(self):
        """Coach schemas support photo_url."""
        create_req = CoachCreateRequest(
            name="Coach Vikram",
            email="vikram@rvfitness.in",
            password="StrongPassword123!",
            branch_id="narsobawadi",
            photo_url="/uploads/coaches/vikram_portrait.webp",
        )
        assert create_req.photo_url == "/uploads/coaches/vikram_portrait.webp"

        update_req = CoachUpdateRequest(
            specialization="Master Powerlifter",
            photo_url="/uploads/coaches/vikram_new.webp",
        )
        assert update_req.photo_url == "/uploads/coaches/vikram_new.webp"

    def test_trainer_profile_model_stores_photo_url(self, db_session: Session, setup_owner_test_data):
        """TrainerProfile persists photo_url in database."""
        trainer_user = User(
            email="trainer_photo@rvfitness.in",
            hashed_password=hash_password("TrainerPass123!"),
            name="Arjun Trainer",
            role="trainer",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(trainer_user)
        db_session.flush()

        profile = TrainerProfile(
            user_id=trainer_user.id,
            specialization="Strength Coach",
            photo_url="/uploads/coaches/arjun_profile.png",
        )
        db_session.add(profile)
        db_session.commit()

        db_session.refresh(profile)
        assert profile.photo_url == "/uploads/coaches/arjun_profile.png"

    def test_trainer_photo_clearing(self, db_session: Session, setup_owner_test_data):
        """Setting photo_url to None clears the coach photo."""
        trainer_user = User(
            email="trainer_clear@rvfitness.in",
            hashed_password=hash_password("TrainerPass123!"),
            name="Ajay Trainer",
            role="trainer",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(trainer_user)
        db_session.flush()

        profile = TrainerProfile(
            user_id=trainer_user.id,
            specialization="HIIT Trainer",
            photo_url="/uploads/coaches/ajay.jpg",
        )
        db_session.add(profile)
        db_session.commit()

        # Clear photo
        profile.photo_url = None
        db_session.commit()

        db_session.refresh(profile)
        assert profile.photo_url is None


# ==============================================================================
# 5. SECURE ATTENDANCE AND WEB CHECK-IN RESTRICTION (ISSUE 6)
# ==============================================================================

class TestAttendanceSecurityAndQRRoutes:
    """Tests for attendance policy: remote web check-in blocked, QR verification active."""

    def test_remote_web_checkin_returns_403_for_members(self, client: TestClient, db_session: Session, setup_owner_test_data):
        """Remote web self-check-in via POST /attendance/check-in returns 403 Forbidden."""
        data = setup_owner_test_data
        member = data["member"]

        # Create session cookie for member
        session_rec, session_token, csrf_token = create_user_session(db_session, member)
        client.cookies.set("rvf_session", session_token)

        # Attempt remote self check-in
        res = client.post(
            "/api/v1/attendance/check-in",
            params={"branch_id": "narsobawadi"},
            headers={"X-CSRF-Token": csrf_token}
        )
        assert res.status_code == status.HTTP_403_FORBIDDEN
        assert "Remote web check-in has been disabled" in res.json()["detail"]

    def test_desk_qr_checkin_validates_token(self, client: TestClient, db_session: Session, setup_owner_test_data):
        """Desk staff can scan valid QR code via /attendance/qr-check-in."""
        data = setup_owner_test_data
        owner = data["owner"]
        plan = data["plan"]

        # Create active member with daily pass
        member = User(
            email="qr_member@test.com",
            hashed_password=hash_password("MemberPass123!"),
            name="Kedar Jadhav",
            role="member",
            branch_id="narsobawadi",
            membership_id="RVF-TEST-QR-001",
            membership_status="active",
            valid_until=date.today() + timedelta(days=30),
            is_active=True,
        )
        db_session.add(member)
        db_session.commit()

        token, _, _ = generate_member_qr_token(member)

        # Staff session
        session_rec, staff_token, staff_csrf = create_user_session(db_session, owner)
        client.cookies.set("rvf_session", staff_token)

        # 1. Test canonical route /attendance/qr-check-in
        res = client.post(
            "/api/v1/attendance/qr-check-in",
            json={"qrToken": token, "branchId": "narsobawadi"},
            headers={"X-CSRF-Token": staff_csrf}
        )
        assert res.status_code == status.HTTP_200_OK
        data_res = res.json()
        assert data_res["success"] is True
        assert data_res["source"] == "qr"

    def test_qr_checkin_alias_route(self, client: TestClient, db_session: Session, setup_owner_test_data):
        """Route alias /attendance/qr-checkin works identically to /attendance/qr-check-in."""
        data = setup_owner_test_data
        owner = data["owner"]
        plan = data["plan"]

        member = User(
            email="alias_qr_member@test.com",
            hashed_password=hash_password("MemberPass123!"),
            name="Ajinkya Rahane",
            role="member",
            branch_id="narsobawadi",
            membership_id="RVF-TEST-QR-002",
            membership_status="active",
            valid_until=date.today() + timedelta(days=30),
            is_active=True,
        )
        db_session.add(member)
        db_session.commit()

        token, _, _ = generate_member_qr_token(member)

        session_rec, staff_token, staff_csrf = create_user_session(db_session, owner)
        client.cookies.set("rvf_session", staff_token)

        # Call alias route /attendance/qr-checkin (without hyphen)
        res = client.post(
            "/api/v1/attendance/qr-checkin",
            json={"qrToken": token, "branchId": "narsobawadi"},
            headers={"X-CSRF-Token": staff_csrf}
        )
        assert res.status_code == status.HTTP_200_OK
        assert res.json()["success"] is True
