"""Running a course: the host-only run button, the in-progress session and its controls."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from src.db.models.course import CourseRun, CourseRunAttendee, CourseSignup
from src.lib.embed import Embed

from ..service import load_course, refresh_course_message

if TYPE_CHECKING:
    from src.bot import HeySpaceBot


async def _resolve_names(guild: discord.Guild | None, user_ids: list[int]) -> dict[int, str]:
    """Map user ids to display names for select labels.

    Default intents don't cache the member list, so fall back to a REST fetch when
    a member isn't in cache — that yields the server nickname / display name.
    """
    names: dict[int, str] = {}
    for uid in user_ids:
        member = guild.get_member(uid) if guild is not None else None
        if member is None and guild is not None:
            try:
                member = await guild.fetch_member(uid)
            except discord.HTTPException:
                member = None
        names[uid] = member.display_name if member is not None else f"Bruger {uid}"
    return names


class AttendeeSelect(discord.ui.Select):
    """Pick one interested member to check off as having attended the run."""

    def __init__(self, remaining: list[int], names: dict[int, str]) -> None:
        options = [
            discord.SelectOption(label=names.get(uid, str(uid))[:100], value=str(uid))
            for uid in remaining[:25]  # Discord caps a select at 25 options
        ]
        super().__init__(
            placeholder="Vælg en deltager der var med", min_values=1, max_values=1, options=options
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: "RunSessionView" = self.view  # type: ignore[assignment]
        await view.mark_attended(interaction, int(self.values[0]))


class FinishRunButton(discord.ui.Button):
    """Finish the run: stamp its end date and stop collecting attendees."""

    def __init__(self) -> None:
        super().__init__(label="Afslut", emoji="🏁", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: "RunSessionView" = self.view  # type: ignore[assignment]
        await view.finish(interaction)


class RunSessionView(discord.ui.View):
    """Ephemeral, host-only run in progress: check off attendees, then finish."""

    def __init__(
        self, course_id: int, run_id: int, remaining: list[int], names: dict[int, str]
    ) -> None:
        super().__init__(timeout=600)
        self.course_id = course_id
        self.run_id = run_id
        self.remaining = remaining
        self.names = names
        self.attended = 0
        self._build()

    def _build(self) -> None:
        self.clear_items()
        if self.remaining:
            self.add_item(AttendeeSelect(self.remaining, self.names))
        self.add_item(FinishRunButton())

    def build_embed(self) -> Embed:
        if self.remaining:
            description = (
                "Vælg de deltagere der mødte op — de flyttes fra interesserede til "
                "fremmødte. Tryk **Afslut**, når alle er registreret."
            )
        else:
            description = "Alle interesserede er registreret som fremmødte. Tryk **Afslut**."
        embed = Embed.notice(
            description, title=f"Igangværende afholdelse · {self.attended} fremmødte", color="blue"
        )
        return embed

    async def mark_attended(self, interaction: discord.Interaction, user_id: int) -> None:
        client: "HeySpaceBot" = interaction.client  # type: ignore[assignment]
        async with client.db.session() as session:
            await session.execute(
                delete(CourseSignup).where(
                    CourseSignup.course_id == self.course_id,
                    CourseSignup.user_id == user_id,
                )
            )
            session.add(CourseRunAttendee(run_id=self.run_id, user_id=user_id))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
        await refresh_course_message(client, self.course_id)
        self.remaining = [uid for uid in self.remaining if uid != user_id]
        self.attended += 1
        self._build()
        await interaction.response.edit_message(content=None, embed=self.build_embed(), view=self)

    async def finish(self, interaction: discord.Interaction) -> None:
        client: "HeySpaceBot" = interaction.client  # type: ignore[assignment]
        async with client.db.session() as session:
            run = await session.get(CourseRun, self.run_id)
            if run is not None and run.ended_at is None:
                run.ended_at = datetime.now(timezone.utc)
                await session.commit()
        await refresh_course_message(client, self.course_id)
        embed = Embed.notice(
            f"Afholdelsen er afsluttet med **{self.attended}** fremmødte.",
            title="Afholdelse afsluttet",
            color="green",
        )
        await interaction.response.edit_message(content=None, embed=embed, view=None)
        self.stop()


class RunCourseButton(discord.ui.Button):
    """Start a new afholdelse for the course's interested members."""

    def __init__(self, course_id: int) -> None:
        super().__init__(label="Afhold kursus", emoji="▶️", style=discord.ButtonStyle.primary)
        self.course_id = course_id

    async def callback(self, interaction: discord.Interaction) -> None:
        client: "HeySpaceBot" = interaction.client  # type: ignore[assignment]
        async with client.db.session() as session:
            course = await load_course(session, self.course_id)
            if course is None:
                await interaction.response.edit_message(
                    content=None,
                    embed=Embed.notice(
                        "Kurset findes ikke længere.", title="Kurset er væk", color="red"
                    ),
                    view=None,
                )
                return
            interested = [s.user_id for s in course.signups]
            if not interested:
                await interaction.response.edit_message(
                    content=None,
                    embed=Embed.notice(
                        "Der er endnu ingen interesserede at afholde kurset for.",
                        title="Ingen interesserede",
                        color="yellow",
                    ),
                    view=None,
                )
                return
            run = CourseRun(course_id=self.course_id, host_id=interaction.user.id)
            session.add(run)
            await session.commit()
            run_id = run.id

        names = await _resolve_names(interaction.guild, interested)
        view = RunSessionView(self.course_id, run_id, interested, names)
        await interaction.response.edit_message(content=None, embed=view.build_embed(), view=view)
