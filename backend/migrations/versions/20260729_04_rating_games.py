"""Add rating games and game results.

Revision ID: 20260729_04
Revises: 20260729_03
Create Date: 2026-07-29
"""

import sqlalchemy as sa
from alembic import op


revision = "20260729_04"
down_revision = "20260729_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rating_game",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "rating_id",
            sa.Uuid(),
            sa.ForeignKey("rating.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("played_at", sa.Date(), nullable=False),
        sa.Column("winner_side", sa.String(length=5), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rating_game_rating_id", "rating_game", ["rating_id"])
    op.create_index("ix_rating_game_played_at", "rating_game", ["played_at"])

    op.create_table(
        "rating_game_result",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "rating_game_id",
            sa.Uuid(),
            sa.ForeignKey("rating_game.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "player_card_id",
            sa.Uuid(),
            sa.ForeignKey("player_card.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=8), nullable=False),
        sa.Column(
            "bonus_points", sa.Numeric(6, 1), nullable=False, server_default="0"
        ),
        sa.Column(
            "total_points", sa.Numeric(6, 1), nullable=False, server_default="0"
        ),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rating_game_id",
            "player_card_id",
            name="uq_rating_game_result_game_player",
        ),
    )
    op.create_index(
        "ix_rating_game_result_rating_game_id",
        "rating_game_result",
        ["rating_game_id"],
    )
    op.create_index(
        "ix_rating_game_result_player_card_id",
        "rating_game_result",
        ["player_card_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_rating_game_result_player_card_id", table_name="rating_game_result")
    op.drop_index("ix_rating_game_result_rating_game_id", table_name="rating_game_result")
    op.drop_table("rating_game_result")
    op.drop_index("ix_rating_game_played_at", table_name="rating_game")
    op.drop_index("ix_rating_game_rating_id", table_name="rating_game")
    op.drop_table("rating_game")
