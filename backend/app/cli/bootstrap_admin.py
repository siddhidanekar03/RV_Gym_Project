import sys
import argparse
from typing import Optional
from sqlalchemy.orm import Session

from backend.app.core.database import SessionLocal
from backend.app.core.security import hash_password
from backend.app.models.user import User
from backend.app.models.organization import Organization, Branch
from backend.app.models.audit import AuditLog


def bootstrap_organization_admin(
    db: Session,
    email: str,
    password: str,
    name: str,
    phone: Optional[str] = None,
    org_name: str = "RV Fitness",
    branch_name: str = "Narsobawadi Main Campus",
) -> User:
    """
    Secure first-organization-admin initialization routine.
    Enforces uniqueness, hashes password, creates core tenant entities,
    and prevents accidental duplicate bootstrap.
    """
    # 1. Enforce single bootstrap constraint: check for any existing admin
    existing_admin = (
        db.query(User)
        .filter(User.role.in_(["admin", "org_admin"]))
        .first()
    )
    if existing_admin:
        raise ValueError(
            "Initialization aborted: An organization administrator already exists in the system."
        )

    # 2. Check for duplicate email
    existing_email = db.query(User).filter(User.email == email.strip().lower()).first()
    if existing_email:
        raise ValueError(f"Initialization aborted: User with email '{email}' already exists.")

    # 3. Password requirements check
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")

    # 4. Ensure Organization entity exists
    org = db.query(Organization).filter(Organization.code == "RVF").first()
    if not org:
        org = Organization(
            name=org_name,
            code="RVF",
            contact_email="management@rvfitness.in",
            contact_phone="+91 98220 12345",
            is_active=True,
        )
        db.add(org)
        db.flush()

    # 5. Ensure default Branch entity exists
    branch = db.query(Branch).filter(Branch.id == "narsobawadi").first()
    if not branch:
        branch = Branch(
            id="narsobawadi",
            organization_id=org.id,
            name=branch_name,
            code="narsobawadi",
            address="Near Datta Mandir Road",
            city="Narsobawadi",
            state="Maharashtra",
            phone="+91 98220 12345",
            email="contact@rvfitness.in",
            is_active=True,
        )
        db.add(branch)
        db.flush()

    # 6. Create initial Organization Administrator
    hashed = hash_password(password)
    admin_user = User(
        email=email.strip().lower(),
        hashed_password=hashed,
        name=name.strip(),
        phone=phone.strip() if phone else None,
        role="org_admin",
        staff_role="Organization Administrator",
        branch_id=branch.id,
        membership_status="active",
        is_active=True,
    )
    db.add(admin_user)
    db.flush()

    # 7. Record immutable audit entry
    audit = AuditLog(
        actor_id=admin_user.id,
        action="admin.bootstrap_cli",
        resource_type="organization_admin",
        resource_id=admin_user.id,
        details={
            "email": admin_user.email,
            "organization": org.name,
            "branch": branch.name,
        },
    )
    db.add(audit)
    db.commit()
    db.refresh(admin_user)

    return admin_user


def main() -> int:
    parser = argparse.ArgumentParser(
        description="RVFitness CLI: Secure First-Organization-Admin Bootstrap"
    )
    parser.add_argument("--email", required=True, help="Administrator email address")
    parser.add_argument("--password", required=True, help="Administrator secure password (min 8 chars)")
    parser.add_argument("--name", default="Principal Administrator", help="Full name of administrator")
    parser.add_argument("--phone", default=None, help="Contact telephone number")
    parser.add_argument("--org-name", default="RV Fitness", help="Primary Organization name")
    parser.add_argument("--branch-name", default="Narsobawadi Main Campus", help="Primary Branch name")

    args = parser.parse_args()

    db: Session = SessionLocal()
    try:
        admin = bootstrap_organization_admin(
            db=db,
            email=args.email,
            password=args.password,
            name=args.name,
            phone=args.phone,
            org_name=args.org_name,
            branch_name=args.branch_name,
        )
        print(
            f"SUCCESS: Organization Administrator created successfully!\n"
            f"  ID: {admin.id}\n"
            f"  Email: {admin.email}\n"
            f"  Role: {admin.role} ({admin.staff_role})\n"
            f"  Branch: {admin.branch_id}"
        )
        return 0
    except ValueError as e:
        print(f"ERROR: {str(e)}", file=sys.stderr)
        return 1
    except Exception as e:
        db.rollback()
        print(f"UNEXPECTED ERROR: {str(e)}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
