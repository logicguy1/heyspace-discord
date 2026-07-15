"""Added course runs

Revision ID: a1b2c3d4e5f6
Revises: 66bdccf72cde
Create Date: 2026-07-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '66bdccf72cde'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('course_run',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('course_id', sa.Integer(), nullable=False),
    sa.Column('host_id', sa.BigInteger(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['course_id'], ['course.id'], name=op.f('fk_course_run_course_id_course'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_course_run'))
    )
    op.create_table('course_run_attendee',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['course_run.id'], name=op.f('fk_course_run_attendee_run_id_course_run'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_course_run_attendee')),
    sa.UniqueConstraint('run_id', 'user_id', name=op.f('uq_course_run_attendee_run_id'))
    )


def downgrade() -> None:
    op.drop_table('course_run_attendee')
    op.drop_table('course_run')
