#!/usr/bin/env python3
"""
RVFitness Staging Platform Admin and Gym Owner Seeder.

Creates or updates isolated staging credentials for:
1. Platform Admin (admin@rvfitness.in) -> role='org_admin', staff_role='Platform Administrator'
2. Gym Owner (owner@rvfitness.in) -> role='org_admin', staff_role='Gym Owner'

Fails closed if ENVIRONMENT != "staging".
"""
import argparse
import os
import sys

workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal
from backend.app.core.security import hash_password
from backend.app.models.organization import Organization, Branch
from backend.app.models.user import User
from backend.app.models.audit import AuditLog

DEFAULT_ADMIN_EMAIL = "admin@rvfitness.in"
DEFAULT_ADMIN_PASS = "StagingAdminPass123!"

DEFAULT_OWNER_EMAIL = "owner@rvfitness.in"
DEFAULT_OWNER_PASS = "StagingOwnerPass123!"


def seed_admin_and_owner(
    admin_email: str = DEFAULT_ADMIN_EMAIL,
    admin_password: str = DEFAULT_ADMIN_PASS,
    owner_email: str = DEFAULT_OWNER_EMAIL,
    owner_password: str = DEFAULT_OWNER_PASS,
) -> None:
    """Safely seed or update platform admin and gym owner in staging database."""
    env = (os.environ.get("ENVIRONMENT") or settings.ENVIRONMENT or "").strip().lower()
    if env != "staging":
        raise RuntimeError(
            f"SAFETY VIOLATION: seed_admin_and_owner is strictly restricted to ENVIRONMENT=staging. "
            f"Detected environment '{env}'. Seeding aborted."
        )

    db_url = (os.environ.get("DATABASE_URL") or settings.DATABASE_URL or "").lower()
    if "staging" not in db_url:
        raise RuntimeError(
            f"SAFETY VIOLATION: Target database URL must be a staging database. Got: '{db_url}'"
        )

    db = SessionLocal()
    try:
        # 1. Verify Organization exists
        org = db.query(Organization).first()
        if not org:
            org = Organization(name="RV Fitness", code="RVF", is_active=True)
            db.add(org)
            db.flush()

        # 2. Verify primary branch exists
        branch = db.query(Branch).filter(Branch.id == "narsobawadi").first()
        if not branch:
            branch = Branch(
                id="narsobawadi",
                organization_id=org.id,
                name="Narsobawadi Main Campus",
                code="narsobawadi",
                city="Narsobawadi",
                state="Maharashtra",
                is_active=True,
            )
            db.add(branch)
            db.flush()

        # 3. Seed / Update Platform Admin
        admin_email_clean = admin_email.strip().lower()
        admin_user = db.query(User).filter(User.email == admin_email_clean).first()
        if admin_user:
            admin_user.hashed_password = hash_password(admin_password)
            admin_user.role = "org_admin"
            admin_user.staff_role = "Platform Administrator"
            admin_user.is_active = True
            print(f"[UPDATED] Existing user '{admin_email_clean}' promoted/updated as org_admin.")
        else:
            admin_user = User(
                email=admin_email_clean,
                hashed_password=hash_password(admin_password),
                name="Platform Administrator",
                role="org_admin",
                staff_role="Platform Administrator",
                branch_id=branch.id,
                membership_status="active",
                is_active=True,
            )
            db.add(admin_user)
            db.flush()
            print(f"[CREATED] Platform Administrator '{admin_email_clean}' created successfully.")

        # Record audit event
        audit_admin = AuditLog(
            actor_id=admin_user.id,
            action="admin.staging_seed",
            resource_type="user",
            resource_id=admin_user.id,
            details={"email": admin_email_clean, "role": "org_admin"},
        )
        db.add(audit_admin)

        # 4. Seed / Update Gym Owner
        owner_email_clean = owner_email.strip().lower()
        owner_user = db.query(User).filter(User.email == owner_email_clean).first()
        if owner_user:
            owner_user.hashed_password = hash_password(owner_password)
            owner_user.role = "org_admin"
            owner_user.staff_role = "Gym Owner"
            owner_user.is_active = True
            print(f"[UPDATED] Existing user '{owner_email_clean}' updated as Gym Owner (org_admin).")
        else:
            owner_user = User(
                email=owner_email_clean,
                hashed_password=hash_password(owner_password),
                name="Gym Owner (Rohit V.)",
                role="org_admin",
                staff_role="Gym Owner",
                branch_id=branch.id,
                membership_status="active",
                is_active=True,
            )
            db.add(owner_user)
            db.flush()
            print(f"[CREATED] Gym Owner '{owner_email_clean}' created successfully.")

        # Record audit event
        audit_owner = AuditLog(
            actor_id=owner_user.id,
            action="admin.staging_seed",
            resource_type="user",
            resource_id=owner_user.id,
            details={"email": owner_email_clean, "role": "org_admin"},
        )
        db.add(audit_owner)

        db.commit()
        print("[SUCCESS] Staging platform admin and gym owner accounts verified and committed.")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="RVFitness Staging Admin & Owner Account Seeder")
    parser.add_argument("--admin-email", default=DEFAULT_ADMIN_EMAIL, help="Platform Admin email")
    parser.add_argument("--admin-password", default=DEFAULT_ADMIN_PASS, help="Platform Admin password")
    parser.add_argument("--owner-email", default=DEFAULT_OWNER_EMAIL, help="Gym Owner email")
    parser.add_argument("--owner-password", default=DEFAULT_OWNER_PASS, help="Gym Owner password")
    args = parser.parse_args()

    seed_admin_and_owner(
        admin_email=args.admin_email,
        admin_password=args.admin_password,
        owner_email=args.owner_email,
        owner_password=args.owner_password,
    )


if __name__ == "__main__":
    main()
