from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from backend.app.models.membership import MembershipPlan, PlanPrice, Enrollment, MembershipChange
from backend.app.models.organization import MemberBranchAccess, Branch
from backend.app.models.billing import Invoice
from backend.app.models.user import User
from backend.app.models.audit import AuditLog
from backend.app.services.billing_service import generate_next_invoice_number, create_invoice_for_enrollment


def get_effective_plan_price(db: Session, plan_id: str, as_of: Optional[date] = None) -> Decimal:
    """
    Retrieve the price active on the given date (default today).
    Queries effective-dated PlanPrice records, falling back to plan.price if unconfigured.
    """
    target_date = as_of or date.today()

    price_record = (
        db.query(PlanPrice)
        .filter(
            PlanPrice.plan_id == plan_id,
            PlanPrice.is_active == True,
            PlanPrice.effective_from <= target_date,
            or_(PlanPrice.effective_to == None, PlanPrice.effective_to >= target_date),
        )
        .order_by(PlanPrice.effective_from.desc())
        .first()
    )
    if price_record:
        return price_record.price

    plan = db.query(MembershipPlan).filter(MembershipPlan.id == plan_id).first()
    if not plan:
        raise ValueError(f"Plan '{plan_id}' not found.")
    return plan.price


def is_member_eligible_for_branch(db: Session, user: User, branch_id: str) -> bool:
    """
    Evaluates whether a member is eligible to train at or access a given branch.
    Rules:
    1. Member's home branch matches branch_id.
    2. Member's membership plan has access_scope == 'all_branches'.
    3. Active explicit grant in member_branch_access table.
    """
    # 1. Home branch eligibility
    if user.branch_id == branch_id:
        return True

    today = date.today()

    # 2. Multi-branch plan tier access
    if user.membership_plan and user.membership_plan.access_scope == "all_branches":
        return True

    # 3. Explicit cross-branch access grant
    grant = (
        db.query(MemberBranchAccess)
        .filter(
            MemberBranchAccess.user_id == user.id,
            MemberBranchAccess.branch_id == branch_id,
            MemberBranchAccess.is_active == True,
            MemberBranchAccess.granted_at <= today,
            or_(MemberBranchAccess.expires_at == None, MemberBranchAccess.expires_at >= today),
        )
        .first()
    )
    return grant is not None


def calculate_expiry(start_from: date, duration_days: int) -> date:
    """Accurate date calculation for membership expiry."""
    return start_from + timedelta(days=duration_days)


def renew_membership(
    db: Session,
    user: User,
    plan_id: Optional[str] = None,
    actor: Optional[User] = None,
) -> Tuple[User, Invoice]:
    """
    Extends membership duration by plan days and creates a renewal invoice.
    If membership is currently active, extends from existing valid_until.
    If expired or missing, extends from today.
    """
    today = date.today()
    target_plan_id = plan_id or user.membership_plan_id
    if not target_plan_id:
        raise ValueError("Cannot renew membership without an assigned membership plan.")

    plan = db.query(MembershipPlan).filter(MembershipPlan.id == target_plan_id).first()
    if not plan:
        raise ValueError(f"Membership plan '{target_plan_id}' not found.")

    price = get_effective_plan_price(db, plan.id, as_of=today)

    # Determine renewal start date
    if user.valid_until and user.valid_until >= today and user.membership_status == "active":
        new_valid_until = calculate_expiry(user.valid_until, plan.duration_days)
    else:
        new_valid_until = calculate_expiry(today, plan.duration_days)

    old_status = user.membership_status
    user.valid_until = new_valid_until
    user.membership_status = "active"
    user.membership_plan_id = plan.id
    if not user.member_since:
        user.member_since = today

    # Create renewal invoice
    current_year = today.year
    prefix = f"INV-{current_year}"
    inv_number = generate_next_invoice_number(db, prefix=prefix)
    due_date = today + timedelta(days=7)

    invoice = Invoice(
        invoice_number=inv_number,
        user_id=user.id,
        branch_id=user.branch_id,
        status="unpaid",
        subtotal=price,
        tax=Decimal("0.00"),
        total_amount=price,
        amount_paid=Decimal("0.00"),
        balance_due=price,
        due_date=due_date,
        notes=f"Renewal invoice for {plan.name} plan extending through {new_valid_until.strftime('%B %d, %Y')}.",
    )
    db.add(invoice)
    db.flush()

    # Record lifecycle change
    change = MembershipChange(
        user_id=user.id,
        action_type="renewal",
        previous_status=old_status,
        new_status="active",
        start_date=today,
        end_date=new_valid_until,
        days_extended=plan.duration_days,
        reason=f"Membership renewal under {plan.name} plan.",
        performed_by_id=actor.id if actor else user.id,
    )
    db.add(change)

    # Audit log
    audit = AuditLog(
        actor_id=actor.id if actor else user.id,
        action="membership.renew",
        resource_type="user",
        resource_id=user.id,
        details={
            "plan_id": plan.id,
            "new_valid_until": new_valid_until.isoformat(),
            "invoice_number": inv_number,
        },
    )
    db.add(audit)
    db.flush()

    return user, invoice


def freeze_membership(
    db: Session,
    user: User,
    freeze_days: int,
    actor: User,
    reason: Optional[str] = None,
) -> User:
    """
    Freezes an active membership and extends valid_until by freeze_days.
    Check-in is prohibited while in 'frozen' status.
    """
    # Branch isolation: actor must belong to same branch as user unless org admin
    if actor.role not in {"org_admin", "admin"}:
        if actor.branch_id and user.branch_id and actor.branch_id != user.branch_id:
            raise PermissionError(f"Access denied: Cannot freeze membership of member from branch '{user.branch_id}'.")

    if user.membership_status != "active":
        raise ValueError(f"Only active memberships can be frozen. Current status: '{user.membership_status}'.")

    today = date.today()

    # Reject overlapping active freeze windows
    active_freeze = (
        db.query(MembershipChange)
        .filter(
            MembershipChange.user_id == user.id,
            MembershipChange.action_type == "freeze",
            MembershipChange.end_date >= today,
        )
        .first()
    )
    if active_freeze:
        raise ValueError("Member already has an active or overlapping freeze period.")

    if freeze_days <= 0 or freeze_days > 90:
        raise ValueError("Freeze duration must be between 1 and 90 days.")

    old_valid_until = user.valid_until or today
    new_valid_until = old_valid_until + timedelta(days=freeze_days)

    old_status = user.membership_status
    user.membership_status = "frozen"
    user.valid_until = new_valid_until

    change = MembershipChange(
        user_id=user.id,
        action_type="freeze",
        previous_status=old_status,
        new_status="frozen",
        start_date=today,
        end_date=today + timedelta(days=freeze_days),
        days_extended=freeze_days,
        reason=reason or f"Temporary membership freeze for {freeze_days} days.",
        performed_by_id=actor.id,
    )
    db.add(change)

    audit = AuditLog(
        actor_id=actor.id,
        action="membership.freeze",
        resource_type="user",
        resource_id=user.id,
        details={
            "freeze_days": freeze_days,
            "old_valid_until": old_valid_until.isoformat(),
            "new_valid_until": new_valid_until.isoformat(),
            "reason": reason,
        },
    )
    db.add(audit)
    db.flush()

    return user


def unfreeze_membership(
    db: Session,
    user: User,
    actor: User,
) -> User:
    """Restores a frozen membership back to active status."""
    if user.membership_status != "frozen":
        raise ValueError(f"Membership is not currently frozen. Status: '{user.membership_status}'.")

    today = date.today()
    user.membership_status = "active"

    change = MembershipChange(
        user_id=user.id,
        action_type="unfreeze",
        previous_status="frozen",
        new_status="active",
        start_date=today,
        days_extended=0,
        reason="Resumed active training access.",
        performed_by_id=actor.id,
    )
    db.add(change)

    audit = AuditLog(
        actor_id=actor.id,
        action="membership.unfreeze",
        resource_type="user",
        resource_id=user.id,
        details={"status": "active"},
    )
    db.add(audit)
    db.flush()

    return user


def cancel_membership(
    db: Session,
    user: User,
    actor: User,
    reason: Optional[str] = None,
) -> User:
    """Cancels a membership and terminates future gym floor access."""
    if actor.role not in {"org_admin", "admin"}:
        if actor.branch_id and user.branch_id and actor.branch_id != user.branch_id:
            raise PermissionError(f"Access denied: Cannot cancel membership of member from branch '{user.branch_id}'.")

    today = date.today()
    old_status = user.membership_status

    user.membership_status = "cancelled"
    # Cap valid_until at today
    if user.valid_until and user.valid_until > today:
        user.valid_until = today

    change = MembershipChange(
        user_id=user.id,
        action_type="cancellation",
        previous_status=old_status,
        new_status="cancelled",
        start_date=today,
        days_extended=0,
        reason=reason or "Membership cancelled.",
        performed_by_id=actor.id,
    )
    db.add(change)

    audit = AuditLog(
        actor_id=actor.id,
        action="membership.cancel",
        resource_type="user",
        resource_id=user.id,
        details={"reason": reason},
    )
    db.add(audit)
    db.flush()

    return user
