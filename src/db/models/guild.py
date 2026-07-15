"""Per-guild configuration model.

The bot is single-guild, so this table holds at most one row, but modelling it
explicitly keeps guild-scoped settings in the database instead of the code.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class GuildConfig(Base):
    __tablename__ = "guild_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    # Example guild-scoped setting: channel the bot logs events to (nullable until set).
    log_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Channel where course admin messages are posted (nullable until set via command).
    courses_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Channel where emoji suggestions are posted for voting.
    emoji_vote_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<GuildConfig guild_id={self.guild_id}>"
