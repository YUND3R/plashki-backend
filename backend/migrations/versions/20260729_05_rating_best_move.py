"""Add best_move to rating game results.

Revision ID: 20260729_05
Revises: 20260729_04
Create Date: 2026-07-29
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260729_05"
down_revision = "20260729_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rating_game_result",
        sa.Column(
            "best_move",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("rating_game_result", "best_move")
