"""Course models: a course plus its hosts, interested members and past runs.

A course owns one self-updating admin message in the configured courses channel.
`CourseHost` rows are the people running it (fixed at registration); `CourseSignup`
rows are the members who raised a hand to signal interest. `CourseRun` records a
time the course was actually held, with `CourseRunAttendee` rows for who attended
(checked off from the interested list when the run happened).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class Course(Base):
    __tablename__ = "course"

    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text)
    # Optional image shown as the course embed's thumbnail (http/https URL).
    thumbnail_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Channel the admin message lives in, and the message id (set after posting).
    channel_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    hosts: Mapped[list["CourseHost"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    signups: Mapped[list["CourseSignup"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    runs: Mapped[list["CourseRun"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )

    @property
    def jump_url(self) -> str | None:
        """Link to the course's admin message, or None before it has been posted."""
        if self.message_id is None:
            return None
        return (
            f"https://discord.com/channels/{self.guild_id}/{self.channel_id}/{self.message_id}"
        )

    @property
    def mention(self) -> str:
        """The course name as a hyperlink to its message; bold fallback if unposted."""
        url = self.jump_url
        return f"[{self.name}]({url})" if url is not None else f"**{self.name}**"

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Course id={self.id} name={self.name!r}>"


class CourseHost(Base):
    __tablename__ = "course_host"
    __table_args__ = (UniqueConstraint("course_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("course.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger)

    course: Mapped[Course] = relationship(back_populates="hosts")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<CourseHost course_id={self.course_id} user_id={self.user_id}>"


class CourseSignup(Base):
    __tablename__ = "course_signup"
    __table_args__ = (UniqueConstraint("course_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("course.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    course: Mapped[Course] = relationship(back_populates="signups")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<CourseSignup course_id={self.course_id} user_id={self.user_id}>"


class CourseRun(Base):
    __tablename__ = "course_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("course.id", ondelete="CASCADE"))
    host_id: Mapped[int] = mapped_column(BigInteger)  # who ran this session
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Null while the run is in progress; set when the host presses "Afslut".
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    course: Mapped[Course] = relationship(back_populates="runs")
    attendees: Mapped[list["CourseRunAttendee"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<CourseRun id={self.id} course_id={self.course_id} ended={self.ended_at}>"


class CourseRunAttendee(Base):
    __tablename__ = "course_run_attendee"
    __table_args__ = (UniqueConstraint("run_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("course_run.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger)

    run: Mapped[CourseRun] = relationship(back_populates="attendees")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<CourseRunAttendee run_id={self.run_id} user_id={self.user_id}>"
