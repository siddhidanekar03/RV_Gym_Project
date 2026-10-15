"""
Database Models Package.
Exports all declarative models to ensure discovery by Alembic and metadata reflection.
"""

from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, generate_uuid
from backend.app.models.organization import Organization, Branch, MemberBranchAccess
from backend.app.models.membership import MembershipPlan, PlanPrice, Enrollment, MembershipChange
from backend.app.models.user import User
from backend.app.models.trainer import TrainerProfile, TrainerMemberAssignment
from backend.app.models.billing import Invoice, InvoiceLine, Payment, InvoiceSequence
from backend.app.models.attendance import AttendanceRecord, AttendanceAttempt, ConsumedQRToken
from backend.app.models.personal_record import PersonalRecord
from backend.app.models.contact import ContactInquiry
from backend.app.models.audit import AuditLog
from backend.app.models.session import UserSession
from backend.app.models.announcement import Announcement
from backend.app.models.leaderboard import PointLedgerEntry
from backend.app.models.workout import (
    WorkoutPlan,
    WorkoutPlanAssignment,
    WorkoutPlanExercise,
    WorkoutSession,
    WorkoutSessionExercise,
    FitnessProgressRecord,
)

__all__ = [
    "Base",
    "TimestampMixin",
    "generate_uuid",
    "Organization",
    "Branch",
    "MemberBranchAccess",
    "MembershipPlan",
    "PlanPrice",
    "Enrollment",
    "MembershipChange",
    "User",
    "TrainerProfile",
    "TrainerMemberAssignment",
    "Invoice",
    "InvoiceLine",
    "Payment",
    "InvoiceSequence",
    "AttendanceRecord",
    "AttendanceAttempt",
    "ConsumedQRToken",
    "PersonalRecord",
    "ContactInquiry",
    "AuditLog",
    "UserSession",
    "Announcement",
    "PointLedgerEntry",
    "WorkoutPlan",
    "WorkoutPlanAssignment",
    "WorkoutPlanExercise",
    "WorkoutSession",
    "WorkoutSessionExercise",
    "FitnessProgressRecord",
]
