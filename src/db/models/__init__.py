"""Import every model here so `Base.metadata` is fully populated for Alembic."""

from src.db.models.course import (
    Course,
    CourseHost,
    CourseRun,
    CourseRunAttendee,
    CourseSignup,
)
from src.db.models.emoji import EmojiSuggestion
from src.db.models.guild import GuildConfig

__all__ = [
    "Course",
    "CourseHost",
    "CourseRun",
    "CourseRunAttendee",
    "CourseSignup",
    "EmojiSuggestion",
    "GuildConfig",
]
