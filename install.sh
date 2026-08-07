#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run as root, for example: sudo VALHEIM_USER=your-user $0" >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VALHEIM_DIR="${VALHEIM_DIR:-/opt/valheim}"
VALHEIM_USER="${VALHEIM_USER:-${SUDO_USER:-}}"
BOT_USER="${BOT_USER:-monke-bot}"
BOT_DIR="${BOT_DIR:-/opt/monke-bot}"

if [[ -z "$VALHEIM_USER" ]] || ! id "$VALHEIM_USER" >/dev/null 2>&1; then
  echo "Set VALHEIM_USER to the existing Valheim service user." >&2
  exit 1
fi
if [[ ! -d "$VALHEIM_DIR" ]]; then
  echo "Valheim directory does not exist: $VALHEIM_DIR" >&2
  exit 1
fi

VALHEIM_GROUP=$(id -gn "$VALHEIM_USER")
VALHEIM_HOME=$(getent passwd "$VALHEIM_USER" | cut -d: -f6)
RCLONE_CONFIG_PATH="${RCLONE_CONFIG_PATH:-$VALHEIM_HOME/.config/rclone/rclone.conf}"

apt-get update
apt-get install -y python3-venv

if ! id "$BOT_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$BOT_DIR" --shell /usr/sbin/nologin "$BOT_USER"
fi
BOT_GROUP=$(id -gn "$BOT_USER")

install -d -o "$BOT_USER" -g "$BOT_GROUP" -m 750 "$BOT_DIR"
install -d -o root -g "$BOT_GROUP" -m 750 /etc/monke-bot
install -d -o root -g root -m 755 /usr/local/libexec

if [[ ! -x "$BOT_DIR/.venv/bin/python" ]]; then
  python3 -m venv "$BOT_DIR/.venv"
fi
"$BOT_DIR/.venv/bin/pip" install --disable-pip-version-check -r "$SCRIPT_DIR/requirements.txt"

install -o "$BOT_USER" -g "$BOT_GROUP" -m 644 "$SCRIPT_DIR/bot.py" "$BOT_DIR/bot.py"
install -o "$BOT_USER" -g "$BOT_GROUP" -m 644 "$SCRIPT_DIR/requirements.txt" "$BOT_DIR/requirements.txt"
rm -rf "$BOT_DIR/monkebot"
cp -a "$SCRIPT_DIR/monkebot" "$BOT_DIR/monkebot"
chown -R "$BOT_USER:$BOT_GROUP" "$BOT_DIR/monkebot"
install -o root -g root -m 755 "$SCRIPT_DIR/helper.py" /usr/local/libexec/monke-bot-helper

if [[ ! -f /etc/monke-bot/bot.env ]]; then
  install -o root -g "$BOT_GROUP" -m 640 "$SCRIPT_DIR/bot.env.example" /etc/monke-bot/bot.env
fi

printf '%s\n' \
  "VALHEIM_DIR=$VALHEIM_DIR" \
  "VALHEIM_SERVICE=valheim.service" \
  "BACKUP_SERVICE=valheim-backup.service" \
  "BACKUP_TIMER=valheim-backup.timer" \
  "STEAMCMD=$VALHEIM_DIR/steamcmd/steamcmd.sh" \
  "SERVER_DIR=$VALHEIM_DIR/server" \
  "VALHEIM_OWNER=$VALHEIM_USER" \
  "VALHEIM_GROUP=$VALHEIM_GROUP" \
  "RCLONE_CONFIG=$RCLONE_CONFIG_PATH" \
  "VALHEIM_RCLONE_CONFIG=$RCLONE_CONFIG_PATH" \
  "VALHEIM_RCLONE_REMOTE=valheim-drive:" \
  > /etc/monke-bot/helper.env
chown root:"$BOT_GROUP" /etc/monke-bot/helper.env
chmod 640 /etc/monke-bot/helper.env

temporary_unit=$(mktemp)
trap 'rm -f "$temporary_unit"' EXIT
sed \
  -e "s|@BOT_USER@|$BOT_USER|g" \
  -e "s|@BOT_GROUP@|$BOT_GROUP|g" \
  -e "s|@BOT_DIR@|$BOT_DIR|g" \
  "$SCRIPT_DIR/monke-bot.service" > "$temporary_unit"
install -o root -g root -m 644 "$temporary_unit" /etc/systemd/system/monke-bot.service

printf '%s ALL=(root) NOPASSWD: /usr/local/libexec/monke-bot-helper\n' "$BOT_USER" \
  > /etc/sudoers.d/monke-bot
chmod 440 /etc/sudoers.d/monke-bot
visudo -cf /etc/sudoers.d/monke-bot

chown -R "$BOT_USER:$BOT_GROUP" "$BOT_DIR"
systemctl daemon-reload
systemctl enable monke-bot.service

echo
echo "MonkeHost Discord bot installed in $BOT_DIR."
echo "Fill /etc/monke-bot/bot.env, then start with:"
echo "  systemctl start monke-bot.service"
