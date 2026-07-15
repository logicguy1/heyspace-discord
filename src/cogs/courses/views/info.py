"""Persistent info button and the assembled course-message view."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from src.lib.embed import Embed

from ..service import load_course
from .host_menu import HostMenuView
from .signup import RaisedHandButton

if TYPE_CHECKING:
    from src.bot import HeySpaceBot


class InfoButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"course:info:(?P<course_id>\d+)",
):
    """Persistent info button: hosts and managers get the menu, others see run history."""

    def __init__(self, course_id: int) -> None:
        self.course_id = course_id
        super().__init__(
            discord.ui.Button(
                emoji="ℹ️",
                style=discord.ButtonStyle.secondary,
                custom_id=f"course:info:{course_id}",
            )
        )

    @classmethod
    async def from_custom_id(  # type: ignore[override]
        cls, interaction: discord.Interaction, item: discord.ui.Button, match, /
    ) -> "InfoButton":
        return cls(int(match["course_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        client: "HeySpaceBot" = interaction.client  # type: ignore[assignment]
        async with client.db.session() as session:
            course = await load_course(session, self.course_id)
            if course is None:
                await interaction.response.send_message(
                    embed=Embed.notice(
                        "Kurset findes ikke længere.", title="Kurset er væk", color="red"
                    ),
                    ephemeral=True,
                )
                return
            is_host = interaction.user.id in {h.user_id for h in course.hosts}
            dates = sorted(
                (run.ended_at for run in course.runs if run.ended_at is not None), reverse=True
            )
            course_name = course.name
            course_url = course.jump_url

        # guild_permissions only exists on Member (present for guild interactions).
        perms = getattr(interaction.user, "guild_permissions", None)
        can_manage = bool(perms and perms.manage_guild)

        history = (
            "\n".join(f"• {discord.utils.format_dt(d, style='D')}" for d in dates)
            if dates
            else "*Kurset er endnu ikke blevet afholdt.*"
        )
        embed = Embed.notice(history, title=f"{course_name} · Tidligere afholdelser", color="blue")
        embed.url = course_url  # makes the title link to the course message
        if is_host or can_manage:
            await interaction.response.send_message(
                embed=embed,
                view=HostMenuView(self.course_id, is_host=is_host, can_manage=can_manage),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


def course_message_view(course_id: int) -> discord.ui.View:
    """Persistent view: raise-hand + info buttons for a course's admin message."""
    view = discord.ui.View(timeout=None)
    view.add_item(RaisedHandButton(course_id))
    view.add_item(InfoButton(course_id))
    return view
