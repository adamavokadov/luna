<h1 align="center">🌙 Luna</h1>

<p align="center">
  <b>Personal fairy tales for your child, and a few warm words for you.</b><br>
  A Telegram bot in Russian, built on an agentic harness over Claude.
</p>

<p align="center">
  <img alt="Python 3.14" src="https://img.shields.io/badge/python-3.14-3776AB?logo=python&logoColor=white">
  <img alt="aiogram 3" src="https://img.shields.io/badge/aiogram-3.x-2CA5E0?logo=telegram&logoColor=white">
  <img alt="uv" src="https://img.shields.io/badge/deps-uv-DE5FE9">
  <img alt="ruff" src="https://img.shields.io/badge/lint-ruff-D7FF64">
  <img alt="mypy strict" src="https://img.shields.io/badge/types-mypy%20--strict-2A6DB2">
</p>

> **По-русски:** Луна — Telegram-бот, который сочиняет сказки для конкретного ребёнка (имя, возраст,
> любимые герои) и по желанию иногда присылает родителю тёплое слово: комплимент, поддержку или
> пословицу. Интерфейс бота полностью на русском.

The repository and Python package are named `skazki-bot` / `skazki_bot`; the bot's persona is **Luna**.

## What's new

**Unreleased (heading to 0.2.0)** — Luna arrives:

- 🌙 **A personality.** `soul.md` defines who Luna is (kind, understanding, responsive; a girl;
  stress on the *u*: Лу́на). She speaks in the feminine, addresses the reader in gender-neutral
  «вы», answers thanks, greetings and a hard day, and narrates tales from off-stage.
- 📚 **Two knowledge bases.** Tales: 25 classic plots (7 new) plus a *folk toolkit* of openings,
  closings, refrains, helpers and magic objects that now flows into every generated tale.
  Warm words: 50 compliments, 36 encouragements, 36 folk proverbs.
- 💛 **A new skill: warm words.** `/cheer` on request, and, only if the user agrees, a gentle
  message a few times a week or daily, in the daytime, with a visible way to stop.
- 🧰 **Repository hygiene.** `AGENTS.md`, `HANDOFF.md`, `CHANGELOG.md`, a complete `.gitignore`,
  `.env.example`, CI, devcontainer, repomix config, and a documented patch-based workflow.

Details: [`CHANGELOG.md`](CHANGELOG.md).

## Features

| | |
|---|---|
| **14 tale formats** (skills) | 🌙 bedtime · 🦋 metaphorical · 🎒 event preparation · 🧘 relaxation · 🎵 rhymed · 🔁 cumulative · 🧩 riddles · 😄 funny · 🔬 educational · 💛 values · 🎂 celebration · 🔗 sequel · ✨ original · 📖 classic retold |
| **Modes** | "Surprise me" (the model picks a format), choose a format, classic retold, your own idea; quick topics for hard moments ("afraid of the dark", "starting kindergarten") |
| **Child profile** | name, gender (for correct Russian endings), age 2-10, interests, a note; up to 3 profiles |
| **For parents** | where useful, a separate note: how to continue the conversation, riddle answers, facts |
| **Streaming** | live text via `sendMessageDraft`, with a "typing…" fallback |
| **Memory** | remembers 👍/👎 and recent tales: no repeats, can continue a favourite |
| **Warm words** 💛 | compliments, encouragement and proverbs on request or (opt-in) on a gentle schedule |
| **Safety** | layered guardrails: input screen, text checks, LLM critic, one revision, block |
| **Privacy** | `/delete` erases everything; logs and traces carry no names or texts |

## Meet Luna

Luna is a warm, attentive storyteller and a gentle companion. [`soul.md`](src/skazki_bot/persona/soul.md)
is the single source of truth for her character, voice, boundaries and examples; its runtime block
is injected into the system prompt, and tests keep every UI string in her voice (feminine
self-reference, no anonymous "storyteller"). She is honest about being an AI, never flirts or
creates dependency, and is not a therapist.

## How it works

```
Parent ─► handlers (aiogram, FSM) ─► TaleService: limits, memory, persistence, traces
                                          │
                                          ▼
                                     TaleHarness
  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │ 1. Input guard: crisis → support, injection → refusal, sensitive → gentle mode  │
  │ 2. Skills: explicit choice → body in context;  auto → the model calls load_skill │
  │ 3. Persona (soul.md) in the system prompt; folk toolkit in the request          │
  │ 4. Model ↔ tools loop (≤ N steps; every turn streams to sendMessageDraft)       │
  │ 5. Output guard: checks + LLM critic → one revision → block                     │
  │ 6. Trace: steps, tools, tokens, cache, time, issue codes → generation_runs      │
  └─────────────────────────────────────────────────────────────────────────────────┘
        tools: load_skill · read_skill_file · pick_classic · get_recent_tales

CheerScheduler (background) ─► CheerService ─► warm words from the knowledge base ─► opted-in parents
```

- **Skills follow the [Agent Skills](https://agentskills.io/specification) spec** with progressive
  disclosure. Authoring guide: [`docs/SKILLS.md`](docs/SKILLS.md).
- **Least privilege:** an explicit format is a single model turn with no tools.
- **Cost of one tale:** explicit format = 1 main-model call + 1 short critic call; "Surprise me" = 2 +
  critic; a revision adds a call. The critic can be turned off (`CRITIC_ENABLED=false`).

## Knowledge bases

All curated content lives in [`src/skazki_bot/knowledge/`](src/skazki_bot/knowledge) as validated YAML.
Guide: [`docs/KNOWLEDGE.md`](docs/KNOWLEDGE.md).

| Base | Files | Used for |
|---|---|---|
| **Tales** | `tales/classics.yaml` (25 plots), `tales/folk_toolkit.yaml` (58 entries) | the `classic` skill; folk building blocks handed to the model on every (non-sensitive) tale |
| **Warm words** | `cheer/compliments.yaml`, `encouragements.yaml`, `proverbs.yaml`, `frames.yaml` | the cheer skill |

`make kb-check` validates everything; tests enforce the authoring rules (e.g. gender-neutral «вы»).

## Warm words (the cheer skill)

`/cheer` offers a mood picker (hard day · anxious · something isn't working · I did well · just
cheer me up). A one-time invitation after the first profile and **Settings → 💛 Warm words** let
parents opt in to a gentle schedule: weekly, a few times a week, or daily; daytime only, at a
personal hour, with **Not now / Stop** always one tap away. Off by default. Full spec:
[`docs/CHEER.md`](docs/CHEER.md).

## Quick start

### GitHub Codespaces (recommended)

1. Open the repository → **Code → Codespaces → Create codespace**. `postCreateCommand` installs
   dependencies and creates `.env` from `.env.example`.
2. Add Codespaces secrets (**Settings → Secrets and variables → Codespaces**): `BOT_TOKEN` (from
   [@BotFather](https://t.me/BotFather)) and `ANTHROPIC_API_KEY`. No key? Set `LLM_PROVIDER=fake`.
3. Run:

   ```bash
   make run          # migrations + bot (polling)
   make check        # ruff + mypy + pytest + skills + knowledge checks: what CI runs
   make eval         # every format × 3 profiles: size, steps, issues, tokens, time
   ```

> A Codespace sleeps when idle, and the bot with it. For 24/7 operation deploy to a host (below).

### Locally

```bash
make install && cp .env.example .env   # fill in BOT_TOKEN and ANTHROPIC_API_KEY
make run
```

### Production (Docker)

```bash
cp .env.example .env           # BOT_TOKEN, ANTHROPIC_API_KEY; RUN_MODE=webhook if desired
docker compose up --build -d   # bot + PostgreSQL + Redis
```

Webhook mode needs HTTPS: `RUN_MODE=webhook`, `WEBHOOK_BASE_URL`, `WEBHOOK_SECRET`, port `8080`
(liveness: `GET /healthz`). Run the warm-words scheduler in every replica if you like: delivery is
claimed atomically in the database, so no one gets a duplicate.

## Configuration

Full commented list: [`.env.example`](.env.example). Key variables:

| Variable | Default | Purpose |
|---|---|---|
| `BOT_TOKEN` | — | bot token |
| `LLM_PROVIDER` | `anthropic` | `anthropic` or `fake` |
| `ANTHROPIC_API_KEY` | — | Anthropic key |
| `LLM_MODEL` / `GUARD_MODEL` | `claude-sonnet-5-5` / `claude-haiku-5-5` | main model / cheap critic |
| `LLM_EFFORT` / `LLM_THINKING` | `medium` / `auto` | Claude 5.x thinking depth; `auto` = no up-front thinking on Sonnet 5.5, adaptive on other models |
| `GUARD_EFFORT` | `low` | thinking depth of the critic |
| `LLM_STRICT_TOOLS` | `true` | strict tool use for the skill tools (kill switch) |
| `CRITIC_ENABLED` | `true` | LLM check of the finished tale |
| `HARNESS_MAX_STEPS` / `_MAX_REVISIONS` / `_TIMEOUT_S` | `4` / `1` / `180` | harness bounds |
| `SKILLS_DIR` | — | extra skills directory (overrides built-ins) |
| `DAILY_TALE_LIMIT` | `5` | tales per parent per day |
| `DATABASE_URL` | SQLite in `./data` | `postgresql+asyncpg://…` for production |
| `REDIS_URL` | — | FSM state in Redis (needed for several replicas) |
| `RUN_MODE` | `polling` | `webhook` for production |
| `ADMIN_IDS` | — | Telegram ids without limits, with `/stats` |
| `TIMEZONE` | `Europe/Moscow` | day boundary for limits and Luna's daytime window |
| `CHEER_ENABLED` | `true` | master switch for scheduled warm words (users still opt in) |
| `CHEER_WINDOW_START` / `_END` | `10` / `21` | local daytime window |
| `CHEER_TICK_S` / `CHEER_BATCH_SIZE` | `300` / `40` | scheduler cadence and per-tick cap |

## Project layout

```
src/skazki_bot/
  persona/    soul.md (who Luna is) · load_persona()
  knowledge/  tales/{classics,folk_toolkit}.yaml · cheer/*.yaml · validated loaders · `make kb-check`
  cheer/      skills/cheer/SKILL.md · compose · schedule · service · scheduler (warm words)
  harness/    runner (loop) · skills (loader) · tools · guard · prompts · types
  skills/     14 tale skills: <name>/SKILL.md [+ references/]
  llm/        ChatLLM interface · Anthropic adapter (stream, tool use) · fake · parse · sanitize
  services/   tale_service (limits, memory, traces) · streaming (sendMessageDraft)
  stories/    classic-plot loader and selector
  db/         models, repository, run traces
  bot/        handlers/ · keyboards · callbacks · texts (Luna's voice) · smalltalk · middlewares
  evals.py    formats × reference profiles
migrations/   Alembic (0001 base, 0002 skills and traces, 0003 warm-words preferences)
tests/        pytest suite (real handlers, fake LLM, SQLite)
docs/         PLAN · SKILLS · KNOWLEDGE · CHEER · MODUS_OPERANDI · PROJECT_INSTRUCTIONS
tools/        unpack_repomix.py (rebuild a repo from a repomix export) · patchkit/ (patch-script engine and builder)
AGENTS.md  HANDOFF.md  CHANGELOG.md  repomix.config.json
```

## Development

```bash
make check                            # lint + types + tests + skills + knowledge (what CI runs)
make fmt                              # format and autofix
make kb-check                         # validate knowledge bases, persona, cheer skill
make revision m="what changed"        # new migration after editing models
make skills-check dir=./my-skills     # validate your own skills
```

CI runs ruff, mypy `--strict`, pytest, the skill and knowledge checks, and a Docker build. The
migration test fails if models change without a migration.

**Working with AI assistants.** [`AGENTS.md`](AGENTS.md) is the briefing for any coding agent;
[`HANDOFF.md`](HANDOFF.md) is the living state of the project (what is done, what is next, what is
unverified); changes arrive as patch scripts, documented in
[`docs/MODUS_OPERANDI.md`](docs/MODUS_OPERANDI.md); the Claude Project instructions are in
[`docs/PROJECT_INSTRUCTIONS.md`](docs/PROJECT_INSTRUCTIONS.md).

## Docs

| Document | What is in it |
|---|---|
| [`docs/PLAN.md`](docs/PLAN.md) | stack, stages and status, what is verified, risks, roadmap |
| [`docs/SKILLS.md`](docs/SKILLS.md) | how tale skills work and how to add one |
| [`docs/KNOWLEDGE.md`](docs/KNOWLEDGE.md) | knowledge-base layout and authoring rules |
| [`docs/CHEER.md`](docs/CHEER.md) | warm-words skill: behaviour, schedule, privacy, code map |
| [`docs/MODUS_OPERANDI.md`](docs/MODUS_OPERANDI.md) | how changes are made: repomix → patch script → checks → HANDOFF |
| [`docs/PROJECT_INSTRUCTIONS.md`](docs/PROJECT_INSTRUCTIONS.md) | instructions for the Claude Project |

## Roadmap

See [`docs/PLAN.md`](docs/PLAN.md#7-дорожная-карта). Next for Luna: a per-user timezone for warm
words, an optional LLM "personalizing" mode under the same guardrails, and more material in both
knowledge bases.

## Status

Automated: ruff, mypy `--strict`, pytest (fake LLM, Anthropic adapter on a mocked transport,
real handlers on SQLite). **Not yet exercised against the real services**: the live Anthropic API,
Telegram delivery of scheduled messages, PostgreSQL/Redis, `docker build`, and the tone of the
Russian copy as read by a native speaker. The checklist is in [`HANDOFF.md`](HANDOFF.md).
