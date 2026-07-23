"""Create the current application schema.

Revision ID: 20260724_01
Revises:
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260724_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This is an immutable snapshot of the pre-normalization schema. Never use
    # application metadata here: later ORM changes must not rewrite history.
    op.create_table(
        "user_profile",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("role", sa.String(9), nullable=False, server_default="user"),
        sa.Column("subscription", sa.String(8), nullable=False, server_default="free"),
        sa.Column("username", sa.String(55), nullable=False, unique=True),
        sa.Column("email", sa.String(55), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("last_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("avatar_url", sa.String(1024)),
        sa.Column("nickname", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("token_version", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("subscription_until", sa.DateTime(timezone=True)),
        sa.Column("active_overlay_lobby_id", sa.Uuid()),
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
    )
    op.create_index("ix_user_profile_email", "user_profile", ["email"], unique=True)
    op.create_index(
        "ix_user_profile_email_verified_at", "user_profile", ["email_verified_at"]
    )
    op.create_index(
        "ix_user_profile_subscription_until", "user_profile", ["subscription_until"]
    )
    op.create_index(
        "ix_user_profile_active_overlay_lobby_id",
        "user_profile",
        ["active_overlay_lobby_id"],
    )

    op.create_table(
        "pending_registration",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(55), nullable=False),
        sa.Column("email", sa.String(55), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("avatar_url", sa.String(1024)),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_pending_registration_username",
        "pending_registration",
        ["username"],
        unique=True,
    )
    op.create_index(
        "ix_pending_registration_email",
        "pending_registration",
        ["email"],
        unique=True,
    )
    op.create_index(
        "ix_pending_registration_expires_at", "pending_registration", ["expires_at"]
    )

    op.create_table(
        "game_lobby",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("overlay_public_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("max_players", sa.SmallInteger(), nullable=False, server_default="10"),
        sa.Column("title", sa.String(120), nullable=False, server_default="Лобби"),
        sa.Column(
            "host_user_id",
            sa.Uuid(),
            sa.ForeignKey("user_profile.id", ondelete="SET NULL"),
        ),
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
        sa.Column("imported_source_url", sa.String(1024)),
        sa.Column("imported_current_key", sa.String(120)),
        sa.Column(
            "imported_variants",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_game_lobby_overlay_public_id", "game_lobby", ["overlay_public_id"])
    op.create_index("ix_game_lobby_host_user_id", "game_lobby", ["host_user_id"])

    op.create_table(
        "player_card",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.Uuid(),
            sa.ForeignKey("user_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("nickname", sa.String(255), nullable=False),
        sa.Column("club", sa.String(255)),
        sa.Column("gomafia_url", sa.String(512)),
        sa.Column(
            "photo_urls",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
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
    )
    op.create_index("ix_player_card_owner_user_id", "player_card", ["owner_user_id"])

    op.create_table(
        "lobby_membership",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "lobby_id",
            sa.Uuid(),
            sa.ForeignKey("game_lobby.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "player_card_id",
            sa.Uuid(),
            sa.ForeignKey("player_card.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seat_order", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("game_role", sa.String(8)),
        sa.Column("status", sa.String(13)),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("lobby_photo_url", sa.String(1024)),
        sa.Column(
            "best_move",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "bonus_points", sa.Numeric(5, 1), nullable=False, server_default="0"
        ),
    )
    op.create_index("ix_lobby_membership_lobby_id", "lobby_membership", ["lobby_id"])
    op.create_index(
        "ix_lobby_membership_player_card_id", "lobby_membership", ["player_card_id"]
    )
    op.create_index("ix_lobby_membership_seat_order", "lobby_membership", ["seat_order"])

    op.create_table(
        "password_reset_token",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    for column in ("user_id", "token_hash", "expires_at"):
        op.create_index(
            f"ix_password_reset_token_{column}",
            "password_reset_token",
            [column],
            unique=column == "token_hash",
        )

    op.create_table(
        "email_verification_token",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_profile.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "pending_registration_id",
            sa.Uuid(),
            sa.ForeignKey("pending_registration.id", ondelete="CASCADE"),
        ),
        sa.Column("token_hash", sa.String(64)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    for column in ("user_id", "pending_registration_id", "token_hash", "expires_at"):
        op.create_index(
            f"ix_email_verification_token_{column}",
            "email_verification_token",
            [column],
            unique=column == "token_hash",
        )

    op.create_table(
        "feedback_message",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("message", sa.String(4000), nullable=False),
        sa.Column("page_url", sa.String(1024)),
        sa.Column("contact_email", sa.String(255)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_feedback_message_user_id", "feedback_message", ["user_id"])

    op.create_table(
        "user_overlay_design_access",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("design_code", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
    )
    for column in ("user_id", "design_code", "expires_at"):
        op.create_index(
            f"ix_user_overlay_design_access_{column}",
            "user_overlay_design_access",
            [column],
        )


def downgrade() -> None:
    raise RuntimeError("The baseline migration cannot be downgraded safely.")
