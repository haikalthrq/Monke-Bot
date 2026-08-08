from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any

import discord


WIB = timezone(timedelta(hours=7), name="WIB")


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
    line = re.sub(
        r"(?i)(access_token|refresh_token|password|token|connectionstring)\s*[=:]\s*\S+",
        r"\1=[redacted]",
        line,
    )
    line = re.sub(r"cv2:\S+", "cv2:[redacted]", line)
    return line.replace("`", "'")


def make_embed(title: str, description: str = "", color: int = 0x5865F2) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=color, timestamp=discord.utils.utcnow())


def format_timestamp(value: str | None) -> str:
    if not value:
        return "Not available"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(WIB).strftime("%d/%m/%Y %H:%M:%S WIB")
    except ValueError:
        return value


def status_text(data: dict[str, Any], display_name: str) -> str:
    state = "ONLINE" if data.get("active") else "OFFLINE"
    player_source = data.get("player_count_source")
    player_label = "Players (heartbeat)" if player_source == "connections_heartbeat" else "Players (last event)"
    lines = [
        f"**Status:** `{state}`",
        f"**Server:** `{data.get('server_name') or display_name}`",
        f"**{player_label}:** `{data.get('player_count', 0)}`",
        f"**PID:** `{data.get('pid', 0)}`",
        f"**Memory:** `{format_bytes(int(data.get('memory_bytes', 0) or 0))}`",
    ]
    if data.get("join_code"):
        lines.append(f"**Join code:** `{data['join_code']}`")
    if data.get("public_ip"):
        lines.append(f"**IP:** `{data['public_ip']}:{data.get('port', 0)}`")
    return "\n".join(lines)
