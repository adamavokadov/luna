#!/usr/bin/env python3
"""Run the bot in the background, so it outlives the terminal and the browser tab.

    python3 tools/botctl.py start | stop | restart | status | resume | ensure-stopped

(`make start`, `make stop`, `make restart`, `make status`, `make logs` wrap it.) Stdlib only.

`start` launches a small supervisor in its own session. The supervisor applies the migrations once,
runs the bot, and restarts it with a growing pause if it crashes. State lives in `data/` (git-ignored):
`bot.pid`, `bot.log` (no names or tale texts: the bot never logs them) and `.autostart`, a flag that
exists only while the bot is meant to be running. The devcontainer calls `resume` whenever the
Codespace starts, so a Codespace that was stopped for being idle brings the bot back by itself.

What this cannot do: keep a Codespace awake. It stops after its idle timeout (30 minutes by default,
4 hours at most) and takes every process with it. For 24/7 operation use a real host (Docker, README).

Environment overrides (used by the tests): BOTCTL_DATA, BOTCTL_ENV_FILE, BOTCTL_BOT_CMD,
BOTCTL_MIGRATE_CMD (empty = skip), BOTCTL_BACKOFF (first restart pause, seconds).
"""

from __future__ import annotations

import contextlib
import os
import shlex
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STOP_GRACE_S = 20.0
LOG_ROTATE_BYTES = 5 * 1024 * 1024
BACKOFF_MAX_S = 300.0
HEALTHY_RUN_S = 60.0  # a run at least this long resets the restart pause


def data_dir() -> Path:
    return Path(os.environ.get("BOTCTL_DATA") or ROOT / "data")


def pid_file() -> Path:
    return data_dir() / "bot.pid"


def log_file() -> Path:
    return data_dir() / "bot.log"


def autostart_file() -> Path:
    return data_dir() / ".autostart"


def _venv_python() -> str:
    candidate = ROOT / ".venv" / "bin" / "python"
    return str(candidate) if candidate.exists() else sys.executable


def bot_cmd() -> list[str]:
    override = os.environ.get("BOTCTL_BOT_CMD")
    return shlex.split(override) if override else [_venv_python(), "-m", "skazki_bot"]


def migrate_cmd() -> list[str]:
    override = os.environ.get("BOTCTL_MIGRATE_CMD")
    if override is not None:
        return shlex.split(override)
    return [_venv_python(), "-m", "alembic", "upgrade", "head"]


# --- state ---------------------------------------------------------------------------------------
def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:  # an exited process nobody has reaped yet still answers kill(pid, 0)
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return True
    fields = stat.rpartition(")")[2].split()
    return not fields or fields[0] != "Z"


def _is_ours(pid: int) -> bool:
    """Guards against a recycled pid: on Linux the command line must be this script."""
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return True  # no /proc (macOS): trust the pid file
    return b"botctl.py" in cmdline


def running_pid() -> int | None:
    try:
        text = pid_file().read_text().strip()
    except OSError:
        return None
    if not text.isdigit():
        return None
    pid = int(text)
    return pid if _alive(pid) and _is_ours(pid) else None


def token_configured() -> bool:
    """True if BOT_TOKEN is set to something real in the environment or in `.env`. Never prints it."""

    def real(value: str) -> bool:
        value = value.strip().strip("\"'")
        return bool(value) and "replace-me" not in value

    if real(os.environ.get("BOT_TOKEN", "")):
        return True
    env_file = Path(os.environ.get("BOTCTL_ENV_FILE") or ROOT / ".env")
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in lines:
        key, sep, value = line.partition("=")
        if sep and key.strip() == "BOT_TOKEN":
            return real(value.split("#", 1)[0])
    return False


# --- commands ------------------------------------------------------------------------------------
def start() -> int:
    if (pid := running_pid()) is not None:
        print(f"already running (pid {pid}); logs: make logs")
        return 0
    if not token_configured():
        print(
            "BOT_TOKEN is not set. Add it as a Codespaces secret (then rebuild or reopen the\n"
            "terminal) or put it in .env, then run `make start` again.",
            file=sys.stderr,
        )
        return 1
    data_dir().mkdir(parents=True, exist_ok=True)
    log = log_file()
    if log.exists() and log.stat().st_size > LOG_ROTATE_BYTES:
        log.replace(log.with_name("bot.log.1"))
    with log.open("ab") as out:
        proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "_supervise"],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    pid_file().write_text(str(proc.pid))
    autostart_file().touch()
    time.sleep(0.3)
    if proc.poll() is not None:
        print(f"the supervisor exited at once (code {proc.returncode}); see {log}", file=sys.stderr)
        pid_file().unlink(missing_ok=True)
        return 1
    print(f"started (pid {proc.pid}); logs: make logs; stop: make stop")
    return 0


def stop() -> int:
    autostart_file().unlink(missing_ok=True)  # an explicit stop must survive a Codespace restart
    pid = running_pid()
    if pid is None:
        pid_file().unlink(missing_ok=True)
        print("not running")
        return 0
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + STOP_GRACE_S
    while time.monotonic() < deadline and _alive(pid):
        time.sleep(0.1)
    if _alive(pid):
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pid, signal.SIGKILL)  # the supervisor leads its own session, the bot is in it
        print("did not stop in time; killed")
    else:
        print("stopped")
    pid_file().unlink(missing_ok=True)
    return 0


def status() -> int:
    if (pid := running_pid()) is None:
        print("not running")
        return 1
    print(f"running (pid {pid}); logs: make logs")
    return 0


def resume() -> int:
    """Called when the Codespace starts: bring the bot back only if it was running when it stopped."""
    if not autostart_file().exists() or running_pid() is not None:
        return 0
    print("resuming the bot that was running before this Codespace stopped")
    return start()


def ensure_stopped() -> int:
    """`make run` runs in the foreground; two pollers on one token would fight over updates."""
    if (pid := running_pid()) is None:
        return 0
    print(
        f"The background bot is running (pid {pid}). Run `make stop` first: two bots on one\n"
        "token take updates away from each other.",
        file=sys.stderr,
    )
    return 1


# --- supervisor (runs detached) --------------------------------------------------------------------
def _say(message: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} botctl: {message}", flush=True)


def supervise() -> int:
    stopping = threading.Event()
    child: subprocess.Popen[bytes] | None = None

    def on_signal(signum: int, _frame: object) -> None:
        stopping.set()
        if child is not None and child.poll() is None:
            child.terminate()  # the bot shuts down gracefully on SIGTERM

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    if migrate := migrate_cmd():
        _say("applying migrations")
        if subprocess.run(migrate, cwd=ROOT, check=False).returncode != 0:
            _say("migrations failed; not starting the bot")
            return 1
    first_pause = delay = float(os.environ.get("BOTCTL_BACKOFF") or 5)
    while not stopping.is_set():
        _say("starting the bot")
        started = time.monotonic()
        child = subprocess.Popen(bot_cmd(), cwd=ROOT)  # same process group: a forced kill gets both
        if stopping.is_set():  # the signal arrived while the child was being created
            on_signal(signal.SIGTERM, None)
        code = child.wait()
        if stopping.is_set():
            break
        ran = time.monotonic() - started
        if ran >= HEALTHY_RUN_S:
            delay = first_pause
        _say(f"the bot exited with code {code} after {ran:.0f}s; restarting in {delay:g}s")
        stopping.wait(delay)
        delay = min(delay * 2, BACKOFF_MAX_S)
    _say("stopped")
    return 0


COMMANDS = {
    "start": start,
    "stop": stop,
    "status": status,
    "resume": resume,
    "ensure-stopped": ensure_stopped,
    "_supervise": supervise,
}


def main(argv: list[str]) -> int:
    if len(argv) == 1 and argv[0] == "restart":
        stop()
        return start()
    if len(argv) != 1 or argv[0] not in COMMANDS:
        print(__doc__)
        return 2
    return COMMANDS[argv[0]]()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
