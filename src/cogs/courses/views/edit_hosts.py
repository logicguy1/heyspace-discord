"""Edit a course's host list via a prefilled member picker."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from sqlalchemy import delete

from src.db.models.course import Course, CourseHost
from src.lib.embed import Embed

from ..service import load_course, refresh_course_message

if TYPE_CHECKING:
    from src.bot import HeySpaceBot


class HostSelect(discord.ui.UserSelect):
    """Pick the course's hosts; prefilled with the current ones."""

    def __init__(self, course_id: int, current_ids: list[int]) -> None:
        super().__init__(
            placeholder="Vælg undervisere",
            min_values=1,
            max_values=25,
            default_values=[discord.Object(id=uid) for uid in current_ids[:25]],
        )
        self.course_id = course_id

    async def callback(self, interaction: discord.Interaction) -> None:
        client: "HeySpaceBot" = interaction.client  # type: ignore[assignment]
        # Dedup while preserving selection order.
        user_ids: list[int] = []
        for user in self.values:
            if user.id not in user_ids:
                user_ids.append(user.id)
        async with client.db.session() as session:
            course = await session.get(Course, self.course_id)
            if course is None:
                await interaction.response.edit_message(
                    embed=Embed.notice(
                        "Kurset findes ikke længere.", title="Kurset er væk", color="red"
                    ),
                    view=None,
                )
                return
            await session.execute(
                delete(CourseHost).where(CourseHost.course_id == self.course_id)
            )
            for uid in user_ids:
                session.add(CourseHost(course_id=self.course_id, user_id=uid))
            await session.commit()
        await refresh_course_message(client, self.course_id)
        await interaction.response.edit_message(
            embed=Embed.notice(
                "Underviserne er opdateret.", title="Undervisere opdateret", color="green"
            ),
            view=None,
        )


class HostSelectView(discord.ui.View):
    """Ephemeral view wrapping the host picker."""

    def __init__(self, course_id: int, current_ids: list[int]) -> None:
        super().__init__(timeout=180)
        self.add_item(HostSelect(course_id, current_ids))


class EditHostsButton(discord.ui.Button):
    """Open the host picker, prefilled with the course's current hosts."""

    def __init__(self, course_id: int) -> None:
        super().__init__(
            label="Rediger undervisere", emoji="👥", style=discord.ButtonStyle.secondary
        )
        self.course_id = course_id

    async def callback(self, interaction: discord.Interaction) -> None:
        client: "HeySpaceBot" = interaction.client  # type: ignore[assignment]
        async with client.db.session() as session:
            course = await load_course(session, self.course_id)
            if course is None:
                await interaction.response.edit_message(
                    embed=Embed.notice(
                        "Kurset findes ikke længere.", title="Kurset er væk", color="red"
                    ),
                    view=None,
                )
                return
            current_ids = [h.user_id for h in course.hosts]
        await interaction.response.edit_message(
            embed=Embed.notice(
                "Vælg de undervisere der skal stå på kurset.",
                title="Rediger undervisere",
                color="blue",
            ),
            view=HostSelectView(self.course_id, current_ids),
        )
