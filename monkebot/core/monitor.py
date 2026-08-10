from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from monkebot.core.formatting import player_event_text
from monkebot.games.base import GameAdapter


LOGGER = logging.getLogger(__name__)
Notify = Callable[[str, int], Awaitable[None]]
PlayerEventKey = tuple[str, str, int]
ServerState = tuple[str, int, int]


def service_lifecycle(data: dict[str, object]) -> str:
    state = str(data.get("state") or "")
    substate = str(data.get("substate") or "")
    if state == "activating" or substate.startswith("start") or substate == "auto-restart":
        return "starting"
    if state == "deactivating" or substate.startswith("stop"):
        return "stopping"
    if data.get("active"):
        return "online"
    return "stopped"


class GameMonitor:
    def __init__(self, adapters: dict[str, GameAdapter], notify: Notify, interval: int, backup_success: bool) -> None:
        self.adapters = adapters
        self.notify = notify
        self.interval = interval
        self.backup_success = backup_success
        self.last_state: dict[str, ServerState] = {}
        self.last_backup: dict[str, str | None] = {}
        self.player_event_seen: dict[str, dict[PlayerEventKey, int]] = {}
        self.player_event_notified: dict[str, set[PlayerEventKey]] = {}
        self.player_event_initialized: set[str] = set()

    async def run(self) -> None:
        await asyncio.sleep(2)
        while True:
            for adapter in self.adapters.values():
                await self.check(adapter)
            await asyncio.sleep(self.interval)

    async def check(self, adapter: GameAdapter) -> None:
        try:
            data = await adapter.status()
            lifecycle = service_lifecycle(data)
            state = (lifecycle, int(data.get("player_count", 0) or 0), int(data.get("pid", 0) or 0))
            previous = self.last_state.get(adapter.key)
            if previous is not None:
                if lifecycle == "starting" and previous[0] != "starting":
                    action = "restarting" if previous[0] in {"online", "stopping"} else "starting"
                    await self.notify(f"**{adapter.display_name}** | Server is {action}.", 0x5865F2)
                elif lifecycle == "stopped" and previous[0] != "stopped":
                    await self.notify(f"**{adapter.display_name}** | Server stopped.", 0xED4245)
                elif lifecycle == "online" and previous[0] in {"starting", "stopping"}:
                    await self.notify(f"**{adapter.display_name}** | Server started.", 0x57F287)
                elif lifecycle == "online" and previous[0] == "online" and state[2] and state[2] != previous[2]:
                    await self.notify(f"**{adapter.display_name}** | Server restarted.", 0x57F287)

            events = data.get("player_events") or []
            event_state = self.player_event_seen.setdefault(adapter.key, {})
            notified_events = self.player_event_notified.setdefault(adapter.key, set())
            event_initialized = adapter.key in self.player_event_initialized
            if events:
                current_keys: set[PlayerEventKey] = set()
                for event in events:
                    key = (
                        str(event.get("timestamp") or ""),
                        str(event.get("event") or ""),
                        int(event.get("count") or 0),
                    )
                    current_keys.add(key)
                    if not event_initialized:
                        event_state[key] = 0
                        notified_events.add(key)
                        continue
                    event_state[key] = event_state.get(key, 0) + 1
                    if key in notified_events or not event.get("name"):
                        continue
                    event_type = event.get("event")
                    color = {
                        "Player joined": 0x57F287,
                        "Player connection lost": 0xFEE75C,
                    }.get(event_type, 0x5865F2)
                    await self.notify(
                        f"**{adapter.display_name}** | {player_event_text(event)}",
                        color,
                    )
                    notified_events.add(key)
                for key in set(event_state) - current_keys:
                    del event_state[key]
                    notified_events.discard(key)
                self.player_event_initialized.add(adapter.key)
            else:
                self.player_event_initialized.add(adapter.key)
                if previous is not None and lifecycle == "online" and previous[0] == "online" and state[1] != previous[1]:
                    await self.notify(f"**{adapter.display_name}** | **Players online:** `{state[1]}`", 0x5865F2)
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
