from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands

from monkebot.core.auth import Authorizer
from monkebot.core.commands import CommandRegistrar
from monkebot.core.config import BotConfig
from monkebot.core.formatting import make_embed
from monkebot.core.helper_client import HelperClient
from monkebot.core.monitor import GameMonitor
from monkebot.games.registry import create_adapters


LOGGER = logging.getLogger("monke-bot")


class MonkeClient(discord.Client):
    def __init__(self, config: BotConfig) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents)
        self.config = config
        self.tree = app_commands.CommandTree(self)
        helper = HelperClient(config.helper_path)
        self.adapters = create_adapters(helper, config.enabled_games)
        self.monitor: GameMonitor | None = None
        if not self.adapters:
            raise ValueError("No valid game adapters are enabled")

    async def setup_hook(self) -> None:
        authorizer = Authorizer(
            self.config.guild_id,
            self.config.operator_role_ids,
        )
        CommandRegistrar(self.tree, authorizer, self.adapters, notify=self.notify).register()
        if self.config.guild_id:
            guild = discord.Object(id=self.config.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            LOGGER.info("Synced commands to guild %s", self.config.guild_id)
        else:
            await self.tree.sync()
            LOGGER.info("Synced global commands")
        self.monitor = GameMonitor(
            self.adapters,
            self.notify,
            self.config.monitor_interval,
            self.config.notify_backup_success,
            presence_updater=self.update_presence,
        )
        asyncio.create_task(self.monitor.run())

    async def on_ready(self) -> None:
        LOGGER.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")

    async def update_presence(self, status_text: str) -> None:
        try:
            activity = discord.Activity(type=discord.ActivityType.watching, name=status_text)
            await self.change_presence(activity=activity)
        except Exception:
            LOGGER.debug("Could not update Discord presence", exc_info=True)

    async def notify(self, message: str, color: int = 0x5865F2) -> None:
        if not self.config.status_channel_id:
            return
        channel = self.get_channel(self.config.status_channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(self.config.status_channel_id)
            except discord.HTTPException:
                LOGGER.exception("Could not fetch notification channel")
                return
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            await channel.send(embed=make_embed("Monke-Bot", message, color))


async def run() -> None:
    config = BotConfig.from_env()
    config.validate()
    client = MonkeClient(config)
    await client.start(config.token)
