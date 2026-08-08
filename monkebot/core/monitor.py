from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from monkebot.games.base import GameAdapter


LOGGER = logging.getLogger(__name__)
Notify = Callable[[str, int], Awaitable[None]]


class GameMonitor:
    def __init__(self, adapters: dict[str, GameAdapter], notify: Notify, interval: int, backup_success: bool) -> None:
        self.adapters = adapters
        self.notify = notify
        self.interval = interval
        self.backup_success = backup_success
        self.last_state: dict[str, tuple[bool, int, str | None]] = {}
        self.last_backup: dict[str, str | None] = {}

    async def run(self) -> None:
        await asyncio.sleep(2)
        while True:
            for adapter in self.adapters.values():
                await self.check(adapter)
            await asyncio.sleep(self.interval)

    async def check(self, adapter: GameAdapter) -> None:
        try:
            data = await adapter.status()
            state = (bool(data.get("active")), int(data.get("player_count", 0) or 0), None)
            previous = self.last_state.get(adapter.key)
            if previous is not None:
                if state[0] != previous[0]:
                    await self.notify(
                        f"{adapter.display_name} {'is back online' if state[0] else 'is offline or restarting'}.",
                        0x57F287 if state[0] else 0xED4245,
                    )
                if state[1] != previous[1]:
                    await self.notify(f"{adapter.display_name} player count changed: {previous[1]} -> {state[1]}.", 0x5865F2)
            self.last_state[adapter.key] = state
            if self.backup_success:
                backup = await adapter.backup_status()
                latest = backup.get("latest")
                previous_backup = self.last_backup.get(adapter.key)
                if latest and previous_backup and latest != previous_backup:
                    await self.notify(f"{adapter.display_name} backup completed: `{latest}`.", 0x57F287)
                self.last_backup[adapter.key] = latest
        except Exception as exc:
            LOGGER.warning("Monitor check failed for %s: %s", adapter.key, exc)
