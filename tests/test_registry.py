import asyncio
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
        CommandRegistrar(tree, Authorizer(1, frozenset({2})), adapters).register()
        return sorted(command.name for command in tree.get_commands())

    def test_valheim_commands_use_v_namespace(self) -> None:
        names = self.command_names(("valheim",))
        self.assertEqual(len(names), 14)
        self.assertTrue(all(name.startswith("v-") for name in names))

    def test_minecraft_commands_are_separate(self) -> None:
        names = self.command_names(("valheim", "minecraft"))
        self.assertEqual(len(names), 28)
        self.assertEqual(sum(name.startswith("v-") for name in names), 14)
        self.assertEqual(sum(name.startswith("mc-") for name in names), 14)

    def test_commands_use_the_expected_access_tier(self) -> None:
        class RecordingAuthorizer:
            def __init__(self) -> None:
                self.tiers: list[str] = []

            async def require_member(self, interaction: object) -> bool:
                self.tiers.append("member")
                return False

            async def require_operator(self, interaction: object) -> bool:
                self.tiers.append("operator")
                return False

        authorizer = RecordingAuthorizer()
        tree = discord.app_commands.CommandTree(discord.Client(intents=discord.Intents.none()))
        adapters = create_adapters(self.helper, ("valheim",))
        CommandRegistrar(tree, authorizer, adapters).register()

        expected_tiers = {
            "v-panel": "member",
            "v-status": "member",
            "v-players": "member",
            "v-join": "member",
            "v-backup-status": "member",
            "v-health": "member",
            "v-logs": "member",
            "v-help": "member",
            "v-start": "operator",
            "v-stop": "operator",
            "v-restart": "operator",
            "v-update": "operator",
            "v-backup": "operator",
            "v-restore": "operator",
        }
        for command in tree.get_commands():
            asyncio.run(command.callback(object()))
            self.assertEqual(authorizer.tiers.pop(), expected_tiers[command.name])

    def test_help_guides_new_users_and_marks_operator_commands(self) -> None:
        class MemberAuthorizer:
            async def require_member(self, interaction: object) -> bool:
                return True

        class FakeResponse:
            async def defer(self, ephemeral: bool) -> None:
                return None

        class FakeFollowup:
            def __init__(self) -> None:
                self.embed: discord.Embed | None = None

            async def send(self, *, embed: discord.Embed, ephemeral: bool) -> None:
                self.embed = embed

        class FakeInteraction:
            def __init__(self) -> None:
                self.response = FakeResponse()
                self.followup = FakeFollowup()

        tree = discord.app_commands.CommandTree(discord.Client(intents=discord.Intents.none()))
        adapters = create_adapters(self.helper, ("valheim",))
        CommandRegistrar(tree, MemberAuthorizer(), adapters).register()
        help_command = next(command for command in tree.get_commands() if command.name == "v-help")
        interaction = FakeInteraction()
        asyncio.run(help_command.callback(interaction))

        self.assertIsNotNone(interaction.followup.embed)
        description = interaction.followup.embed.description or ""
        self.assertIn("**Start here**", description)
        self.assertIn("**Available to everyone**", description)
        self.assertIn("**Monke Operator only**", description)
        self.assertIn("`confirm:true`", description)


if __name__ == "__main__":
    unittest.main()
