from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

import discord
from discord import app_commands

from monkebot.core.auth import Authorizer
from monkebot.core.formatting import (
    format_bytes,
    format_log_lines,
    format_timestamp,
    make_embed,
    player_event_text,
    safe_inline,
    status_text,
)
from monkebot.games.base import GameAdapter


LOGGER = logging.getLogger(__name__)


class CommandRegistrar:
    def __init__(self, tree: app_commands.CommandTree, authorizer: Authorizer, adapters: dict[str, GameAdapter]) -> None:
        self.tree = tree
        self.authorizer = authorizer
        self.adapters = adapters

    async def _guard(self, interaction: discord.Interaction) -> bool:
        return await self.authorizer.require(interaction)

    async def _defer(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)

    async def _send(
        self,
        interaction: discord.Interaction,
        adapter: GameAdapter,
        message: str,
        color: int = 0x5865F2,
    ) -> None:
        await interaction.followup.send(
            embed=make_embed(f"MonkeHost | {adapter.display_name}", message, color),
            ephemeral=False,
        )

    async def _send_error(self, interaction: discord.Interaction, exc: Exception) -> None:
        LOGGER.warning("Command failed: %s", exc)
        error = safe_inline(exc, max_length=500)
        await interaction.followup.send(
            embed=make_embed("MonkeHost", f"Command failed: `{error}`", 0xED4245),
            ephemeral=False,
        )

    async def _wait_online(self, adapter: GameAdapter) -> dict[str, Any]:
        data = await adapter.status()
        for _ in range(12):
            if data.get("active") and (data.get("join_code") or adapter.key != "valheim"):
                return data
            await asyncio.sleep(3)
            data = await adapter.status()
        return data

    def _add(self, adapter: GameAdapter, suffix: str, description: str, callback: Callable[..., Any]) -> None:
        self.tree.add_command(
            app_commands.Command(
                name=f"{adapter.command_prefix}-{suffix}",
                description=description,
                callback=callback,
            )
        )

    def _register_start(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            try:
                before = await adapter.status()
                if before.get("active"):
                    await self._send(interaction, adapter, f"Server is already online.\n\n{status_text(before, adapter.display_name)}", 0x57F287)
                    return
                await adapter.start()
                data = await self._wait_online(adapter)
                await self._send(interaction, adapter, f"Server started.\n\n{status_text(data, adapter.display_name)}", 0x57F287)
            except Exception as exc:
                await self._send_error(interaction, exc)

        self._add(adapter, "start", f"Start {adapter.display_name} server", callback)

    def _register_stop(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction, confirm: bool = False) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            try:
                data = await adapter.status()
                if not data.get("active"):
                    await self._send(interaction, adapter, "Server is already offline.", 0xFEE75C)
                    return
                players = int(data.get("player_count", 0) or 0)
                if players > 0 and not confirm:
                    await self._send(interaction, adapter, f"There are `{players}` players online. Run the command with `confirm:true` if you are sure.", 0xFEE75C)
                    return
                await adapter.stop()
                await self._send(interaction, adapter, "Server stopped gracefully. All players were disconnected.", 0xFEE75C)
            except Exception as exc:
                await self._send_error(interaction, exc)

        callback = app_commands.describe(confirm="Set to true to stop the server while players are online")(callback)
        self._add(adapter, "stop", f"Stop {adapter.display_name} server gracefully", callback)

    def _register_restart(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction, confirm: bool = False) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            try:
                data = await adapter.status()
                players = int(data.get("player_count", 0) or 0)
                if players > 0 and not confirm:
                    await self._send(interaction, adapter, f"There are `{players}` players online. Run the command with `confirm:true` if you are sure.", 0xFEE75C)
                    return
                await adapter.restart()
                data = await self._wait_online(adapter)
                await self._send(interaction, adapter, f"Server restarted successfully.\n\n{status_text(data, adapter.display_name)}", 0x57F287)
            except Exception as exc:
                await self._send_error(interaction, exc)

        callback = app_commands.describe(confirm="Set to true to restart the server while players are online")(callback)
        self._add(adapter, "restart", f"Restart server {adapter.display_name}", callback)

    def _register_update(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction, confirm: bool = False) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            if not confirm:
                await self._send(interaction, adapter, "The update will stop the server. Use `confirm:true`.", 0xFEE75C)
                return
            try:
                data = await adapter.status()
                if int(data.get("player_count", 0) or 0) > 0:
                    await self._send(interaction, adapter, "Players are still online. Stop them before updating.", 0xFEE75C)
                    return
                data = await adapter.update()
                await self._send(interaction, adapter, f"Server update completed.\n\n{status_text(data, adapter.display_name)}", 0x57F287)
            except Exception as exc:
                await self._send_error(interaction, exc)

        callback = app_commands.describe(confirm="Must be true because the update stops the server")(callback)
        self._add(adapter, "update", f"Update {adapter.display_name}", callback)

    def _register_status(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            try:
                data = await adapter.status()
                try:
                    backup = await adapter.backup_status()
                    backup_text = (
                        f"**Backup files:** `{backup.get('count') or 0}`\n"
                        f"**Latest backup:** `{safe_inline(backup.get('latest'), max_length=200)}`"
                    )
                except Exception:
                    backup_text = "**Backup:** `Not available`"
                await self._send(
                    interaction,
                    adapter,
                    f"{status_text(data, adapter.display_name)}\n\n{backup_text}",
                    0x57F287 if data.get("active") else 0xED4245,
                )
            except Exception as exc:
                await self._send_error(interaction, exc)

        self._add(adapter, "status", f"Show {adapter.display_name} server status", callback)

    def _register_players(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            try:
                data = await adapter.status()
                source = data.get("player_count_source", "unknown")
                source_text = {
                    "connections_heartbeat": "server connection heartbeat",
                    "player_event": "latest join/leave event",
                }.get(source, "Not available")
                events = [event for event in data.get("player_events") or [] if event.get("name")]
                event_lines = []
                for event in reversed(events):
                    event_lines.append(f"`{format_timestamp(event.get('timestamp'))}` | {player_event_text(event)}")
                recent_events = "\n".join(event_lines) or "No recent connection activity."
                player_count = data.get("player_count") or 0
                player_word = "player" if player_count == 1 else "players"
                player_names = data.get("player_names") or []
                if player_names:
                    names_text = "\n".join(
                        f"- `{safe_inline(name, max_length=100)}`" for name in player_names
                    )
                elif player_count:
                    names_text = "Player names are not available."
                else:
                    names_text = "No players online."
                await self._send(
                    interaction,
                    adapter,
                    f"**Online players**\n`{player_count}` {player_word}\n{names_text}\n\n"
                    f"**Data source**\n{source_text}\n\n"
                    f"**Last updated**\n`{format_timestamp(data.get('player_count_at'))}`\n\n"
                    f"**Recent activity**\n{recent_events}",
                )
            except Exception as exc:
                await self._send_error(interaction, exc)

        self._add(adapter, "players", f"Show {adapter.display_name} players", callback)

    def _register_join(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            try:
                data = await adapter.status()
                lines = [f"**Server:** `{safe_inline(data.get('server_name'), adapter.display_name, 100)}`"]
                lines.append(f"**Join code:** `{safe_inline(data.get('join_code'), max_length=100)}`")
                address = f"{data['public_ip']}:{data.get('port', 0)}" if data.get("public_ip") else None
                lines.append(f"**IP:** `{safe_inline(address, max_length=100)}`")
                lines.append("Password is not displayed by the bot.")
                await self._send(interaction, adapter, "\n".join(lines))
            except Exception as exc:
                await self._send_error(interaction, exc)

        self._add(adapter, "join", f"Show how to join {adapter.display_name}", callback)

    def _register_backup(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            try:
                data = await adapter.backup()
                await self._send(
                    interaction,
                    adapter,
                    f"**Backup completed**\n"
                    f"**Latest backup:** `{safe_inline(data.get('latest'), max_length=200)}`\n"
                    f"**Total files:** `{data.get('count') or 0}`",
                    0x57F287,
                )
            except Exception as exc:
                await self._send_error(interaction, exc)

        self._add(adapter, "backup", f"Run {adapter.display_name} backup", callback)

    def _register_backup_status(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            try:
                data = await adapter.backup_status()
                timer = "Active" if data.get("timer_active") else "Inactive"
                files = "\n".join(
                    f"- `{safe_inline(item, max_length=100)}`" for item in data.get("files") or []
                ) or "No backups yet."
                await self._send(
                    interaction,
                    adapter,
                    f"**Backup timer:** `{timer}`\n"
                    f"**Total files:** `{data.get('count') or 0}`\n"
                    f"**Latest backup:** `{safe_inline(data.get('latest'), max_length=200)}`\n\n"
                    f"**Recent backups**\n{files}",
                )
            except Exception as exc:
                await self._send_error(interaction, exc)

        self._add(adapter, "backup-status", f"Show {adapter.display_name} backups", callback)

    def _register_restore(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction, confirm: bool = False) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            was_active = False
            try:
                before = await adapter.status()
                was_active = bool(before.get("active"))
                players = int(before.get("player_count", 0) or 0)
                if was_active and (players > 0 or not confirm):
                    reason = f"There are `{players}` players online." if players > 0 else "Server is online."
                    await self._send(interaction, adapter, f"{reason} Use `confirm:true` if you are sure.", 0xFEE75C)
                    return
                if was_active:
                    await adapter.stop()
                restored = await adapter.restore()
                if was_active:
                    await adapter.start()
                    state = "Server brought back online."
                else:
                    state = "Server remains offline."
                await self._send(
                    interaction,
                    adapter,
                    f"**Restore completed**\n"
                    f"**Backup:** `{safe_inline(restored.get('restored'), max_length=200)}`\n"
                    f"**Server:** {state}",
                    0x57F287,
                )
            except Exception as exc:
                if was_active:
                    try:
                        await adapter.start()
                    except Exception:
                        LOGGER.exception("Could not restart %s after restore failure", adapter.key)
                await self._send_error(interaction, exc)

        callback = app_commands.describe(confirm="Must be true because restore may stop the server")(callback)
        self._add(adapter, "restore", f"Restore the latest {adapter.display_name} backup", callback)

    def _register_health(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            try:
                data = await adapter.health()
                await self._send(
                    interaction,
                    adapter,
                    f"**Disk usage:** `{format_bytes(data['disk_used'])}` / `{format_bytes(data['disk_total'])}`\n"
                    f"**Disk free:** `{format_bytes(data['disk_free'])}`\n"
                    f"**Memory available:** `{format_bytes(data['memory_available'])}` / `{format_bytes(data['memory_total'])}`\n"
                    f"**Load (1m):** `{data['load_1m']:.2f}`\n\n{status_text(data['server'], adapter.display_name)}",
                )
            except Exception as exc:
                await self._send_error(interaction, exc)

        self._add(adapter, "health", f"Show {adapter.display_name} health", callback)

    def _register_logs(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction, lines: app_commands.Range[int, 5, 50] = 20) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            try:
                data = await adapter.logs(int(lines))
                text = format_log_lines(data.get("lines") or [])
                await self._send(interaction, adapter, f"```text\n{text or 'No logs.'}\n```")
            except Exception as exc:
                await self._send_error(interaction, exc)

        callback = app_commands.describe(lines="Number of log lines, between 5 and 50")(callback)
        self._add(adapter, "logs", f"Show {adapter.display_name} logs", callback)

    def _register_help(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            prefix = adapter.command_prefix
            commands = [
                f"- `/{prefix}-status` server status and backups",
                f"- `/{prefix}-start` and `/{prefix}-stop` server controls",
                f"- `/{prefix}-restart confirm:true` restart the server",
                f"- `/{prefix}-update confirm:true` update the server",
                f"- `/{prefix}-players` recent players",
                f"- `/{prefix}-join` connection information",
                f"- `/{prefix}-backup` create a backup now",
                f"- `/{prefix}-backup-status` backup history",
                f"- `/{prefix}-restore confirm:true` restore the latest backup",
                f"- `/{prefix}-health` host health",
                f"- `/{prefix}-logs` latest logs",
            ]
            await self._send(interaction, adapter, "\n".join(commands))

        self._add(adapter, "help", f"List {adapter.display_name} commands", callback)

    def register(self) -> None:
        for adapter in self.adapters.values():
            self._register_start(adapter)
            self._register_stop(adapter)
            self._register_restart(adapter)
            self._register_update(adapter)
            self._register_status(adapter)
            self._register_players(adapter)
            self._register_join(adapter)
            self._register_backup(adapter)
            self._register_backup_status(adapter)
            self._register_restore(adapter)
            self._register_health(adapter)
            self._register_logs(adapter)
            self._register_help(adapter)
