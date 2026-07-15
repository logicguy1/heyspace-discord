"""Edit a course's title and description via a modal dialog."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from src.db.models.course import Course
from src.lib.embed import Embed

from ..service import refresh_course_message

if TYPE_CHECKING:
    from src.bot import HeySpaceBot


class EditCourseModal(discord.ui.Modal, title="Rediger kursus"):
    """Dialog for editing a course's title and description."""

    def __init__(self, course_id: int, name: str, description: str) -> None:
        super().__init__()
        self.course_id = course_id
        self.name_input = discord.ui.TextInput(
            label="Titel",
            default=name,
            max_length=256,  # matches Course.name column
            required=True,
        )
        self.description_input = discord.ui.TextInput(
            label="Beskrivelse",
            style=discord.TextStyle.paragraph,
            default=description,
            max_length=4000,  # Discord modal input cap
            required=True,
        )
        self.add_item(self.name_input)
        self.add_item(self.description_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        client: "HeySpaceBot" = interaction.client  # type: ignore[assignment]
        async with client.db.session() as session:
            course = await session.get(Course, self.course_id)
            if course is None:
                await interaction.response.send_message(
                    embed=Embed.notice(
                        "Kurset findes ikke længere.", title="Kurset er væk", color="red"
                    ),
                    ephemeral=True,
                )
                return
            course.name = self.name_input.value
            course.description = self.description_input.value
            await session.commit()
        await refresh_course_message(client, self.course_id)
        await interaction.response.send_message(
            embed=Embed.notice(
                "Kursets titel og beskrivelse er opdateret.",
                title="Kursus opdateret",
                color="green",
            ),
            ephemeral=True,
        )


class EditCourseButton(discord.ui.Button):
    """Open the edit dialog, prefilled with the course's current title/description."""

    def __init__(self, course_id: int) -> None:
        super().__init__(label="Rediger kursus", emoji="✏️", style=discord.ButtonStyle.secondary)
        self.course_id = course_id

    async def callback(self, interaction: discord.Interaction) -> None:
        client: "HeySpaceBot" = interaction.client  # type: ignore[assignment]
        async with client.db.session() as session:
            course = await session.get(Course, self.course_id)
            if course is None:
                await interaction.response.edit_message(
                    content=None,
                    embed=Embed.notice(
                        "Kurset findes ikke længere.", title="Kurset er væk", color="red"
                    ),
                    view=None,
                )
                return
            name, description = course.name, course.description
        await interaction.response.send_modal(EditCourseModal(self.course_id, name, description))
