"""Normalize broadcast, lobby overlay, and commerce-owned data.

Revision ID: 20260724_02
Revises: 20260724_01
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260724_02"
down_revision = "20260724_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broadcast_user_settings",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_profile.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "active_overlay_lobby_id",
            sa.Uuid(),
            sa.ForeignKey("game_lobby.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_broadcast_user_settings_active_overlay_lobby_id",
        "broadcast_user_settings",
        ["active_overlay_lobby_id"],
    )
    op.execute(
        """
        INSERT INTO broadcast_user_settings
            (user_id, active_overlay_lobby_id, updated_at)
        SELECT
            u.id,
            CASE WHEN l.id IS NULL THEN NULL ELSE u.active_overlay_lobby_id END,
            COALESCE(u.updated_at, now())
        FROM user_profile AS u
        LEFT JOIN game_lobby AS l ON l.id = u.active_overlay_lobby_id
        """
    )

    op.create_table(
        "lobby_overlay_state",
        sa.Column(
            "lobby_id",
            sa.Uuid(),
            sa.ForeignKey("game_lobby.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("overlay_public_id", sa.Uuid(), nullable=False),
        sa.Column(
            "selected_overlay_design",
            sa.String(13),
            nullable=False,
            server_default="classic",
        ),
        sa.Column(
            "active_overlay_screen",
            sa.String(64),
            nullable=False,
            server_default="lobby",
        ),
        sa.Column(
            "show_victory_scores", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "sheriff_check",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "best_move",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_index(
        "ix_lobby_overlay_state_overlay_public_id",
        "lobby_overlay_state",
        ["overlay_public_id"],
        unique=True,
    )
    op.execute(
        """
        INSERT INTO lobby_overlay_state (
            lobby_id, overlay_public_id, selected_overlay_design,
            active_overlay_screen, show_victory_scores, sheriff_check, best_move
        )
        SELECT
            id, overlay_public_id, selected_overlay_design,
            active_overlay_screen, show_victory_scores, sheriff_check, best_move
        FROM game_lobby
        """
    )

    op.create_table(
        "commerce_user_subscription",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_profile.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "subscription", sa.String(8), nullable=False, server_default="free"
        ),
        sa.Column("subscription_until", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_commerce_user_subscription_subscription_until",
        "commerce_user_subscription",
        ["subscription_until"],
    )
    op.execute(
        """
        INSERT INTO commerce_user_subscription
            (user_id, subscription, subscription_until)
        SELECT id, subscription, subscription_until
        FROM user_profile
        """
    )

    op.drop_index("ix_user_profile_active_overlay_lobby_id", table_name="user_profile")
    op.drop_index("ix_user_profile_subscription_until", table_name="user_profile")
    op.drop_index("ix_game_lobby_overlay_public_id", table_name="game_lobby")
    op.drop_column("user_profile", "active_overlay_lobby_id")
    op.drop_column("user_profile", "subscription_until")
    op.drop_column("user_profile", "subscription")
    op.drop_column("game_lobby", "best_move")
    op.drop_column("game_lobby", "sheriff_check")
    op.drop_column("game_lobby", "show_victory_scores")
    op.drop_column("game_lobby", "active_overlay_screen")
    op.drop_column("game_lobby", "selected_overlay_design")
    op.drop_column("game_lobby", "overlay_public_id")


def downgrade() -> None:
    op.add_column(
        "user_profile",
        sa.Column("subscription", sa.String(8), nullable=True, server_default="free"),
    )
    op.add_column(
        "user_profile", sa.Column("subscription_until", sa.DateTime(timezone=True))
    )
    op.add_column("user_profile", sa.Column("active_overlay_lobby_id", sa.Uuid()))
    op.execute(
        """
        UPDATE user_profile AS u
        SET subscription = s.subscription,
            subscription_until = s.subscription_until,
            active_overlay_lobby_id = b.active_overlay_lobby_id
        FROM commerce_user_subscription AS s
        JOIN broadcast_user_settings AS b ON b.user_id = s.user_id
        WHERE u.id = s.user_id
        """
    )
    op.alter_column("user_profile", "subscription", nullable=False)
    op.create_index(
        "ix_user_profile_subscription_until", "user_profile", ["subscription_until"]
    )
    op.create_index(
        "ix_user_profile_active_overlay_lobby_id",
        "user_profile",
        ["active_overlay_lobby_id"],
    )

    op.add_column("game_lobby", sa.Column("overlay_public_id", sa.Uuid()))
    op.add_column(
        "game_lobby",
        sa.Column(
            "selected_overlay_design",
            sa.String(13),
            nullable=True,
            server_default="classic",
        ),
    )
    op.add_column(
        "game_lobby",
        sa.Column(
            "active_overlay_screen",
            sa.String(64),
            nullable=True,
            server_default="lobby",
        ),
    )
    op.add_column(
        "game_lobby",
        sa.Column(
            "show_victory_scores",
            sa.Boolean(),
            nullable=True,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "game_lobby",
        sa.Column(
            "sheriff_check",
            postgresql.JSONB(),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "game_lobby",
        sa.Column(
            "best_move",
            postgresql.JSONB(),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.execute(
        """
        UPDATE game_lobby AS l
        SET overlay_public_id = s.overlay_public_id,
            selected_overlay_design = s.selected_overlay_design,
            active_overlay_screen = s.active_overlay_screen,
            show_victory_scores = s.show_victory_scores,
            sheriff_check = s.sheriff_check,
            best_move = s.best_move
        FROM lobby_overlay_state AS s
        WHERE l.id = s.lobby_id
        """
    )
    for column in (
        "overlay_public_id",
        "selected_overlay_design",
        "active_overlay_screen",
        "show_victory_scores",
        "sheriff_check",
        "best_move",
    ):
        op.alter_column("game_lobby", column, nullable=False)
    op.create_unique_constraint(
        "uq_game_lobby_overlay_public_id", "game_lobby", ["overlay_public_id"]
    )
    op.create_index(
        "ix_game_lobby_overlay_public_id", "game_lobby", ["overlay_public_id"]
    )

    op.drop_table("commerce_user_subscription")
    op.drop_table("broadcast_user_settings")
    op.drop_table("lobby_overlay_state")
