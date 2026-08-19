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


def safe_inline(value: Any, fallback: str = "Not available", max_length: int = 500) -> str:
    text = fallback if value is None else str(value).strip()
    if not text:
        text = fallback
    text = re.sub(r"\s+", " ", clean_log(text))
    if max_length <= 0:
        return ""
    if len(text) > max_length:
        if max_length <= 3:
            return text[:max_length]
        return f"{text[: max_length - 3]}..."
    return text


def player_event_text(event: dict[str, Any]) -> str:
    action = {
        "Player joined": "joined",
        "Player connection lost": "left",
    }.get(event.get("event"), "changed status")
    name = safe_inline(event.get("name"), fallback="", max_length=100)
    if not name:
        return ""
    count = event.get("count") or 0
    return f"`{name}` {action} | **Players online:** `{count}`"


def format_log_lines(lines: list[str], max_chars: int = 1850) -> str:
    selected: list[str] = []
    total = 0
    for raw_line in reversed(lines):
        line = clean_log(raw_line)
        separator = 1 if selected else 0
        if total + separator + len(line) > max_chars:
            if not selected and max_chars > 0:
                selected.append(line[:max_chars])
            break
        selected.append(line)
        total += separator + len(line)
    return "\n".join(reversed(selected))


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
        return "Not available"


def status_text(data: dict[str, Any], display_name: str) -> str:
    state = "ONLINE" if data.get("active") else "OFFLINE"
    player_source = data.get("player_count_source")
    player_label = {
        "connections_heartbeat": "Players (heartbeat)",
        "player_event": "Players (last event)",
    }.get(player_source, "Players")
    lines = [
        f"**Status:** `{state}`",
        f"**Server:** `{safe_inline(data.get('server_name'), display_name, 100)}`",
        f"**{player_label}:** `{data.get('player_count') or 0}`",
        f"**PID:** `{data.get('pid') or 0}`",
        f"**Memory:** `{format_bytes(int(data.get('memory_bytes', 0) or 0))}`",
        f"**Join code:** `{safe_inline(data.get('join_code'), max_length=100)}`",
    ]
    if data.get("public_ip"):
        address = f"{data['public_ip']}:{data.get('port', 0)}"
        lines.append(f"**IP:** `{safe_inline(address, max_length=100)}`")
    return "\n".join(lines)
