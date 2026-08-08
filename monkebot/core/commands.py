from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

import discord
from discord import app_commands

from monkebot.core.auth import Authorizer
from monkebot.core.formatting import clean_log, format_bytes, make_embed, status_text
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
        await interaction.followup.send(
            embed=make_embed("MonkeHost", f"Gagal menjalankan perintah: `{str(exc)[:500]}`", 0xED4245),
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
                    await self._send(interaction, adapter, f"Server sudah online.\n\n{status_text(before, adapter.display_name)}", 0x57F287)
                    return
                await adapter.start()
                data = await self._wait_online(adapter)
                await self._send(interaction, adapter, f"Server dinyalakan.\n\n{status_text(data, adapter.display_name)}", 0x57F287)
            except Exception as exc:
                await self._send_error(interaction, exc)

        self._add(adapter, "start", f"Nyalakan server {adapter.display_name}", callback)

    def _register_stop(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction, confirm: bool = False) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            try:
                data = await adapter.status()
                if not data.get("active"):
                    await self._send(interaction, adapter, "Server sudah offline.", 0xFEE75C)
                    return
                players = int(data.get("player_count", 0) or 0)
                if players > 0 and not confirm:
                    await self._send(interaction, adapter, f"Masih ada `{players}` pemain. Jalankan command dengan `confirm:true` jika yakin.", 0xFEE75C, True)
                    return
                await adapter.stop()
                await self._send(interaction, adapter, "Server dimatikan dengan graceful stop. Semua pemain terputus.", 0xFEE75C)
            except Exception as exc:
                await self._send_error(interaction, exc)

        callback = app_commands.describe(confirm="Set true jika tetap ingin mematikan saat ada pemain")(callback)
        self._add(adapter, "stop", f"Matikan server {adapter.display_name} secara aman", callback)

    def _register_restart(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction, confirm: bool = False) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            try:
                data = await adapter.status()
                players = int(data.get("player_count", 0) or 0)
                if players > 0 and not confirm:
                    await self._send(interaction, adapter, f"Masih ada `{players}` pemain. Jalankan command dengan `confirm:true` jika yakin.", 0xFEE75C, True)
                    return
                await adapter.restart()
                data = await self._wait_online(adapter)
                await self._send(interaction, adapter, f"Server berhasil direstart.\n\n{status_text(data, adapter.display_name)}", 0x57F287)
            except Exception as exc:
                await self._send_error(interaction, exc)

        callback = app_commands.describe(confirm="Set true jika tetap ingin restart saat ada pemain")(callback)
        self._add(adapter, "restart", f"Restart server {adapter.display_name}", callback)

    def _register_update(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction, confirm: bool = False) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            if not confirm:
                await self._send(interaction, adapter, "Update akan menghentikan server. Gunakan `confirm:true`.", 0xFEE75C, True)
                return
            try:
                data = await adapter.status()
                if int(data.get("player_count", 0) or 0) > 0:
                    await self._send(interaction, adapter, "Masih ada pemain online. Hentikan pemain dulu sebelum update.", 0xFEE75C, True)
                    return
                data = await adapter.update()
                await self._send(interaction, adapter, f"Server selesai di-update.\n\n{status_text(data, adapter.display_name)}", 0x57F287)
            except Exception as exc:
                await self._send_error(interaction, exc)

        callback = app_commands.describe(confirm="Wajib true karena update menghentikan server")(callback)
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
                    backup_text = f"{backup.get('count', 0)} file, terbaru `{backup.get('latest') or 'n/a'}`"
                except Exception:
                    backup_text = "tidak tersedia"
                await self._send(
                    interaction,
                    adapter,
                    f"{status_text(data, adapter.display_name)}\n**Backup:** {backup_text}",
                    0x57F287 if data.get("active") else 0xED4245,
                )
            except Exception as exc:
                await self._send_error(interaction, exc)

        self._add(adapter, "status", f"Lihat status server {adapter.display_name}", callback)

    def _register_players(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            try:
                data = await adapter.status()
                source = data.get("player_count_source", "unknown")
                source_text = {
                    "connections_heartbeat": "heartbeat koneksi server",
                    "player_event": "event join/leave terakhir",
                }.get(source, source)
                events = data.get("player_events") or []
                event_lines = []
                for event in reversed(events):
                    label = "join" if event.get("event") == "Player joined" else "leave"
                    event_lines.append(f"`{event.get('timestamp', 'n/a')}` {label}, count `{event.get('count', 0)}`")
                recent_events = "\n".join(event_lines) or "Belum ada event koneksi terbaru."
                await self._send(
                    interaction,
                    adapter,
                    f"**Pemain online:** `{data.get('player_count', 0)}`\n"
                    f"**Sumber:** `{source_text}`\n"
                    f"**Waktu data:** `{data.get('player_count_at') or 'n/a'}`\n\n"
                    f"**Event koneksi terbaru:**\n{recent_events}",
                )
            except Exception as exc:
                await self._send_error(interaction, exc)

        self._add(adapter, "players", f"Lihat pemain {adapter.display_name}", callback)

    def _register_join(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            try:
                data = await adapter.status()
                lines = [f"**Server:** `{data.get('server_name') or adapter.display_name}`"]
                if data.get("join_code"):
                    lines.append(f"**Join code:** `{data['join_code']}`")
                if data.get("public_ip"):
                    lines.append(f"**IP:** `{data['public_ip']}:{data.get('port', 0)}`")
                lines.append("Password tidak ditampilkan oleh bot.")
                await self._send(interaction, adapter, "\n".join(lines))
            except Exception as exc:
                await self._send_error(interaction, exc)

        self._add(adapter, "join", f"Lihat cara join {adapter.display_name}", callback)

    def _register_backup(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            try:
                data = await adapter.backup()
                await self._send(interaction, adapter, f"Backup berhasil. `{data.get('latest')}`\nTotal file: `{data.get('count', 0)}`", 0x57F287, True)
            except Exception as exc:
                await self._send_error(interaction, exc)

        self._add(adapter, "backup", f"Jalankan backup {adapter.display_name}", callback)

    def _register_backup_status(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            try:
                data = await adapter.backup_status()
                files = "\n".join(f"- `{item}`" for item in data.get("files", [])) or "Belum ada backup."
                await self._send(interaction, adapter, f"**Timer:** `{data.get('timer_active')}`\n**Jumlah:** `{data.get('count', 0)}`\n**File terbaru:** `{data.get('latest') or 'n/a'}`\n\n{files}")
            except Exception as exc:
                await self._send_error(interaction, exc)

        self._add(adapter, "backup-status", f"Lihat backup {adapter.display_name}", callback)

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
                    reason = f"Masih ada `{players}` pemain." if players > 0 else "Server sedang online."
                    await self._send(interaction, adapter, f"{reason} Gunakan `confirm:true` jika yakin.", 0xFEE75C)
                    return
                if was_active:
                    await adapter.stop()
                restored = await adapter.restore()
                if was_active:
                    await adapter.start()
                    state = "Server dikembalikan online."
                else:
                    state = "Server tetap offline."
                await self._send(interaction, adapter, f"Restore berhasil: `{restored.get('restored')}`\n{state}", 0x57F287)
            except Exception as exc:
                if was_active:
                    try:
                        await adapter.start()
                    except Exception:
                        LOGGER.exception("Could not restart %s after restore failure", adapter.key)
                await self._send_error(interaction, exc)

        callback = app_commands.describe(confirm="Wajib true karena restore dapat menghentikan server")(callback)
        self._add(adapter, "restore", f"Restore {adapter.display_name} terbaru", callback)

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
                    f"**Disk:** `{format_bytes(data['disk_used'])}` / `{format_bytes(data['disk_total'])}` used\n"
                    f"**Disk free:** `{format_bytes(data['disk_free'])}`\n"
                    f"**RAM available:** `{format_bytes(data['memory_available'])}` / `{format_bytes(data['memory_total'])}`\n"
                    f"**Load 1m:** `{data['load_1m']:.2f}`\n\n{status_text(data['server'], adapter.display_name)}",
                )
            except Exception as exc:
                await self._send_error(interaction, exc)

        self._add(adapter, "health", f"Lihat kesehatan {adapter.display_name}", callback)

    def _register_logs(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction, lines: app_commands.Range[int, 5, 50] = 20) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            try:
                data = await adapter.logs(int(lines))
                text = "\n".join(clean_log(line) for line in data.get("lines", []))
                if len(text) > 1850:
                    text = text[-1850:]
                await self._send(interaction, adapter, f"```text\n{text or 'Tidak ada log.'}\n```")
            except Exception as exc:
                await self._send_error(interaction, exc)

        callback = app_commands.describe(lines="Jumlah baris log, antara 5 dan 50")(callback)
        self._add(adapter, "logs", f"Lihat log {adapter.display_name}", callback)

    def _register_help(self, adapter: GameAdapter) -> None:
        async def callback(interaction: discord.Interaction) -> None:
            if not await self._guard(interaction):
                return
            await self._defer(interaction)
            prefix = adapter.command_prefix
            commands = [
                f"`/{prefix}-status` status server dan backup",
                f"`/{prefix}-start` dan `/{prefix}-stop` kontrol server",
                f"`/{prefix}-restart confirm:true` restart server",
                f"`/{prefix}-update confirm:true` update server",
                f"`/{prefix}-players` pemain terbaru",
                f"`/{prefix}-join` info koneksi",
                f"`/{prefix}-backup` backup sekarang",
                f"`/{prefix}-backup-status` riwayat backup",
                f"`/{prefix}-restore confirm:true` restore terbaru",
                f"`/{prefix}-health` kesehatan host",
                f"`/{prefix}-logs` log terbaru",
            ]
            await self._send(interaction, adapter, "\n".join(commands))

        self._add(adapter, "help", f"Daftar command {adapter.display_name}", callback)

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
