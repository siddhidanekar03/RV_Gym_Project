from typing import List, Optional
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.auth import get_current_user, require_roles, require_csrf
from backend.app.models.user import User
from backend.app.models.membership import MembershipPlan, PlanPrice
from backend.app.services.membership_service import (
    get_effective_plan_price,
    renew_membership,
    freeze_membership,
    unfreeze_membership,
    cancel_membership,
)
from backend.app.schemas.membership import (
    PlansResponse,
    PlanItem,
    RenewalRequest,
    RenewalResponse,
    FreezeRequest,
    FreezeResponse,
    CancelRequest,
    CancelResponse,
)

router = APIRouter()

DEFAULT_PLANS = [
    {
        "id": "plan_monthly",
        "name": "Monthly",
        "category": "general",
        "access_scope": "single_branch",
        "price": Decimal("1500.00"),
        "currency": "₹",
        "billing_cycle": "per month",
        "duration_days": 30,
        "is_featured": False,
        "is_active": True,
        "perks": [
            "Full gym floor access",
            "Standard locker room access",
            "Initial fitness assessment",
            "Free equipment orientation",
        ],
    },
    {
        "id": "plan_quarterly",
        "name": "Quarterly",
        "category": "strength",
        "access_scope": "single_branch",
        "price": Decimal("4000.00"),
        "currency": "₹",
        "billing_cycle": "per 3 months",
        "duration_days": 90,
        "is_featured": True,
        "is_active": True,
        "perks": [
            "Full gym floor access",
            "Priority locker allocation",
            "Nutritional guidance framework",
            "One dedicated 1-on-1 coach session",
            "Quarterly body composition check",
        ],
    },
    {
        "id": "plan_yearly",
        "name": "Yearly",
        "category": "vip",
        "access_scope": "all_branches",
        "price": Decimal("12000.00"),
        "currency": "₹",
        "billing_cycle": "per year",
        "duration_days": 365,
        "is_featured": False,
        "is_active": True,
        "perks": [
            "Unlimited year-round gym access",
            "Dedicated personalized workout routine",
            "Two complimentary guest passes monthly",
            "Priority coaching slot reservations",
            "Complete transformation tracking",
        ],
    },
]


@router.get("/plans", response_model=PlansResponse, summary="Available Membership Plans")
def get_plans(db: Session = Depends(get_db)) -> PlansResponse:
    """Fetch active membership plans from database, initializing defaults if unseeded."""
    plans = (
        db.query(MembershipPlan)
        .filter(MembershipPlan.is_active == True)
        .order_by(MembershipPlan.price.asc())
        .all()
    )

    if not plans:
        # Seed verified default plans
        for p in DEFAULT_PLANS:
            new_plan = MembershipPlan(**p)
            db.add(new_plan)
        db.commit()
        plans = (
            db.query(MembershipPlan)
            .filter(MembershipPlan.is_active == True)
            .order_by(MembershipPlan.price.asc())
            .all()
        )

    items: List[PlanItem] = []
    for plan in plans:
        # Resolve effective-dated active price
        effective_price = get_effective_plan_price(db, plan.id)
        items.append(
            PlanItem(
                id=plan.id,
                name=plan.name,
                category=plan.category,
                accessScope=plan.access_scope,
                price=int(effective_price),
                currency=plan.currency,
                billingCycle=plan.billing_cycle,
                durationDays=plan.duration_days,
                status="active" if plan.is_active else "inactive",
                featured=plan.is_featured,
                perks=plan.perks or [],
            )
        )

    return PlansResponse(plans=items)


@router.post(
    "/memberships/renew",
    response_model=RenewalResponse,
    dependencies=[Depends(require_csrf)],
    summary="Renew Membership Duration and Generate Renewal Invoice",
)
def handle_renewal(
    payload: RenewalRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RenewalResponse:
    try:
        updated_user, invoice = renew_membership(
            db=db,
            user=user,
            plan_id=payload.planId,
            actor=user,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return RenewalResponse(
        success=True,
        message=f"Membership successfully renewed! Expiry extended to {updated_user.valid_until.strftime('%B %d, %Y')}.",
        validUntil=updated_user.valid_until.isoformat(),
        invoiceNumber=invoice.invoice_number,
    )


@router.post(
    "/memberships/freeze",
    response_model=FreezeResponse,
    dependencies=[Depends(require_csrf), Depends(require_roles("org_admin", "admin", "branch_manager", "manager"))],
    summary="Freeze Member Access (Supervisory Action)",
)
def handle_freeze(
    payload: FreezeRequest,
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FreezeResponse:
    target_user = db.query(User).filter(User.id == payload.userId).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target member not found.")

    try:
        updated = freeze_membership(
            db=db,
            user=target_user,
            freeze_days=payload.freezeDays,
            actor=actor,
            reason=payload.reason,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return FreezeResponse(
        success=True,
        message=f"Membership for {updated.name} frozen for {payload.freezeDays} days.",
        status=updated.membership_status,
        newValidUntil=updated.valid_until.isoformat() if updated.valid_until else "",
    )


@router.post(
    "/memberships/cancel",
    response_model=CancelResponse,
    dependencies=[Depends(require_csrf), Depends(require_roles("org_admin", "admin", "branch_manager", "manager"))],
    summary="Cancel Member Access (Supervisory Action)",
)
def handle_cancel(
    payload: CancelRequest,
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CancelResponse:
    target_user = db.query(User).filter(User.id == payload.userId).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target member not found.")

    try:
        updated = cancel_membership(
            db=db,
            user=target_user,
            actor=actor,
            reason=payload.reason,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return CancelResponse(
        success=True,
        message=f"Membership for {updated.name} has been cancelled.",
        status=updated.membership_status,
    )
