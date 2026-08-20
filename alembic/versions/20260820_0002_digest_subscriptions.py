"""Add daily digest subscriptions.

Revision ID: 20260820_0002
Revises: 20260820_0001
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260820_0002"
down_revision: str | None = "20260820_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "digest_subscriptions",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("min_discount", sa.Integer(), server_default="50", nullable=False),
        sa.Column("deals_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("releases_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_sent_on", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("min_discount IN (25, 50, 75)", name="ck_digest_min_discount"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("digest_subscriptions")
