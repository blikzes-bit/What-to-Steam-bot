"""Initial MVP schema.

Revision ID: 20260820_0001
Revises:
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260820_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("telegram_id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])

    op.create_table(
        "chats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("telegram_id"),
    )
    op.create_index("ix_chats_telegram_id", "chats", ["telegram_id"])

    op.create_table(
        "games",
        sa.Column("app_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("icon_hash", sa.String(length=128), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "steam_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("steam_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("profile_url", sa.String(length=512), nullable=False),
        sa.Column("avatar_url", sa.String(length=512), nullable=True),
        sa.Column(
            "linked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("steam_id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_steam_accounts_steam_id", "steam_accounts", ["steam_id"])
    op.create_index("ix_steam_accounts_user_id", "steam_accounts", ["user_id"])

    op.create_table(
        "chat_members",
        sa.Column("chat_id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "user_games",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("app_id", sa.Integer(), primary_key=True),
        sa.Column("playtime_forever", sa.Integer(), nullable=False),
        sa.Column("playtime_two_weeks", sa.Integer(), nullable=True),
        sa.Column(
            "synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["app_id"], ["games.app_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_games_app_id", "user_games", ["app_id"])

    op.create_table(
        "watched_games",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("app_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("threshold_percent", sa.Integer(), nullable=False),
        sa.Column("last_seen_discount", sa.Integer(), nullable=False),
        sa.Column("last_seen_price", sa.Integer(), nullable=True),
        sa.Column("last_notified_discount", sa.Integer(), nullable=True),
        sa.Column("last_notified_price", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "app_id"),
    )

    op.create_table(
        "lobbies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.Integer(), nullable=False),
        sa.Column("creator_user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("winner_app_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["creator_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["winner_app_id"], ["games.app_id"]),
    )
    op.create_index("ix_lobbies_chat_id", "lobbies", ["chat_id"])

    op.create_table(
        "lobby_members",
        sa.Column("lobby_id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["lobby_id"], ["lobbies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "lobby_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lobby_id", sa.Integer(), nullable=False),
        sa.Column("app_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["app_id"], ["games.app_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lobby_id"], ["lobbies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("lobby_id", "app_id"),
        sa.UniqueConstraint("lobby_id", "position"),
    )

    op.create_table(
        "lobby_votes",
        sa.Column("lobby_id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column(
            "voted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["lobby_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lobby_id"], ["lobbies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_lobby_votes_candidate_id", "lobby_votes", ["candidate_id"])


def downgrade() -> None:
    op.drop_index("ix_lobby_votes_candidate_id", table_name="lobby_votes")
    op.drop_table("lobby_votes")
    op.drop_table("lobby_candidates")
    op.drop_table("lobby_members")
    op.drop_index("ix_lobbies_chat_id", table_name="lobbies")
    op.drop_table("lobbies")
    op.drop_table("watched_games")
    op.drop_index("ix_user_games_app_id", table_name="user_games")
    op.drop_table("user_games")
    op.drop_table("chat_members")
    op.drop_index("ix_steam_accounts_user_id", table_name="steam_accounts")
    op.drop_index("ix_steam_accounts_steam_id", table_name="steam_accounts")
    op.drop_table("steam_accounts")
    op.drop_table("games")
    op.drop_index("ix_chats_telegram_id", table_name="chats")
    op.drop_table("chats")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")
