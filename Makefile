.PHONY: install migrate run test lint fmt typecheck check skills-check kb-check unpack eval smoke revision docker-up

UV ?= uv

install:  ## Установить зависимости (включая dev и redis)
	$(UV) sync --all-extras

migrate:  ## Применить миграции БД
	$(UV) run alembic upgrade head

run: migrate  ## Запустить бота (polling или webhook — см. RUN_MODE в .env)
	$(UV) run python -m skazki_bot

test:
	$(UV) run pytest

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

fmt:
	$(UV) run ruff check . --fix
	$(UV) run ruff format .

typecheck:
	$(UV) run mypy

skills-check:  ## Проверить навыки (встроенные или каталог: make skills-check dir=./my-skills)
	$(UV) run python -m skazki_bot.harness.skills_cli $(dir)

kb-check:  ## Validate the knowledge bases, Luna's persona and the cheer skill
	$(UV) run python -m skazki_bot.knowledge

unpack:  ## Rebuild a repo from a repomix export: make unpack src=repomix-output.xml dst=/tmp/repo
	python3 tools/unpack_repomix.py $(src) $(dst)

smoke:  ## Quick live check: 2 tales (explicit + auto) with the critic; fails if the critic silently did not run
	$(UV) run python -m skazki_bot.evals --smoke

eval:  ## Прогнать форматы на эталонных профилях (LLM_PROVIDER=fake — офлайн; make eval skill=bedtime)
	$(UV) run python -m skazki_bot.evals $(if $(skill),--skill $(skill),)

check: lint typecheck test skills-check kb-check  ## Всё, что гоняет CI

revision:  ## Новая миграция: make revision m="описание"
	$(UV) run alembic revision --autogenerate -m "$(m)"

docker-up:
	docker compose up --build -d
