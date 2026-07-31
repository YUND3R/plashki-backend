"""Add ratings and rating participants.

Revision ID: 20260729_03
Revises: 20260724_02
Create Date: 2026-07-29
"""

import sqlalchemy as sa
from alembic import op


revision = "20260729_03"
down_revision = "20260724_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rating",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "owner_user_id",
            sa.Uuid(),
            sa.ForeignKey("user_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
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
    op.create_index("ix_rating_owner_user_id", "rating", ["owner_user_id"])
    op.create_index("ix_rating_event_date", "rating", ["event_date"])

    op.create_table(
        "rating_participant",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "rating_id",
            sa.Uuid(),
            sa.ForeignKey("rating.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "player_card_id",
            sa.Uuid(),
            sa.ForeignKey("player_card.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rating_id",
            "player_card_id",
            name="uq_rating_participant_rating_player_card",
        ),
    )
    op.create_index(
        "ix_rating_participant_rating_id", "rating_participant", ["rating_id"]
    )
    op.create_index(
        "ix_rating_participant_player_card_id",
        "rating_participant",
        ["player_card_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_rating_participant_player_card_id", table_name="rating_participant")
    op.drop_index("ix_rating_participant_rating_id", table_name="rating_participant")
    op.drop_table("rating_participant")
    op.drop_index("ix_rating_event_date", table_name="rating")
    op.drop_index("ix_rating_owner_user_id", table_name="rating")
    op.drop_table("rating")
