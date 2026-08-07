import unittest

import discord

from monkebot.core.auth import Authorizer
from monkebot.core.commands import CommandRegistrar
from monkebot.core.config import BotConfig
from monkebot.core.helper_client import HelperClient
from monkebot.games.registry import create_adapters


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helper = HelperClient("/usr/local/libexec/monke-bot-helper")

    def command_names(self, games: tuple[str, ...]) -> list[str]:
        tree = discord.app_commands.CommandTree(discord.Client(intents=discord.Intents.none()))
        adapters = create_adapters(self.helper, games)
        CommandRegistrar(tree, Authorizer(1, frozenset({2}), frozenset()), adapters).register()
        return sorted(command.name for command in tree.get_commands())

    def test_valheim_commands_use_v_namespace(self) -> None:
        names = self.command_names(("valheim",))
        self.assertEqual(len(names), 13)
        self.assertTrue(all(name.startswith("v-") for name in names))

    def test_minecraft_commands_are_separate(self) -> None:
        names = self.command_names(("valheim", "minecraft"))
        self.assertEqual(len(names), 26)
        self.assertEqual(sum(name.startswith("v-") for name in names), 13)
        self.assertEqual(sum(name.startswith("mc-") for name in names), 13)


if __name__ == "__main__":
    unittest.main()
