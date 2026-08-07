from __future__ import annotations

from typing import Any

from monkebot.core.helper_client import HelperClient


class GameAdapter:
    key = "game"
    command_prefix = "game"
    display_name = "Game"

    def __init__(self, helper: HelperClient) -> None:
        self.helper = helper

    async def call(self, action: str, argument: int | None = None) -> dict[str, Any]:
        return await self.helper.call(self.key, action, argument)

    async def status(self) -> dict[str, Any]:
        return await self.call("status")

    async def start(self) -> dict[str, Any]:
        return await self.call("start")

    async def stop(self) -> dict[str, Any]:
        return await self.call("stop")

    async def restart(self) -> dict[str, Any]:
        return await self.call("restart")

    async def update(self) -> dict[str, Any]:
        return await self.call("update")

    async def backup(self) -> dict[str, Any]:
        return await self.call("backup")

    async def backup_status(self) -> dict[str, Any]:
        return await self.call("backup-status")

    async def restore(self) -> dict[str, Any]:
        return await self.call("restore")

    async def health(self) -> dict[str, Any]:
        return await self.call("health")

    async def logs(self, lines: int) -> dict[str, Any]:
        return await self.call("logs", lines)
