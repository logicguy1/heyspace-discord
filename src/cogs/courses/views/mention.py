"""Thread-only button that pings everyone signed up for the course."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from src.lib.embed import Embed

from ..service import load_course

if TYPE_CHECKING:
    from src.bot import HeySpaceBot


class MentionSignupsButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"course:mention:(?P<course_id>\d+)",
):
    """Persistent button: pings every interested member. Hosts / managers only."""

    def __init__(self, course_id: int) -> None:
        self.course_id = course_id
        super().__init__(
            discord.ui.Button(
                emoji="📣",
                label="Nævn tilmeldte",
                style=discord.ButtonStyle.secondary,
                custom_id=f"course:mention:{course_id}",
            )
        )

    @classmethod
    async def from_custom_id(  # type: ignore[override]
        cls, interaction: discord.Interaction, item: discord.ui.Button, match, /
    ) -> "MentionSignupsButton":
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
            host_ids = {h.user_id for h in course.hosts}
            signup_ids = [s.user_id for s in course.signups]

        perms = getattr(interaction.user, "guild_permissions", None)
        can_manage = bool(perms and perms.manage_guild)
        if interaction.user.id not in host_ids and not can_manage:
            await interaction.response.send_message(
                embed=Embed.notice(
                    "Kun undervisere kan nævne de tilmeldte.",
                    title="Adgang nægtet",
                    color="red",
                ),
                ephemeral=True,
            )
            return
        if not signup_ids:
            await interaction.response.send_message(
                embed=Embed.notice(
                    "Ingen har tilmeldt sig endnu.", title="Ingen tilmeldte", color="yellow"
                ),
                ephemeral=True,
            )
            return

        # Mentions must be in content to actually ping.
        mentions = " ".join(f"<@{uid}>" for uid in signup_ids)
        await interaction.response.send_message(
            content=f"{interaction.user.mention} nævnte alle tilmeldte:\n{mentions}"
        )
