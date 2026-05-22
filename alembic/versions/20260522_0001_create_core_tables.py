"""create core tables

Revision ID: 20260522_0001
Revises:
Create Date: 2026-05-22 12:50:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260522_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "photographers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("folder_name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_photographers_folder_name"), "photographers", ["folder_name"], unique=True)

    op.create_table(
        "batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("batch_key", sa.String(length=64), nullable=False),
        sa.Column("photographer_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("originals_path", sa.Text(), nullable=False),
        sa.Column("backup_path", sa.Text(), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("total_size_bytes", sa.Integer(), nullable=False),
        sa.Column("silence_age_seconds", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["photographer_id"], ["photographers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_batches_batch_key"), "batches", ["batch_key"], unique=True)
    op.create_index(op.f("ix_batches_photographer_id"), "batches", ["photographer_id"], unique=False)

    op.create_table(
        "photos",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("original_path", sa.Text(), nullable=False),
        sa.Column("backup_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_photos_batch_id"), "photos", ["batch_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_photos_batch_id"), table_name="photos")
    op.drop_table("photos")
    op.drop_index(op.f("ix_batches_photographer_id"), table_name="batches")
    op.drop_index(op.f("ix_batches_batch_key"), table_name="batches")
    op.drop_table("batches")
    op.drop_index(op.f("ix_photographers_folder_name"), table_name="photographers")
    op.drop_table("photographers")
