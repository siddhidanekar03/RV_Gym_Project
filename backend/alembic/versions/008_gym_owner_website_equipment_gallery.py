"""008_gym_owner_website_equipment_gallery

Revision ID: 008_owner_website_equipment_gallery
Revises: 007_workout_plans_and_progress
Create Date: 2026-10-16 19:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "008_owner_web_equip_gallery"
down_revision: Union[str, Sequence[str], None] = "007_workout_plans_and_progress"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. website_content table
    op.create_table(
        "website_content",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("section", sa.String(length=50), nullable=False),
        sa.Column("branch_id", sa.String(length=50), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("updated_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_website_content_section", "website_content", ["section"], unique=False)
    op.create_index("ix_website_content_branch_id", "website_content", ["branch_id"], unique=False)

    # 2. equipment_items table
    op.create_table(
        "equipment_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("branch_id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("spec", sa.Text(), nullable=False),
        sa.Column("brand_model", sa.String(length=100), nullable=True),
        sa.Column("primary_image_url", sa.String(length=500), nullable=True),
        sa.Column("images", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_published", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_equipment_items_branch_id", "equipment_items", ["branch_id"], unique=False)
    op.create_index("ix_equipment_items_category", "equipment_items", ["category"], unique=False)
    op.create_index("ix_equipment_items_is_published", "equipment_items", ["is_published"], unique=False)

    # 3. gallery_items table
    op.create_table(
        "gallery_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("branch_id", sa.String(length=50), nullable=False),
        sa.Column("zone", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="In Active Use", nullable=False),
        sa.Column("is_published", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gallery_items_branch_id", "gallery_items", ["branch_id"], unique=False)
    op.create_index("ix_gallery_items_is_published", "gallery_items", ["is_published"], unique=False)

    # 4. Add optional description column to membership_plans
    op.add_column("membership_plans", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("membership_plans", "description")
    op.drop_index("ix_gallery_items_is_published", table_name="gallery_items")
    op.drop_index("ix_gallery_items_branch_id", table_name="gallery_items")
    op.drop_table("gallery_items")
    op.drop_index("ix_equipment_items_is_published", table_name="equipment_items")
    op.drop_index("ix_equipment_items_category", table_name="equipment_items")
    op.drop_index("ix_equipment_items_branch_id", table_name="equipment_items")
    op.drop_table("equipment_items")
    op.drop_index("ix_website_content_branch_id", table_name="website_content")
    op.drop_index("ix_website_content_section", table_name="website_content")
    op.drop_table("website_content")
