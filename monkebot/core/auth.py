from __future__ import annotations

from typing import Any

import discord


class Authorizer:
    def __init__(self, guild_id: int, operator_role_ids: frozenset[int]) -> None:
        self.guild_id = guild_id
        self.operator_role_ids = operator_role_ids

    def _in_configured_guild(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild_id or (self.guild_id and interaction.guild_id != self.guild_id):
            return False
        return True

    @staticmethod
    def _has_role(interaction: discord.Interaction, role_ids: frozenset[int]) -> bool:
        roles: Any = getattr(interaction.user, "roles", [])
        return any(role.id in role_ids for role in roles)

    def is_member(self, interaction: discord.Interaction) -> bool:
        return self._in_configured_guild(interaction)

    def can_operate(self, interaction: discord.Interaction) -> bool:
        return self._in_configured_guild(interaction) and self._has_role(interaction, self.operator_role_ids)

    async def require_member(self, interaction: discord.Interaction) -> bool:
        if self.is_member(interaction):
            return True
        await interaction.response.send_message("This bot is only available in its configured Discord server.")
        return False

    async def require_operator(self, interaction: discord.Interaction) -> bool:
        if self.can_operate(interaction):
            return True
        await interaction.response.send_message("This command requires the `Monke Operator` role.")
        return False
