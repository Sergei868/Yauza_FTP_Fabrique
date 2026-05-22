"""add broken files count and app settings

Revision ID: 20260522_0004
Revises: 20260522_0003
Create Date: 2026-05-22 17:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260522_0004"
down_revision = "20260522_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "batches",
        sa.Column("broken_files_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("batches", "broken_files_count", server_default=None)

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_column("batches", "broken_files_count")
