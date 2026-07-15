"""Course rendering + data helpers shared by the command layer and the UI.

Kept in its own module so the commands (`__init__`) and the interaction UI
(`views`) reuse the same rendering without depending on each other.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import discord
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.models.course import Course
from src.lib.embed import Embed

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.bot import HeySpaceBot

# Static brand bar shown as every course embed's main image. Referenced via
# attachment:// so it never expires — it must be attached to the course message.
_ASSETS_DIR = Path(__file__).resolve().parents[3] / "assets"
EMBED_BAR_FILENAME = "embed-bar.png"


def embed_bar_file() -> discord.File:
    """Fresh File handle for the brand bar; include it whenever (re)setting attachments."""
    return discord.File(_ASSETS_DIR / EMBED_BAR_FILENAME, filename=EMBED_BAR_FILENAME)


# Discord caps an embed field value at 1024 chars; leave room for the "+N more" tail.
_MENTIONS_BUDGET = 900


def render_mentions(user_ids: list[int], empty: str) -> str:
    """Render user ids as mentions, truncating with a "+N more" tail if too long."""
    if not user_ids:
        return empty
    full = " ".join(f"<@{uid}>" for uid in user_ids)
    if len(full) <= _MENTIONS_BUDGET:
        return full
    kept: list[int] = []
    total = 0
    for uid in user_ids:
        chunk = f"<@{uid}> "
        if total + len(chunk) > _MENTIONS_BUDGET:
            break
        kept.append(uid)
        total += len(chunk)
    remaining = len(user_ids) - len(kept)
    return " ".join(f"<@{uid}>" for uid in kept) + f" … +{remaining} more"


def last_run_date(course: Course) -> str | None:
    """Most recent finished run as a Discord long-date timestamp, or None if never held."""
    finished = [run for run in course.runs if run.ended_at is not None]
    if not finished:
        return None
    latest = max(finished, key=lambda run: run.ended_at)
    return discord.utils.format_dt(latest.ended_at, style="D")


def build_course_embed(course: Course) -> Embed:
    """Branded embed showing the course, its hosts and the interested members."""
    host_ids = [h.user_id for h in course.hosts]
    signup_ids = [s.user_id for s in course.signups]
    description = course.description
    if course.thread_url is not None:
        description += f"\n\n[💬 Gå til kursustråden]({course.thread_url})"
    embed = Embed(title=course.name, description=description)
    embed.set_image(url=f"attachment://{EMBED_BAR_FILENAME}")
    if course.thumbnail_url:
        embed.set_thumbnail(url=course.thumbnail_url)
    embed.add_field(
        name="Undervisere", value=render_mentions(host_ids, "*Ingen*"), inline=True
    )
    held = last_run_date(course)
    if held is not None:
        # Inline + adjacent to Undervisere so the two sit on the same row.
        embed.add_field(name="Sidst afholdt", value=held, inline=True)
    embed.add_field(
        name=f"Interesserede ({len(signup_ids)})",
        value=render_mentions(signup_ids, "*Ingen endnu*"),
        inline=False,
    )
    return embed


async def load_course(session: "AsyncSession", course_id: int) -> Course | None:
    """Load a course with its hosts, signups + runs eagerly (safe for async rendering)."""
    stmt = (
        select(Course)
        .where(Course.id == course_id)
        .options(
            selectinload(Course.hosts),
            selectinload(Course.signups),
            selectinload(Course.runs),
        )
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def refresh_course_message(client: "HeySpaceBot", course_id: int) -> None:
    """Re-render and edit the public admin message to match current DB state."""
    async with client.db.session() as session:
        course = await load_course(session, course_id)
        if course is None or course.message_id is None:
            return
        embed = build_course_embed(course)
        channel_id = course.channel_id
        message_id = course.message_id

    channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
    await channel.get_partial_message(message_id).edit(embed=embed)
