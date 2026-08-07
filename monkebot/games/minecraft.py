from monkebot.games.base import GameAdapter


class MinecraftAdapter(GameAdapter):
    """Minecraft adapter surface; enable it after its runtime is configured."""

    key = "minecraft"
    command_prefix = "mc"
    display_name = "Minecraft"
