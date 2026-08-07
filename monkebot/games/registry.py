from __future__ import annotations

import logging

from monkebot.core.helper_client import HelperClient
from monkebot.games.base import GameAdapter
from monkebot.games.minecraft import MinecraftAdapter
from monkebot.games.valheim import ValheimAdapter


LOGGER = logging.getLogger(__name__)


def create_adapters(helper: HelperClient, enabled_games: tuple[str, ...]) -> dict[str, GameAdapter]:
    factories = {
        "valheim": ValheimAdapter,
        "minecraft": MinecraftAdapter,
    }
    adapters: dict[str, GameAdapter] = {}
    for key in enabled_games:
        factory = factories.get(key)
        if factory is None:
            LOGGER.warning("Ignoring unknown game adapter: %s", key)
            continue
        adapters[key] = factory(helper)
    return adapters
