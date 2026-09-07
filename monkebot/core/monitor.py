from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from monkebot.games.base import GameAdapter


LOGGER = logging.getLogger(__name__)
Notify = Callable[[str, int], Awaitable[None]]
ServerState = tuple[str, int, int]
PlayerPresence = tuple[int, int, bool]


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
    def __init__(
        self,
        adapters: dict[str, GameAdapter],
        notify: Notify,
        interval: int,
        backup_success: bool,
        presence_updater: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.adapters = adapters
        self.notify = notify
        self.interval = interval
        self.backup_success = backup_success
        self.presence_updater = presence_updater
        self.last_state: dict[str, ServerState] = {}
        self.last_backup: dict[str, str | None] = {}
        self.backup_ticks: dict[str, int] = {}
        self.player_presence: dict[str, dict[str, PlayerPresence]] = {}
        self.player_presence_initialized: set[str] = set()

    async def run(self) -> None:
        await asyncio.sleep(2)
        while True:
            for adapter in self.adapters.values():
                await self.check(adapter)
            await asyncio.sleep(self.interval)

    async def _check_player_presence(self, adapter: GameAdapter, data: dict[str, object]) -> None:
        names = {
            str(name).strip()
            for name in (data.get("player_names") or [])
            if str(name).strip()
        }
        states = self.player_presence.setdefault(adapter.key, {})
        if adapter.key not in self.player_presence_initialized:
            for name in names:
                states[name] = (0, 0, True)
            self.player_presence_initialized.add(adapter.key)
            return

        for name in set(states) | names:
            present_count, absent_count, announced = states.get(name, (0, 0, False))
            if name in names:
                present_count += 1
                absent_count = 0
                if not announced and present_count >= 2:
                    await self.notify(
                        f"**{adapter.display_name}** | `{name}` joined | "
                        f"**Players online:** `{len(names)}`",
                        0x57F287,
                    )
                    announced = True
            else:
                absent_count += 1
                present_count = 0
                if announced and absent_count >= 2:
                    await self.notify(
                        f"**{adapter.display_name}** | `{name}` left | "
                        f"**Players online:** `{len(names)}`",
                        0xFEE75C,
                    )
                    states.pop(name, None)
                    continue
            states[name] = (present_count, absent_count, announced)

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

            await self._check_player_presence(adapter, data)
            self.last_state[adapter.key] = state
            if self.backup_success:
                ticks = self.backup_ticks.get(adapter.key, 0)
                if ticks == 0 or ticks >= 10:
                    self.backup_ticks[adapter.key] = 1
                    backup = await adapter.backup_status()
                    latest = backup.get("latest")
                    previous_backup = self.last_backup.get(adapter.key)
                    if latest and previous_backup and latest != previous_backup:
                        await self.notify(f"{adapter.display_name} backup completed: `{latest}`.", 0x57F287)
                    self.last_backup[adapter.key] = latest
                else:
                    self.backup_ticks[adapter.key] = ticks + 1

            if self.presence_updater:
                status_label = "ONLINE" if data.get("active") else "OFFLINE"
                count = int(data.get("player_count", 0) or 0)
                await self.presence_updater(f"{adapter.display_name}: {status_label} ({count} players)")
        except Exception as exc:
            LOGGER.warning("Monitor check failed for %s: %s", adapter.key, exc)
