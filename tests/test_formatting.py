import unittest

from monkebot.core.formatting import format_timestamp


class FormattingTests(unittest.TestCase):
    def test_timestamp_is_converted_to_wib(self) -> None:
        self.assertEqual(
            format_timestamp("2026-08-08T07:22:51+00:00"),
            "08/08/2026 14:22:51 WIB",
        )

    def test_missing_timestamp_is_human_readable(self) -> None:
        self.assertEqual(format_timestamp(None), "Not available")


if __name__ == "__main__":
    unittest.main()
