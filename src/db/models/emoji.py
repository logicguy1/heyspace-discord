"""Emoji suggestion awaiting votes in the emoji vote channel.

One row per suggestion message. When its vote reaction reaches the threshold the
bot creates the custom emoji and flips `added` so it isn't processed again.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class EmojiSuggestion(Base):
    __tablename__ = "emoji_suggestion"

    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger)
    channel_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    name: Mapped[str] = mapped_column(String(32))
    created_by: Mapped[int] = mapped_column(BigInteger)
    added: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<EmojiSuggestion id={self.id} name={self.name!r} added={self.added}>"
