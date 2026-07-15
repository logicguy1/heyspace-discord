"""Interaction UI for courses, split one view (plus its own sub-components) per module.

The raised-hand and info buttons are persistent `DynamicItem`s — their `custom_id`
encodes the course id, so they keep working after a restart without loading every
course into memory. They're registered in the cog's `setup` (see the package
`__init__` one level up).
"""

from .info import InfoButton, course_message_view, thread_controls_view
from .mention import MentionSignupsButton
from .signup import RaisedHandButton

__all__ = [
    "InfoButton",
    "MentionSignupsButton",
    "RaisedHandButton",
    "course_message_view",
    "thread_controls_view",
]
