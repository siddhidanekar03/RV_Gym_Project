import pytest
from sqlalchemy.orm import Session
from backend.app.models.user import User
from backend.app.models.organization import Organization, Branch
from backend.app.cli.bootstrap_admin import bootstrap_organization_admin
from backend.app.core.security import verify_password


def test_bootstrap_organization_admin_success(db_session: Session):
    """Verify first-organization-admin bootstrap initializes tenant, branch, and admin with hashed password."""
    admin = bootstrap_organization_admin(
        db=db_session,
        email="admin@rvfitness.in",
        password="SecureAdminPassword2026!",
        name="Rohit V. (Principal)",
        phone="+91 98220 12345",
        org_name="RV Fitness Group",
        branch_name="Narsobawadi Main Campus",
    )

    assert admin.id is not None
    assert admin.email == "admin@rvfitness.in"
    assert admin.role == "org_admin"
    assert admin.staff_role == "Organization Administrator"
    assert admin.membership_status == "active"
    assert admin.branch_id == "narsobawadi"
    assert verify_password("SecureAdminPassword2026!", admin.hashed_password)

    # Verify Organization and Branch exist
    org = db_session.query(Organization).filter(Organization.code == "RVF").first()
    assert org is not None
    assert org.name == "RV Fitness Group"

    branch = db_session.query(Branch).filter(Branch.id == "narsobawadi").first()
    assert branch is not None
    assert branch.organization_id == org.id


def test_bootstrap_aborts_on_duplicate_admin(db_session: Session):
    """Verify bootstrap aborts and refuses to run if an administrator already exists."""
    # First bootstrap
    bootstrap_organization_admin(
        db=db_session,
        email="admin1@rvfitness.in",
        password="FirstAdminPassword123!",
        name="First Admin",
    )

    # Second bootstrap attempt should fail
    with pytest.raises(ValueError, match="An organization administrator already exists"):
        bootstrap_organization_admin(
            db=db_session,
            email="admin2@rvfitness.in",
            password="SecondAdminPassword123!",
            name="Second Admin",
        )


def test_bootstrap_validates_password_length(db_session: Session):
    """Verify bootstrap rejects short passwords."""
    with pytest.raises(ValueError, match="Password must be at least 8 characters"):
        bootstrap_organization_admin(
            db=db_session,
            email="admin_short@rvfitness.in",
            password="short",
            name="Short Pw Admin",
        )
