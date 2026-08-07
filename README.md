# MonkeHost Discord Bot

Discord control bot for Valheim now, with Minecraft support planned as a
separate module. The bot uses slash commands and every current command starts
with `v-`:

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
STATUS_CHANNEL_ID=optional-notification-channel-id
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
IDs or role IDs can run commands.
