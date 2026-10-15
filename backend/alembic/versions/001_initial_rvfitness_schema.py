"""001_initial_rvfitness_schema

Revision ID: 001_initial_rvfitness_schema
Revises: 
Create Date: 2026-10-14 21:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001_initial_rvfitness_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Membership Plans Table
    op.create_table(
        "membership_plans",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=10), server_default="₹", nullable=False),
        sa.Column("billing_cycle", sa.String(length=50), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("is_featured", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("perks", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # 2. Users Table
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("role", sa.String(length=30), server_default="member", nullable=False),
        sa.Column("staff_role", sa.String(length=100), nullable=True),
        sa.Column("membership_id", sa.String(length=50), nullable=True),
        sa.Column("membership_plan_id", sa.String(length=50), nullable=True),
        sa.Column("membership_status", sa.String(length=30), server_default="pending", nullable=False),
        sa.Column("member_since", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("streak_days", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["membership_plan_id"], ["membership_plans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_membership_id"), "users", ["membership_id"], unique=True)
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)
    op.create_index(op.f("ix_users_membership_status"), "users", ["membership_status"], unique=False)

    # 3. Enrollments Table
    op.create_table(
        "enrollments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=10), server_default="₹", nullable=False),
        sa.Column("status", sa.String(length=50), server_default="pending_verification", nullable=False),
        sa.Column("accepted_terms", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("verified_by_id", sa.String(length=36), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["membership_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verified_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_enrollments_plan_id"), "enrollments", ["plan_id"], unique=False)
    op.create_index(op.f("ix_enrollments_phone"), "enrollments", ["phone"], unique=False)
    op.create_index(op.f("ix_enrollments_email"), "enrollments", ["email"], unique=False)
    op.create_index(op.f("ix_enrollments_status"), "enrollments", ["status"], unique=False)

    # 4. Attendance Records Table (with compound daily uniqueness)
    op.create_table(
        "attendance_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("check_in_date", sa.Date(), nullable=False),
        sa.Column("check_in_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("method", sa.String(length=30), server_default="portal", nullable=False),
        sa.Column("notes", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "check_in_date", name="uq_user_attendance_daily"),
    )
    op.create_index(op.f("ix_attendance_records_user_id"), "attendance_records", ["user_id"], unique=False)
    op.create_index(op.f("ix_attendance_records_check_in_date"), "attendance_records", ["check_in_date"], unique=False)

    # 5. Personal Records (PRs) Table
    op.create_table(
        "personal_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("exercise_name", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("unit", sa.String(length=20), server_default="kg", nullable=False),
        sa.Column("reps", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("is_coach_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("verified_by_id", sa.String(length=36), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["verified_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_personal_records_user_id"), "personal_records", ["user_id"], unique=False)
    op.create_index(op.f("ix_personal_records_exercise_name"), "personal_records", ["exercise_name"], unique=False)

    # 6. Contact Inquiries Table
    op.create_table(
        "contact_inquiries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="new", nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_contact_inquiries_phone"), "contact_inquiries", ["phone"], unique=False)
    op.create_index(op.f("ix_contact_inquiries_email"), "contact_inquiries", ["email"], unique=False)
    op.create_index(op.f("ix_contact_inquiries_status"), "contact_inquiries", ["status"], unique=False)

    # 7. Audit Logs Table
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.String(length=100), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"], unique=False)
    op.create_index(op.f("ix_audit_logs_resource_type"), "audit_logs", ["resource_type"], unique=False)
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("contact_inquiries")
    op.drop_table("personal_records")
    op.drop_table("attendance_records")
    op.drop_table("enrollments")
    op.drop_table("users")
    op.drop_table("membership_plans")
