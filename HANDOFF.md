# HANDOFF

Living state of the project: what is done, what is decided, what is next, what is **not**
verified. It is the memory between sessions (human or AI). Read it right after `AGENTS.md`.

**Update protocol (every session, no exceptions)**

1. The patch script inserts a dated entry in the *Session log* (section 7). Review it.
2. Refresh the *Snapshot* (1) and *Unverified* (3) lists; move finished items out of *Next steps* (5).
3. Add a line to *Decisions* (4) when a choice was made that a future reader would otherwise
   have to rediscover. Keep entries short and factual.
4. Keep it honest: anything not exercised by a test or a real run goes into *Unverified*.

## 1. Snapshot (update each session)

- **State as of 2026-10-25:** Luna persona, two knowledge bases and the warm-words skill are
  implemented on top of the 0.1.0 harness (patch `0001-luna-foundation`); tooling hardened (`0002`);
  toolchain moved to Python 3.14 with refreshed dependencies and CI actions (`0003`).
- **Quality gate:** `make check` green in the authoring sandbox on Python 3.14.4 (296 tests, ruff, mypy
  `--strict`, skills check, knowledge check).
- **Toolchain:** Python 3.14 (`.python-version`, `requires-python >=3.14`); resolved on 2026-10-25: aiogram 3.31.0,
  anthropic 2.3.0, SQLAlchemy 2.1.6, alembic 1.20.1, pydantic 2.13.5 (aiogram caps `<2.14`), redis-py 7.4.1.
  `uv.lock` is not in exports: the owner refreshes it (`uv lock --upgrade`).
- **DB head:** migration `0003` (warm-words columns on `users`).
- **Content:** 14 tale skills; 25 classic plots; 58 folk-toolkit entries; 50 compliments,
  36 encouragements, 36 proverbs.
- **Version:** `0.1.0` in `pyproject.toml` (not bumped; see `CHANGELOG.md`).

## 2. What works (covered by automated tests)

- Harness loop, skills, guard, critic, traces (unchanged from 0.1.0) plus: persona in the system
  prompt, folk toolkit in the user message (single turn, no tools, skipped for sensitive topics,
  calm entries for bedtime).
- Warm words: composition rules, schedule rules, atomic claiming, delivery, blocked users, flood
  control, invitation exactly once, settings flows, `/cheer` flows, small talk.
- Knowledge bases: schema, authoring rules (gender-neutral «вы», no role words, `{child}` rules,
  emoji, duplicates), toolkit coverage for every age, theme vocabulary.
- Persona: `soul.md` validation; every UI string free of masculine self-reference.

## 3. Unverified / needs a human

1. **Real model output** with the persona and folk toolkit: run `make eval` with a real
   `ANTHROPIC_API_KEY`, read tales for several ages and formats; tune `soul.md` if the tone drifts.
2. **Live Telegram:** scheduled message delivery; rendering of «Лу́на» (combining accent) and of
   the 😮‍💨 button label on all clients.
3. **Native-speaker read of all Russian copy:** `knowledge/cheer/*.yaml`, `bot/texts.py`,
   `persona/soul.md` runtime block. Automated rules catch typical grammar traps, not taste.
4. **PostgreSQL:** migration `0003` is tested on SQLite only; run `alembic upgrade head` and
   `downgrade -1` on a real Postgres.
5. **First CI run and first Codespace rebuild on the new toolchain:** `ci.yml` now pins `actions/checkout` v7.0.1 and
   `astral-sh/setup-uv` v10.3.2 by SHA and syncs with `--locked`; the devcontainer uses
   `mcr.microsoft.com/devcontainers/python:3-3.14-trixie`. The SHAs were verified as real commits with `git fetch`;
   the image tag was confirmed from public sources only. None of it has run on GitHub yet. (The infra dotfiles are
   now in the export, so the old "created only if missing" worry is closed.)
6. **Crisis text for adults:** free-text crisis wording now routes to `texts.CRISIS_SUPPORT`,
   whose contacts are written for child safety (112 and the children's helpline). Owner to decide
   whether adults in distress need a different message.
7. **Docker build and compose stack** (new bases `uv:python3.14-trixie-slim` and `python:3.14-slim-trixie`, `postgres:18-alpine`,
   `redis:8-alpine`; Docker is not available in the authoring sandbox, only the builder's `uv sync --frozen --no-dev --extra redis
   --no-editable` was replayed on 3.14) and webhook mode with the scheduler running in several replicas.
8. **Real Anthropic API with SDK 2.x:** the adapter passes its tests against a fake HTTP transport on `anthropic` 2.3.0
   (the floor used to be 1.15); streaming and tool use against the live API are untested. Same for `RedisStorage` with
   redis-py 7.4.1: constructed in a smoke test, never connected to a server.
9. **Python patch level:** the sandbox ran 3.14.4; the Docker and Codespace images carry newer 3.14.x.

## 4. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | Persona lives in `src/skazki_bot/persona/soul.md`; its runtime block heads the system prompt | One source of truth; ships in the wheel and the Docker image (which copies only `src`) |
| D2 | UI voice enforced by tests (feminine self-reference, no "storyteller") | Prevents silent drift when texts are edited |
| D3 | All curated data under `knowledge/`; classics moved from `stories/data/` | One place for content; loaders validate with pydantic |
| D4 | `cheer` is a *companion skill* with its own validator, not part of `SkillRegistry` | Zero ripple on the tale catalog, menus, counts and tests |
| D5 | Warm words come from the curated KB, not the LLM | Free, instant, deterministic, safe; LLM personalization deferred |
| D6 | Opt-in, default off, one invitation after the first profile, existing users not messaged | Consent for proactive messages |
| D7 | Gaps live in `SKILL.md` metadata; window/tick/batch in settings; personal hour = `user_id % window` | Cadence is content; operations are config; load is spread |
| D8 | Slots claimed with an atomic `UPDATE` | Safe with several replicas, no extra infrastructure |
| D9 | Folk toolkit is prompt data with its own RNG, skipped for sensitive topics | Keeps single-turn/no-tools principle; does not disturb classic selection |
| D10 | Reader addressed as gender-neutral «вы»; no role words; `{child}` nominative only | The reader's and child's grammatical gender are unknown at message time |
| D11 | Changes ship as patch scripts; scripts and repomix exports are not committed | Reproducible, reviewable, no repo noise (`/patch_*.py` is ignored) |
| D12 | Small talk is regex-based and deterministic; crisis wording wins | Cheap, predictable, safe |
| D13 | One timezone (`TIMEZONE`) for everyone | Simplicity; per-user timezone is a roadmap item |
| D14 | Version not bumped | `uv.lock` records it; bump together with a tag |
| D15 | `.python-version` pins the interpreter (3.12 at the time) | A Codespace ships its own Python; uv must not pick it by accident. *Version superseded by D16* |
| D16 | Python 3.14 (not 3.15) | 3.15.0 is out (2026-10), but aiogram 3.31 declares `python<3.15`; 3.14 also matches the Codespace default |
| D17 | Floors in `pyproject.toml` = versions `make check` ran against; `anthropic>=2.3,<3`, `redis>=7.4,<8` | Reproducible without a lock; `redis<8` follows aiogram's `RedisStorage` declaration |
| D18 | CI actions pinned by commit SHA (+ version comment); `uv sync --locked` in CI | `setup-uv` v8+ has no floating tags; a stale lock must fail loudly |
| D19 | `postgres:18-alpine` (volume `pgdata18` at `/var/lib/postgresql`) and `redis:8-alpine` in compose | PG 19 is RC only (GA planned 2026-11-19), 18 is the newest release; a new volume name leaves any old PG 17 volume untouched; Redis only holds FSM state |

## 5. Next steps (prioritized)

1. After patch 0003: `uv lock --upgrade && uv sync --all-extras && make check`, commit `uv.lock` with the patch, rebuild the
   Codespace container (Python 3.14 image), delete finished patch scripts (`docs/MODUS_OPERANDI.md`), watch the first CI run.
2. `make run` (fake LLM is fine) and click through: first profile → invitation, `/cheer`, Settings → warm words, small talk phrases.
3. `docker compose up --build -d` once: PostgreSQL 18 and Redis 8 have never been started with this stack (item 7 below).
4. BotFather: set the bot's name to «Луна» and an avatar (description/commands refresh at startup).
5. `make eval` with a real key (SDK 2.x, item 8 above); read the tales; adjust persona or prompts.
6. Native-speaker read-through of Russian copy; extend the KBs (target: 100+ compliments).
7. Per-user timezone for warm words (store an offset or IANA name; ask during onboarding).
8. Decide on a LICENSE and add it.
9. Optional LLM "personalizing" mode for warm words, bounded by the same guard checks.
10. Roadmap items in `docs/PLAN.md` section 7.

## 6. Manual steps for the owner

- Run the patch from the repo root in Codespaces (`docs/MODUS_OPERANDI.md`), then `make check`. If it changed dependencies,
  run `uv lock --upgrade` first and commit `uv.lock` too (exports and patches never carry it).
- Commit (suggested message is printed by the script); do **not** commit the patch script.
- Codespaces secrets: `BOT_TOKEN`, `ANTHROPIC_API_KEY`.
- BotFather: `/setname` Луна, `/setuserpic`.

## 7. Session log

Newest first. Entries are inserted by the patch scripts.

<!-- HANDOFF:LOG:BEGIN -->

### 2026-10-25 — patch 0003-python-314-toolchain

**Goal:** check how patches 0001 and 0002 landed, then upgrade the toolchain (Python and everything around it).

**Audit of 0001/0002 (from the repomix export):** every file and behaviour the two entries describe is present (docs, persona, knowledge, cheer skill, migration `0003`, infra dotfiles, `.python-version`, the engine's `uv`/`make` hint and its tests); the classics file moved; the baseline `make check` on the untouched export was green (294 tests), though one test in it was flaky (below). Both patches are applied. Old `patch_*.py` files and `.patch-backups/` are excluded from exports by design, so they were not inspected; patches never delete themselves, so leftovers are expected, not a failed application.

**Changed**
- Python 3.14: `.python-version`, `requires-python >=3.14`, ruff `py314`, mypy 3.14, Dockerfile (`uv:python3.14-trixie-slim` → `python:3.14-slim-trixie`), devcontainer (`python:3-3.14-trixie`), README badge, docs. 3.15 is out but aiogram 3.31 declares `python<3.15` (D16).
- Dependencies: floors raised to what `make check` ran against; `anthropic>=2.3,<3` (major jump from `>=1.15`), `redis>=7.4,<8` (aiogram's `RedisStorage` cap; the resolver had been free to pick redis-py 8.1.0), `pyyaml>=6.0.3` (3.14 wheels), current pytest, pytest-asyncio, ruff, mypy, httpx2.
- CI: `actions/checkout` v7.0.1 and `astral-sh/setup-uv` v10.3.2 pinned by commit SHA (Node 24; `setup-uv` has no floating tags since v8), `uv sync --locked` (D18).
- **Flaky test fixed:** `test_auto_mode_lets_model_load_a_skill` failed in 6 of 40 runs. Cause: `FakeLLM` routed on the whole prompt, and the folk-toolkit helper `hp_dragonet` («боится щекотки») matched its fear rule whenever the unseeded toolkit RNG drew it, so "Surprise me" went to `metaphorical`. `FakeLLM` now strips the `<folk_toolkit>` block before routing; a regression test walks every toolkit entry and fails without the fix.
- Patch engine: next steps print the exact `rm` line for *finished* `patch_*.py` files in the repo root (applied and not rolled back, judged by `.patch-backups/`), never for scripts that were not applied yet (the next ones of a chain); nothing is deleted by the patch. One test covers finished, pending and rolled-back scripts.
- Docs: AGENTS.md (stack, `uv lock` rule, upgrade recipe, new pitfalls: aiogram caps, lock not in exports, SHA-pinned actions, PG 18 volume change, stale patch scripts; testing rule: randomness must not decide a test), MODUS_OPERANDI.md (cleanup section, `--locked` row, lock note), PROJECT_INSTRUCTIONS.md (Python 3.14), PLAN.md, CHANGELOG, HANDOFF (snapshot, unverified list, D15 superseded, D16-D19).
- `docker-compose.yml`: `postgres:18-alpine` on a new `pgdata18` volume mounted at `/var/lib/postgresql` (the 18+ layout; any old PG 17 volume is left alone) and `redis:8-alpine` (D19). PostgreSQL 19 is RC only, GA planned 2026-11-19.

**Verified (authoring sandbox):** `make check` green on Python 3.14.4 with the refreshed lock (296 tests, ruff, mypy `--strict`, skills and knowledge checks); the flaky test: 6 failures in 40 runs before the fix, 0 in 60 after, and 10 consecutive full-suite runs green; the suite also passes with deprecation and resource warnings as errors; the Dockerfile builder's `uv sync --frozen --no-dev --extra redis --no-editable` replayed on 3.14 and the knowledge and skills checks run from that non-editable install; `RedisStorage` constructs with redis-py 7.4.1; both pinned action SHAs fetched as real commits; the patch itself applied to a fresh copy of the export (dry run, apply, second run, rollback, anchor drift).

**Unverified:** see section 3, items 5, 7, 8 and 9 (first CI run, Docker build and the PostgreSQL 18 / Redis 8 compose stack, live Anthropic API with SDK 2.x, newer 3.14.x patch levels). `uv.lock` is not in the export, so the owner's lock was never seen; it must be refreshed locally.

**Next:** `uv lock --upgrade && uv sync --all-extras && make check`, commit with `uv.lock`, rebuild the Codespace container, delete finished patch scripts, watch the first CI run; start the compose stack once (D19).


### 2026-10-25 — patch 0002-verify-uv-hint

**Goal:** fix a failure reported after patch 0001: `--verify` crashed with `FileNotFoundError: 'uv'` in a Codespace that had no `uv` on PATH (it was created before `.devcontainer/` existed, and ships Python 3.14).

**Changed**
- Patch engine (`tools/patchkit/engine.py.tmpl`): `--verify` checks for `uv` and `make`, prints install hints and exits 2 instead of a traceback (the patch itself stays applied); next steps mention `pip install uv` when `uv` is missing.
- `.python-version` pins Python 3.12 (created only if missing) so uv does not pick the Codespace's 3.14.
- Tests for both behaviours; docs (`MODUS_OPERANDI.md` troubleshooting row, `AGENTS.md` setup note), decision D15.

**Verified (authoring sandbox):** `make check` green (294 tests); patch 0002 applied on a copy of the post-0001 tree.

**Unverified:** a first `uv sync` under Python 3.12 inside the owner's Codespace (uv downloads 3.12 on demand); dependency resolution on Python 3.14 was never tried.

**Next:** `pip install uv`, `uv sync --all-extras`, `make check`, then the click-through in section 5.


### 2026-10-24 — patch 0001-luna-foundation

**Goal:** give the bot a personality (Luna), build two knowledge bases, add a warm-words skill, and bring the repository to a documented, AI-friendly state.

**Changed**
- Persona: `persona/soul.md` + loader; system prompt starts from it; every UI string in Luna's feminine voice (tested); main menu and settings gain warm-words entries; small talk for thanks/greetings/hard day.
- Knowledge: `knowledge/` with 25 classic plots (7 new, file moved from `stories/data/`), a folk toolkit used in every non-sensitive tale, and 122 warm words; `make kb-check`.
- Cheer skill: `/cheer`, opt-in schedule, scheduler task in `app.run`, atomic slot claiming, migration `0003`.
- Repo: `AGENTS.md`, `CLAUDE.md`, `HANDOFF.md`, `CHANGELOG.md`, `.gitignore` (merged), `.env.example`, CI, devcontainer, repomix config, `tools/unpack_repomix.py`, `docs/*`, README rewritten.

**Verified (authoring sandbox):** `make check` green: 292 tests, ruff, mypy `--strict`, skills and knowledge checks; migration 0003 up/down on SQLite.

**Unverified:** see section 3 above (real model output, live Telegram, Postgres, CI/devcontainer first run, native-speaker read).

**Next:** apply, `make check`, click through the flows, BotFather name and avatar, `make eval` with a real key (section 5).

<!-- HANDOFF:LOG:END -->
