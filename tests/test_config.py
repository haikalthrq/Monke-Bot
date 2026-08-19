import os
import unittest
from unittest.mock import patch

from monkebot.core.config import BotConfig


class BotConfigTests(unittest.TestCase):
    def test_parses_operator_role_ids(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DISCORD_TOKEN": "test-token",
                "DISCORD_GUILD_ID": "1",
                "OPERATOR_ROLE_IDS": "30, 31",
            },
            clear=True,
        ):
            config = BotConfig.from_env()

        self.assertEqual(config.operator_role_ids, frozenset({30, 31}))

    def test_operator_role_is_required(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DISCORD_TOKEN": "test-token",
                "DISCORD_GUILD_ID": "1",
            },
            clear=True,
        ):
            config = BotConfig.from_env()

        with self.assertRaisesRegex(ValueError, "OPERATOR_ROLE_IDS"):
            config.validate()
