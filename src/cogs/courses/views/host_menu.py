"""Ephemeral management menu shown from the info button."""

from __future__ import annotations

import discord

from .edit_course import EditCourseButton
from .edit_hosts import EditHostsButton
from .edit_image import EditImageButton
from .run_session import RunCourseButton


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
