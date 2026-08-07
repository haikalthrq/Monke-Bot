#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

import discord
from discord import app_commands


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
LOGGER = logging.getLogger("valheim-discord-bot")


def parse_ids(value: str) -> set[int]:
    result: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if item:
            try:
                result.add(int(item))
            except ValueError:
                LOGGER.warning("Ignoring invalid Discord ID: %s", item)
    return result


def parse_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except ValueError:
        return default


TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = parse_int(os.getenv("DISCORD_GUILD_ID", "0") or "0")
ALLOWED_USER_IDS = parse_ids(os.getenv("ALLOWED_USER_IDS", ""))
ALLOWED_ROLE_IDS = parse_ids(os.getenv("ALLOWED_ROLE_IDS", ""))
STATUS_CHANNEL_ID = parse_int(os.getenv("STATUS_CHANNEL_ID", "0") or "0")
NOTIFY_BACKUP_SUCCESS = os.getenv("NOTIFY_BACKUP_SUCCESS", "false").lower() in {"1", "true", "yes"}
MONITOR_INTERVAL = max(15, int(os.getenv("MONITOR_INTERVAL", "30") or 30))
HELPER_PATH = os.getenv("HELPER_PATH", "/usr/local/libexec/monke-bot-helper")


class HelperError(RuntimeError):
    pass


async def helper(action: str, argument: int | None = None) -> dict[str, Any]:
    args = ["sudo", "-n", HELPER_PATH, action]
    if argument is not None:
        args.append(str(argument))
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    raw = stdout.decode("utf-8", errors="replace").strip()
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise HelperError(stderr.decode("utf-8", errors="replace").strip() or raw) from exc
    if process.returncode != 0 or not payload.get("ok", False):
        raise HelperError(payload.get("error") or stderr.decode("utf-8", errors="replace").strip() or "helper failed")
    return payload.get("data", {})


def format_bytes(value: int) -> str:
    if value <= 0:
        return "n/a"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return "n/a"


def clean_log(line: str) -> str:
    line = re.sub(r"(?i)(access_token|refresh_token|password|token|connectionstring)\s*[=:]\s*\S+", r"\1=[redacted]", line)
    line = re.sub(r"cv2:\S+", "cv2:[redacted]", line)
    return line.replace("`", "'")


def embed(title: str, description: str = "", color: int = 0x5865F2) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=color, timestamp=discord.utils.utcnow())


class ValheimClient(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.monitor_task: asyncio.Task[None] | None = None
        self.last_active: bool | None = None
        self.last_player_count: int | None = None
        self.last_backup: str | None = None

    async def setup_hook(self) -> None:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            LOGGER.info("Synced commands to guild %s", GUILD_ID)
        else:
            await self.tree.sync()
            LOGGER.info("Synced global commands")
        self.monitor_task = asyncio.create_task(self.monitor_loop())

    async def on_ready(self) -> None:
        LOGGER.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")

    async def close(self) -> None:
        if self.monitor_task:
            self.monitor_task.cancel()
        await super().close()

    async def notify(self, message: str, color: int = 0x5865F2) -> None:
        if not STATUS_CHANNEL_ID:
            return
        channel = self.get_channel(STATUS_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.fetch_channel(STATUS_CHANNEL_ID)
            except discord.HTTPException:
                LOGGER.exception("Could not fetch notification channel")
                return
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            await channel.send(embed=embed("Valheim Host", message, color))

    async def monitor_loop(self) -> None:
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                data = await helper("status")
                active = bool(data.get("active"))
                player_count = int(data.get("player_count", 0))
                if self.last_active is not None and active != self.last_active:
                    if active:
                        await self.notify("Server kembali online.", 0x57F287)
                    else:
                        await self.notify("Server offline atau sedang restart.", 0xED4245)
                if self.last_player_count is not None and player_count != self.last_player_count:
                    await self.notify(f"Jumlah pemain berubah: {self.last_player_count} -> {player_count}.")
                self.last_active = active
                self.last_player_count = player_count
                if NOTIFY_BACKUP_SUCCESS:
                    backup = await helper("backup-status")
                    latest = backup.get("latest")
                    if latest and latest != self.last_backup:
                        if self.last_backup is not None:
                            await self.notify(f"Backup Drive berhasil: `{latest}`.", 0x57F287)
                        self.last_backup = latest
            except Exception as exc:
                LOGGER.warning("Monitor check failed: %s", exc)
            await asyncio.sleep(MONITOR_INTERVAL)


bot = ValheimClient()


async def authorized(interaction: discord.Interaction) -> bool:
    if not interaction.guild_id or (GUILD_ID and interaction.guild_id != GUILD_ID):
        return False
    if interaction.user.id in ALLOWED_USER_IDS:
        return True
    roles = getattr(interaction.user, "roles", [])
    return any(role.id in ALLOWED_ROLE_IDS for role in roles)


async def require_auth(interaction: discord.Interaction) -> bool:
    if await authorized(interaction):
        return True
    await interaction.response.send_message("Kamu tidak punya akses ke bot ini.", ephemeral=True)
    return False


async def defer(interaction: discord.Interaction, ephemeral: bool = False) -> None:
    await interaction.response.defer(ephemeral=ephemeral)


async def result(interaction: discord.Interaction, message: str, color: int = 0x5865F2, ephemeral: bool = False) -> None:
    await interaction.followup.send(embed=embed("Valheim Host", message, color), ephemeral=ephemeral)


async def error_result(interaction: discord.Interaction, exc: Exception) -> None:
    LOGGER.warning("Command failed: %s", exc)
    await interaction.followup.send(
        embed=embed("Valheim Host", f"Gagal menjalankan perintah: `{str(exc)[:500]}`", 0xED4245),
        ephemeral=True,
    )


def status_text(data: dict[str, Any]) -> str:
    state = "ONLINE" if data.get("active") else "OFFLINE"
    lines = [
        f"**Status:** `{state}`",
        f"**Server:** `{data.get('server_name') or 'n/a'}`",
        f"**Pemain:** `{data.get('player_count', 0)}`",
        f"**Join code:** `{data.get('join_code') or 'belum tersedia'}`",
        f"**IP:** `{data.get('public_ip') or 'n/a'}:{data.get('port', 2456)}`",
        f"**PID:** `{data.get('pid', 0)}`",
        f"**Memory:** `{format_bytes(int(data.get('memory_bytes', 0) or 0))}`",
    ]
    return "\n".join(lines)


@bot.tree.command(name="v-start", description="Nyalakan server Valheim")
async def v_start(interaction: discord.Interaction) -> None:
    if not await require_auth(interaction):
        return
    await defer(interaction)
    try:
        before = await helper("status")
        if before.get("active"):
            await result(interaction, f"Server sudah online.\n\n{status_text(before)}", 0x57F287)
            return
        await helper("start")
        data = before
        for _ in range(12):
            await asyncio.sleep(3)
            data = await helper("status")
            if data.get("active") and data.get("join_code"):
                break
        await result(interaction, f"Server dinyalakan.\n\n{status_text(data)}", 0x57F287)
    except Exception as exc:
        await error_result(interaction, exc)


@bot.tree.command(name="v-stop", description="Matikan server Valheim secara aman")
@app_commands.describe(confirm="Set true jika tetap ingin mematikan saat ada pemain")
async def v_stop(interaction: discord.Interaction, confirm: bool = False) -> None:
    if not await require_auth(interaction):
        return
    await defer(interaction)
    try:
        data = await helper("status")
        if not data.get("active"):
            await result(interaction, "Server sudah offline.", 0xFEE75C)
            return
        players = int(data.get("player_count", 0))
        if players > 0 and not confirm:
            await result(interaction, f"Masih ada `{players}` pemain. Jalankan `/v-stop confirm:true` jika yakin.", 0xFEE75C, True)
            return
        await helper("stop")
        await result(interaction, "Server dimatikan dengan graceful stop. Semua pemain terputus.", 0xFEE75C)
    except Exception as exc:
        await error_result(interaction, exc)


@bot.tree.command(name="v-restart", description="Restart server Valheim")
@app_commands.describe(confirm="Set true jika tetap ingin restart saat ada pemain")
async def v_restart(interaction: discord.Interaction, confirm: bool = False) -> None:
    if not await require_auth(interaction):
        return
    await defer(interaction)
    try:
        data = await helper("status")
        players = int(data.get("player_count", 0))
        if players > 0 and not confirm:
            await result(interaction, f"Masih ada `{players}` pemain. Jalankan `/v-restart confirm:true` jika yakin.", 0xFEE75C, True)
            return
        await helper("restart")
        for _ in range(12):
            await asyncio.sleep(3)
            data = await helper("status")
            if data.get("active") and data.get("join_code"):
                break
        await result(interaction, f"Server berhasil direstart. Join code mungkin berubah.\n\n{status_text(data)}", 0x57F287)
    except Exception as exc:
        await error_result(interaction, exc)


@bot.tree.command(name="v-update", description="Update Valheim Dedicated Server via SteamCMD")
@app_commands.describe(confirm="Wajib true karena update menghentikan server")
async def v_update(interaction: discord.Interaction, confirm: bool = False) -> None:
    if not await require_auth(interaction):
        return
    await defer(interaction)
    if not confirm:
        await result(interaction, "Update akan menghentikan server. Jalankan `/v-update confirm:true`.", 0xFEE75C, True)
        return
    try:
        data = await helper("status")
        if int(data.get("player_count", 0)) > 0:
            await result(interaction, "Masih ada pemain online. Hentikan pemain dulu sebelum update.", 0xFEE75C, True)
            return
        data = await helper("update")
        await result(interaction, f"Server selesai di-update dan dijalankan kembali.\n\n{status_text(data)}", 0x57F287)
    except Exception as exc:
        await error_result(interaction, exc)


@bot.tree.command(name="v-status", description="Lihat status server Valheim")
async def v_status(interaction: discord.Interaction) -> None:
    if not await require_auth(interaction):
        return
    await defer(interaction)
    try:
        data = await helper("status")
        try:
            backup = await helper("backup-status")
            backup_text = f"{backup.get('count', 0)} file, terbaru `{backup.get('latest') or 'n/a'}`"
        except Exception:
            backup_text = "tidak tersedia"
        await result(interaction, f"{status_text(data)}\n**Backup Drive:** {backup_text}", 0x57F287 if data.get("active") else 0xED4245)
    except Exception as exc:
        await error_result(interaction, exc)


@bot.tree.command(name="v-players", description="Lihat jumlah dan pemain terbaru")
async def v_players(interaction: discord.Interaction) -> None:
    if not await require_auth(interaction):
        return
    await defer(interaction, ephemeral=True)
    try:
        data = await helper("players")
        names = data.get("recent_players") or []
        names_text = ", ".join(f"`{name}`" for name in names) if names else "Belum ada nama pemain di log terbaru."
        await result(interaction, f"**Pemain terdeteksi:** `{data.get('player_count', 0)}`\n**Nama terbaru:** {names_text}", ephemeral=True)
    except Exception as exc:
        await error_result(interaction, exc)


@bot.tree.command(name="v-join", description="Lihat cara join server")
async def v_join(interaction: discord.Interaction) -> None:
    if not await require_auth(interaction):
        return
    await defer(interaction, ephemeral=True)
    try:
        data = await helper("status")
        await result(
            interaction,
            f"**Server:** `{data.get('server_name') or 'MonkeEmpire'}`\n"
            f"**Join code:** `{data.get('join_code') or 'belum tersedia'}`\n"
            f"**IP:** `{data.get('public_ip') or 'n/a'}:{data.get('port', 2456)}`\n"
            "Password tidak ditampilkan oleh bot.",
            ephemeral=True,
        )
    except Exception as exc:
        await error_result(interaction, exc)


@bot.tree.command(name="v-backup", description="Jalankan backup world ke Google Drive sekarang")
async def v_backup(interaction: discord.Interaction) -> None:
    if not await require_auth(interaction):
        return
    await defer(interaction, ephemeral=True)
    try:
        data = await helper("backup")
        await result(interaction, f"Backup berhasil. `{data.get('latest')}`\nTotal file Drive: `{data.get('count', 0)}`", 0x57F287, True)
    except Exception as exc:
        await error_result(interaction, exc)


@bot.tree.command(name="v-backup-status", description="Lihat status backup lokal dan Google Drive")
async def v_backup_status(interaction: discord.Interaction) -> None:
    if not await require_auth(interaction):
        return
    await defer(interaction, ephemeral=True)
    try:
        data = await helper("backup-status")
        files = "\n".join(f"- `{item}`" for item in data.get("files", [])) or "Belum ada backup."
        await result(interaction, f"**Timer:** `{data.get('timer_active')}`\n**Jumlah:** `{data.get('count', 0)}`\n**File terbaru:** `{data.get('latest') or 'n/a'}`\n\n{files}", ephemeral=True)
    except Exception as exc:
        await error_result(interaction, exc)


@bot.tree.command(name="v-restore", description="Restore backup world terbaru dari Google Drive")
@app_commands.describe(confirm="Wajib true karena restore dapat menghentikan server")
async def v_restore(interaction: discord.Interaction, confirm: bool = False) -> None:
    if not await require_auth(interaction):
        return
    await defer(interaction, ephemeral=True)
    was_active = False
    try:
        before = await helper("status")
        was_active = bool(before.get("active"))
        players = int(before.get("player_count", 0))
        if was_active and (players > 0 or not confirm):
            reason = f"Masih ada `{players}` pemain." if players > 0 else "Server sedang online."
            await result(interaction, f"{reason} Jalankan `/v-restore confirm:true` jika yakin.", 0xFEE75C, True)
            return
        if was_active:
            await helper("stop")
        restored = await helper("restore")
        if was_active:
            await helper("start")
            state = "Server dikembalikan online."
        else:
            state = "Server tetap offline."
        await result(interaction, f"Restore berhasil: `{restored.get('restored')}`\n{state}", 0x57F287, True)
    except Exception as exc:
        if was_active:
            try:
                await helper("start")
            except Exception:
                LOGGER.exception("Could not restart server after restore failure")
        await error_result(interaction, exc)


@bot.tree.command(name="v-health", description="Lihat kesehatan VPS dan server")
async def v_health(interaction: discord.Interaction) -> None:
    if not await require_auth(interaction):
        return
    await defer(interaction, ephemeral=True)
    try:
        data = await helper("health")
        await result(
            interaction,
            f"**Disk:** `{format_bytes(data['disk_used'])}` / `{format_bytes(data['disk_total'])}` used\n"
            f"**Disk free:** `{format_bytes(data['disk_free'])}`\n"
            f"**RAM available:** `{format_bytes(data['memory_available'])}` / `{format_bytes(data['memory_total'])}`\n"
            f"**Load 1m:** `{data['load_1m']:.2f}`\n\n{status_text(data['server'])}",
            ephemeral=True,
        )
    except Exception as exc:
        await error_result(interaction, exc)


@bot.tree.command(name="v-logs", description="Tampilkan log server terbaru")
@app_commands.describe(lines="Jumlah baris log, antara 5 dan 50")
async def v_logs(interaction: discord.Interaction, lines: app_commands.Range[int, 5, 50] = 20) -> None:
    if not await require_auth(interaction):
        return
    await defer(interaction, ephemeral=True)
    try:
        data = await helper("logs", int(lines))
        text = "\n".join(clean_log(line) for line in data.get("lines", []))
        if len(text) > 1850:
            text = text[-1850:]
        await result(interaction, f"```text\n{text or 'Tidak ada log.'}\n```", ephemeral=True)
    except Exception as exc:
        await error_result(interaction, exc)


@bot.tree.command(name="v-help", description="Daftar command bot Valheim")
async def v_help(interaction: discord.Interaction) -> None:
    if not await require_auth(interaction):
        return
    await defer(interaction, ephemeral=True)
    commands = [
        "`/v-status` server, join code, pemain, backup",
        "`/v-start` dan `/v-stop` kontrol server",
        "`/v-restart confirm:true` restart server",
        "`/v-update confirm:true` update via SteamCMD",
        "`/v-players` pemain terbaru",
        "`/v-join` info koneksi privat",
        "`/v-backup` backup Drive sekarang",
        "`/v-backup-status` riwayat backup",
        "`/v-restore confirm:true` restore backup terbaru",
        "`/v-health` kesehatan VPS",
        "`/v-logs` log server terbaru",
    ]
    await result(interaction, "\n".join(commands), ephemeral=True)


async def main() -> None:
    if not TOKEN or TOKEN == "CHANGE_ME":
        raise SystemExit("DISCORD_TOKEN is not configured")
    if not GUILD_ID:
        LOGGER.warning("DISCORD_GUILD_ID is empty; commands will sync globally and may take time")
    if not ALLOWED_USER_IDS and not ALLOWED_ROLE_IDS:
        raise SystemExit("Configure ALLOWED_USER_IDS or ALLOWED_ROLE_IDS")
    await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
