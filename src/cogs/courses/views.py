"""Interaction UI for courses: the persistent buttons and their prompts.

The raised-hand and info buttons are persistent `DynamicItem`s — their
`custom_id` encodes the course id, so they keep working after a restart without
loading every course into memory. They're registered in the cog's `setup`
(see this package's `__init__`).
"""

from __future__ import annotations

import asyncio
import io
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import discord
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from src.db.models.course import Course, CourseHost, CourseRun, CourseRunAttendee, CourseSignup
from src.db.models.guild import GuildConfig
from src.lib.embed import Embed

from .service import build_course_embed, embed_bar_file, load_course, refresh_course_message

if TYPE_CHECKING:
    from src.bot import HeySpaceBot

# How long the bot waits for a user to upload a thumbnail image, in seconds.
_IMAGE_UPLOAD_TIMEOUT = 120


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


class HostMenuView(discord.ui.View):
    """Ephemeral management menu shown from the info button.

    Buttons are gated per user: only hosts can start an afholdelse, while hosts and
    members with Manage Server can edit the course details, hosts and image.
    """

    def __init__(self, course_id: int, *, is_host: bool, can_manage: bool) -> None:
        super().__init__(timeout=180)
        self.course_id = course_id
        if is_host:
            self.add_item(RunCourseButton(course_id))
        if is_host or can_manage:
            self.add_item(EditCourseButton(course_id))
            self.add_item(EditHostsButton(course_id))
            self.add_item(EditImageButton(course_id))


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
            "\n".join(f"• {d.strftime('%d/%m/%Y')}" for d in dates)
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
