"""Raise-hand button and its ephemeral signup / removal prompts."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from src.db.models.course import Course, CourseSignup
from src.lib.embed import Embed

from ..service import refresh_course_message

if TYPE_CHECKING:
    from src.bot import HeySpaceBot


class SignupConfirmView(discord.ui.View):
    """Ephemeral prompt shown when a member who isn't signed up raises their hand."""

    def __init__(self, course_id: int) -> None:
        super().__init__(timeout=120)
        self.course_id = course_id

    @discord.ui.button(label="Bekræft", emoji="✅", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        client: "HeySpaceBot" = interaction.client  # type: ignore[assignment]
        added = True
        async with client.db.session() as session:
            session.add(CourseSignup(course_id=self.course_id, user_id=interaction.user.id))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                added = False
        await refresh_course_message(client, self.course_id)
        if added:
            embed = Embed.notice(
                "Du er nu tilmeldt kurset og står på listen over interesserede.",
                title="Tilmelding bekræftet",
                color="green",
            )
        else:
            embed = Embed.notice(
                "Du stod allerede på listen over interesserede.",
                title="Allerede tilmeldt",
                color="yellow",
            )
        await interaction.response.edit_message(content=None, embed=embed, view=None)

    @discord.ui.button(label="Annullér", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        embed = Embed.notice("Handlingen blev annulleret.", color="grey")
        await interaction.response.edit_message(content=None, embed=embed, view=None)


class RemoveConfirmView(discord.ui.View):
    """Ephemeral prompt shown when an already-signed-up member raises their hand."""

    def __init__(self, course_id: int) -> None:
        super().__init__(timeout=120)
        self.course_id = course_id

    @discord.ui.button(label="Fjern", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def remove(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        client: "HeySpaceBot" = interaction.client  # type: ignore[assignment]
        async with client.db.session() as session:
            await session.execute(
                delete(CourseSignup).where(
                    CourseSignup.course_id == self.course_id,
                    CourseSignup.user_id == interaction.user.id,
                )
            )
            await session.commit()
        await refresh_course_message(client, self.course_id)
        embed = Embed.notice(
            "Du er fjernet fra listen over interesserede.",
            title="Interesse fjernet",
            color="green",
        )
        await interaction.response.edit_message(content=None, embed=embed, view=None)

    @discord.ui.button(label="Annullér", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        embed = Embed.notice("Ingen ændringer blev foretaget.", color="grey")
        await interaction.response.edit_message(content=None, embed=embed, view=None)


class RaisedHandButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"course:hand:(?P<course_id>\d+)",
):
    """Persistent raise-hand button; its custom_id carries the course id."""

    def __init__(self, course_id: int) -> None:
        self.course_id = course_id
        super().__init__(
            discord.ui.Button(
                emoji="✋",
                style=discord.ButtonStyle.primary,
                custom_id=f"course:hand:{course_id}",
            )
        )

    @classmethod
    async def from_custom_id(  # type: ignore[override]
        cls, interaction: discord.Interaction, item: discord.ui.Button, match, /
    ) -> "RaisedHandButton":
        return cls(int(match["course_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
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
            existing = (
                await session.execute(
                    select(CourseSignup).where(
                        CourseSignup.course_id == self.course_id,
                        CourseSignup.user_id == interaction.user.id,
                    )
                )
            ).scalar_one_or_none()
            course_mention = course.mention

        if existing is not None:
            await interaction.response.send_message(
                embed=Embed.notice(
                    f"Du er allerede tilmeldt {course_mention}.\n"
                    "Vil du fjerne dig fra listen over interesserede?",
                    title="Fjern tilmelding?",
                    color="blue",
                ),
                view=RemoveConfirmView(self.course_id),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=Embed.notice(
                    f"Vil du tilmelde dig {course_mention} som interesseret?",
                    title="Tilmeld dig kurset?",
                    color="blue",
                ),
                view=SignupConfirmView(self.course_id),
                ephemeral=True,
            )
