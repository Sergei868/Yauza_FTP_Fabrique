"""add archive ttl columns to batches

Revision ID: 20260524_0005
Revises: 20260522_0004
Create Date: 2026-05-24 12:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260524_0005"
down_revision = "20260522_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("batches", sa.Column("removed_from_incoming_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("batches", sa.Column("archive_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("batches", "archive_expires_at")
    op.drop_column("batches", "removed_from_incoming_at")
