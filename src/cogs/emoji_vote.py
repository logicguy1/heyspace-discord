"""Emoji voting: members suggest an emoji; enough votes adds it to the server.

`/emoji_forslag` posts the image in the configured vote channel with a 👍 seed
reaction. A reaction listener tallies votes and, once the threshold is reached,
creates the custom emoji and marks the suggestion done so it isn't added twice.
"""

from __future__ import annotations

import asyncio
import io
import re

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageSequence
from sqlalchemy import select

from src.db.models.emoji import EmojiSuggestion
from src.db.models.guild import GuildConfig
from src.lib.cog import BaseCog
from src.lib.embed import Embed

VOTE_EMOJI = "👍"
VOTE_THRESHOLD = 5
MAX_EMOJI_BYTES = 256 * 1024  # Discord's per-emoji upload limit.
# Dimensions to try when shrinking an oversized image, largest first.
_EMOJI_SIZES = (128, 96, 64, 48, 32)

_INVALID_NAME = re.compile(r"[^a-zA-Z0-9_]+")


def sanitize_name(raw: str) -> str | None:
    """Coerce a suggested name to a valid emoji name, or None if impossible.

    Emoji names must be 2-32 chars of letters, digits and underscores.
    """
    name = _INVALID_NAME.sub("_", raw.strip()).strip("_")
    if not 2 <= len(name) <= 32:
        return None
    return name


def prepare_emoji_image(data: bytes) -> bytes:
    """Downscale/compress image bytes to fit within Discord's emoji size limit.

    Returns the original bytes untouched if already small enough. Preserves
    animation for animated GIFs. Runs Pillow, so call it via a thread.
    """
    if len(data) <= MAX_EMOJI_BYTES:
        return data

    with Image.open(io.BytesIO(data)) as img:
        animated = getattr(img, "is_animated", False)
        if animated:
            frames = [frame.convert("RGBA") for frame in ImageSequence.Iterator(img)]
            duration = img.info.get("duration", 100)
            loop = img.info.get("loop", 0)
            smallest = data
            for size in _EMOJI_SIZES:
                resized = []
                for frame in frames:
                    copy = frame.copy()
                    copy.thumbnail((size, size))
                    resized.append(copy)
                buf = io.BytesIO()
                resized[0].save(
                    buf,
                    format="GIF",
                    save_all=True,
                    append_images=resized[1:],
                    loop=loop,
                    duration=duration,
                    disposal=2,
                    optimize=True,
                )
                smallest = buf.getvalue()
                if len(smallest) <= MAX_EMOJI_BYTES:
                    break
            return smallest

        rgba = img.convert("RGBA")
        smallest = data
        for size in _EMOJI_SIZES:
            copy = rgba.copy()
            copy.thumbnail((size, size))
            buf = io.BytesIO()
            copy.save(buf, format="PNG", optimize=True)
            smallest = buf.getvalue()
            if len(smallest) <= MAX_EMOJI_BYTES:
                break
        return smallest


class EmojiVote(BaseCog):
    @app_commands.command(
        name="emoji_kanal", description="Sæt kanalen hvor emoji-forslag sendes til afstemning."
    )
    @app_commands.describe(channel="Kanal til emoji-afstemninger.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_emoji_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        guild_id = self.bot.settings.guild_id
        async with self.session() as session:
            cfg = await session.get(GuildConfig, guild_id)
            if cfg is None:
                cfg = GuildConfig(guild_id=guild_id)
                session.add(cfg)
            cfg.emoji_vote_channel_id = channel.id
            await session.commit()
        await interaction.response.send_message(
            embed=Embed.notice(
                f"Emoji-forslag sendes nu til afstemning i {channel.mention}.",
                title="Emoji-kanal opdateret",
                color="green",
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="emoji_forslag", description="Foreslå et nyt server-emoji til afstemning."
    )
    @app_commands.describe(
        navn="Emoji-navn (2-32 tegn: bogstaver, tal, understregning).",
        billede="Billedet der skal blive til en emoji.",
    )
    async def suggest_emoji(
        self, interaction: discord.Interaction, navn: str, billede: discord.Attachment
    ) -> None:
        name = sanitize_name(navn)
        if name is None:
            await interaction.response.send_message(
                embed=Embed.notice(
                    "Ugyldigt navn. Brug 2-32 tegn: bogstaver, tal eller understregning.",
                    title="Ugyldigt navn",
                    color="red",
                ),
                ephemeral=True,
            )
            return
        if not (billede.content_type or "").startswith("image/"):
            await interaction.response.send_message(
                embed=Embed.notice(
                    "Vedhæftningen skal være et billede.", title="Ugyldig fil", color="red"
                ),
                ephemeral=True,
            )
            return
        # Any size is accepted here; the bot downscales it when the emoji is created.

        guild_id = self.bot.settings.guild_id
        async with self.session() as session:
            cfg = await session.get(GuildConfig, guild_id)
            channel_id = cfg.emoji_vote_channel_id if cfg else None
        if channel_id is None:
            await interaction.response.send_message(
                embed=Embed.notice(
                    "Der er ikke valgt en emoji-kanal endnu. Brug `/emoji_kanal` først.",
                    title="Ingen emoji-kanal",
                    color="yellow",
                ),
                ephemeral=True,
            )
            return

        channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
        data = await billede.read()
        ext = billede.filename.rsplit(".", 1)[-1].lower() if "." in billede.filename else "png"
        filename = f"emoji_{name}.{ext}"

        embed = Embed(
            title="Nyt emoji-forslag",
            description=(
                f"Navn: `:{name}:`\n"
                f"Foreslået af {interaction.user.mention}\n\n"
                f"Stem med {VOTE_EMOJI} — **{VOTE_THRESHOLD}** stemmer tilføjer emojiet."
            ),
        )
        embed.set_color("blue")
        embed.set_image(url=f"attachment://{filename}")
        message = await channel.send(
            embed=embed, file=discord.File(io.BytesIO(data), filename=filename)
        )
        await message.add_reaction(VOTE_EMOJI)

        async with self.session() as session:
            session.add(
                EmojiSuggestion(
                    guild_id=guild_id,
                    channel_id=channel_id,
                    message_id=message.id,
                    name=name,
                    created_by=interaction.user.id,
                )
            )
            await session.commit()

        await interaction.response.send_message(
            embed=Embed.notice(
                f"Dit forslag `:{name}:` er sendt til afstemning i {channel.mention}.",
                title="Forslag sendt",
                color="green",
            ),
            ephemeral=True,
        )

    async def _suggestion_image_bytes(self, message: discord.Message) -> bytes | None:
        """Image bytes for a suggestion message.

        A file referenced by an embed via ``attachment://`` is served as the embed
        image and dropped from ``message.attachments``, so fall back to downloading
        the embed image URL.
        """
        if message.attachments:
            return await message.attachments[0].read()
        if message.embeds and message.embeds[0].image and message.embeds[0].image.url:
            url = message.embeds[0].image.url
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    self.log.warning("Embed image download failed: HTTP %s", resp.status)
        return None

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        self.log.info(
            "Reaction add: emoji=%s message=%s user=%s guild=%s member=%s bot=%s",
            payload.emoji,
            payload.message_id,
            payload.user_id,
            payload.guild_id,
            payload.member,
            getattr(payload.member, "bot", None),
        )
        if payload.guild_id is None or payload.member is None or payload.member.bot:
            self.log.info(
                "Ignoring reaction: guild=%s member=%s bot=%s",
                payload.guild_id,
                payload.member,
                getattr(payload.member, "bot", None),
            )
            return
        if str(payload.emoji) != VOTE_EMOJI:
            self.log.info("Ignoring reaction: %r is not the vote emoji %r", str(payload.emoji), VOTE_EMOJI)
            return

        async with self.session() as session:
            suggestion = (
                await session.execute(
                    select(EmojiSuggestion).where(
                        EmojiSuggestion.message_id == payload.message_id
                    )
                )
            ).scalar_one_or_none()
            if suggestion is None:
                self.log.debug("No suggestion for message %s", payload.message_id)
                return
            if suggestion.added:
                self.log.debug("Suggestion %s already added", suggestion.id)
                return
            suggestion_id = suggestion.id
            name = suggestion.name
            channel_id = suggestion.channel_id
            created_by = suggestion.created_by

        channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.HTTPException:
            self.log.warning("Could not fetch suggestion message %s", payload.message_id)
            return

        votes = next(
            (r.count for r in message.reactions if str(r.emoji) == VOTE_EMOJI), 0
        ) - 1  # exclude the bot's seed reaction
        self.log.info(
            "Suggestion %r (id=%s) has %d/%d votes", name, suggestion_id, votes, VOTE_THRESHOLD
        )
        if votes < VOTE_THRESHOLD:
            return

        # Acquire the image before claiming, so a failure here stays retriable.
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            self.log.warning("Cannot create emoji: guild %s not found", payload.guild_id)
            return
        raw = await self._suggestion_image_bytes(message)
        if raw is None:
            self.log.warning("No image found on suggestion message %s", payload.message_id)
            return

        # Claim the suggestion so a burst of reactions can't add it twice.
        async with self.session() as session:
            suggestion = await session.get(EmojiSuggestion, suggestion_id)
            if suggestion is None or suggestion.added:
                self.log.debug("Suggestion %s claimed by another handler", suggestion_id)
                return
            suggestion.added = True
            await session.commit()

        self.log.info("Threshold reached for %r — creating emoji", name)
        # Shrink to fit the emoji size limit (offloaded — Pillow is blocking).
        image = await asyncio.to_thread(prepare_emoji_image, raw)
        try:
            created = await guild.create_custom_emoji(
                name=name,
                image=image,
                reason=f"Emoji-afstemning nåede {VOTE_THRESHOLD} stemmer",
            )
        except discord.HTTPException as error:
            # Roll back the claim so it can be retried once the cause is fixed.
            async with self.session() as session:
                suggestion = await session.get(EmojiSuggestion, suggestion_id)
                if suggestion is not None:
                    suggestion.added = False
                    await session.commit()
            self.log.warning("Failed to create emoji %r: %s", name, error)
            await message.reply(
                embed=Embed.notice(
                    "Kunne ikke tilføje emojiet (måske er der ikke flere emoji-pladser).",
                    title="Fejl ved tilføjelse",
                    color="red",
                )
            )
            return

        self.log.info("Created emoji %r (id=%s)", created.name, created.id)
        result = Embed(
            title="Emoji tilføjet 🎉",
            description=(
                f"{created} `:{created.name}:` er nu tilføjet til serveren!\n"
                f"Foreslået af <@{created_by}>."
            ),
        )
        result.set_color("green")
        result.set_thumbnail(url=created.url)
        # Drop the original image now that it's a live emoji (attachments=[] clears it).
        await message.edit(embed=result, attachments=[])
        try:
            await message.clear_reactions()
        except discord.HTTPException:
            pass


async def setup(bot) -> None:
    await bot.add_cog(EmojiVote(bot))
