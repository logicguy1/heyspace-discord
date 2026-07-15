"""Branded embed used across the bot.

`Embed` applies the house style on construction: a named color from the palette,
a timestamp, and a footer whose text + icon are the current server's name + icon.

The footer can't be hardcoded because it must always track the server icon, so the
bot calls `Embed.set_branding(guild)` once the guild is known (on ready); every
embed built afterwards picks up the icon from these class-level attributes.
"""

from __future__ import annotations

import datetime

import discord
from discord import Colour
from discord import Embed as DiscordEmbed

# Palette shared by every embed. Class-level so it isn't rebuilt per instance.
COLORS: dict[str, Colour] = {
    "green": Colour(0x058b8c),
    "red": Colour(0xBF3036),
    "blue": Colour(0x303F9C),
    "yellow": Colour(0xB0BA2A),
    "magenta": Colour(0xA829B0),
    "brown": Colour(0x2B1313),
    "purple": Colour(0x5300B0),
    "pink": Colour(0xFF00FC),
    "black": Colour(0x000000),
    "white": Colour(0xFFFFFF),
    "cyan": Colour(0x00FFFF),
    "grey": Colour(0x696969),  # yeah the funny number is grey
    "lightgreen": Colour(0x89F292),
    "lightred": Colour(0xFF7171),
    "lightblue": Colour(0x807BFF),
    "lightyellow": Colour(0xF7FF80),
    "lightmagenta": Colour(0xFF8DFC),
    "lightbrown": Colour(0x956767),
    "lightpurple": Colour(0xBF67FF),
    "lightpink": Colour(0xFF88DC),
    "lightcyan": Colour(0xBCFBFF),
}


class Embed(DiscordEmbed):
    """Custom implementation of a discord embed object."""

    colors = COLORS

    # Set by the bot on ready (see HeySpaceBot.set_branding); the footer always
    # reflects the current server name + icon.
    footer_text: str | None = None
    footer_icon_url: str | None = None

    def __init__(self, *args, **kwargs) -> None:
        DiscordEmbed.__init__(self, *args, **kwargs)

        self.set_footer(text=self.footer_text, icon_url=self.footer_icon_url)
        self.timestamp = datetime.datetime.now()
        self.set_color("green")

    def set_color(self, color: str) -> None:
        """Set a color from the default colorlist."""
        self.color = self.colors[color]

    @classmethod
    def notice(
        cls, description: str, *, title: str | None = None, color: str = "blue"
    ) -> "Embed":
        """Build a short feedback embed (confirmations, errors, prompts).

        `color` is a palette name — use "green" for success, "red" for errors,
        "yellow" for warnings and "blue" for neutral info.
        """
        embed = cls(title=title, description=description)
        embed.set_color(color)
        return embed

    @classmethod
    def set_branding(cls, guild: discord.Guild) -> None:
        """Point the footer branding at a guild's name + icon."""
        cls.footer_text = guild.name
        cls.footer_icon_url = guild.icon.url if guild.icon else None
