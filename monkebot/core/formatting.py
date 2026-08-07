from __future__ import annotations

import re
from typing import Any

import discord


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


def status_text(data: dict[str, Any], display_name: str) -> str:
    state = "ONLINE" if data.get("active") else "OFFLINE"
    lines = [
        f"**Status:** `{state}`",
        f"**Server:** `{data.get('server_name') or display_name}`",
        f"**Pemain:** `{data.get('player_count', 0)}`",
        f"**PID:** `{data.get('pid', 0)}`",
        f"**Memory:** `{format_bytes(int(data.get('memory_bytes', 0) or 0))}`",
    ]
    if data.get("join_code"):
        lines.append(f"**Join code:** `{data['join_code']}`")
    if data.get("public_ip"):
        lines.append(f"**IP:** `{data['public_ip']}:{data.get('port', 0)}`")
    return "\n".join(lines)
