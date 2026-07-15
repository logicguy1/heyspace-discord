"""General-purpose commands."""

from __future__ import annotations

import discord
from discord import app_commands

from src.lib.cog import BaseCog


class General(BaseCog):
    @app_commands.command(name="ping", description="Tjek bottens svartid.")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency_ms = round(self.bot.latency * 1000)
        embed = self.embed(title="🏓 Pong!", description=f"Svartid: **{latency_ms} ms**")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="genindlaes", description="Genindlæs cogs og synkronisér kommandoer."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reload(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await self.bot.reload_cogs()
        guild = self.bot.guild_object
        self.bot.tree.copy_global_to(guild=guild)
        synced = await self.bot.tree.sync(guild=guild)
        embed = self.embed(
            title="Genindlæsning fuldført",
            description=f"Cogs blev genindlæst og **{len(synced)}** kommando(er) synkroniseret.",
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot) -> None:
    await bot.add_cog(General(bot))
