"""Set a course thumbnail by asking the user to upload an image in the image channel."""

from __future__ import annotations

import asyncio
import io
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import discord

from src.db.models.course import Course
from src.db.models.guild import GuildConfig
from src.lib.embed import Embed

from ..service import build_course_embed, embed_bar_file, load_course

if TYPE_CHECKING:
    from src.bot import HeySpaceBot

# How long the bot waits for a user to upload a thumbnail image, in seconds.
_IMAGE_UPLOAD_TIMEOUT = 120


class EditImageButton(discord.ui.Button):
    """Set the course thumbnail: ping the user in the image channel, then grab the upload.

    The image is re-hosted as an attachment on the course message and referenced via
    `attachment://`, so it stays valid indefinitely (raw Discord CDN URLs expire).
    """

    def __init__(self, course_id: int) -> None:
        super().__init__(
            label="Rediger billede", emoji="🖼️", style=discord.ButtonStyle.secondary
        )
        self.course_id = course_id

    async def callback(self, interaction: discord.Interaction) -> None:
        client: "HeySpaceBot" = interaction.client  # type: ignore[assignment]
        async with client.db.session() as session:
            cfg = await session.get(GuildConfig, client.settings.guild_id)
            image_channel_id = cfg.image_channel_id if cfg else None
            course = await session.get(Course, self.course_id)
            course_mention = course.mention if course is not None else None

        if course_mention is None:
            await interaction.response.edit_message(
                embed=Embed.notice(
                    "Kurset findes ikke længere.", title="Kurset er væk", color="red"
                ),
                view=None,
            )
            return
        if image_channel_id is None:
            await interaction.response.edit_message(
                embed=Embed.notice(
                    "Der er ikke valgt en billedkanal endnu. Brug `/billedkanal` først.",
                    title="Ingen billedkanal valgt",
                    color="yellow",
                ),
                view=None,
            )
            return

        image_channel = client.get_channel(image_channel_id) or await client.fetch_channel(
            image_channel_id
        )
        # Discord relative timestamp — renders as a live countdown in the client.
        deadline = discord.utils.format_dt(
            datetime.now(timezone.utc) + timedelta(seconds=_IMAGE_UPLOAD_TIMEOUT), style="R"
        )
        await interaction.response.edit_message(
            embed=Embed.notice(
                f"Gå til {image_channel.mention} og upload billedet. Timeout {deadline}.",
                title="Afventer billede",
                color="green",
            ),
            view=None,
        )

        prompt = await image_channel.send(
            content=interaction.user.mention,  # in content so it actually pings
            embed=Embed.notice(
                f"Upload billedet til {course_mention} i chatten her (vedhæft en "
                f"billedfil).\nTimeout {deadline}.",
                title="Upload billede",
                color="green",
            ),
        )

        def check(message: discord.Message) -> bool:
            return (
                message.author.id == interaction.user.id
                and message.channel.id == image_channel_id
                and bool(message.attachments)
            )

        try:
            message = await client.wait_for(
                "message", check=check, timeout=_IMAGE_UPLOAD_TIMEOUT
            )
        except asyncio.TimeoutError:
            await prompt.edit(
                content=interaction.user.mention,
                embed=Embed.notice(
                    "Tiden løb ud. Prøv igen via ℹ️-menuen.",
                    title="Tiden løb ud",
                    color="yellow",
                ),
            )
            return

        attachment = message.attachments[0]
        if not (attachment.content_type or "").startswith("image/"):
            await prompt.edit(
                content=interaction.user.mention,
                embed=Embed.notice(
                    "Vedhæftningen var ikke et billede. Prøv igen via ℹ️-menuen.",
                    title="Ugyldig fil",
                    color="red",
                ),
            )
            return

        data = await attachment.read()
        ext = attachment.filename.rsplit(".", 1)[-1].lower() if "." in attachment.filename else "png"
        filename = f"thumbnail_{self.course_id}.{ext}"

        async with client.db.session() as session:
            course = await session.get(Course, self.course_id)
            if course is None or course.message_id is None:
                await prompt.edit(
                    content=interaction.user.mention,
                    embed=Embed.notice(
                        "Kurset findes ikke længere.", title="Kurset er væk", color="red"
                    ),
                )
                return
            course.thumbnail_url = f"attachment://{filename}"
            channel_id, course_message_id = course.channel_id, course.message_id
            await session.commit()

        async with client.db.session() as session:
            course = await load_course(session, self.course_id)
            embed = build_course_embed(course)

        course_channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
        upload = discord.File(io.BytesIO(data), filename=filename)
        # Re-attach the brand bar too — passing `attachments` replaces them all, so
        # omitting it would drop the embed's main image.
        await course_channel.get_partial_message(course_message_id).edit(
            embed=embed, attachments=[embed_bar_file(), upload]
        )

        # Report completion on the original (ephemeral) menu message.
        await interaction.edit_original_response(
            embed=Embed.notice(
                f"Billedet til {course_mention} blev uploadet.",
                title="Upload gennemført",
                color="green",
            )
        )
        # Short-lived confirmation in the image channel, then tidy up.
        await image_channel.send(
            content=interaction.user.mention,
            embed=Embed.notice(
                f"Billedet til {course_mention} er modtaget ✅",
                title="Modtaget",
                color="green",
            ),
            delete_after=5,
        )
        await prompt.delete()
        try:
            await message.delete()
        except discord.HTTPException:
            pass
