# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/) once releases are tagged.

## [Unreleased]

### Added
- **Claude 5.x-native LLM layer**: explicit `thinking` and `output_config.effort` on every request (`LLM_THINKING=auto`, `LLM_EFFORT=medium`,
  `GUARD_EFFORT=low`; Sonnet 5.5 runs `between_tools`, other models adaptive); strict tool use for the four skill tools
  (`LLM_STRICT_TOOLS`); the critic answers under a JSON schema (`CRITIC_SCHEMA`, structured outputs); `ModelRefusal` /
  `ModelRefused` carry the refusal's policy category; run outcome `refused`. 29 new tests (325 total).
- **Luna's persona**: `persona/soul.md` (character, voice, boundaries, examples) with a validated
  runtime block that becomes the head of the system prompt; `load_persona()`.
- **Knowledge bases** under `knowledge/`: a folk toolkit for tales (12 openings, 10 closings,
  8 refrains, 12 helpers, 11 objects, 5 lullaby lines) injected into every non-sensitive tale
  request; 7 new classic plots (Petushok, Lisichka and the wolf, Snegurochka, Puss in Boots,
  Little Red Riding Hood, Cinderella, Sivka-Burka); warm words: 50 compliments, 36 encouragements,
  36 proverbs, and Luna's framing lines. `make kb-check` validates them.
- **Warm-words skill** (`cheer/`): `/cheer` with a mood picker; opt-in scheduled messages
  (weekly / a few times a week / daily) in a daytime window at a personal hour; one-time
  invitation after the first profile; settings screen; "stop" button under every scheduled
  message; atomic slot claiming so replicas never double-send; blocked users are switched off.
  Migration `0003` adds `users.cheer_freq`, `cheer_asked`, `cheer_last_at`, `cheer_recent`.
- **Small talk**: Luna answers thanks, greetings and "hard day" phrases; crisis wording is routed
  to the support text.
- Settings: `CHEER_ENABLED`, `CHEER_TICK_S`, `CHEER_WINDOW_START`, `CHEER_WINDOW_END`,
  `CHEER_BATCH_SIZE`.
- **Repository hygiene**: `AGENTS.md`, `CLAUDE.md`, `HANDOFF.md`, this changelog, a complete
  `.gitignore`, `.gitattributes`, `.editorconfig`, `.dockerignore`, `.env.example`, CI workflow,
  devcontainer, `repomix.config.json`, `tools/unpack_repomix.py`, `tools/patchkit/` (the patch-script
  engine and builder, with its own tests).
- **Docs**: `docs/KNOWLEDGE.md`, `docs/CHEER.md`, `docs/MODUS_OPERANDI.md`,
  `docs/PROJECT_INSTRUCTIONS.md`; README rewritten.
- 108 new tests (294 total); 296 after the toolchain upgrade and its fixes; 325 after the LLM-layer upgrade.

### Fixed
- Per the Claude Platform docs for Sonnet 5.5, the adapter would have run every tale at default adaptive thinking and `high` effort (slow and costly),
  dropped thinking blocks that the API wants back in tool loops and revisions, and let the critic's 700-token budget be spent on
  thinking. None of this had been seen yet because the adapter had only run against a fake transport.
- **Flaky test** `test_auto_mode_lets_model_load_a_skill` (about 15% of runs, since the folk toolkit arrived): the fake model routed on
  the whole prompt, and the toolkit helper «дракончик, который боится щекотки» matched its fear rule, so "Surprise me" went to
  `metaphorical`. The fake model now ignores the `<folk_toolkit>` block when routing; a regression test checks every toolkit entry.
- CI no longer depends on Node 20 actions (`checkout@v4`, `setup-uv@v6`; GitHub scheduled their removal from runners for
  2026-09-16): both are pinned by commit SHA at current majors (`checkout` v7.0.1, `setup-uv` v10.3.2), and `uv sync --locked` fails on a stale `uv.lock`.
- `redis` is bounded to `<8`, matching what aiogram's `RedisStorage` declares (the unbounded `redis>=5.0` let the resolver pick redis-py 8.1.0).
- Patch scripts print the exact `rm` line for *finished* `patch_*.py` files in the repo root (applied and not rolled back, judged by
  `.patch-backups/`); scripts that were never applied, such as the next ones of a chain, are never listed. They delete nothing themselves.
- Patch scripts: `--verify` now reports a missing `uv`/`make` with install hints instead of crashing, and the
  next steps mention installing `uv` when it is not on PATH.
- `.python-version` pins the interpreter so uv does not pick whatever Python the machine has (3.12 at first; 3.14 since the toolchain upgrade).

### Changed
- `TurnResult.assistant_content` keeps every reply block (thinking and redacted thinking verbatim, in order) and the runner replays it
  append-only; the critic gets `max_tokens=1200` plus thinking headroom, and a critic that is refused or cut off is logged and leaves
  `critic_used=False` instead of being silently ignored. `parse_critic` accepts any capitalisation of `code` and `severity`.
- **Python 3.14** everywhere: `.python-version`, `requires-python`, ruff/mypy targets, Dockerfile (`uv:python3.14-trixie-slim` →
  `python:3.14-slim-trixie`, Debian 13), devcontainer (`python:3-3.14-trixie`), README badge. 3.15 is out but aiogram 3.31 caps
  `python<3.15`.
- Dependency floors raised to the versions `make check` ran against: `anthropic>=2.3,<3` (was `>=1.15`), `redis>=7.4,<8`,
  `pyyaml>=6.0.3` (first with 3.14 wheels), pytest 9.1, pytest-asyncio 1.4, ruff 0.17, mypy 2.4, httpx2 2.16. Refresh the lock with
  `uv lock --upgrade`.
- `docker-compose.yml`: PostgreSQL 18 (`postgres:18-alpine`, volume `pgdata18` mounted at `/var/lib/postgresql`, the layout 18+ images
  expect) and Redis 8 (`redis:8-alpine`). PostgreSQL 19 is only at RC (GA planned 2026-11-19), so 18 is the newest release.
- The bot speaks as Luna: feminine voice in all UI strings, bot description and `/help`;
  main menu gains "💛 Тёплые слова"; settings screen shows the warm-words frequency.
- The system prompt starts from Luna's persona instead of an anonymous storyteller.
- Free text outside any dialog is first checked for small talk, then falls back to the hint.
- Classic plots moved from `stories/data/classics.yaml` to `knowledge/tales/classics.yaml`
  (loader updated); 18 → 25 plots.

### Notes
- Scheduled warm words are off for everyone until they opt in; existing users are not messaged.
- Version is not bumped yet: `uv.lock` records the project version; bump together with a tag.

## [0.1.0]

Baseline: aiogram bot with an agentic harness (14 skills, tools, guardrails, critic, traces),
SQLite/PostgreSQL storage, Anthropic adapter, evals, Docker, CI.
