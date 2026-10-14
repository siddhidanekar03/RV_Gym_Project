"""003_enterprise_organization_billing_and_coaching

Revision ID: 003_enterprise_org_billing
Revises: 002_user_sessions_and_branch_scope
Create Date: 2026-10-14 22:25:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "003_enterprise_org_billing"
down_revision: Union[str, Sequence[str], None] = "002_user_sessions_and_branch_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create organizations table
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=50), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organizations_code", "organizations", ["code"], unique=True)

    # 2. Create branches table
    op.create_table(
        "branches",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), server_default="Narsobawadi", nullable=False),
        sa.Column("state", sa.String(length=100), server_default="Maharashtra", nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_branches_code", "branches", ["code"], unique=True)
    op.create_index("ix_branches_organization_id", "branches", ["organization_id"], unique=False)

    # 3. Create member_branch_access table
    op.create_table(
        "member_branch_access",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("branch_id", sa.String(length=50), nullable=False),
        sa.Column("granted_at", sa.Date(), server_default=sa.func.current_date(), nullable=False),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("notes", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_member_branch_access_user_id", "member_branch_access", ["user_id"], unique=False)
    op.create_index("ix_member_branch_access_branch_id", "member_branch_access", ["branch_id"], unique=False)

    # 4. Alter membership_plans table (category and access_scope)
    with op.batch_alter_table("membership_plans", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("category", sa.String(length=50), server_default="general", nullable=False)
        )
        batch_op.add_column(
            sa.Column("access_scope", sa.String(length=50), server_default="single_branch", nullable=False)
        )
        batch_op.create_index("ix_membership_plans_category", ["category"], unique=False)

    # 5. Create plan_prices table
    op.create_table(
        "plan_prices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=50), nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=10), server_default="₹", nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["membership_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_prices_plan_id", "plan_prices", ["plan_id"], unique=False)
    op.create_index("ix_plan_prices_effective_from", "plan_prices", ["effective_from"], unique=False)
    op.create_index("ix_plan_prices_effective_to", "plan_prices", ["effective_to"], unique=False)

    # 6. Create membership_changes table
    op.create_table(
        "membership_changes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("action_type", sa.String(length=50), nullable=False),
        sa.Column("previous_status", sa.String(length=30), nullable=False),
        sa.Column("new_status", sa.String(length=30), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("days_extended", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("performed_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["performed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_membership_changes_user_id", "membership_changes", ["user_id"], unique=False)
    op.create_index("ix_membership_changes_action_type", "membership_changes", ["action_type"], unique=False)

    # 7. Create trainer_profiles table
    op.create_table(
        "trainer_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("specialization", sa.String(length=100), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("certifications", sa.JSON(), nullable=False),
        sa.Column("experience_years", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("rating", sa.Numeric(precision=3, scale=2), server_default=sa.text("5.00"), nullable=False),
        sa.Column("max_clients", sa.Integer(), server_default=sa.text("20"), nullable=False),
        sa.Column("is_accepting_clients", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trainer_profiles_user_id", "trainer_profiles", ["user_id"], unique=True)

    # 8. Create trainer_member_assignments table
    op.create_table(
        "trainer_member_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("trainer_id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("assigned_by_id", sa.String(length=36), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["assigned_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["member_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trainer_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trainer_member_assignments_trainer_id", "trainer_member_assignments", ["trainer_id"], unique=False)
    op.create_index("ix_trainer_member_assignments_member_id", "trainer_member_assignments", ["member_id"], unique=False)

    # 9. Create invoice_sequences table
    op.create_table(
        "invoice_sequences",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("prefix", sa.String(length=20), nullable=False),
        sa.Column("current_number", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # 10. Create invoices table
    op.create_table(
        "invoices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("invoice_number", sa.String(length=50), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("branch_id", sa.String(length=50), nullable=False),
        sa.Column("enrollment_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="unpaid", nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("tax", sa.Numeric(precision=10, scale=2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("amount_paid", sa.Numeric(precision=10, scale=2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("balance_due", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["enrollment_id"], ["enrollments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invoices_invoice_number", "invoices", ["invoice_number"], unique=True)
    op.create_index("ix_invoices_user_id", "invoices", ["user_id"], unique=False)
    op.create_index("ix_invoices_branch_id", "invoices", ["branch_id"], unique=False)
    op.create_index("ix_invoices_enrollment_id", "invoices", ["enrollment_id"], unique=False)
    op.create_index("ix_invoices_status", "invoices", ["status"], unique=False)

    # 11. Create invoice_lines table
    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("invoice_id", sa.String(length=36), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invoice_lines_invoice_id", "invoice_lines", ["invoice_id"], unique=False)

    # 12. Create payments table
    op.create_table(
        "payments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("invoice_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("branch_id", sa.String(length=50), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("payment_method", sa.String(length=50), nullable=False),
        sa.Column("reference_number", sa.String(length=100), nullable=True),
        sa.Column("idempotency_key", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="completed", nullable=False),
        sa.Column("is_reversal", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("reversed_payment_id", sa.String(length=36), nullable=True),
        sa.Column("recorded_by_id", sa.String(length=36), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reversed_payment_id"], ["payments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"], unique=False)
    op.create_index("ix_payments_user_id", "payments", ["user_id"], unique=False)
    op.create_index("ix_payments_branch_id", "payments", ["branch_id"], unique=False)
    op.create_index("ix_payments_idempotency_key", "payments", ["idempotency_key"], unique=True)
    op.create_index("ix_payments_created_at", "payments", ["created_at"], unique=False)

    # 13. Alter enrollments (add branch_id)
    with op.batch_alter_table("enrollments", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("branch_id", sa.String(length=50), server_default="narsobawadi", nullable=False)
        )
        batch_op.create_index("ix_enrollments_branch_id", ["branch_id"], unique=False)

    # 14. Alter attendance_records (add branch_id)
    with op.batch_alter_table("attendance_records", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("branch_id", sa.String(length=50), server_default="narsobawadi", nullable=False)
        )
        batch_op.create_index("ix_attendance_records_branch_id", ["branch_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("attendance_records", schema=None) as batch_op:
        batch_op.drop_index("ix_attendance_records_branch_id")
        batch_op.drop_column("branch_id")

    with op.batch_alter_table("enrollments", schema=None) as batch_op:
        batch_op.drop_index("ix_enrollments_branch_id")
        batch_op.drop_column("branch_id")

    op.drop_table("payments")
    op.drop_table("invoice_lines")
    op.drop_table("invoices")
    op.drop_table("invoice_sequences")
    op.drop_table("trainer_member_assignments")
    op.drop_table("trainer_profiles")
    op.drop_table("membership_changes")
    op.drop_table("plan_prices")

    with op.batch_alter_table("membership_plans", schema=None) as batch_op:
        batch_op.drop_index("ix_membership_plans_category")
        batch_op.drop_column("access_scope")
        batch_op.drop_column("category")

    op.drop_table("member_branch_access")
    op.drop_table("branches")
    op.drop_table("organizations")
