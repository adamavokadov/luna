# AGENTS.md

Briefing for any AI coding agent (Claude, Codex, Copilot, Cursor...) working on this repository.
Humans: the same file is the fastest way to understand the project's rules.

**Read in this order:** this file → `HANDOFF.md` (current state, next steps, what is unverified)
→ `docs/PLAN.md` (stack, stages, risks, roadmap) → `docs/MODUS_OPERANDI.md` (how changes ship).

## 1. Project snapshot

- **What:** a Telegram bot, **Luna**, that writes personal Russian-language fairy tales for one
  specific child (name, gender, age 2-10, interests) and, if the parent opts in, sends the parent
  warm words (compliments, encouragement, proverbs).
- **Repo / package:** `skazki-bot` / `skazki_bot` (do not rename; the persona is Luna).
- **Stack:** Python 3.14, uv, aiogram 3, SQLAlchemy 2 async + Alembic (SQLite dev / PostgreSQL
  prod), pydantic-settings, structlog, Anthropic Messages API behind a `ChatLLM` interface,
  optional Redis for FSM state. Quality: ruff, mypy `--strict`, pytest.
- **Core idea:** an agentic *harness* (`harness/`) runs a model↔tools loop over *skills*
  (`skills/<name>/SKILL.md`, Agent Skills format) with layered guardrails. Luna's *persona*
  (`persona/soul.md`) and *knowledge bases* (`knowledge/`) are data, editable without code.
- **Owner:** Adam (Russian-speaking; the bot's audience is Russian-speaking parents).

## 2. Golden rules

1. **Never break `make check`.** It is the definition of done: ruff, ruff format, mypy
   `--strict`, pytest, skills check, knowledge check.
2. **Language policy.** Think, write code, comments, docstrings, commit messages and docs in
   **English**. **Everything the bot says is Russian** (UI texts, prompts sent to the model, KB
   content, skill bodies). Existing Russian comments may stay; do not mass-translate them. New
   or touched code gets English comments.
3. **Luna's voice is a contract.** Feminine self-reference («я рада»), polite «вы» addressed to the
   reader in **gender-neutral forms**, no role words (мама/папа). See section 7 and
   `src/skazki_bot/persona/soul.md`.
4. **Proactive messages are opt-in, daytime-only, stoppable.** Never add a message that the user
   did not ask for or consent to. Never use guilt, absence, streaks or FOMO.
5. **Privacy of children.** No names, tale texts or free-text user input in logs or traces. The
   only personal field warm words may use is the child's first name, as a nominative subject.
6. **Safety is layered and deterministic first.** Do not weaken `harness/guard.py` or the
   safety rules in `harness/prompts.py` to make a test pass.
7. **Schema changes need a migration** (`make revision m="..."`); the migration test enforces
   model/migration equality, and downgrade must work.
8. **Secrets never enter git.** `.env` is ignored; `.env.example` has placeholders only.
9. **Small, verified steps.** Do not claim something works unless a test or a run shows it.
   Say plainly what is unverified (see `HANDOFF.md`).
10. **Keep `HANDOFF.md` current** (section 11). It is the memory between sessions.

## 3. Setup and commands

```bash
make install            # uv sync --all-extras
cp .env.example .env    # fill BOT_TOKEN, ANTHROPIC_API_KEY (or LLM_PROVIDER=fake)
make run                # migrations + bot (polling)
make check              # lint + typecheck + test + skills-check + kb-check  (== CI)
make fmt                # ruff --fix + ruff format
make test               # pytest only
make kb-check           # validate knowledge bases, persona, cheer skill
make skills-check       # validate tale skills (dir=./path for custom ones)
make eval               # every format x 3 profiles (LLM_PROVIDER=fake works offline)
make revision m="..."   # new Alembic migration after model changes
make unpack src=repomix-output.xml dst=/tmp/repo   # rebuild a repo from a repomix export
```

`uv` must be on PATH (`pip install uv` if it is missing); `.python-version` pins Python 3.14 and uv fetches it on demand.
After editing dependencies in `pyproject.toml`, run `uv lock` (or `uv lock --upgrade` to refresh everything) and commit `uv.lock`;
CI runs `uv sync --locked` and fails when the lock is stale.

`LLM_PROVIDER=fake` runs everything offline with canned stories (skill routing and tools still work).

## 4. Repository map

```
src/skazki_bot/
  app.py            wiring: bot, dispatcher (workflow data: settings, sf, tales, skills, cheer),
                    commands, startup, polling/webhook, cheer scheduler task
  config.py         pydantic-settings (env names = field names in UPPER_CASE)
  persona/          soul.md (Luna's character; runtime block -> system prompt) + loader
  knowledge/        tales/{classics,folk_toolkit}.yaml, cheer/{compliments,encouragements,proverbs,frames}.yaml
                    + validated loaders (tale_kb.py, cheer_kb.py); `python -m skazki_bot.knowledge`
  cheer/            warm words: skills/cheer/SKILL.md, skill.py, schedule.py, compose.py,
                    service.py (DB, no Telegram), scheduler.py (background loop + delivery)
  harness/          runner.py (loop), skills.py (loader/registry), tools.py, guard.py,
                    prompts.py (system prompt = persona + craft rules), types.py
  skills/           14 tale skills (<name>/SKILL.md [+ references/])
  llm/              base.py (ChatLLM), anthropic_llm.py, fake.py, parse.py, sanitize.py
  services/         tale_service.py (limits, memory, traces), streaming.py (sendMessageDraft)
  stories/          library.py + selector.py for classic plots (data: knowledge/tales/classics.yaml)
  db/               base.py (engine/session), models.py, repo.py (all queries live here)
  domain/           enums, age rules, interests catalog, text helpers
  bot/              handlers/ (start, onboarding, tale, profile, history, settings, cheer, errors,
                    fallback), keyboards.py, callbacks.py, texts.py, smalltalk.py, middlewares.py,
                    states.py, utils.py, views.py, delivery.py, formatting.py
migrations/versions/  0001 base, 0002 skills+traces, 0003 warm-words columns on users
tests/              conftest.py (App, Client, RecordingSession), fakes.py (ScriptedChat, make_story), test_*.py
docs/               PLAN, SKILLS, KNOWLEDGE, CHEER, MODUS_OPERANDI, PROJECT_INSTRUCTIONS
tools/              unpack_repomix.py; patchkit/ (patch-script engine + builder, tested in tests/test_patchkit.py)
```

## 5. Architecture essentials

- **Request path:** handler → `TaleService` (daily limit, memory, saving, traces) → `TaleHarness`
  (input guard → skill selection → model↔tools loop with streaming → output guard + critic →
  one revision → trace). An explicit format is a single model turn with **no tools** (least
  privilege); "Surprise me" lets the model call `load_skill`.
- **Skills (tale formats):** `SkillRegistry` loads `skills/*/SKILL.md` with strict validation;
  the catalog is in the system prompt, bodies on demand. `cheer` is a *companion* skill with its
  own validator; it is never in the tale catalog.
- **LLM layer (Claude 5.x), `llm/anthropic_llm.py`:** every request states its thinking and effort explicitly
  (`LLM_THINKING=auto` → `between_tools` on Sonnet 5.5, adaptive elsewhere; `LLM_EFFORT=medium`; critic on
  `GUARD_EFFORT=low`). `TurnResult.assistant_content` keeps *every* reply block, thinking blocks verbatim, and the
  runner replays it append-only. Skill tools use strict tool use; the critic answers under a JSON schema
  (`CRITIC_SCHEMA`, structured outputs). A refusal becomes `ModelRefusal` (policy category only, never content) →
  `ModelRefused` → run outcome `refused` and the same gentle message as a guard block.
- **System prompt** = `persona/soul.md` runtime block + craft rules (`harness/prompts.py`).
  Budget: keep it under ~14k characters (a test enforces it; it is ~7k today).
- **Folk toolkit:** `harness/runner.py` adds an optional `<folk_toolkit>` block (opening,
  closing, refrain, helper, magic object) to the user message, from its own RNG, skipped for
  sensitive topics; bedtime requests get calm entries only.
- **Warm words:** `CheerService.claim_due` selects due users (window, personal hour, minimum gap)
  and claims each with an atomic `UPDATE` (safe across replicas); `CheerScheduler` sends; blocked
  users are switched off. On-demand `/cheer` uses the same composer.
- **Persistence:** every query goes through `db/repo.py`. Timestamps are timezone-aware UTC via
  `UTCDateTime`. JSON columns are replaced, not mutated in place.
- **Dispatcher DI:** handlers receive `user` (middleware), `sf`, `settings`, `tales`, `skills`,
  `cheer` by parameter name. Router order matters: `fallback` must stay last.

## 6. Code conventions

- Python 3.14, `from __future__ import annotations` (kept on purpose, harmless on 3.14), full type hints, mypy `--strict` clean.
  Line length 100 (ruff format decides). Async everywhere that touches I/O.
- Pydantic models for external/data-file schemas (`extra="forbid"`); frozen dataclasses for
  internal value objects.
- Telegram HTML parse mode is on by default: **escape anything user- or data-derived** with
  `aiogram.html.quote` (UI text constants may contain `<b>`/`<i>`). Callback data is capped at
  64 bytes (aiogram `CallbackData` classes in `bot/callbacks.py`; keep fields short).
- `show(event, bot, text, markup, fresh=False)` edits the message for callbacks and sends for
  messages; use `fresh=True` when the old message must stay.
- UI strings live in `bot/texts.py` (Russian); keyboards in `bot/keyboards.py`. No Russian text
  inline in handlers except trivial labels.
- Log with `structlog` (`get_logger(__name__)`), event names in snake_case, **no PII**.
- No new dependencies without a strong reason; if added, update `pyproject.toml` and `uv.lock`.
- Prefer data over code: new formats, plots, phrases and persona tweaks go in YAML/Markdown.

## 7. Luna: persona and voice

Source of truth: `src/skazki_bot/persona/soul.md` (English notes + a Russian runtime block).

- Traits: **kind, understanding, responsive**; calm, lightly playful, honest. A girl: «я рада»,
  «я подготовила», «я не поняла». The stress mark (Лу́на, combining U+0301) appears only in the
  welcome text and the bot description.
- To the reader: polite «вы», gender-neutral predicates («вы справляетесь», «вы молодец»); no
  «вы добрая/добрый», no «устал(а)», no мама/папа/мать/отец.
- Short (1-3 sentences), at most two emojis (🌙 ✨ 💛 🌿 🌱 ☀️), no exclamation chains, no officialese.
- Boundaries: honest about being an AI, no romance or exclusivity, no dependency mechanics, not a
  therapist, no judgment of parenting. Crisis wording → `texts.CRISIS_SUPPORT`, no chit-chat.
- Changing the persona: edit `soul.md` (and `texts.py` if wording changes), run `make check`.
  `tests/test_persona.py` scans every UI string for masculine self-reference.

## 8. Knowledge bases

Full guide: `docs/KNOWLEDGE.md`. Essentials:

- `knowledge/tales/classics.yaml`: synopses only (never reproduce protected texts); fields and
  theme vocabulary are validated; frightening endings are softened via `ending_hint`.
- `knowledge/tales/folk_toolkit.yaml`: openings, closings, refrains, helpers, objects, lullabies;
  each entry has age range, `calm`, optional themes. Tests require every age 2-10 to be servable.
- `knowledge/cheer/*.yaml`: ids `cm`/`en`/`pr` + digits, `moods`, `times`, `{child}` rules.
  Tests reject role words, gendered predicates after «вы», `(а)` suffixes, `{child}` after a
  preposition, emoji in items, duplicates, proverbs without a note.
- After editing any KB file: `make kb-check && make test`.

## 9. Testing guide

- Handlers are tested end to end with the `client` fixture (`tests/conftest.py`): it feeds real
  updates to the real dispatcher with `LLM_PROVIDER=fake`, SQLite, and a `RecordingSession` that
  records every Bot API call (`sent_texts()`, `edited_texts()`, `last_markup_data()`).
- The harness is tested with `ScriptedChat` (`tests/fakes.py`): scripted model turns, inspect
  `chat.calls`.
- Database-level tests build a throwaway SQLite engine (`tests/test_cheer.py::env` is a template).
- Time-dependent logic takes `now` explicitly; do not sleep in tests.
- Randomness must not decide a test's outcome. `FakeLLM` routes skills with regexes over the request only (the random
  `<folk_toolkit>` block is stripped first); a toolkit entry that merely mentions a trigger word once failed ~15% of runs.
  When a test fails once and passes on re-run, find the unseeded RNG or time source instead of re-running.
- When you add a handler or a setting, add a flow test. When you add KB content, the existing
  rule tests already cover it; add rules there when you add a new rule to the docs.
- Run a single file: `uv run pytest tests/test_cheer.py -q`.

## 10. Recipes

| Task | Steps |
|---|---|
| Add a tale format | New `skills/<name>/SKILL.md` (spec in `docs/SKILLS.md`), `make skills-check`, update the expected set in `tests/test_skills.py`, `docs/PLAN.md` |
| Add warm words | Append to `knowledge/cheer/*.yaml` following the rules, `make kb-check && make test` |
| Add a classic plot | Append to `knowledge/tales/classics.yaml`, keep `id` short, `make test` |
| Add a user setting | Column in `db/models.py` + migration + repo function + handler + keyboard/text + flow test |
| Add a UI text | `bot/texts.py` in Luna's voice; the persona test checks it automatically |
| Change model, thinking or effort | `LLM_MODEL` / `LLM_THINKING` / `LLM_EFFORT` (see `config.py`); levels are recalibrated per model, so run `make eval` with a real key and compare length, quality and `/stats` cost before keeping a change |
| Change prompts | `harness/prompts.py` / `persona/soul.md`; keep `len(system) < 14000`; run `make eval` with a real key and read the output |
| Upgrade Python or dependencies | Edit pins in `pyproject.toml` (floor = the version `make check` ran against), `uv lock --upgrade`, `uv sync --all-extras`, `make check`; commit `uv.lock`. Read the aiogram caps in section 12 first |
| Add a scheduled behaviour | Put pure rules in a module, DB access in `service.py`, delivery in a scheduler; opt-in, daytime, stoppable, atomic claim |

## 11. Workflow, HANDOFF and definition of done

Changes ship as **patch scripts** run in GitHub Codespaces (see `docs/MODUS_OPERANDI.md`):
repomix export → plan → implement and verify in a sandbox → one idempotent `patch_NNNN_<slug>.py`
(built with `tools/patchkit/build_patch.py`) → owner runs it with `--dry-run`, then for real, then `make check` → commit.

**Definition of done for every change:**

1. `make check` is green.
2. New behaviour has tests; new data passes `make kb-check`.
3. Docs touched where behaviour changed (`README.md`, `docs/*`, this file if rules changed).
4. `CHANGELOG.md` updated under `[Unreleased]`.
5. **`HANDOFF.md` updated**: the session-log entry (the patch script inserts it), the snapshot,
   next steps, and the "unverified" list. If you learned a durable rule, put it here or in
   `soul.md`, not only in chat.

## 12. Pitfalls we already hit or avoided

- **Claude 5.5 thinks unless told otherwise** (adaptive, effort `high`). Always send `thinking` and `output_config.effort`.
  `between_tools` is the lowest setting and exists on Sonnet 5.5 only (it rejects `disabled`, and `xhigh`/`max` with
  `between_tools`); Haiku 5.5 knows adaptive only. `max_tokens` covers thinking, so adaptive thinking gets headroom in the adapter.
- **Never filter reply blocks.** Thinking blocks (empty text, a signature) must go back unmodified with tool results, and the
  history must stay append-only (`system`, `tools` and earlier messages unchanged), or the API returns 400.
- Removed on Claude 5.x: `temperature`/`top_p`/`top_k`, assistant prefill, `budget_tokens`; Sonnet 5.5 also rejects forced
  `tool_choice`. Use `auto` plus strict tools or structured outputs.
- **Strict tools and structured outputs accept a JSON Schema subset:** every object closed (`additionalProperties: false`), no
  `minimum`/`maximum`/length constraints, at most 20 strict tools and 24 optional parameters per request. `tests/test_llm_config.py`
  checks this; `LLM_STRICT_TOOLS=false` is the kill switch. A structured reply is valid only if `stop_reason` is not `refusal` or
  `max_tokens` (the adapter raises), enum values may differ in capitalisation, and a field that asks for reasoning can trigger a
  `reasoning_extraction` refusal.
- Claude 5.x counts about 30% more tokens than 4.x for the same text; re-check `LLM_MAX_TOKENS` and cost after a model change.
- `.gitignore` must anchor runtime data as `/data/`; a bare `data/` hides package data dirs.
- `uv.lock` is committed (Dockerfile uses `--frozen`); do not ignore it.
- SQLAlchemy `rowcount` needs `# type: ignore[attr-defined]` under mypy strict (existing pattern).
- Alembic: new NOT NULL columns need `server_default`; use `batch_alter_table` for SQLite.
- aiogram: stacking `@router.callback_query(...)` decorators registers one handler for several
  filters (used in `bot/handlers/cheer.py`).
- A fallback handler that answers every text must be registered last and must not shadow FSM states.
- Russian grammar is gendered: never write a predicate about the reader or the child without
  checking it against the rules above.
- `repomix` skips what `.gitignore` ignores; patch scripts and exports are ignored by design.
- `uv.lock` is not part of repomix exports or patch scripts (the builder skips it). A patch that changes dependencies cannot ship the lock:
  the owner runs `uv lock --upgrade` and commits it; CI (`--locked`) catches a forgotten lock.
- aiogram declares upper bounds that cap everything else: `python<3.15`, `pydantic<2.14`, `aiohttp<3.15`, and `redis<8` for its
  RedisStorage. Check its metadata before raising Python or those libraries; the Python target stays 3.14 until aiogram allows 3.15.
- GitHub Actions in `ci.yml` are pinned by commit SHA with a version comment: `astral-sh/setup-uv` publishes immutable tags only
  (no floating `@v10`). Verify a SHA with `git ls-remote --tags <repo>` before changing it.
- Patch scripts never delete anything, themselves included. Delete finished ones after committing: an old patch with an
  overwrite-mode step (e.g. a rewritten README) would silently revert later edits if run again.
- PostgreSQL 18+ Docker images keep data in `/var/lib/postgresql/<major>/docker` (volume mounted at `/var/lib/postgresql`).
  `docker-compose.yml` uses 18 with a volume named `pgdata18`; for the next major use a new volume name plus `pg_dump`/`pg_restore`
  (or `pg_upgrade`), never a bare tag bump over an existing volume.

## 13. Not verified yet (see `HANDOFF.md` for the live list)

Real Anthropic output quality, live Telegram delivery of scheduled messages, PostgreSQL/Redis,
`docker build`, GitHub Actions run, and a native-speaker read of all Russian copy.
