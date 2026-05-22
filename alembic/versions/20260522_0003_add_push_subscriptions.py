"""add push subscriptions

Revision ID: 20260522_0003
Revises: 20260522_0002
Create Date: 2026-05-22 16:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260522_0003"
down_revision = "20260522_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint"),
    )


def downgrade() -> None:
    op.drop_table("push_subscriptions")
