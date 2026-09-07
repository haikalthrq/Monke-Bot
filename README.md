# Monke-Bot

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Discord](https://img.shields.io/badge/Discord-Slash%20commands-5865F2?logo=discord&logoColor=white)](https://discord.com/)
[![Valheim](https://img.shields.io/badge/Valheim-Self--hosted-8B5CF6)](#current-support)

**A secure Discord control plane for self-hosted game servers.**

Monke-Bot lets a Discord guild operate a Valheim server without exposing SSH,
server scripts, tokens, or root access to Discord users. It uses native slash
commands, systemd, an allowlisted privileged helper, and readable Discord
embeds for day-to-day server administration.

```text
/v-status     Check server, player, join-code, and backup status
/v-players    See the current player list
/v-backup     Create a backup on demand
/v-health     Inspect host disk, memory, and load
```

## Features

- **Discord-native operations:** Control the server with slash commands instead
  of giving players shell access.
- **Safe-by-design privileges:** The bot runs as an unprivileged system user and
  can only invoke a fixed, root-owned helper.
- **Live context:** Player names, server status, join code, backups, host
  health, and sanitized logs are available in Discord.
- **Self-hosted:** Systemd, SteamCMD, and rclone stay on your VPS under your
  control.
- **Extensible:** Game adapters keep the Discord command layer separate from
  game-specific runtime details.

## Current Support

| Game | Status | Command prefix |
| --- | --- | --- |
| Valheim | Ready to self-host | `/v-*` |
| Minecraft | Adapter scaffold; enable after its runtime is configured | `/mc-*` |

## Example Output

`/v-status` output:

```text
Server: MyValheimServer
Status: ONLINE
Players: 2
Join code: 123456

Backups: 10
Latest: MyValheimServer-20260820T120000Z.tar.gz
```

## Commands

| Command | Access | Purpose |
| --- | --- | --- |
| `/v-status` | Everyone | Server state, player count, join code, and latest backup |
| `/v-players` | Everyone | Current player list and update time |
| `/v-join` | Everyone | Join code and connection information |
| `/v-backup-status` | Everyone | Backup timer state and recent backups |
| `/v-health` | Everyone | Disk, memory, load, and compact server state |
| `/v-logs` | Everyone | Recent sanitized server logs |
| `/v-help` | Everyone | In-Discord command reference and first-use guide |
| `/v-start` | Operator | Start the server |
| `/v-stop` | Operator | Gracefully stop the server; requires confirmation when players are online |
| `/v-restart` | Operator | Restart the server; requires confirmation when players are online |
| `/v-update` | Operator | Update the dedicated server through SteamCMD |
| `/v-backup` | Operator | Run an on-demand backup |
| `/v-restore` | Operator | Restore the latest backup; requires confirmation |

## Architecture

```text
Discord slash command
        |
        v
monke-bot.service                 Runs as the unprivileged monke-bot user
        |
        v  sudo -n, one allowlisted command
/usr/local/libexec/monke-bot-helper
        |
        +-- systemctl   Valheim lifecycle
        +-- journalctl  Status and sanitized logs
        +-- SteamCMD    Game updates
        +-- rclone      Backup and restore
```

The Discord layer only knows the adapter interface. The helper owns service
names, update behavior, log parsing, and backup locations.

## Quick Start

### 1. Create a Discord application

Create a Discord application and bot, then install it with these scopes:

- `bot`
- `applications.commands`

Grant only these bot permissions:

- View Channels
- Send Messages
- Embed Links
- Read Message History

No privileged intents or Administrator permission are required.

### 2. Install on the VPS

Run the installer from this repository on the Valheim VPS:

```bash
git clone https://github.com/haikalthrq/Monke-Bot.git
cd Monke-Bot

sudo VALHEIM_USER=your-valheim-user \
  VALHEIM_DIR=/path/to/valheim \
  ./install.sh
```

The installer creates the dedicated system user, virtual environment, helper,
restricted sudo rule, and `monke-bot.service`.

### 3. Configure the bot

Edit `/etc/monke-bot/bot.env`:

```text
DISCORD_TOKEN=your-bot-token
DISCORD_GUILD_ID=your-discord-server-id
# Every guild member can use information commands. This role controls server operations.
OPERATOR_ROLE_IDS=your-operator-role-id
STATUS_CHANNEL_ID=optional-notification-channel-id
ENABLED_GAMES=valheim
NOTIFY_BACKUP_SUCCESS=false
MONITOR_INTERVAL=30
HELPER_PATH=/usr/local/libexec/monke-bot-helper
```

Use Discord Developer Mode to copy guild, user, role, and channel IDs. Keep
`DISCORD_TOKEN` private and never commit `bot.env`.

> [!WARNING]
> All members of the configured guild can use information commands. Assign
> `Monke Operator` only to trusted administrators who need to change the server.

### 4. Start the bot

```bash
sudo systemctl start monke-bot.service
sudo systemctl status monke-bot.service
sudo journalctl -u monke-bot.service -f
```

Commands are synced to `DISCORD_GUILD_ID` at startup.

## Security Model

- The Discord bot runs as the dedicated `monke-bot` system user.
- The bot can call only `/usr/local/libexec/monke-bot-helper` through a narrow
  `sudo` rule.
- The root-owned helper accepts fixed game actions rather than arbitrary shell
  commands.
- All guild members can inspect server information; only the Operator role can
  run lifecycle, update, backup, or restore actions.
- Secrets, server passwords, OAuth tokens, and live server data stay out of the
  repository.
- Log output redacts common token and password patterns before it reaches
  Discord.

Read [SECURITY.md](SECURITY.md) before deploying this bot to a public guild.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

Run the full suite before submitting a change. See
[CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

## Runtime Paths

| Path | Purpose |
| --- | --- |
| `/opt/monke-bot` | Bot code and Python virtual environment |
| `/etc/monke-bot/bot.env` | Discord token and bot configuration |
| `/etc/monke-bot/helper.env` | Game runtime configuration |
| `monke-bot.service` | Discord bot systemd service |
| `/usr/local/libexec/monke-bot-helper` | Root-owned privileged helper |

## Contributing

Issues and pull requests are welcome. Please read
[CONTRIBUTING.md](CONTRIBUTING.md) before opening a change.

## License

Monke-Bot is released under the [MIT License](LICENSE).
