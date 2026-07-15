"""Application entrypoint: configure logging and run the bot."""

from __future__ import annotations

import asyncio
import logging

import discord

from src.bot import HeySpaceBot
from src.config import get_settings


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    discord.utils.setup_logging(level=logging.getLevelName(settings.log_level.upper()))

    async with HeySpaceBot(settings) as bot:
        await bot.start(settings.discord_token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
