"""Add source and lobby_id for rating games.

Revision ID: 20260730_06
Revises: 20260729_05
Create Date: 2026-07-30
"""

import sqlalchemy as sa
from alembic import op


revision = "20260730_06"
down_revision = "20260729_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rating_game",
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
    )
    op.add_column("rating_game", sa.Column("lobby_id", sa.Uuid(), nullable=True))
    op.create_index("ix_rating_game_lobby_id", "rating_game", ["lobby_id"])
    op.create_foreign_key(
        "fk_rating_game_lobby_id_game_lobby",
        "rating_game",
        "game_lobby",
        ["lobby_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_rating_game_lobby_id_game_lobby", "rating_game", type_="foreignkey")
    op.drop_index("ix_rating_game_lobby_id", table_name="rating_game")
    op.drop_column("rating_game", "lobby_id")
    op.drop_column("rating_game", "source")
