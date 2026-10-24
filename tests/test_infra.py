"""Инфраструктура: миграции совпадают с моделями, вебхук защищён секретом."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from aiohttp.test_utils import TestClient, TestServer
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from skazki_bot.app import build_web_app
from skazki_bot.db.models import Base
from tests.conftest import App

ROOT = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return cfg


def test_migrations_apply_and_match_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "migrated.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")

    command.upgrade(_alembic_config(), "head")

    engine = sa.create_engine(f"sqlite:///{db_file}")
    with engine.connect() as conn:
        tables = set(sa.inspect(conn).get_table_names())
        assert {"users", "children", "tales"} <= tables
        # Если модели изменили без новой миграции — здесь будет непустой diff
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
    engine.dispose()

    command.downgrade(_alembic_config(), "base")  # откат тоже должен работать


@pytest.mark.filterwarnings("ignore:Detected unknown update type")
async def test_webhook_requires_secret_and_healthz_works(app: App) -> None:
    web_app = build_web_app(app.bot, app.dp, path="/telegram/webhook", secret="s3cr3t")
    async with TestClient(TestServer(web_app)) as http:
        health = await http.get("/healthz")
        assert health.status == 200

        update = {"update_id": 1}
        denied = await http.post("/telegram/webhook", json=update)
        assert denied.status == 401

        wrong = await http.post(
            "/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": "nope"}
        )
        assert wrong.status == 401

        ok = await http.post(
            "/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": "s3cr3t"}
        )
        assert ok.status == 200


@pytest.mark.parametrize("bedtime", [False, True])
async def test_evals_cover_every_skill_for_every_sample_child(
    bedtime: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    from skazki_bot.config import Settings
    from skazki_bot.evals import run_evals

    settings = Settings(bot_token="1:T", llm_provider="fake", _env_file=None)  # type: ignore[call-arg]
    code = await run_evals(settings, [], bedtime=bedtime)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "Ошибок: 0" in out
    for skill in ("metaphorical", "meditation", "rhyme", "original", "auto"):
        if bedtime and skill == "auto":
            continue
        assert skill in out
