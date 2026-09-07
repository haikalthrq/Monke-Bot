from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
from typing import Any

import discord
from discord import app_commands

from monkebot.core.auth import Authorizer
from monkebot.core.formatting import (
    format_bytes,
    format_log_lines,
    make_embed,
    players_text,
    safe_inline,
    status_text,
)
from monkebot.games.base import GameAdapter


LOGGER = logging.getLogger(__name__)
Notify = Callable[[str, int], Awaitable[None]]


class ConfirmView(discord.ui.View):
    def __init__(
        self,
        authorizer: Authorizer,
        on_confirm: Callable[[discord.Interaction], Awaitable[None]],
        timeout: float = 60.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.authorizer = authorizer
        self.on_confirm = on_confirm

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.authorizer.can_operate(interaction):
            await interaction.response.send_message(
                "This command requires the `Monke Operator` role.",
                ephemeral=True,
            )
            return
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.response.edit_message(view=self)
        await self.on_confirm(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.response.edit_message(content="Action canceled.", embed=None, view=self)


class ControlPanelView(discord.ui.View):
    def __init__(
        self,
        adapter: GameAdapter,
        authorizer: Authorizer,
        on_action: Callable[[discord.Interaction, GameAdapter, str], Awaitable[None]],
        timeout: float | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.adapter = adapter
        self.authorizer = authorizer
        self.on_action = on_action

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success, emoji="▶️")
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.on_action(interaction, self.adapter, "start")

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.on_action(interaction, self.adapter, "stop")

    @discord.ui.button(label="Restart", style=discord.ButtonStyle.primary, emoji="🔄")
    async def restart_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.on_action(interaction, self.adapter, "restart")

    @discord.ui.button(label="Join Info", style=discord.ButtonStyle.secondary, emoji="📋")
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.on_action(interaction, self.adapter, "join")

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔃")
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.on_action(interaction, self.adapter, "refresh")


class CommandRegistrar:
    def __init__(
        self,
        tree: app_commands.CommandTree,
        authorizer: Authorizer,
        adapters: dict[str, GameAdapter],
        notify: Notify | None = None,
    ) -> None:
        self.tree = tree
        self.authorizer = authorizer
        self.adapters = adapters
        self.notify = notify

    async def _guard(self, interaction: discord.Interaction, operator: bool = False) -> bool:
        if operator:
            return await self.authorizer.require_operator(interaction)
        return await self.authorizer.require_member(interaction)

    async def _defer(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)

    async def _send(
        self,
        interaction: discord.Interaction,
        adapter: GameAdapter,
        message: str,
        color: int = 0x5865F2,
    ) -> None:
        is_done_fn = getattr(interaction.response, "is_done", None)
        if is_done_fn and not is_done_fn():
            await interaction.response.send_message(
                embed=make_embed(f"Monke-Bot | {adapter.display_name}", message, color),
                ephemeral=False,
            )
        else:
            await interaction.followup.send(
                embed=make_embed(f"Monke-Bot | {adapter.display_name}", message, color),
                ephemeral=False,
            )

    async def _send_error(self, interaction: discord.Interaction, exc: Exception) -> None:
        LOGGER.warning("Command failed: %s", exc)
        error = safe_inline(exc, max_length=500)
        embed = make_embed("Monke-Bot", f"Command failed: `{error}`", 0xED4245)
        is_done_fn = getattr(interaction.response, "is_done", None)
        if is_done_fn and not is_done_fn():
            await interaction.response.send_message(embed=embed, ephemeral=False)
        else:
            await interaction.followup.send(embed=embed, ephemeral=False)

    async def _audit(self, interaction: discord.Interaction, adapter: GameAdapter, action: str) -> None:
        if self.notify and interaction.user:
            user_mention = getattr(interaction.user, "mention", "Unknown operator")
            await self.notify(
                f"🛡️ **Audit:** {user_mention} executed `{action}` on **{adapter.display_name}**.",
                0x5865F2,
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

    async def _panel_embed(self, adapter: GameAdapter) -> discord.Embed:
        try:
            data = await adapter.status()
        except Exception:
            data = {"active": False}
        try:
            backup = await adapter.backup_status()
            backup_text = (
                f"**Backups:** `{backup.get('count') or 0}` | "
                f"**Latest:** `{safe_inline(backup.get('latest'), max_length=100)}`"
            )
        except Exception:
            backup_text = "**Backups:** `Not available`"
        color = 0x57F287 if data.get("active") else 0xED4245
        description = (
            f"{status_text(data, adapter.display_name)}\n\n"
            f"{backup_text}\n\n"
            "💡 *Use the buttons below to control or inspect the server.*"
        )
        return make_embed(f"Monke-Bot | {adapter.display_name} Control Panel", description, color)

    def _make_panel_view(self, adapter: GameAdapter) -> ControlPanelView:
        return ControlPanelView(
            adapter=adapter,
            authorizer=self.authorizer,
            on_action=self._handle_panel_action,
        )

    async def _handle_panel_action(self, interaction: discord.Interaction, adapter: GameAdapter, action: str) -> None:
        if action == "refresh":
            await interaction.response.defer()
            embed = await self._panel_embed(adapter)
            await interaction.edit_original_response(embed=embed, view=self._make_panel_view(adapter))
            return

        if action == "join":
            try:
                data = await adapter.status()
                lines = [f"**Server:** `{safe_inline(data.get('server_name'), adapter.display_name, 100)}`"]
                lines.append(f"**Join code:** `{safe_inline(data.get('join_code'), max_length=100)}`")
                if data.get("public_ip"):
                    address = f"{data['public_ip']}:{data.get('port', 0)}"
                    lines.append(f"**IP:** `{safe_inline(address, max_length=100)}`")
                lines.append("Password is not displayed by the bot.")
                await interaction.response.send_message("\n".join(lines), ephemeral=True)
            except Exception as exc:
                await interaction.response.send_message(f"Could not load join details: {exc}", ephemeral=True)
            return

        if not self.authorizer.can_operate(interaction):
            await interaction.response.send_message(
                "This command requires the `Monke Operator` role.",
                ephemeral=True,
            )
            return

        if action == "start":
            await interaction.response.defer()
            try:
                before = await adapter.status()
                if not before.get("active"):
                    await adapter.start()
                    await self._wait_online(adapter)
                    await self._audit(interaction, adapter, "start")
                embed = await self._panel_embed(adapter)
                await interaction.edit_original_response(embed=embed, view=self._make_panel_view(adapter))
            except Exception as exc:
                await self._send_error(interaction, exc)
            return

        if action == "stop":
            try:
                data = await adapter.status()
                if not data.get("active"):
                    await interaction.response.send_message("Server is already offline.", ephemeral=True)
                    return
                players = int(data.get("player_count", 0) or 0)
                if players > 0:
                    async def confirm_stop(btn_it: discord.Interaction) -> None:
                        await adapter.stop()
                        await self._audit(btn_it, adapter, "stop")
                        embed = await self._panel_embed(adapter)
                        await interaction.edit_original_response(embed=embed, view=self._make_panel_view(adapter))

                    view = ConfirmView(self.authorizer, confirm_stop)
                    await interaction.response.send_message(
                        f"⚠️ There are `{players}` players online. Confirm stopping the server?",
                        view=view,
                        ephemeral=True,
                    )
                    return

                await interaction.response.defer()
                await adapter.stop()
                await self._audit(interaction, adapter, "stop")
                embed = await self._panel_embed(adapter)
                await interaction.edit_original_response(embed=embed, view=self._make_panel_view(adapter))
            except Exception as exc:
                await self._send_error(interaction, exc)
            return

        if action == "restart":
            try:
                data = await adapter.status()
                players = int(data.get("player_count", 0) or 0)
                if players > 0:
                    async def confirm_restart(btn_it: discord.Interaction) -> None:
                        await adapter.restart()
                        await self._wait_online(adapter)
                        await self._audit(btn_it, adapter, "restart")
                        embed = await self._panel_embed(adapter)
                        await interaction.edit_original_response(embed=embed, view=self._make_panel_view(adapter))

                    view = ConfirmView(self.authorizer, confirm_restart)
                    await interaction.response.send_message(
                        f"⚠️ There are `{players}` players online. Confirm restarting the server?",
                        view=view,
                        ephemeral=True,
                    )
                    return

                await interaction.response.defer()
                await adapter.restart()
                await self._wait_online(adapter)
                await self._audit(interaction, adapter, "restart")
                embed = await self._panel_embed(adapter)
                await interaction.edit_original_response(embed=embed, view=self._make_panel_view(adapter))
            except Exception as exc:
                await self._send_error(interaction, exc)
            return

    def _register_panel(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            try:
                embed = await self._panel_embed(adapter)
                view = self._make_panel_view(adapter)
                await interaction.followup.send(embed=embed, view=view)
            except Exception as exc:
                await self._send_error(interaction, exc)

        self._add(adapter, "panel", f"Show interactive control panel for {adapter.display_name}", callback)

    def _register_start(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction) -> None:
            if not await self._guard(interaction, operator=True):
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
                await self._audit(interaction, adapter, "start")
            except Exception as exc:
                await self._send_error(interaction, exc)

        self._add(adapter, "start", f"Start {adapter.display_name} server", callback)

    def _register_stop(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction, confirm: bool = False) -> None:
            if not await self._guard(interaction, operator=True):
                return
            await self._defer(interaction)
            try:
                data = await adapter.status()
                if not data.get("active"):
                    await self._send(interaction, adapter, "Server is already offline.", 0xFEE75C)
                    return
                players = int(data.get("player_count", 0) or 0)
                if players > 0 and not confirm:
                    async def on_confirm(btn_it: discord.Interaction) -> None:
                        try:
                            await adapter.stop()
                            await self._send(btn_it, adapter, "Server stopped gracefully. All players were disconnected.", 0xFEE75C)
                            await self._audit(btn_it, adapter, "stop")
                        except Exception as exc:
                            await self._send_error(btn_it, exc)

                    view = ConfirmView(self.authorizer, on_confirm)
                    await interaction.followup.send(
                        embed=make_embed(
                            f"Monke-Bot | {adapter.display_name}",
                            f"⚠️ **Warning:** There are `{players}` players online.\nClick **Confirm** below to stop the server, or **Cancel**.",
                            0xFEE75C,
                        ),
                        view=view,
                    )
                    return
                await adapter.stop()
                await self._send(interaction, adapter, "Server stopped gracefully. All players were disconnected.", 0xFEE75C)
                await self._audit(interaction, adapter, "stop")
            except Exception as exc:
                await self._send_error(interaction, exc)

        callback = app_commands.describe(confirm="Set to true to stop the server while players are online")(callback)
        self._add(adapter, "stop", f"Stop {adapter.display_name} server gracefully", callback)

    def _register_restart(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction, confirm: bool = False) -> None:
            if not await self._guard(interaction, operator=True):
                return
            await self._defer(interaction)
            try:
                data = await adapter.status()
                players = int(data.get("player_count", 0) or 0)
                if players > 0 and not confirm:
                    async def on_confirm(btn_it: discord.Interaction) -> None:
                        try:
                            await adapter.restart()
                            res = await self._wait_online(adapter)
                            await self._send(btn_it, adapter, f"Server restarted successfully.\n\n{status_text(res, adapter.display_name)}", 0x57F287)
                            await self._audit(btn_it, adapter, "restart")
                        except Exception as exc:
                            await self._send_error(btn_it, exc)

                    view = ConfirmView(self.authorizer, on_confirm)
                    await interaction.followup.send(
                        embed=make_embed(
                            f"Monke-Bot | {adapter.display_name}",
                            f"⚠️ **Warning:** There are `{players}` players online.\nClick **Confirm** below to restart the server, or **Cancel**.",
                            0xFEE75C,
                        ),
                        view=view,
                    )
                    return
                await adapter.restart()
                data = await self._wait_online(adapter)
                await self._send(interaction, adapter, f"Server restarted successfully.\n\n{status_text(data, adapter.display_name)}", 0x57F287)
                await self._audit(interaction, adapter, "restart")
            except Exception as exc:
                await self._send_error(interaction, exc)

        callback = app_commands.describe(confirm="Set to true to restart the server while players are online")(callback)
        self._add(adapter, "restart", f"Restart server {adapter.display_name}", callback)

    def _register_update(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction, confirm: bool = False) -> None:
            if not await self._guard(interaction, operator=True):
                return
            await self._defer(interaction)
            if not confirm:
                async def on_confirm(btn_it: discord.Interaction) -> None:
                    try:
                        chk = await adapter.status()
                        if int(chk.get("player_count", 0) or 0) > 0:
                            await self._send(btn_it, adapter, "Players are still online. Stop them before updating.", 0xFEE75C)
                            return
                        res = await adapter.update()
                        await self._send(btn_it, adapter, f"Server update completed.\n\n{status_text(res, adapter.display_name)}", 0x57F287)
                        await self._audit(btn_it, adapter, "update")
                    except Exception as exc:
                        await self._send_error(btn_it, exc)

                view = ConfirmView(self.authorizer, on_confirm)
                await interaction.followup.send(
                    embed=make_embed(
                        f"Monke-Bot | {adapter.display_name}",
                        "⚠️ **Notice:** The update will stop the server while SteamCMD runs.\nClick **Confirm** below to proceed.",
                        0xFEE75C,
                    ),
                    view=view,
                )
                return
            try:
                data = await adapter.status()
                if int(data.get("player_count", 0) or 0) > 0:
                    await self._send(interaction, adapter, "Players are still online. Stop them before updating.", 0xFEE75C)
                    return
                data = await adapter.update()
                await self._send(interaction, adapter, f"Server update completed.\n\n{status_text(data, adapter.display_name)}", 0x57F287)
                await self._audit(interaction, adapter, "update")
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
                        f"**Backups:** `{backup.get('count') or 0}`\n"
                        f"**Latest:** `{safe_inline(backup.get('latest'), max_length=200)}`"
                    )
                except Exception:
                    backup_text = "**Backups:** `Not available`"
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
                await self._send(interaction, adapter, players_text(data))
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
                if data.get("public_ip"):
                    address = f"{data['public_ip']}:{data.get('port', 0)}"
                    lines.append(f"**IP:** `{safe_inline(address, max_length=100)}`")
                lines.append("Password is not displayed by the bot.")
                await self._send(interaction, adapter, "\n".join(lines))
            except Exception as exc:
                await self._send_error(interaction, exc)

        self._add(adapter, "join", f"Show how to join {adapter.display_name}", callback)

    def _register_backup(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction) -> None:
            if not await self._guard(interaction, operator=True):
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
                await self._audit(interaction, adapter, "backup")
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
                    f"- `{safe_inline(item, max_length=100)}`" for item in reversed((data.get("files") or [])[-5:])
                ) or "No backups yet."
                await self._send(
                    interaction,
                    adapter,
                    f"**Backup timer:** `{timer}`\n"
                    f"**Total files:** `{data.get('count') or 0}`\n\n"
                    f"**Recent backups**\n{files}",
                )
            except Exception as exc:
                await self._send_error(interaction, exc)

        self._add(adapter, "backup-status", f"Show {adapter.display_name} backups", callback)

    def _register_restore(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction, confirm: bool = False) -> None:
            if not await self._guard(interaction, operator=True):
                return
            await self._defer(interaction)
            was_active = False
            try:
                before = await adapter.status()
                was_active = bool(before.get("active"))
                players = int(before.get("player_count", 0) or 0)
                if was_active and (players > 0 or not confirm):
                    reason = f"There are `{players}` players online." if players > 0 else "Server is online."

                    async def on_confirm(btn_it: discord.Interaction) -> None:
                        try:
                            await adapter.stop()
                            restored = await adapter.restore()
                            await adapter.start()
                            await self._send(
                                btn_it,
                                adapter,
                                f"**Restore completed**\n"
                                f"**Backup:** `{safe_inline(restored.get('restored'), max_length=200)}`\n"
                                f"**Server state:** `Starting`",
                                0x57F287,
                            )
                            await self._audit(btn_it, adapter, "restore")
                        except Exception as restore_err:
                            try:
                                await adapter.start()
                            except Exception:
                                LOGGER.exception("Could not restart %s after restore failure", adapter.key)
                            await self._send_error(btn_it, restore_err)

                    view = ConfirmView(self.authorizer, on_confirm)
                    await interaction.followup.send(
                        embed=make_embed(
                            f"Monke-Bot | {adapter.display_name}",
                            f"⚠️ **Warning:** {reason}\nRestoring will stop the server and overwrite game data.\nClick **Confirm** below to proceed.",
                            0xFEE75C,
                        ),
                        view=view,
                    )
                    return

                if was_active:
                    await adapter.stop()
                restored = await adapter.restore()
                if was_active:
                    await adapter.start()
                    state = "Starting"
                else:
                    state = "Offline"
                await self._send(
                    interaction,
                    adapter,
                    f"**Restore completed**\n"
                    f"**Backup:** `{safe_inline(restored.get('restored'), max_length=200)}`\n"
                    f"**Server state:** `{state}`",
                    0x57F287,
                )
                await self._audit(interaction, adapter, "restore")
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
                "**Start here**",
                f"1. `/{prefix}-panel` opens the interactive control panel with quick action buttons.",
                f"2. `/{prefix}-status` checks whether the server is online and shows the current join code.",
                f"3. `/{prefix}-players` shows who is online.",
                f"4. `/{prefix}-join` shows connection details. The password is never displayed.",
                "",
                "**Available to everyone**",
                f"- `/{prefix}-panel` interactive control panel with quick action buttons",
                f"- `/{prefix}-status` server, player, join-code, and backup summary",
                f"- `/{prefix}-players` current and recently updated player list",
                f"- `/{prefix}-join` join code and connection information",
                f"- `/{prefix}-backup-status` backup schedule and recent backups",
                f"- `/{prefix}-health` VPS disk, memory, load, and server state",
                f"- `/{prefix}-logs` latest sanitized server logs",
                "",
                "**Monke Operator only**",
                f"- `/{prefix}-start` start the server",
                f"- `/{prefix}-stop` stop the server; use buttons or `confirm:true` while players are online",
                f"- `/{prefix}-restart` restart the server; use buttons or `confirm:true` while players are online",
                f"- `/{prefix}-update` update the server; use buttons or `confirm:true`",
                f"- `/{prefix}-backup` create a backup now",
                f"- `/{prefix}-restore` restore the latest backup; use buttons or `confirm:true`",
                "",
                "Ask a server admin for the `Monke Operator` role to run server operations.",
            ]
            await self._send(interaction, adapter, "\n".join(commands))

        self._add(adapter, "help", f"List {adapter.display_name} commands", callback)

    def register(self) -> None:
        for adapter in self.adapters.values():
            self._register_panel(adapter)
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
