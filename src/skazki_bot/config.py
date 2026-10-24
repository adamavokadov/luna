"""Конфигурация приложения. Значения читаются из переменных окружения и `.env`."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Telegram ---
    bot_token: SecretStr
    run_mode: Literal["polling", "webhook"] = "polling"
    webhook_base_url: str | None = None  # https://bot.example.com
    webhook_path: str = "/telegram/webhook"
    webhook_secret: SecretStr | None = None
    web_host: str = "0.0.0.0"
    web_port: int = 8080
    draft_min_interval: float = Field(default=0.9, ge=0.0)  # пауза между sendMessageDraft, сек.

    # --- Хранилища ---
    database_url: str = "sqlite+aiosqlite:///./data/skazki.db"
    redis_url: str | None = None  # если задан — FSM-состояния живут в Redis

    # --- LLM ---
    llm_provider: Literal["anthropic", "fake"] = "anthropic"
    anthropic_api_key: SecretStr | None = None
    llm_model: str = "claude-sonnet-5-5"
    llm_max_tokens: int = Field(default=4500, ge=500)
    llm_timeout_s: float = Field(default=90.0, gt=0)

    # --- Харнесс (агентный цикл, навыки, guardrails) ---
    guard_model: str = "claude-haiku-5-5"  # дешёвая быстрая модель для LLM-критика
    critic_enabled: bool = True  # LLM-проверка готовой сказки (безопасность, возраст, род, имя)
    harness_max_steps: int = Field(default=4, ge=1, le=8)  # ходов «модель ↔ инструменты»
    harness_max_revisions: int = Field(default=1, ge=0, le=2)  # правок по замечаниям критика
    harness_timeout_s: float = Field(default=180.0, gt=0)  # общий бюджет времени на одну сказку
    skills_dir: str | None = None  # доп. каталог навыков (перекрывает встроенные)

    # --- Продуктовые лимиты ---
    daily_tale_limit: int = Field(default=5, ge=1)
    max_children_per_user: int = Field(default=3, ge=1)
    timezone: str = "Europe/Moscow"  # граница «суток» для дневного лимита
    admin_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)  # без лимитов

    # --- Логи ---
    log_level: str = "INFO"
    log_json: bool = False

    @field_validator(
        "anthropic_api_key",
        "webhook_secret",
        "webhook_base_url",
        "redis_url",
        "skills_dir",
        mode="before",
    )
    @classmethod
    def _empty_means_unset(cls, value: object) -> object:
        # В .env/Codespaces пустая строка — это «не задано»
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _split_admin_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part) for part in value.replace(";", ",").split(",") if part.strip()]
        return value

    @model_validator(mode="after")
    def _check_consistency(self) -> Settings:
        if self.llm_provider == "anthropic" and self.anthropic_api_key is None:
            raise ValueError("ANTHROPIC_API_KEY обязателен при LLM_PROVIDER=anthropic")
        if self.run_mode == "webhook" and not self.webhook_base_url:
            raise ValueError("WEBHOOK_BASE_URL обязателен при RUN_MODE=webhook")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # значения приходят из окружения


class _DatabaseOnlySettings(BaseSettings):
    """Облегчённые настройки для Alembic: ему нужен только URL базы, а не токены."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    database_url: str = "sqlite+aiosqlite:///./data/skazki.db"


def get_database_url() -> str:
    return _DatabaseOnlySettings().database_url
