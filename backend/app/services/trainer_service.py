from typing import Optional, List
from sqlalchemy.orm import Session

from backend.app.models.user import User
from backend.app.models.trainer import TrainerProfile, TrainerMemberAssignment
from backend.app.models.audit import AuditLog


def get_trainer_assigned_members(db: Session, trainer_id: str) -> List[User]:
    """Retrieve list of active members assigned to a specific coach."""
    return (
        db.query(User)
        .filter(
            User.role == "member",
            User.assigned_trainer_id == trainer_id,
            User.is_active == True,
        )
        .all()
    )


def verify_trainer_access_to_member(trainer: User, member: User) -> None:
    """
    Enforce server-side isolation for trainers.
    If user has 'trainer' role, they may only view members assigned to them.
    Admins, managers, and staff retain supervisor visibility.
    """
    if trainer.role in ("org_admin", "admin", "branch_manager", "manager", "front_desk", "staff"):
        return

    if trainer.role == "trainer":
        if member.assigned_trainer_id != trainer.id:
            raise PermissionError("Access denied: You are not assigned to coach this member.")
        return

    # If member themselves
    if trainer.id == member.id:
        return

    raise PermissionError("Access denied: Insufficient permissions to view member profile.")


def assign_member_to_trainer(
    db: Session,
    trainer_id: str,
    member_id: str,
    actor: User,
    notes: Optional[str] = None,
) -> TrainerMemberAssignment:
    """
    Assign a member to a coach with capacity checking and audit logging.
    Requires Branch Manager or Organization Admin privileges.
    """
    trainer = db.query(User).filter(User.id == trainer_id, User.role == "trainer").first()
    if not trainer:
        raise ValueError(f"Trainer '{trainer_id}' not found or does not have trainer role.")

    member = db.query(User).filter(User.id == member_id, User.role == "member").first()
    if not member:
        raise ValueError(f"Member '{member_id}' not found.")

    # Check coach capacity
    if trainer.trainer_profile:
        current_count = (
            db.query(User)
            .filter(User.assigned_trainer_id == trainer.id, User.is_active == True)
            .count()
        )
        if current_count >= trainer.trainer_profile.max_clients:
            raise ValueError(
                f"Coach {trainer.name} is currently at maximum client capacity ({trainer.trainer_profile.max_clients} clients)."
            )

    # Deactivate previous active assignments for this member
    previous_assignments = (
        db.query(TrainerMemberAssignment)
        .filter(
            TrainerMemberAssignment.member_id == member.id,
            TrainerMemberAssignment.is_active == True,
        )
        .all()
    )
    for pa in previous_assignments:
        pa.is_active = False

    # Create new assignment record
    assignment = TrainerMemberAssignment(
        trainer_id=trainer.id,
        member_id=member.id,
        assigned_by_id=actor.id,
        is_active=True,
        notes=notes or f"Assigned by {actor.name} ({actor.role}).",
    )
    db.add(assignment)

    # Update member pointer
    member.assigned_trainer_id = trainer.id

    # Audit Trail
    audit = AuditLog(
        actor_id=actor.id,
        action="trainer.assigned",
        resource_type="user",
        resource_id=member.id,
        details={
            "member_name": member.name,
            "trainer_id": trainer.id,
            "trainer_name": trainer.name,
        },
    )
    db.add(audit)
    db.flush()

    return assignment
