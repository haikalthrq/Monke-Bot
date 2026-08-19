# Security Policy

## Supported Versions

Security fixes are applied to the active development branch and released
through the default branch.

## Reporting a Vulnerability

Do not disclose vulnerabilities, Discord tokens, server passwords, rclone
credentials, or host access details in public issues or pull requests.

Use GitHub private vulnerability reporting when it is available for this
repository. If private reporting is unavailable, contact the repository owner
privately through GitHub before publishing any details.

Include a clear description, affected files or configuration, reproduction
steps, expected impact, and any suggested mitigation.

## Deployment Guidance

- Keep `DISCORD_TOKEN` in `/etc/monke-bot/bot.env` with restrictive file
  permissions.
- Assign `OPERATOR_ROLE_IDS` only to trusted administrators; all guild members
  can use read-only information commands.
- Grant the bot only the Discord channel permissions it needs.
- Rotate the bot token immediately if it is exposed.
- Keep the helper root-owned and do not broaden its sudo allowlist.
