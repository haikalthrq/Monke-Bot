from __future__ import annotations

from typing import Any

import discord


class Authorizer:
    def __init__(self, guild_id: int, user_ids: frozenset[int], role_ids: frozenset[int]) -> None:
        self.guild_id = guild_id
        self.user_ids = user_ids
        self.role_ids = role_ids

    def allowed(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild_id or (self.guild_id and interaction.guild_id != self.guild_id):
            return False
        if interaction.user.id in self.user_ids:
            return True
        roles: Any = getattr(interaction.user, "roles", [])
        return any(role.id in self.role_ids for role in roles)

    async def require(self, interaction: discord.Interaction) -> bool:
        if self.allowed(interaction):
            return True
        await interaction.response.send_message("Kamu tidak punya akses ke bot ini.", ephemeral=True)
        return False
