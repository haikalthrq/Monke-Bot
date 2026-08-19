import unittest

from monkebot.core.formatting import (
    format_log_lines,
    format_timestamp,
    player_event_text,
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

    def test_status_includes_join_code(self) -> None:
        output = status_text({"active": True, "join_code": "735150"}, "Valheim")
        self.assertIn("**Join code:** `735150`", output)

    def test_player_event_text_is_compact(self) -> None:
        self.assertEqual(
            player_event_text({"event": "Player joined", "name": "Alice", "count": 1}),
            "`Alice` joined | **Players online:** `1`",
        )
        self.assertEqual(player_event_text({"event": "Player joined", "name": None, "count": 1}), "")


if __name__ == "__main__":
    unittest.main()
