import unittest

from monkebot.core.formatting import (
    format_log_lines,
    format_timestamp,
    players_text,
    safe_inline,
    status_text,
)


class FormattingTests(unittest.TestCase):
    def test_timestamp_is_converted_to_wib(self) -> None:
        self.assertEqual(
            format_timestamp("2026-08-08T07:22:51+00:00"),
            "08/08/2026 14:22:51 WIB",
        )

    def test_missing_timestamp_is_human_readable(self) -> None:
        self.assertEqual(format_timestamp(None), "Not available")

    def test_invalid_timestamp_is_human_readable(self) -> None:
        self.assertEqual(format_timestamp("not-a-timestamp"), "Not available")

    def test_safe_inline_removes_embed_breaking_characters(self) -> None:
        self.assertEqual(safe_inline("error `details`\nnext"), "error 'details' next")
        self.assertEqual(safe_inline(None), "Not available")
        self.assertEqual(safe_inline("abcd", max_length=3), "abc")

    def test_log_formatter_keeps_recent_complete_lines(self) -> None:
        self.assertEqual(format_log_lines(["old", "middle", "new"], max_chars=10), "middle\nnew")

    def test_status_uses_generic_player_label_without_source(self) -> None:
        output = status_text({"active": False, "player_count": 0}, "Valheim")
        self.assertIn("**Players:** `0`", output)
        self.assertIn("**Join code:** `Not available`", output)

    def test_status_is_compact(self) -> None:
        output = status_text(
            {
                "active": True,
                "server_name": "MonkeEmpire",
                "player_count": 2,
                "join_code": "735150",
                "pid": 123,
                "memory_bytes": 1024,
                "public_ip": "127.0.0.1",
            },
            "Valheim",
        )
        self.assertEqual(
            output,
            "**Server:** `MonkeEmpire`\n**Status:** `ONLINE`\n**Players:** `2`\n**Join code:** `735150`",
        )

    def test_status_includes_join_code(self) -> None:
        output = status_text({"active": True, "join_code": "735150"}, "Valheim")
        self.assertIn("**Join code:** `735150`", output)

    def test_players_text_is_compact(self) -> None:
        self.assertEqual(
            players_text(
                {
                    "player_count": 2,
                    "player_names": ["Alice", "Bob"],
                    "player_count_at": "2026-08-08T07:22:51+00:00",
                }
            ),
            "**Online players:** `2`\n- `Alice`\n- `Bob`\n\n**Updated:** `08/08/2026 14:22:51 WIB`",
        )


if __name__ == "__main__":
    unittest.main()
