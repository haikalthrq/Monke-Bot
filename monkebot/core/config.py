from __future__ import annotations

from dataclasses import dataclass
import os
import logging


LOGGER = logging.getLogger(__name__)


def parse_ids(value: str) -> frozenset[int]:
    result: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if item:
            try:
                result.add(int(item))
            except ValueError:
                LOGGER.warning("Ignoring invalid Discord ID: %s", item)
    return frozenset(result)


def parse_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except ValueError:
        return default


def parse_bool(value: str, default: bool = False) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class BotConfig:
    token: str
    guild_id: int
    operator_role_ids: frozenset[int]
    status_channel_id: int
    enabled_games: tuple[str, ...]
    notify_backup_success: bool
    monitor_interval: int
    helper_path: str

    @classmethod
    def from_env(cls) -> "BotConfig":
        games = tuple(
            item.strip().lower()
            for item in os.getenv("ENABLED_GAMES", "valheim").split(",")
            if item.strip()
        )
        return cls(
            token=os.getenv("DISCORD_TOKEN", "").strip(),
            guild_id=parse_int(os.getenv("DISCORD_GUILD_ID", "")),
            operator_role_ids=parse_ids(os.getenv("OPERATOR_ROLE_IDS", "")),
            status_channel_id=parse_int(os.getenv("STATUS_CHANNEL_ID", "")),
            enabled_games=games or ("valheim",),
            notify_backup_success=parse_bool(os.getenv("NOTIFY_BACKUP_SUCCESS", "false")),
            monitor_interval=max(15, parse_int(os.getenv("MONITOR_INTERVAL", "30"), 30)),
            helper_path=os.getenv("HELPER_PATH", "/usr/local/libexec/monke-bot-helper"),
        )

    def validate(self) -> None:
        if not self.token or self.token == "CHANGE_ME":
            raise ValueError("DISCORD_TOKEN is not configured")
        if not self.operator_role_ids:
            raise ValueError("Configure OPERATOR_ROLE_IDS")
