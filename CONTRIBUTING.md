# Contributing to Monke-Bot

Thanks for helping improve Monke-Bot.

## Before You Start

- Search existing issues and pull requests before opening a new one.
- Open an issue first for large features or behavior changes.
- Do not open public issues for security vulnerabilities; follow [SECURITY.md](SECURITY.md).
- Never include Discord tokens, server passwords, rclone credentials, IP
  addresses, or live server data in issues, commits, or screenshots.

## Local Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

## Guidelines

- Keep the Discord command layer independent from game-specific runtime code.
- Add game behavior through an adapter under `monkebot/games/`.
- Keep privileged actions in the allowlisted helper. Do not add arbitrary shell
  execution paths.
- Preserve public, readable Discord output. Prefer concise user-facing messages
  over raw system details.
- Add or update tests when changing log parsing, output formatting, command
  registration, or monitor behavior.
- Run the full test suite before opening a pull request.

## Pull Requests

- Use a focused title that describes the user-visible or operational change.
- Explain how the change was tested.
- Keep generated files and local environment files out of the pull request.

