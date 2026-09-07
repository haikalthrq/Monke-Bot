#!/usr/bin/env python3
"""Allowlisted root helper shared by all Monke-Bot game adapters."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

try:
    import fcntl
except ImportError:
    fcntl = None  # Non-Unix compatibility for unit testing


CONFIG_FILE = Path(os.environ.get("MONKE_BOT_HELPER_CONFIG", "/etc/monke-bot/helper.env"))
LOCK_DIR = Path(
    os.environ.get(
        "MONKE_BOT_LOCK_DIR",
        "/run/monke-bot" if Path("/run").is_dir() else tempfile.gettempdir(),
    )
)


class HelperError(RuntimeError):
    pass


@contextmanager
def operation_lock(game: str, action: str):
    if fcntl is None:
        yield
        return
    try:
        LOCK_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    lock_file = LOCK_DIR / f"{game}.lock"
    try:
        fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR, 0o644)
    except OSError as exc:
        raise HelperError(f"could not open lock file: {exc}") from exc

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        os.close(fd)
        raise HelperError(f"another operation is currently in progress for {game}")

    try:
        os.ftruncate(fd, 0)
        os.write(fd, f"pid={os.getpid()} action={action}\n".encode("utf-8"))
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)


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


@dataclass(frozen=True)
class Runtime:
    key: str
    directory: Path
    service: str
    backup_service: str
    backup_timer: str
    steamcmd: str
    server_dir: str
    owner: str
    group: str
    rclone_config: str
    rclone_remote: str
    world_name: str
    app_id: str
    update_script: str
    status_log_lines: int


def runtime_for(game: str) -> Runtime:
    if not re.fullmatch(r"[a-z0-9-]+", game):
        raise HelperError("invalid game key")
    prefix = game.upper().replace("-", "_")
    directory_value = CONFIG.get(f"{prefix}_DIR")
    if not directory_value and game == "valheim":
        directory_value = CONFIG.get("VALHEIM_DIR")
    if not directory_value:
        raise HelperError(f"game is not configured: {game}")

    directory = Path(directory_value)
    server_env_path = directory / "server.env"
    server_env = load_env(server_env_path) if server_env_path.is_file() else {}
    world_name = (
        server_env.get(f"{prefix}_WORLD")
        or server_env.get("WORLD_NAME")
        or CONFIG.get(f"{prefix}_WORLD")
        or game
    )
    return Runtime(
        key=game,
        directory=directory,
        service=CONFIG.get(f"{prefix}_SERVICE", f"{game}.service"),
        backup_service=CONFIG.get(f"{prefix}_BACKUP_SERVICE", f"{game}-backup.service"),
        backup_timer=CONFIG.get(f"{prefix}_BACKUP_TIMER", f"{game}-backup.timer"),
        steamcmd=CONFIG.get(f"{prefix}_STEAMCMD", str(directory / "steamcmd/steamcmd.sh")),
        server_dir=CONFIG.get(f"{prefix}_SERVER_DIR", str(directory / "server")),
        owner=CONFIG.get(f"{prefix}_OWNER", CONFIG.get("VALHEIM_OWNER", "")),
        group=CONFIG.get(f"{prefix}_GROUP", CONFIG.get("VALHEIM_GROUP", "")),
        rclone_config=CONFIG.get(f"{prefix}_RCLONE_CONFIG", CONFIG.get("RCLONE_CONFIG", "")),
        rclone_remote=CONFIG.get(f"{prefix}_RCLONE_REMOTE", CONFIG.get("RCLONE_REMOTE", "valheim-drive:")),
        world_name=world_name,
        app_id=CONFIG.get(f"{prefix}_APP_ID", "896660" if game == "valheim" else ""),
        update_script=CONFIG.get(f"{prefix}_UPDATE_SCRIPT", ""),
        status_log_lines=max(400, integer(CONFIG.get(f"{prefix}_STATUS_LOG_LINES", "5000"))),
    )


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


def systemctl(action: str, runtime: Runtime, *, timeout: int = 30) -> str:
    return command(["systemctl", action, runtime.service], timeout=timeout)


def is_active(runtime: Runtime) -> bool:
    try:
        command(["systemctl", "is-active", "--quiet", runtime.service], timeout=10)
        return True
    except HelperError:
        return False


def integer(value: str | None) -> int:
    try:
        return int(value or 0)
    except ValueError:
        return 0


def systemd_properties(runtime: Runtime) -> dict[str, str]:
    raw = command(
        [
            "systemctl",
            "show",
            runtime.service,
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


def journal(runtime: Runtime, lines: int = 400, output_format: str = "cat") -> str:
    return command(
        ["journalctl", "-u", runtime.service, "-n", str(lines), "--no-pager", "-o", output_format],
        timeout=15,
    )


def parse_valheim_players(log: str) -> dict[str, Any]:
    records: list[tuple[int, str, dict[str, Any]]] = []
    player_pattern = re.compile(
        r'(?m)^(?P<timestamp>\S+).*?Player (?P<event>joined|connection lost) '
        r'server "[^"]+".*?now (?P<count>\d+) player\(s\)'
    )
    character_pattern = re.compile(
        r"(?m)^(?P<timestamp>\S+).*?Got character ZDOID from "
        r"(?P<name>.+?)\s+:\s+\d+:\d+"
    )
    heartbeat_pattern = re.compile(
        r"(?m)^(?P<timestamp>\S+).*?Connections (?P<count>\d+) ZDOS:"
    )

    for match in player_pattern.finditer(log):
        records.append((match.start(), "player", match.groupdict()))
    for match in character_pattern.finditer(log):
        records.append((match.start(), "character", match.groupdict()))
    for match in heartbeat_pattern.finditer(log):
        records.append((match.start(), "heartbeat", match.groupdict()))
    records.sort(key=lambda item: item[0])

    active_names: dict[str, int] = {}
    pending_joins: list[dict[str, Any]] = []
    player_events: list[dict[str, Any]] = []
    latest_heartbeat: tuple[int, str, int] | None = None
    latest_event: tuple[int, str, int, str, str | None] | None = None

    def remove_oldest() -> str | None:
        if not active_names:
            return None
        name = min(active_names, key=active_names.get)
        del active_names[name]
        return name

    for sequence, (_, kind, record) in enumerate(records):
        if kind == "character":
            name = record["name"].strip()
            if not name:
                continue
            active_names[name] = sequence
            if pending_joins:
                pending_joins.pop(0)["name"] = name
            continue

        count = int(record["count"])
        timestamp = record["timestamp"]
        if kind == "heartbeat":
            latest_heartbeat = (sequence, timestamp, count)
            if count == 0:
                active_names.clear()
                pending_joins.clear()
            while len(active_names) > count:
                remove_oldest()
            continue

        event = "Player joined" if record["event"] == "joined" else "Player connection lost"
        player_event: dict[str, Any] = {
            "timestamp": timestamp,
            "event": event,
            "count": count,
            "name": None,
        }
        player_events.append(player_event)
        if event == "Player joined":
            pending_joins.append(player_event)
        else:
            if count < len(active_names) or len(active_names) == 1:
                player_event["name"] = remove_oldest()
        latest_event = (sequence, timestamp, count, event, player_event["name"])

    if latest_heartbeat and (latest_event is None or latest_heartbeat[0] >= latest_event[0]):
        _, player_count_at, player_count = latest_heartbeat
        player_count_source = "connections_heartbeat"
    elif latest_event:
        _, player_count_at, event_count, event, event_name = latest_event
        if event == "Player connection lost" and event_name:
            player_count = len(active_names) if active_names else max(0, event_count - 1)
        else:
            player_count = event_count
        player_count_source = "player_event"
    else:
        player_count_at, player_count = None, 0
        player_count_source = "unknown"

    if player_count == 0:
        active_names.clear()
    while len(active_names) > player_count:
        remove_oldest()

    return {
        "player_count": player_count,
        "player_count_source": player_count_source,
        "player_count_at": player_count_at,
        "player_events": player_events[-5:],
        "player_names": sorted(active_names, key=str.casefold),
    }


def parse_valheim(log: str) -> dict[str, Any]:
    active_sessions = re.findall(
        r'Session "([^"]+)" with join code (\d+) and IP ([^:\s]+):(\d+) is active',
        log,
    )
    registered_sessions = re.findall(
        r'Session "([^"]+)" registered with join code (\d+)',
        log,
    )
    player_sessions = re.findall(
        r'(?m)Player (?:joined|connection lost) server "([^"]+)" '
        r"that has join code (\d+)",
        log,
    )
    names = re.findall(r"Got character ZDOID from (.+?) : \d+:\d+", log)
    players = parse_valheim_players(log)
    current = active_sessions[-1] if active_sessions else None
    registered = registered_sessions[-1] if registered_sessions else None
    player_session = player_sessions[-1] if player_sessions else None
    return {
        "server_name": current[0] if current else (registered[0] if registered else (player_session[0] if player_session else None)),
        "join_code": current[1] if current else (registered[1] if registered else (player_session[1] if player_session else None)),
        "public_ip": current[2] if current else None,
        "port": int(current[3]) if current else 2456,
        **players,
        "recent_players": list(dict.fromkeys(reversed(names)))[:10],
    }


def parse_minecraft(log: str) -> dict[str, Any]:
    online_counts = re.findall(r"There are (\d+) of a max", log)
    joined = re.findall(r": ([A-Za-z0-9_]{1,16}) joined the game", log)
    return {
        "server_name": "Minecraft",
        "join_code": None,
        "public_ip": None,
        "port": 25565,
        "player_count": int(online_counts[-1]) if online_counts else 0,
        "player_names": [],
        "recent_players": list(dict.fromkeys(reversed(joined)))[:10],
    }


def parse_game_status(runtime: Runtime, log: str) -> dict[str, Any]:
    if runtime.key == "valheim":
        return parse_valheim(log)
    if runtime.key == "minecraft":
        return parse_minecraft(log)
    return {"server_name": runtime.key, "player_count": 0, "player_names": [], "recent_players": []}


def status(runtime: Runtime) -> dict[str, Any]:
    properties = systemd_properties(runtime)
    data: dict[str, Any] = {
        "active": properties.get("ActiveState") == "active" and properties.get("SubState") == "running",
        "state": properties.get("ActiveState", "unknown"),
        "substate": properties.get("SubState", "unknown"),
        "pid": integer(properties.get("MainPID")),
        "active_since": properties.get("ActiveEnterTimestamp", ""),
        "memory_bytes": integer(properties.get("MemoryCurrent")),
    }
    data.update(parse_game_status(runtime, journal(runtime, runtime.status_log_lines, "short-iso")))
    return data


def rclone_env(runtime: Runtime) -> dict[str, str]:
    env = os.environ.copy()
    if runtime.rclone_config:
        env["RCLONE_CONFIG"] = runtime.rclone_config
    return env


def backup_files(runtime: Runtime) -> list[str]:
    raw = command(
        [
            "rclone",
            "lsf",
            runtime.rclone_remote,
            "--files-only",
            "--max-depth",
            "1",
            "--include",
            f"{runtime.world_name}-*.tar.gz",
        ],
        timeout=30,
        env=rclone_env(runtime),
    )
    return sorted(line.strip() for line in raw.splitlines() if line.strip())


def backup_status(runtime: Runtime) -> dict[str, Any]:
    files = backup_files(runtime)
    return {
        "timer_active": is_active_service(runtime.backup_timer),
        "count": len(files),
        "latest": files[-1] if files else None,
        "files": files[-10:],
    }


def is_active_service(service: str) -> bool:
    try:
        command(["systemctl", "is-active", "--quiet", service], timeout=10)
        return True
    except HelperError:
        return False


def health(runtime: Runtime) -> dict[str, Any]:
    usage = shutil.disk_usage(runtime.directory)
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
        "server": status(runtime),
    }


def restore_world(runtime: Runtime) -> dict[str, Any]:
    if is_active(runtime):
        raise HelperError("stop the game service before restoring")
    files = backup_files(runtime)
    if not files:
        raise HelperError(f"no {runtime.world_name} backup found in {runtime.rclone_remote}")

    with tempfile.TemporaryDirectory(prefix=f"{runtime.key}-restore-") as temporary_dir:
        archive = Path(temporary_dir) / files[-1]
        command(
            ["rclone", "copyto", f"{runtime.rclone_remote}{files[-1]}", str(archive)],
            timeout=60,
            env=rclone_env(runtime),
        )
        listing = command(["tar", "-tzf", str(archive)], timeout=30)
        allowed = ("worlds_local/", "adminlist.txt", "bannedlist.txt", "permittedlist.txt")
        for item in listing.splitlines():
            item = item.strip()
            if item.startswith("/") or ".." in Path(item).parts or not item.startswith(allowed):
                raise HelperError("backup archive contains an unsafe path")
        save_dir = runtime.directory / "data"
        save_dir.mkdir(parents=True, exist_ok=True)
        command(["tar", "-xzf", str(archive), "-C", str(save_dir)], timeout=60)
    return {"restored": files[-1], **backup_status(runtime)}


def update(runtime: Runtime) -> dict[str, Any]:
    was_active = is_active(runtime)
    if was_active:
        systemctl("stop", runtime, timeout=120)
    try:
        if runtime.update_script:
            command([runtime.update_script], timeout=900)
        elif runtime.steamcmd and runtime.app_id:
            command(
                [
                    runtime.steamcmd,
                    "+login",
                    "anonymous",
                    "+force_install_dir",
                    runtime.server_dir,
                    "+app_update",
                    runtime.app_id,
                    "-beta",
                    "public",
                    "validate",
                    "+quit",
                ],
                timeout=900,
            )
        else:
            raise HelperError(f"no update method configured for {runtime.key}")
        if runtime.owner and runtime.group:
            command(["chown", "-R", f"{runtime.owner}:{runtime.group}", runtime.server_dir], timeout=60)
    finally:
        if was_active:
            systemctl("start", runtime, timeout=30)
    return status(runtime)


def output(payload: dict[str, Any], code: int = 0) -> int:
    print(json.dumps({"ok": code == 0, **payload}, ensure_ascii=True))
    return code


def main() -> int:
    if len(sys.argv) < 3:
        return output({"error": "usage: helper GAME ACTION [ARG]"}, 1)
    game, action = sys.argv[1:3]
    try:
        runtime = runtime_for(game)
        if action in {"status", "players"}:
            return output({"data": status(runtime)})
        if action == "health":
            return output({"data": health(runtime)})
        if action == "backup-status":
            return output({"data": backup_status(runtime)})
        if action == "logs":
            lines = int(sys.argv[3]) if len(sys.argv) > 3 else 20
            if not 5 <= lines <= 50:
                raise HelperError("log line count must be between 5 and 50")
            return output({"data": {"lines": journal(runtime, lines).splitlines()}})
        if action in {"start", "stop", "restart", "backup", "restore", "update"}:
            with operation_lock(game, action):
                if action in {"start", "stop", "restart"}:
                    systemctl(action, runtime, timeout=120 if action != "start" else 30)
                    return output({"data": status(runtime)})
                if action == "backup":
                    command(["systemctl", "start", runtime.backup_service], timeout=180)
                    return output({"data": backup_status(runtime)})
                if action == "restore":
                    return output({"data": restore_world(runtime)})
                if action == "update":
                    return output({"data": update(runtime)})
        raise HelperError("unknown action")
    except (HelperError, ValueError) as exc:
        return output({"error": str(exc)}, 1)


if __name__ == "__main__":
    raise SystemExit(main())
