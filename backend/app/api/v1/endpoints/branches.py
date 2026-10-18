from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.auth import get_current_user, require_roles, require_csrf
from backend.app.models.user import User
from backend.app.models.organization import Branch, MemberBranchAccess, Organization
from backend.app.models.audit import AuditLog
from backend.app.schemas.organization import (
    BranchItem,
    BranchListResponse,
    MemberBranchAccessRequest,
    MemberBranchAccessResponse,
)

router = APIRouter()


@router.get(
    "/branches",
    response_model=BranchListResponse,
    summary="List Active Gym Branches",
)
def list_branches(db: Session = Depends(get_db)) -> BranchListResponse:
    branches = db.query(Branch).filter(Branch.is_active == True).order_by(Branch.name.asc()).all()
    if not branches:
        # Seed default branch if empty
        org = db.query(Organization).first()
        if not org:
            org = Organization(name="RV Fitness", code="RVF", is_active=True)
            db.add(org)
            db.flush()
        default_branch = Branch(
            id="narsobawadi",
            organization_id=org.id,
            name="Narsobawadi Main Campus",
            code="narsobawadi",
            address="Near Datta Mandir Road",
            city="Narsobawadi",
            state="Maharashtra",
            phone="+91 98220 12345",
            email="contact@rvfitness.in",
            is_active=True,
        )
        db.add(default_branch)
        db.commit()
        branches = [default_branch]

    items = [
        BranchItem(
            id=b.id,
            organizationId=b.organization_id,
            name=b.name,
            code=b.code,
            address=b.address,
            city=b.city,
            state=b.state,
            phone=b.phone,
            email=b.email,
            isActive=b.is_active,
        )
        for b in branches
    ]
    return BranchListResponse(branches=items)


@router.post(
    "/branches/access-grants",
    response_model=MemberBranchAccessResponse,
    dependencies=[Depends(require_csrf), Depends(require_roles("org_admin", "admin", "branch_manager", "manager"))],
    summary="Grant Cross-Branch Floor Access to Member",
)
def grant_branch_access(
    payload: MemberBranchAccessRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MemberBranchAccessResponse:
    member = db.query(User).filter(User.id == payload.userId, User.role == "member").first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member account not found.")

    target_branch = db.query(Branch).filter(Branch.id == payload.branchId, Branch.is_active == True).first()
    if not target_branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target branch not found.")

    if user.role not in ("org_admin", "admin"):
        if user.branch_id not in (member.branch_id, target_branch.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Branch manager of '{user.branch_id}' cannot grant access between '{member.branch_id}' and '{target_branch.id}'.",
            )

    # Create grant
    grant = MemberBranchAccess(
        user_id=member.id,
        branch_id=target_branch.id,
        expires_at=payload.expiresAt,
        is_active=True,
        notes=payload.notes,
    )
    db.add(grant)

    # Audit log
    audit = AuditLog(
        actor_id=user.id,
        action="branch.access_granted",
        resource_type="member_branch_access",
        resource_id=grant.id,
        details={
            "member_id": member.id,
            "target_branch": target_branch.name,
            "expires_at": payload.expiresAt.isoformat() if payload.expiresAt else None,
        },
    )
    db.add(audit)
    db.commit()

    return MemberBranchAccessResponse(
        success=True,
        message=f"Cross-branch access to {target_branch.name} granted for {member.name}.",
        grantId=grant.id,
    )
