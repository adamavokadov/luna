"""tools/botctl.py: the background runner (real subprocesses, a stand-in command instead of the bot)."""

from __future__ import annotations

import importlib.util
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "botctl.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("botctl_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wait_for(condition: Callable[[], bool], timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


def dead(pid: int) -> bool:
    return not load()._alive(pid)


@pytest.fixture
def ctl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    monkeypatch.setenv("BOTCTL_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("BOTCTL_ENV_FILE", str(tmp_path / "no.env"))
    monkeypatch.setenv("BOTCTL_MIGRATE_CMD", "")
    monkeypatch.setenv("BOTCTL_BACKOFF", "0.05")
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    module = load()
    yield module
    module.stop()  # never leave a supervisor behind


def sleeper(tmp_path: Path) -> tuple[str, Path]:
    """A stand-in bot that records its pid and then waits."""
    marker = tmp_path / "child.pid"
    code = f"import os,time,pathlib; pathlib.Path({str(marker)!r}).write_text(str(os.getpid())); time.sleep(300)"
    return f'{sys.executable} -c "{code}"', marker


def test_start_status_stop(
    ctl: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    command, marker = sleeper(tmp_path)
    monkeypatch.setenv("BOTCTL_BOT_CMD", command)

    assert ctl.status() == 1
    assert ctl.start() == 0
    assert wait_for(marker.exists)
    child_pid = int(marker.read_text())
    supervisor = ctl.running_pid()
    assert supervisor is not None and ctl.status() == 0
    assert ctl.autostart_file().exists()

    assert ctl.start() == 0  # a second start is a no-op
    assert ctl.running_pid() == supervisor
    assert "already running" in capsys.readouterr().out

    assert ctl.stop() == 0
    assert ctl.running_pid() is None
    assert not ctl.pid_file().exists() and not ctl.autostart_file().exists()
    assert wait_for(lambda: dead(supervisor)) and wait_for(lambda: dead(child_pid))


def test_a_crashing_bot_is_restarted(
    ctl: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = tmp_path / "runs.txt"
    code = f"import pathlib; f=pathlib.Path({str(runs)!r}); f.open('a').write('x'); raise SystemExit(1)"
    monkeypatch.setenv("BOTCTL_BOT_CMD", f'{sys.executable} -c "{code}"')

    assert ctl.start() == 0
    assert wait_for(lambda: runs.exists() and len(runs.read_text()) >= 3)
    assert ctl.running_pid() is not None  # still supervised after crashing
    assert "restarting in" in ctl.log_file().read_text()


def test_failed_migrations_do_not_start_the_bot(
    ctl: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    command, marker = sleeper(tmp_path)
    monkeypatch.setenv("BOTCTL_BOT_CMD", command)
    monkeypatch.setenv("BOTCTL_MIGRATE_CMD", f'{sys.executable} -c "raise SystemExit(3)"')

    assert ctl.start() == 1  # the supervisor gave up at once and start says so
    assert ctl.running_pid() is None and not ctl.pid_file().exists()
    assert not marker.exists()
    assert "migrations failed" in ctl.log_file().read_text()


def test_start_needs_a_real_token(
    ctl: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("BOT_TOKEN", "")
    assert ctl.start() == 1
    assert "BOT_TOKEN is not set" in capsys.readouterr().err
    assert not ctl.pid_file().exists()

    monkeypatch.setenv("BOT_TOKEN", "123456:replace-me")
    assert ctl.start() == 1  # the placeholder from .env.example is not a token


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("BOT_TOKEN=123456:abc-DEF", True),
        ('BOT_TOKEN="123456:abc-DEF"  # from @BotFather', True),
        ("BOT_TOKEN=123456:replace-me           # from @BotFather", False),
        ("BOT_TOKEN=", False),
        ("# BOT_TOKEN=123456:abc", False),
        ("OTHER=1", False),
    ],
)
def test_token_is_read_from_the_env_file(
    ctl: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, line: str, expected: bool
) -> None:
    monkeypatch.setenv("BOT_TOKEN", "")
    env_file = tmp_path / "x.env"
    env_file.write_text(f"LOG_LEVEL=INFO\n{line}\n", encoding="utf-8")
    monkeypatch.setenv("BOTCTL_ENV_FILE", str(env_file))
    assert ctl.token_configured() is expected


def test_resume_only_restarts_a_bot_that_was_meant_to_run(
    ctl: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    command, marker = sleeper(tmp_path)
    monkeypatch.setenv("BOTCTL_BOT_CMD", command)

    assert ctl.resume() == 0  # never started: nothing happens
    assert ctl.running_pid() is None

    ctl.start()
    assert wait_for(marker.exists)
    supervisor = ctl.running_pid()
    assert supervisor is not None
    ctl.resume()  # already running: nothing happens
    assert ctl.running_pid() == supervisor

    # The Codespace stopped: the processes are gone, the flag and a stale pid file remain.
    os.killpg(supervisor, signal.SIGKILL)  # the supervisor leads its own process group
    assert wait_for(lambda: dead(supervisor))
    assert ctl.autostart_file().exists() and ctl.running_pid() is None
    marker.unlink()
    assert ctl.resume() == 0
    assert wait_for(marker.exists)
    assert ctl.running_pid() not in (None, supervisor)

    ctl.stop()  # an explicit stop clears the flag: the next resume stays quiet
    assert ctl.resume() == 0 and ctl.running_pid() is None


def test_ensure_stopped_guards_make_run(
    ctl: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    command, marker = sleeper(tmp_path)
    monkeypatch.setenv("BOTCTL_BOT_CMD", command)
    assert ctl.ensure_stopped() == 0
    ctl.start()
    assert wait_for(marker.exists)
    assert ctl.ensure_stopped() == 1
    assert "make stop" in capsys.readouterr().err


def test_a_stale_pid_file_is_ignored(ctl: ModuleType) -> None:
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    ctl.data_dir().mkdir(parents=True)
    ctl.pid_file().write_text(str(gone.pid))
    assert ctl.running_pid() is None
    assert ctl.status() == 1
    assert ctl.stop() == 0 and not ctl.pid_file().exists()


def test_usage_and_unknown_command(ctl: ModuleType) -> None:
    assert ctl.main([]) == 2
    assert ctl.main(["frobnicate"]) == 2
