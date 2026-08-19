import os
from pathlib import Path
import unittest


os.environ["MONKE_BOT_HELPER_CONFIG"] = str(Path(__file__).with_name("helper_fixture.env"))

from helper import parse_valheim  # noqa: E402


class ValheimParsingTests(unittest.TestCase):
    def test_active_player_names_are_reconciled_with_connection_count(self) -> None:
        log = "\n".join(
            [
                '2026-08-10T10:00:00+0700: Player joined server "MonkeEmpire" that has join code 123456, now 1 player(s)',
                "2026-08-10T10:00:02+0700: Got character ZDOID from Alice : 1:1",
                '2026-08-10T10:01:00+0700: Player joined server "MonkeEmpire" that has join code 123456, now 2 player(s)',
                "2026-08-10T10:01:02+0700: Got character ZDOID from Bob : 2:1",
                "2026-08-10T10:02:00+0700: Connections 2 ZDOS:123 sent:0 recv:0",
                '2026-08-10T10:03:00+0700: Player connection lost server "MonkeEmpire" that has join code 123456, now 1 player(s)',
                "2026-08-10T10:04:00+0700: Connections 1 ZDOS:123 sent:0 recv:0",
            ]
        )

        data = parse_valheim(log)

        self.assertEqual(data["player_count"], 1)
        self.assertEqual(data["player_names"], ["Bob"])
        self.assertEqual(data["player_events"][0]["name"], "Alice")
        self.assertEqual(data["player_events"][-1]["name"], "Alice")

    def test_short_iso_journal_prefix_is_supported(self) -> None:
        log = "\n".join(
            [
                '2026-08-10T10:00:00+07:00 host[1]: 08/10/2026 10:00:00: Player joined server "MonkeEmpire" that has join code 123456, now 1 player(s)',
                '2026-08-10T10:00:02+07:00 host[1]: 08/10/2026 10:00:02: Got character ZDOID from Alice : 1:1',
                "2026-08-10T10:01:00+07:00 host[1]: 08/10/2026 10:01:00: Connections 1 ZDOS:123 sent:0 recv:0",
            ]
        )

        data = parse_valheim(log)

        self.assertEqual(data["player_names"], ["Alice"])
        self.assertEqual(data["player_count_at"], "2026-08-10T10:01:00+07:00")

    def test_newer_player_event_overrides_stale_heartbeat(self) -> None:
        log = "\n".join(
            [
                "2026-08-10T10:00:00+0700: Connections 0 ZDOS:123 sent:0 recv:0",
                '2026-08-10T10:01:00+0700: Player joined server "MonkeEmpire" that has join code 123456, now 1 player(s)',
                "2026-08-10T10:01:02+0700: Got character ZDOID from Alice : 1:1",
            ]
        )

        data = parse_valheim(log)

        self.assertEqual(data["player_count"], 1)
        self.assertEqual(data["player_count_source"], "player_event")
        self.assertEqual(data["player_names"], ["Alice"])

    def test_single_player_disconnect_gets_the_known_name(self) -> None:
        log = "\n".join(
            [
                '2026-08-10T10:00:00+0700: Player joined server "MonkeEmpire" that has join code 123456, now 1 player(s)',
                "2026-08-10T10:00:02+0700: Got character ZDOID from Alice : 1:1",
                '2026-08-10T10:05:00+0700: Player connection lost server "MonkeEmpire" that has join code 123456, now 1 player(s)',
            ]
        )

        data = parse_valheim(log)

        self.assertEqual(data["player_count"], 0)
        self.assertEqual(data["player_events"][-1]["name"], "Alice")

    def test_join_name_can_arrive_after_an_interleaved_disconnect(self) -> None:
        log = "\n".join(
            [
                '2026-08-10T10:00:00+0700: Player joined server "MonkeEmpire" that has join code 123456, now 2 player(s)',
                '2026-08-10T10:00:05+0700: Player connection lost server "MonkeEmpire" that has join code 123456, now 2 player(s)',
                "2026-08-10T10:00:10+0700: Got character ZDOID from Bidjisalak : 1:1",
            ]
        )

        data = parse_valheim(log)

        self.assertEqual(data["player_events"][0]["name"], "Bidjisalak")

    def test_join_code_is_read_from_player_events(self) -> None:
        log = '2026-08-10T10:00:00+0700: Player joined server "MonkeEmpire" that has join code 735150, now 1 player(s)'

        data = parse_valheim(log)

        self.assertEqual(data["server_name"], "MonkeEmpire")
        self.assertEqual(data["join_code"], "735150")
