import unittest

from monkebot.core.monitor import GameMonitor


class FakeAdapter:
    key = "valheim"
    display_name = "Valheim"

    def __init__(self, data: dict) -> None:
        self.data = data

    async def status(self) -> dict:
        return self.data


class MonitorTests(unittest.IsolatedAsyncioTestCase):
    async def test_player_join_and_leave_notifications_are_compact(self) -> None:
        adapter = FakeAdapter({"active": True, "player_count": 0, "player_names": []})
        notifications: list[str] = []

        async def notify(message: str, color: int) -> None:
            notifications.append(message)

        monitor = GameMonitor({"valheim": adapter}, notify, interval=30, backup_success=False)
        await monitor.check(adapter)

        adapter.data = {
            "active": True,
            "player_count": 1,
            "player_names": ["Alice"],
        }
        await monitor.check(adapter)
        await monitor.check(adapter)

        adapter.data = {
            "active": True,
            "player_count": 1,
            "player_names": [],
        }
        await monitor.check(adapter)
        adapter.data = {"active": True, "player_count": 1, "player_names": ["Alice"]}
        await monitor.check(adapter)
        adapter.data = {"active": True, "player_count": 0, "player_names": []}
        await monitor.check(adapter)
        await monitor.check(adapter)

        self.assertEqual(
            notifications,
            [
                "**Valheim** | `Alice` joined | **Players online:** `1`",
                "**Valheim** | `Alice` left | **Players online:** `0`",
            ],
        )

    async def test_server_lifecycle_notifications_are_deduplicated(self) -> None:
        adapter = FakeAdapter(
            {"active": True, "state": "active", "substate": "running", "pid": 100, "player_count": 0}
        )
        notifications: list[str] = []

        async def notify(message: str, color: int) -> None:
            notifications.append(message)

        monitor = GameMonitor({"valheim": adapter}, notify, interval=30, backup_success=False)
        await monitor.check(adapter)

        adapter.data = {"active": False, "state": "activating", "substate": "start", "pid": 0, "player_count": 0}
        await monitor.check(adapter)
        await monitor.check(adapter)

        adapter.data = {"active": True, "state": "active", "substate": "running", "pid": 200, "player_count": 0}
        await monitor.check(adapter)

        adapter.data = {"active": False, "state": "inactive", "substate": "dead", "pid": 0, "player_count": 0}
        await monitor.check(adapter)

        adapter.data = {"active": False, "state": "activating", "substate": "start", "pid": 0, "player_count": 0}
        await monitor.check(adapter)

        self.assertEqual(
            notifications,
            [
                "**Valheim** | Server is restarting.",
                "**Valheim** | Server started.",
                "**Valheim** | Server stopped.",
                "**Valheim** | Server is starting.",
            ],
        )
