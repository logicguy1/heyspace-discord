"""Custom bot object: owns config, the database, cog loading and command sync."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import discord
from discord.ext import commands

from src.config import Settings, get_settings
from src.db import Database, get_database
from src.lib.embed import Embed

log = logging.getLogger("bot")

COGS_DIR = Path(__file__).parent / "cogs"
COGS_PACKAGE = "src.cogs"


class HeySpaceBot(commands.Bot):
    """Single-guild slash-command bot.

    Commands are synced to one guild for instant registration (global commands
    take up to an hour to propagate).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.db: Database = get_database()

        intents = discord.Intents.default()
        # Required so the bot can read attachments on members' uploads (e.g. the
        # course thumbnail flow). Privileged: also enable "Message Content Intent"
        # in the Discord developer portal (Bot → Privileged Gateway Intents).
        intents.message_content = True

        super().__init__(
            command_prefix=commands.when_mentioned,  # unused; slash-only
            intents=intents,
            help_command=None,
        )

    @property
    def guild_object(self) -> discord.Object:
        """Lightweight reference to the target guild for command scoping."""
        return discord.Object(id=self.settings.guild_id)

    def embed(self, *args, **kwargs) -> Embed:
        """Build a branded embed."""
        return Embed(*args, **kwargs)

    @staticmethod
    def _discover_extensions() -> list[str]:
        """Every cog extension under `src/cogs`.

        A cog is either a single `*.py` module or a package directory with an
        `__init__.py` (self-contained cogs bundling their commands, views and
        helpers). Entries prefixed with `_` or `.` are ignored.
        """
        exts: list[str] = []
        for path in sorted(COGS_DIR.iterdir()):
            if path.name.startswith(("_", ".")):
                continue
            if path.is_dir() and (path / "__init__.py").exists():
                exts.append(f"{COGS_PACKAGE}.{path.name}")
            elif path.is_file() and path.suffix == ".py":
                exts.append(f"{COGS_PACKAGE}.{path.stem}")
        return exts

    async def load_cogs(self) -> None:
        """Load every discovered cog extension."""
        for ext in self._discover_extensions():
            try:
                await self.load_extension(ext)
                log.info("Loaded cog %s", ext)
            except Exception:
                log.exception("Failed to load cog %s", ext)

    async def reload_cogs(self) -> None:
        """Reload already-loaded extensions, loading any that appeared since.

        `reload_extension` only re-executes the extension's top-level module, so a
        package cog's submodules (`views`, `service`, ...) and shared `src.lib.*`
        helpers stay cached in `sys.modules` and edits there wouldn't take effect.
        Drop those from the cache first so the reload re-imports them. `src.lib.embed`
        is excluded: it holds class-level footer branding set once in `on_ready`,
        which a mid-run reload would wipe.
        """
        exts = self._discover_extensions()
        stale = {"src.lib.embed"}
        purge = [
            m
            for m in sys.modules
            if (m.startswith("src.lib.") or any(m.startswith(f"{e}.") for e in exts))
            and m not in stale
        ]
        for name in purge:
            del sys.modules[name]

        for ext in exts:
            try:
                if ext in self.extensions:
                    await self.reload_extension(ext)
                    log.info("Reloaded cog %s", ext)
                else:
                    await self.load_extension(ext)
                    log.info("Loaded cog %s", ext)
            except Exception:
                log.exception("Failed to reload cog %s", ext)

    async def setup_hook(self) -> None:
        """Async startup: load cogs then sync commands to the target guild.

        Persistent-view registration lives in each cog's own `setup`, so cogs stay
        self-contained.
        """
        await self.load_cogs()
        self.tree.copy_global_to(guild=self.guild_object)
        synced = await self.tree.sync(guild=self.guild_object)
        log.info("Synced %d command(s) to guild %s", len(synced), self.settings.guild_id)

    async def on_ready(self) -> None:
        # Cache the guild's branding so every embed footer shows the server icon.
        guild = self.get_guild(self.settings.guild_id)
        if guild is not None:
            Embed.set_branding(guild)
        log.info("Logged in as %s (id=%s)", self.user, getattr(self.user, "id", "?"))

    async def close(self) -> None:
        await self.db.dispose()
        await super().close()
