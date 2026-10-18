"""
Seed isolated staging test accounts for Phase 12A smoke test.
"""

import os
from backend.app.core.config import settings
from backend.app.core.database import SessionLocal
from backend.app.core.security import hash_password
from backend.app.models.organization import Organization, Branch
from backend.app.models.user import User

MGR_N_EMAIL = "smoke_mgr_narsobawadi@staging.rvfitness.com"
MGR_N_PASS = "StagingManagerPass123!"

MGR_K_EMAIL = "smoke_mgr_kurundwad@staging.rvfitness.com"
MGR_K_PASS = "StagingManagerPass123!"


def seed_staging_accounts():
    env = (os.environ.get("ENVIRONMENT") or settings.ENVIRONMENT or "").strip().lower()
    if env != "staging":
        raise RuntimeError(
            f"SAFETY VIOLATION: seed_staging_accounts is strictly restricted to ENVIRONMENT=staging. "
            f"Detected environment '{env}'. Staging test seeding aborted."
        )

    db = SessionLocal()
    try:
        # 1. Fetch organization
        org = db.query(Organization).first()
        if not org:
            org = Organization(name="RV Fitness", code="RVF", is_active=True)
            db.add(org)
            db.flush()

        # 2. Ensure narsobawadi branch
        branch_n = db.query(Branch).filter(Branch.id == "narsobawadi").first()
        if not branch_n:
            branch_n = Branch(
                id="narsobawadi",
                organization_id=org.id,
                name="Narsobawadi Main Campus",
                code="narsobawadi",
                city="Narsobawadi",
                state="Maharashtra",
                is_active=True,
            )
            db.add(branch_n)
            db.flush()

        # 3. Ensure kurundwad branch
        branch_k = db.query(Branch).filter(Branch.id == "kurundwad").first()
        if not branch_k:
            branch_k = Branch(
                id="kurundwad",
                organization_id=org.id,
                name="Kurundwad Annex",
                code="kurundwad",
                city="Kurundwad",
                state="Maharashtra",
                is_active=True,
            )
            db.add(branch_k)
            db.flush()

        # 4. Manager Narsobawadi
        mgr_n = db.query(User).filter(User.email == MGR_N_EMAIL).first()
        if not mgr_n:
            mgr_n = User(
                email=MGR_N_EMAIL,
                hashed_password=hash_password(MGR_N_PASS),
                name="Manager Narsobawadi (Test)",
                role="branch_manager",
                staff_role="manager",
                branch_id="narsobawadi",
                membership_status="active",
                is_active=True,
            )
            db.add(mgr_n)

        # 5. Manager Kurundwad
        mgr_k = db.query(User).filter(User.email == MGR_K_EMAIL).first()
        if not mgr_k:
            mgr_k = User(
                email=MGR_K_EMAIL,
                hashed_password=hash_password(MGR_K_PASS),
                name="Manager Kurundwad (Test)",
                role="branch_manager",
                staff_role="manager",
                branch_id="kurundwad",
                membership_status="active",
                is_active=True,
            )
            db.add(mgr_k)

        db.commit()
        print("[SUCCESS] Staging test branches and branch manager accounts verified and seeded.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_staging_accounts()
