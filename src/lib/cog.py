"""Base class every cog inherits from.

Provides typed access to the bot, a per-cog logger, and a shortcut to build
branded embeds and open database sessions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from src.lib.embed import Embed

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.bot import HeySpaceBot


class BaseCog(commands.Cog):
    def __init__(self, bot: "HeySpaceBot") -> None:
        self.bot = bot
        self.log = logging.getLogger(f"cog.{self.__class__.__name__.lower()}")

    def embed(self, *args, **kwargs) -> Embed:
        """Build a branded embed (footer already set to the server icon)."""
        return Embed(*args, **kwargs)

    def session(self) -> "AsyncSession":
        """Open a new database session: `async with self.session() as s:`."""
        return self.bot.db.session()

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Default error handler shared by every cog.

        Reports missing permissions using whatever the failing command actually
        required, and logs anything unexpected. Cogs may override for
        command-specific handling.
        """
        if isinstance(error, app_commands.MissingPermissions):
            perms = ", ".join(
                p.replace("_", " ").title() for p in error.missing_permissions
            )
            embed = Embed.notice(
                f"Du har ikke de nødvendige tilladelser: **{perms}**.",
                title="Adgang nægtet",
                color="red",
            )
        else:
            self.log.exception("Command error in %s", self.__class__.__name__, exc_info=error)
            embed = Embed.notice(
                "Der opstod en uventet fejl. Prøv igen senere.",
                title="Noget gik galt",
                color="red",
            )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
