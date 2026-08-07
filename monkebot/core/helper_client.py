from __future__ import annotations

import asyncio
import json
from typing import Any


class HelperError(RuntimeError):
    pass


class HelperClient:
    def __init__(self, path: str) -> None:
        self.path = path

    async def call(self, game: str, action: str, argument: int | None = None) -> dict[str, Any]:
        args = ["sudo", "-n", self.path, game, action]
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
            detail = stderr.decode("utf-8", errors="replace").strip() or raw
            raise HelperError(detail or "helper returned invalid JSON") from exc
        if process.returncode != 0 or not payload.get("ok", False):
            detail = payload.get("error") or stderr.decode("utf-8", errors="replace").strip()
            raise HelperError(detail or "helper command failed")
        return payload.get("data", {})
