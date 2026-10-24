# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app

# Сначала зависимости — слой кэшируется, пока не меняется uv.lock
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra redis --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra redis --no-editable


FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/app/.venv/bin:$PATH"
RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
    && mkdir -p /app/data && chown -R app:app /app
WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations ./migrations
USER app
VOLUME ["/app/data"]
# Миграции при каждом старте безопасны (идемпотентны)
CMD ["sh", "-c", "alembic upgrade head && python -m skazki_bot"]
