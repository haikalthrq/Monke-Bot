# MonkeHost Discord Bot

Modular Discord control bot for Valheim and Minecraft. The bot uses slash
commands generated from the enabled game adapters. Valheim commands start
with `v-`; Minecraft commands will start with `mc-`.

- `/v-start`
- `/v-stop`
- `/v-restart`
- `/v-update`
- `/v-status`
- `/v-players`
- `/v-join`
- `/v-backup`
- `/v-backup-status`
- `/v-restore`
- `/v-health`
- `/v-logs`
- `/v-help`

Set `ENABLED_GAMES=valheim,minecraft` after the Minecraft runtime and helper
configuration are ready to register the `/mc-*` command set.

## Architecture

```text
bot.py
monkebot/core/       Discord client, auth, commands, monitor, helper client
monkebot/games/      Valheim and Minecraft adapters
helper.py            Root-owned generic game runtime helper
```

The command layer only knows the adapter interface. Service names, update
methods, log parsing, and backup locations are selected by the helper runtime
configuration for each game.

The runtime is separate from the Valheim repository:

- Bot code: `/opt/monke-bot`
- Bot config: `/etc/monke-bot`
- Bot service: `monke-bot.service`
- Privileged helper: `/usr/local/libexec/monke-bot-helper`

The repository contains no Discord token, Valheim password, OAuth token, or
live server data. The bot runs as a dedicated `monke-bot` user and can only
invoke the fixed actions implemented by the root-owned helper.

## Discord Application

Create a Discord application and bot, then install it with these scopes:

- `bot`
- `applications.commands`

Required bot permissions:

- View Channels
- Send Messages
- Embed Links
- Read Message History

No privileged intents or Administrator permission are required.

## Install

From this repository on the Valheim VPS:

```bash
sudo VALHEIM_USER=haikalthoriqa \
  VALHEIM_DIR=/home/haikalthoriqa/valheim \
  ./install.sh
```

The default runtime path is `/opt/monke-bot`. Set `BOT_DIR` if a different
location is needed.

The installer creates the system user, Python virtualenv, helper, restricted
sudo rule, and systemd service. It does not start the bot until credentials are
configured.

## Credentials

Edit `/etc/monke-bot/bot.env`:

```text
DISCORD_TOKEN=the-bot-token
DISCORD_GUILD_ID=your-discord-server-id
ALLOWED_USER_IDS=your-discord-user-id
ALLOWED_ROLE_IDS=
ALLOW_ALL_GUILD_MEMBERS=true
STATUS_CHANNEL_ID=optional-notification-channel-id
ENABLED_GAMES=valheim
NOTIFY_BACKUP_SUCCESS=false
MONITOR_INTERVAL=30
HELPER_PATH=/usr/local/libexec/monke-bot-helper
```

Use Discord Developer Mode to copy the guild, user, role, and channel IDs.
Keep `DISCORD_TOKEN` private and never commit `bot.env`.

Start and inspect the service:

```bash
sudo systemctl start monke-bot.service
sudo systemctl status monke-bot.service
sudo journalctl -u monke-bot.service -f
```

Commands are synced to `DISCORD_GUILD_ID` immediately. Only configured user
IDs or role IDs can run commands unless `ALLOW_ALL_GUILD_MEMBERS=true`. In
that mode every member of the configured guild can run commands, including
server stop, restart, update, and restore commands.
