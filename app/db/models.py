from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(255))


class SteamAccount(Base):
    __tablename__ = "steam_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    steam_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    profile_url: Mapped[str] = mapped_column(String(512))
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Chat(TimestampMixin, Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))


class ChatMember(Base):
    __tablename__ = "chat_members"

    chat_id: Mapped[int] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Game(Base):
    __tablename__ = "games"

    app_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(512))
    icon_hash: Mapped[str | None] = mapped_column(String(128))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UserGame(Base):
    __tablename__ = "user_games"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    app_id: Mapped[int] = mapped_column(
        ForeignKey("games.app_id", ondelete="CASCADE"), primary_key=True
    )
    playtime_forever: Mapped[int] = mapped_column(Integer, default=0)
    playtime_two_weeks: Mapped[int | None] = mapped_column(Integer)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_user_games_app_id", "app_id"),)


class Lobby(Base):
    __tablename__ = "lobbies"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    creator_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="open", server_default="open")
    winner_app_id: Mapped[int | None] = mapped_column(ForeignKey("games.app_id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LobbyMember(Base):
    __tablename__ = "lobby_members"

    lobby_id: Mapped[int] = mapped_column(
        ForeignKey("lobbies.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LobbyCandidate(Base):
    __tablename__ = "lobby_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    lobby_id: Mapped[int] = mapped_column(ForeignKey("lobbies.id", ondelete="CASCADE"))
    app_id: Mapped[int] = mapped_column(ForeignKey("games.app_id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        UniqueConstraint("lobby_id", "app_id"),
        UniqueConstraint("lobby_id", "position"),
    )


class LobbyVote(Base):
    __tablename__ = "lobby_votes"

    lobby_id: Mapped[int] = mapped_column(
        ForeignKey("lobbies.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("lobby_candidates.id", ondelete="CASCADE"), index=True
    )
    voted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WatchedGame(Base):
    __tablename__ = "watched_games"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    app_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(512))
    threshold_percent: Mapped[int] = mapped_column(Integer, default=50)
    last_seen_discount: Mapped[int] = mapped_column(Integer, default=0)
    last_seen_price: Mapped[int | None] = mapped_column(Integer)
    last_notified_discount: Mapped[int | None] = mapped_column(Integer)
    last_notified_price: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("user_id", "app_id"),)
