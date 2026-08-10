"""Add email change confirmation tokens.

Revision ID: 20260810_07
Revises: 20260730_06
Create Date: 2026-08-10
"""

import sqlalchemy as sa
from alembic import op


revision = "20260810_07"
down_revision = "20260730_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_change_token",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("new_email", sa.String(length=55), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["user_profile.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_change_token_user_id", "email_change_token", ["user_id"])
    op.create_index("ix_email_change_token_new_email", "email_change_token", ["new_email"])
    op.create_index("ix_email_change_token_expires_at", "email_change_token", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_email_change_token_expires_at", table_name="email_change_token")
    op.drop_index("ix_email_change_token_new_email", table_name="email_change_token")
    op.drop_index("ix_email_change_token_user_id", table_name="email_change_token")
    op.drop_table("email_change_token")
