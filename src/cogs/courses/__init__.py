"""Makerspace course registration + interest tracking.

A moderator registers a course with `/opret_kursus`; the bot posts a self-updating
admin message (title, description, hosts, interested headcount) in the preconfigured
courses channel. Members raise a hand on that message to signal interest, confirming
or removing their signup through an ephemeral prompt.

This cog is fully self-contained: the command layer lives here, rendering + data
helpers in `service`, and the interaction UI in `views`. Persistent buttons are
registered in `setup`/`teardown` so they survive restarts and reloads cleanly.
"""

from __future__ import annotations

import discord
from discord import app_commands
from sqlalchemy import func, select

from src.db.models.course import Course, CourseHost, CourseSignup
from src.db.models.guild import GuildConfig
from src.lib.cog import BaseCog
from src.lib.embed import Embed

from .service import build_course_embed, embed_bar_file, refresh_course_message
from .views import (
    InfoButton,
    MentionSignupsButton,
    RaisedHandButton,
    course_message_view,
    thread_controls_view,
)


class Courses(BaseCog):
    @app_commands.command(
        name="kursuskanal",
        description="Sæt kanalen hvor kursusbeskeder sendes.",
    )
    @app_commands.describe(channel="Kanal hvor kursusbeskeder sendes.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_course_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        guild_id = self.bot.settings.guild_id
        async with self.session() as session:
            cfg = await session.get(GuildConfig, guild_id)
            if cfg is None:
                cfg = GuildConfig(guild_id=guild_id)
                session.add(cfg)
            cfg.courses_channel_id = channel.id
            await session.commit()
        await interaction.response.send_message(
            embed=Embed.notice(
                f"Nye kurser bliver nu offentliggjort i {channel.mention}.",
                title="Kursuskanal opdateret",
                color="green",
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="opret_kursus", description="Opret et nyt makerspace-kursus."
    )
    @app_commands.describe(
        name="Kursustitel.",
        description="Hvad kurset handler om.",
        host="Primær underviser.",
        host2="Ekstra underviser (valgfri).",
        host3="Ekstra underviser (valgfri).",
        host4="Ekstra underviser (valgfri).",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def register_course(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str,
        host: discord.Member,
        host2: discord.Member | None = None,
        host3: discord.Member | None = None,
        host4: discord.Member | None = None,
    ) -> None:
        guild_id = self.bot.settings.guild_id
        async with self.session() as session:
            cfg = await session.get(GuildConfig, guild_id)
            channel_id = cfg.courses_channel_id if cfg else None
        if channel_id is None:
            await interaction.response.send_message(
                embed=Embed.notice(
                    "Der er ikke valgt en kursuskanal endnu. Brug `/kursuskanal` for at "
                    "vælge, hvor kurser skal offentliggøres.",
                    title="Ingen kursuskanal valgt",
                    color="yellow",
                ),
                ephemeral=True,
            )
            return

        channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)

        # Dedup hosts, preserving the order they were given.
        host_ids: list[int] = []
        for member in (host, host2, host3, host4):
            if member is not None and member.id not in host_ids:
                host_ids.append(member.id)

        async with self.session() as session:
            course = Course(
                guild_id=guild_id,
                name=name,
                description=description,
                channel_id=channel_id,
                created_by=interaction.user.id,
            )
            course.hosts = [CourseHost(user_id=uid) for uid in host_ids]
            # Explicit so the collections are loaded for rendering (no lazy load).
            course.signups = []
            course.runs = []
            session.add(course)
            await session.commit()
            course_id = course.id
            embed = build_course_embed(course)

        message = await channel.send(
            embed=embed, view=course_message_view(course_id), files=[embed_bar_file()]
        )
        thread = await message.create_thread(name=name[:100], auto_archive_duration=10080)

        async with self.session() as session:
            saved = await session.get(Course, course_id)
            saved.message_id = message.id
            saved.thread_id = thread.id
            await session.commit()
            course_mention = saved.mention

        # Re-render so the embed picks up the thread link now that it exists.
        await refresh_course_message(self.bot, course_id)

        # The starter message's buttons render disabled inside the thread, so post a
        # separate controls message there. Same persistent view, keyed by course id.
        await thread.send(
            embed=Embed.notice(
                f"Brug knapperne herunder til at tilmelde dig eller administrere "
                f"{course_mention}.",
                title="Kursusstyring",
                color="green",
            ),
            view=thread_controls_view(course_id),
        )

        await interaction.response.send_message(
            embed=Embed.notice(
                f"Kurset {course_mention} er oprettet og offentliggjort i {channel.mention}.",
                title="Kursus oprettet",
                color="green",
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="find_kursus", description="Søg efter kurser på navn."
    )
    @app_commands.describe(query="Tekst der matches mod kursusnavne.")
    async def search_course(self, interaction: discord.Interaction, query: str) -> None:
        guild_id = self.bot.settings.guild_id
        async with self.session() as session:
            stmt = (
                select(Course, func.count(CourseSignup.id))
                .outerjoin(CourseSignup, CourseSignup.course_id == Course.id)
                .where(Course.guild_id == guild_id, Course.name.ilike(f"%{query}%"))
                .group_by(Course.id)
                .order_by(Course.created_at.desc())
                .limit(10)
            )
            rows = list((await session.execute(stmt)).all())

        if not rows:
            await interaction.response.send_message(
                embed=Embed.notice(
                    f"Ingen kurser matcher **{query}**.",
                    title="Ingen resultater",
                    color="yellow",
                ),
                ephemeral=True,
            )
            return

        lines = [
            f"{course.mention} — {interested} interesserede" for course, interested in rows
        ]

        embed = self.embed(
            title=f"Kurser der matcher “{query}”", description="\n".join(lines)
        )
        embed.set_color("blue")
        await interaction.response.send_message(embed=embed, ephemeral=False)


async def setup(bot) -> None:
    # Persistent buttons must be registered so they keep routing across restarts;
    # their custom_id carries the course id, so no per-course state is needed.
    bot.add_dynamic_items(RaisedHandButton, InfoButton, MentionSignupsButton)
    await bot.add_cog(Courses(bot))


async def teardown(bot) -> None:
    # Runs before a reload re-invokes setup, so the dynamic items are cleanly
    # re-registered instead of duplicated.
    bot.remove_dynamic_items(RaisedHandButton, InfoButton, MentionSignupsButton)
