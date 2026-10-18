from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

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


def approve_enrollment(
    db: Session,
    enrollment_id: str,
    actor: User,
    record_payment: bool = False,
    payment_method: Optional[str] = "cash",
    payment_amount: Optional[Decimal] = None,
    reference_number: Optional[str] = None,
    notes: Optional[str] = None,
) -> Enrollment:
    """
    Approves a membership enrollment application.
    If payment is confirmed (or recorded now), immediately activates the membership.
    Otherwise sets status to 'payment_pending' awaiting front-desk payment.
    """
    enrollment = (
        db.query(Enrollment)
        .filter(Enrollment.id == enrollment_id)
        .with_for_update()
        .first()
    )
    if not enrollment:
        raise ValueError(f"Enrollment application '{enrollment_id}' not found.")

    # Branch authorization
    if actor.role not in {"org_admin", "admin"}:
        if actor.branch_id and enrollment.branch_id and actor.branch_id != enrollment.branch_id:
            raise PermissionError(
                f"Access denied: You are not authorized to approve applications for branch '{enrollment.branch_id}'."
            )

    if enrollment.status == "active":
        raise ValueError("Enrollment application is already approved and activated.")

    if enrollment.status == "payment_pending" and not record_payment:
        raise ValueError("Enrollment application is already approved and awaiting payment.")

    if enrollment.status == "rejected":
        raise ValueError("Cannot approve a rejected enrollment application. The member must submit a new request.")

    # Link member user account if not already linked
    user = None
    if enrollment.user_id:
        user = db.query(User).filter(User.id == enrollment.user_id).first()
    elif enrollment.email:
        clean_email = enrollment.email.strip().lower()
        user = db.query(User).filter(func.lower(User.email) == clean_email).first()
        if user:
            enrollment.user_id = user.id

    plan = db.query(MembershipPlan).filter(MembershipPlan.id == enrollment.plan_id).first()
    if not plan:
        raise ValueError(f"Membership plan '{enrollment.plan_id}' not found.")

    invoice = (
        db.query(Invoice)
        .filter(Invoice.enrollment_id == enrollment.id)
        .with_for_update()
        .first()
    )

    if invoice and user and not invoice.user_id:
        invoice.user_id = user.id

    # Record desk payment if requested
    if record_payment and invoice:
        from backend.app.services.billing_service import record_offline_payment
        pay_amt = payment_amount if payment_amount is not None else invoice.balance_due
        if pay_amt > Decimal("0.00"):
            record_offline_payment(
                db=db,
                invoice_id=invoice.id,
                amount=pay_amt,
                payment_method=payment_method or "cash",
                recorded_by=actor,
                reference_number=reference_number,
                idempotency_key=f"enr_pay_{enrollment.id}_{int(datetime.now(timezone.utc).timestamp())}",
                notes=notes or "Payment recorded during enrollment approval",
            )
            db.refresh(invoice)

    # Set approval audit trail
    enrollment.verified_by_id = actor.id
    enrollment.verified_at = datetime.now(timezone.utc)
    if notes:
        enrollment.notes = notes

    today = date.today()
    is_paid = invoice is not None and (invoice.balance_due <= Decimal("0.00") or invoice.status == "paid")

    if is_paid:
        # Full payment confirmed: Activate membership immediately
        enrollment.status = "active"
        if user:
            old_status = user.membership_status
            user.membership_status = "active"
            user.membership_plan_id = plan.id
            user.branch_id = enrollment.branch_id
            if not user.member_since:
                user.member_since = today
            user.valid_until = calculate_expiry(today, plan.duration_days)

            change = MembershipChange(
                user_id=user.id,
                action_type="enrollment",
                previous_status=old_status,
                new_status="active",
                start_date=today,
                end_date=user.valid_until,
                days_extended=plan.duration_days,
                reason=f"Membership approved and activated for {plan.name} plan.",
                performed_by_id=actor.id,
            )
            db.add(change)

        audit = AuditLog(
            actor_id=actor.id,
            action="enrollment.approved_and_activated",
            resource_type="enrollment",
            resource_id=enrollment.id,
            details={
                "plan_id": plan.id,
                "plan_name": plan.name,
                "user_id": user.id if user else None,
                "status": "active",
                "valid_until": user.valid_until.isoformat() if user and user.valid_until else None,
            },
        )
        db.add(audit)
    else:
        # Payment pending: Approve request, associate plan, wait for desk payment
        enrollment.status = "payment_pending"
        if user:
            user.membership_status = "approved"
            user.membership_plan_id = plan.id
            user.branch_id = enrollment.branch_id

        audit = AuditLog(
            actor_id=actor.id,
            action="enrollment.approved_pending_payment",
            resource_type="enrollment",
            resource_id=enrollment.id,
            details={
                "plan_id": plan.id,
                "plan_name": plan.name,
                "user_id": user.id if user else None,
                "status": "payment_pending",
                "balance_due": str(invoice.balance_due) if invoice else str(enrollment.price),
            },
        )
        db.add(audit)

    db.flush()
    return enrollment


def reject_enrollment(
    db: Session,
    enrollment_id: str,
    actor: User,
    reason: str,
    notes: Optional[str] = None,
) -> Enrollment:
    """
    Rejects a membership enrollment application.
    Preserves enrollment history without activating membership.
    """
    enrollment = (
        db.query(Enrollment)
        .filter(Enrollment.id == enrollment_id)
        .with_for_update()
        .first()
    )
    if not enrollment:
        raise ValueError(f"Enrollment application '{enrollment_id}' not found.")

    if actor.role not in {"org_admin", "admin"}:
        if actor.branch_id and enrollment.branch_id and actor.branch_id != enrollment.branch_id:
            raise PermissionError(
                f"Access denied: You are not authorized to reject applications for branch '{enrollment.branch_id}'."
            )

    if enrollment.status == "active":
        raise ValueError("Cannot reject an enrollment that is already active.")

    if enrollment.status == "rejected":
        raise ValueError("Enrollment application has already been rejected.")

    enrollment.status = "rejected"
    enrollment.rejection_reason = reason.strip()
    enrollment.verified_by_id = actor.id
    enrollment.verified_at = datetime.now(timezone.utc)
    if notes:
        enrollment.notes = notes

    # Void unpaid initial invoice if no payments were made
    invoice = db.query(Invoice).filter(Invoice.enrollment_id == enrollment.id).first()
    if invoice and invoice.amount_paid == Decimal("0.00") and invoice.status == "unpaid":
        invoice.status = "void"
        invoice.notes = f"Invoice voided due to enrollment application rejection: {reason}"

    # If linked user is currently pending, mark membership_status as rejected
    if enrollment.user_id:
        user = db.query(User).filter(User.id == enrollment.user_id).first()
        if user and user.membership_status in ("pending", "approved"):
            user.membership_status = "rejected"

    audit = AuditLog(
        actor_id=actor.id,
        action="enrollment.rejected",
        resource_type="enrollment",
        resource_id=enrollment.id,
        details={
            "reason": reason,
            "user_id": enrollment.user_id,
            "plan_id": enrollment.plan_id,
        },
    )
    db.add(audit)
    db.flush()
    return enrollment


def activate_enrollment_from_paid_invoice(db: Session, invoice: Invoice) -> Optional[Enrollment]:
    """
    Checks if a paid invoice corresponds to an approved enrollment and activates the membership.
    Called automatically when invoice balance reaches zero.
    """
    if not invoice.enrollment_id:
        return None

    enrollment = (
        db.query(Enrollment)
        .filter(Enrollment.id == invoice.enrollment_id)
        .with_for_update()
        .first()
    )
    if not enrollment or enrollment.status == "active" or enrollment.status == "rejected":
        return enrollment

    # Check if invoice is fully paid
    if invoice.balance_due > Decimal("0.00") or invoice.status != "paid":
        return enrollment

    enrollment.status = "active"
    plan = enrollment.plan or db.query(MembershipPlan).filter(MembershipPlan.id == enrollment.plan_id).first()
    if not plan:
        return enrollment

    # Find user
    user = None
    if enrollment.user_id:
        user = db.query(User).filter(User.id == enrollment.user_id).first()
    elif invoice.user_id:
        user = db.query(User).filter(User.id == invoice.user_id).first()
        enrollment.user_id = user.id
    elif enrollment.email:
        clean_email = enrollment.email.strip().lower()
        user = db.query(User).filter(func.lower(User.email) == clean_email).first()
        if user:
            enrollment.user_id = user.id

    if user:
        today = date.today()
        old_status = user.membership_status
        user.membership_status = "active"
        user.membership_plan_id = plan.id
        user.branch_id = enrollment.branch_id
        if not user.member_since:
            user.member_since = today
        user.valid_until = calculate_expiry(today, plan.duration_days)

        change = MembershipChange(
            user_id=user.id,
            action_type="enrollment",
            previous_status=old_status,
            new_status="active",
            start_date=today,
            end_date=user.valid_until,
            days_extended=plan.duration_days,
            reason=f"Membership activated upon payment confirmation for {plan.name} plan.",
            performed_by_id=invoice.user_id or user.id,
        )
        db.add(change)

        audit = AuditLog(
            actor_id=invoice.user_id or user.id,
            action="enrollment.activated_on_payment",
            resource_type="enrollment",
            resource_id=enrollment.id,
            details={
                "plan_id": plan.id,
                "invoice_id": invoice.id,
                "valid_until": user.valid_until.isoformat(),
            },
        )
        db.add(audit)

    db.flush()
    return enrollment


def assign_membership_to_user(
    db: Session,
    target_user_id: str,
    plan_id: str,
    actor: User,
    branch_id: Optional[str] = None,
    record_payment: bool = False,
    payment_method: Optional[str] = "cash",
    payment_amount: Optional[Decimal] = None,
    reference_number: Optional[str] = None,
    notes: Optional[str] = None,
) -> Tuple[Enrollment, Invoice, User]:
    """
    Directly assigns a membership plan to an existing member account.
    Creates enrollment and initial invoice.
    If record_payment is True, immediately approves and activates membership.
    Otherwise, marks status as pending verification / payment pending.
    Guards against:
    1. Cross-branch unauthorized access.
    2. Overlapping active memberships (must use renewal).
    3. Duplicate pending enrollments.
    """
    import random

    if actor.role not in {"org_admin", "admin", "branch_manager", "manager"}:
        raise PermissionError("Access denied: Only owners and authorized managers can assign memberships.")

    target_user = db.query(User).filter(User.id == target_user_id).first()
    if not target_user:
        raise ValueError(f"Target member '{target_user_id}' not found.")

    effective_branch = (branch_id or target_user.branch_id or "narsobawadi").strip()

    # Branch authorization
    if actor.role in {"branch_manager", "manager"}:
        if actor.branch_id and effective_branch != actor.branch_id:
            raise PermissionError(f"Access denied: You are not authorized to assign memberships for branch '{effective_branch}'.")
        if target_user.branch_id and actor.branch_id != target_user.branch_id:
            raise PermissionError(f"Access denied: Target member belongs to branch '{target_user.branch_id}'.")

    # Guard 1: Conflicting active membership
    today = date.today()
    if target_user.membership_status == "active" and target_user.valid_until and target_user.valid_until >= today:
        plan_name = target_user.membership_plan.name if target_user.membership_plan else "Active Plan"
        raise ValueError(
            f"Member '{target_user.name}' already has an active {plan_name} membership "
            f"valid through {target_user.valid_until.strftime('%B %d, %Y')}. "
            "Please use the Renewal action instead of assigning a new initial plan."
        )

    # Guard 2: Duplicate pending enrollment
    pending_enr = (
        db.query(Enrollment)
        .filter(
            Enrollment.user_id == target_user.id,
            Enrollment.status.in_(["pending_verification", "Pending Verification at Gym Desk", "payment_pending"]),
        )
        .first()
    )
    if pending_enr:
        raise ValueError(
            f"Member '{target_user.name}' already has a pending enrollment request "
            f"(ID: {pending_enr.id[:8]}..., Status: {pending_enr.status}). "
            "Please resolve the existing request in Membership Requests."
        )

    # Validate plan
    plan = db.query(MembershipPlan).filter(MembershipPlan.id == plan_id, MembershipPlan.is_active == True).first()
    if not plan:
        raise ValueError(f"Active membership plan '{plan_id}' not found.")

    # Ensure member has a keycard code assigned
    if not target_user.membership_id:
        year = today.year
        rand_code = random.randint(100, 999)
        card_code = f"RVF-{year}-{rand_code}"
        while db.query(User).filter(User.membership_id == card_code).first():
            rand_code = random.randint(100, 999)
            card_code = f"RVF-{year}-{rand_code}"
        target_user.membership_id = card_code

    # Create Enrollment
    enrollment = Enrollment(
        plan_id=plan.id,
        user_id=target_user.id,
        branch_id=effective_branch,
        name=target_user.name,
        phone=target_user.phone or "0000000000",
        email=target_user.email,
        price=plan.price,
        currency=plan.currency,
        status="pending_verification",
        notes=notes or f"Membership assigned by {actor.name} ({actor.role})",
        accepted_terms=True,
    )
    db.add(enrollment)
    db.flush()

    # Create Initial Invoice
    invoice = create_invoice_for_enrollment(
        db=db,
        enrollment=enrollment,
        plan=plan,
        user_id=target_user.id,
        branch_id=effective_branch,
    )

    # Update member target
    target_user.membership_plan_id = plan.id
    target_user.branch_id = effective_branch
    target_user.membership_status = "pending"

    # Audit log
    audit = AuditLog(
        actor_id=actor.id,
        action="membership.assigned_by_admin",
        resource_type="enrollment",
        resource_id=enrollment.id,
        details={
            "plan_id": plan.id,
            "plan_name": plan.name,
            "user_id": target_user.id,
            "user_name": target_user.name,
            "branch_id": effective_branch,
            "invoice_number": invoice.invoice_number,
            "record_payment": record_payment,
        },
    )
    db.add(audit)
    db.flush()

    if record_payment:
        enrollment = approve_enrollment(
            db=db,
            enrollment_id=enrollment.id,
            actor=actor,
            record_payment=True,
            payment_method=payment_method,
            payment_amount=payment_amount,
            reference_number=reference_number,
            notes=notes or "Immediate payment recorded upon membership assignment",
        )

    return enrollment, invoice, target_user

