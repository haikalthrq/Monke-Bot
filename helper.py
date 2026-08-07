#!/usr/bin/env python3
"""Small, allowlisted root helper for the Discord bot."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


CONFIG_FILE = Path(os.environ.get("MONKE_BOT_HELPER_CONFIG", "/etc/monke-bot/helper.env"))


class HelperError(RuntimeError):
    pass


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        raise HelperError(f"Missing helper config: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


CONFIG = load_env(CONFIG_FILE)
VALHEIM_DIR = Path(CONFIG.get("VALHEIM_DIR", "/opt/valheim"))
VALHEIM_SERVICE = CONFIG.get("VALHEIM_SERVICE", "valheim.service")
BACKUP_SERVICE = CONFIG.get("BACKUP_SERVICE", "valheim-backup.service")
BACKUP_TIMER = CONFIG.get("BACKUP_TIMER", "valheim-backup.timer")
STEAMCMD = CONFIG.get("STEAMCMD", str(VALHEIM_DIR / "steamcmd/steamcmd.sh"))
SERVER_DIR = CONFIG.get("SERVER_DIR", str(VALHEIM_DIR / "server"))
VALHEIM_OWNER = CONFIG.get("VALHEIM_OWNER", "")
VALHEIM_GROUP = CONFIG.get("VALHEIM_GROUP", "")
RCLONE_CONFIG = CONFIG.get("RCLONE_CONFIG", "")
RCLONE_REMOTE = CONFIG.get("RCLONE_REMOTE", "valheim-drive:")

SERVER_ENV = load_env(VALHEIM_DIR / "server.env")
WORLD_NAME = SERVER_ENV.get("VALHEIM_WORLD", "MonkeEmpire")


def command(args: list[str], *, timeout: int = 30, env: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HelperError(str(exc)) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise HelperError(detail or f"Command failed: {' '.join(args)}")
    return result.stdout


def systemctl(action: str, service: str, *, timeout: int = 30) -> str:
    return command(["systemctl", action, service], timeout=timeout)


def is_active(service: str) -> bool:
    try:
        command(["systemctl", "is-active", "--quiet", service], timeout=10)
        return True
    except HelperError:
        return False


def systemd_properties() -> dict[str, str]:
    raw = command(
        [
            "systemctl",
            "show",
            VALHEIM_SERVICE,
            "--no-pager",
            "--property=ActiveState,SubState,MainPID,ActiveEnterTimestamp,MemoryCurrent",
        ],
        timeout=10,
    )
    values: dict[str, str] = {}
    for line in raw.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def integer(value: str | None) -> int:
    try:
        return int(value or 0)
    except ValueError:
        return 0


def journal(lines: int = 400) -> str:
    return command(
        ["journalctl", "-u", VALHEIM_SERVICE, "-n", str(lines), "--no-pager", "-o", "cat"],
        timeout=15,
    )


def parse_world_status(log: str) -> dict[str, Any]:
    active_sessions = re.findall(
        r'Session "([^"]+)" with join code (\d+) and IP ([^:\s]+):(\d+) is active',
        log,
    )
    registered_sessions = re.findall(
        r'Session "([^"]+)" registered with join code (\d+)',
        log,
    )
    player_events = re.findall(
        r'(?:Player joined|Player connection lost) server "[^"]+".*?now (\d+) player\(s\)',
        log,
    )
    names = re.findall(r"Got character ZDOID from (.+?) : \d+:\d+", log)
    recent_players: list[str] = []
    for name in reversed(names):
        if name not in recent_players:
            recent_players.append(name)
    current = active_sessions[-1] if active_sessions else None
    registered = registered_sessions[-1] if registered_sessions else None
    return {
        "server_name": current[0] if current else (registered[0] if registered else None),
        "join_code": current[1] if current else (registered[1] if registered else None),
        "public_ip": current[2] if current else None,
        "port": int(current[3]) if current else 2456,
        "player_count": int(player_events[-1]) if player_events else 0,
        "recent_players": recent_players[:10],
    }


def status() -> dict[str, Any]:
    properties = systemd_properties()
    service_status = {
        "active": properties.get("ActiveState") == "active" and properties.get("SubState") == "running",
        "state": properties.get("ActiveState", "unknown"),
        "substate": properties.get("SubState", "unknown"),
        "pid": integer(properties.get("MainPID")),
        "active_since": properties.get("ActiveEnterTimestamp", ""),
        "memory_bytes": integer(properties.get("MemoryCurrent")),
    }
    service_status.update(parse_world_status(journal()))
    return service_status


def rclone_env() -> dict[str, str]:
    env = os.environ.copy()
    if RCLONE_CONFIG:
        env["RCLONE_CONFIG"] = RCLONE_CONFIG
    return env


def backup_files() -> list[str]:
    pattern = f"{WORLD_NAME}-*.tar.gz"
    raw = command(
        [
            "rclone",
            "lsf",
            RCLONE_REMOTE,
            "--files-only",
            "--max-depth",
            "1",
            "--include",
            pattern,
        ],
        timeout=30,
        env=rclone_env(),
    )
    return sorted(line.strip() for line in raw.splitlines() if line.strip())


def backup_status() -> dict[str, Any]:
    files = backup_files()
    return {
        "timer_active": is_active(BACKUP_TIMER),
        "count": len(files),
        "latest": files[-1] if files else None,
        "files": files[-10:],
    }


def health() -> dict[str, Any]:
    usage = shutil.disk_usage(VALHEIM_DIR)
    memory: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, value = line.split(":", 1)
            memory[key] = int(value.strip().split()[0]) * 1024
    except (OSError, ValueError):
        memory = {}
    return {
        "disk_total": usage.total,
        "disk_used": usage.used,
        "disk_free": usage.free,
        "memory_total": memory.get("MemTotal", 0),
        "memory_available": memory.get("MemAvailable", 0),
        "load_1m": os.getloadavg()[0],
        "server": status(),
    }


def restore_world() -> dict[str, Any]:
    if is_active(VALHEIM_SERVICE):
        raise HelperError("stop the Valheim service before restoring")
    files = backup_files()
    if not files:
        raise HelperError(f"no {WORLD_NAME} backup found in {RCLONE_REMOTE}")

    import tempfile

    with tempfile.TemporaryDirectory(prefix="valheim-restore-") as temporary_dir:
        archive = Path(temporary_dir) / files[-1]
        command(
            ["rclone", "copyto", f"{RCLONE_REMOTE}{files[-1]}", str(archive)],
            timeout=60,
            env=rclone_env(),
        )
        listing = command(["tar", "-tzf", str(archive)], timeout=30)
        allowed = ("worlds_local/", "adminlist.txt", "bannedlist.txt", "permittedlist.txt")
        for item in listing.splitlines():
            item = item.strip()
            if item.startswith("/") or ".." in Path(item).parts or not item.startswith(allowed):
                raise HelperError("backup archive contains an unsafe path")
        save_dir = VALHEIM_DIR / "data"
        save_dir.mkdir(parents=True, exist_ok=True)
        command(["tar", "-xzf", str(archive), "-C", str(save_dir)], timeout=60)
    return {"restored": files[-1], **backup_status()}


def output(payload: dict[str, Any], code: int = 0) -> int:
    print(json.dumps({"ok": code == 0, **payload}, ensure_ascii=True))
    return code


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if action in {"status", "players"}:
            return output({"data": status()})
        if action == "health":
            return output({"data": health()})
        if action == "backup-status":
            return output({"data": backup_status()})
        if action == "logs":
            lines = int(sys.argv[2]) if len(sys.argv) > 2 else 20
            if not 5 <= lines <= 50:
                raise HelperError("log line count must be between 5 and 50")
            return output({"data": {"lines": journal(lines).splitlines()}})
        if action in {"start", "stop", "restart"}:
            systemctl(action, VALHEIM_SERVICE, timeout=120 if action != "start" else 30)
            return output({"data": status()})
        if action == "backup":
            systemctl("start", BACKUP_SERVICE, timeout=180)
            return output({"data": backup_status()})
        if action == "restore":
            return output({"data": restore_world()})
        if action == "update":
            was_active = is_active(VALHEIM_SERVICE)
            if was_active:
                systemctl("stop", VALHEIM_SERVICE, timeout=120)
            try:
                command(
                    [
                        STEAMCMD,
                        "+login",
                        "anonymous",
                        "+force_install_dir",
                        SERVER_DIR,
                        "+app_update",
                        "896660",
                        "-beta",
                        "public",
                        "validate",
                        "+quit",
                    ],
                    timeout=900,
                )
                if VALHEIM_OWNER and VALHEIM_GROUP:
                    command(["chown", "-R", f"{VALHEIM_OWNER}:{VALHEIM_GROUP}", SERVER_DIR], timeout=60)
            finally:
                if was_active:
                    systemctl("start", VALHEIM_SERVICE, timeout=30)
            return output({"data": status()})
        raise HelperError("unknown action")
    except (HelperError, ValueError) as exc:
        return output({"error": str(exc)}, 1)


if __name__ == "__main__":
    raise SystemExit(main())
