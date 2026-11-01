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

- **State as of 2026-11-01:** Luna persona, two knowledge bases and the warm-words skill are
  implemented on top of the 0.1.0 harness (patch `0001-luna-foundation`); tooling hardened (`0002`);
  toolchain moved to Python 3.14 with refreshed dependencies and CI actions (`0003`); LLM layer made native to
  Claude 5.5 (`0004`): explicit thinking and effort, thinking blocks kept, strict tools, structured critic, refusal handling;
  `make smoke` live check (`0005`); world folk sources as a knowledge base (`0006`) that the bot now picks from automatically (`0007`); more plots (`0008`); the offline model's repeating tale fixed, a repetition check in the output guard and Luna's avatar (`0009`).
- **Quality gate:** `make check` green in the authoring sandbox on Python 3.14.4 (420 tests, ruff, mypy
  `--strict`, skills check, knowledge check).
- **Toolchain:** Python 3.14 (`.python-version`, `requires-python >=3.14`); resolved on 2026-10-25: aiogram 3.31.0,
  anthropic 2.3.0, SQLAlchemy 2.1.6, alembic 1.20.1, pydantic 2.13.5 (aiogram caps `<2.14`), redis-py 7.4.1.
  `uv.lock` is not in exports: the owner refreshes it (`uv lock --upgrade`).
- **DB head:** migration `0003` (warm-words columns on `users`).
- **Content:** 14 tale skills; 25 classic plots; 81 world folk plots (491 beats, 14 collections, 35 cultures); 58 folk-toolkit entries;
  50 compliments, 36 encouragements, 36 proverbs.
- **Version:** `0.1.0` in `pyproject.toml` (not bumped; see `CHANGELOG.md`).

## 2. What works (covered by automated tests)

- Harness loop, skills, guard, critic, traces (unchanged from 0.1.0) plus: persona in the system
  prompt, folk toolkit in the user message (single turn, no tools, skipped for sensitive topics,
  calm entries for bedtime).
- Warm words: composition rules, schedule rules, atomic claiming, delivery, blocked users, flood
  control, invitation exactly once, settings flows, `/cheer` flows, small talk.
- Knowledge bases: schema, authoring rules (gender-neutral «вы», no role words, `{child}` rules,
  emoji, duplicates), toolkit coverage for every age, theme vocabulary.
- World folk sources in the harness: which formats get a plot, a parent's idea wins, value ideas steer by motif, sensitive topics
  and the kill switch turn it off, every age by day and at bedtime gets a fitting plot, history/likes steer the pick, the id is
  recorded (`seed_id`, mode `folk`), classic selection is unchanged.
- World folk sources: schema and links to collections, no quotation marks or dialogue dashes, `scary >= 2` needs an
  `ending_hint`, every age 2-10 (daytime and bedtime) can be served, retrieval is deterministic, age/bedtime-safe and
  prefers themes, motifs and unseen plots, prompt block shape.
- Persona: `soul.md` validation; every UI string free of masculine self-reference.
- Output guard `repetition`: a looping tale (one paragraph over and over, or 40%+ copies) is flagged and revised once; a refrain that
  returns a few times and short rhythm lines are not; the harness asks for new events in the revision message.
- Offline model (`FakeLLM`): no repeated paragraph at any word target, name only as a nominative subject, verbs follow the child's
  gender, the tale passes the deterministic checks at every target the bot can ask for.

## 3. Unverified / needs a human

1. **Real model output** with the persona and folk toolkit: run `make eval` with a real
   `ANTHROPIC_API_KEY`, read tales for several ages and formats; tune `soul.md` if the tone drifts. The same run is the
   effort sweep for D20: compare `LLM_EFFORT` low / medium / high on length, quality, latency and cost.
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
   (the floor used to be 1.15); streaming and tool use against the live API are untested. The request shapes
   (`thinking: between_tools | adaptive`, `output_config.effort`, `output_config.format` JSON schema, `strict: true` tools) were
   written from the Claude Platform docs for Sonnet 5.5 and Haiku 5.5 (read 2026-10-25) and never accepted by the live API:
   a 400 on the first real request means a schema or parameter mismatch (kill switch for tools: `LLM_STRICT_TOOLS=false`).
   `make smoke` is the cheapest way to find out.
   Strict tools and the critic schema also add one-time grammar-compile latency on the first request. Same for `RedisStorage` with
   redis-py 7.4.1: constructed in a smoke test, never connected to a server.
9. **Python patch level:** the sandbox ran 3.14.4; the Docker and Codespace images carry newer 3.14.x.
10. **World folk sources (0006), read by a human:** the 35 plots were written by the assistant from the books; plots of 1,500+ words
    (e.g. Белый мышонок, Волшебный котёл, Три дерева, Белый дракон, Илья Муромец и Соловей-разбойник, Садко) were summarized from
    sampled passages, not a full read, so a few middle beats may differ from the books; the Russian is unreviewed by a native
    speaker; the `scary`, `calm` and `ending_hint` values are the assistant's judgement; the plots were never run through
    a real model (no real-key run).
11. **Copyright stance (D23):** the owner supplied commercial editions (2003-2026); the repository keeps only own-word synopses
    and beats. If the owner wants verbatim texts for a private corpus, that is a separate decision and must stay out of the
    repository and the package.
12. **Folk plots in the live harness (0007):** all tests use fakes. Not yet seen with a real model: whether it follows the
    `<folk_source>` block (retells in its own words, does not copy a beat list), whether "surprise me" still calls `pick_classic`
    despite the instruction, how often it picks a format that ignores the plot, token and cost impact (about 1,000 characters
    per request), and whether the keyword hints for `values` ideas (`folk_idea_hints.yaml`) match what parents really type.
13. **Second batch of folk plots (0008):** the 46 plots were written from the assistant's general knowledge of each tradition, not from a
    book; only Anansi's stories and Tiddalik were checked against public sources. Names, origins (which people a tale belongs to), and
    details such as who tricks whom may be off, and several plots exist in many versions. Needs a read by someone who knows the cultures
    (Indigenous, Aboriginal, African and Asian plots especially), and a native-speaker read of the Russian (transliterations such as Иссумбоси,
    Нольбу, Бенандоннер, Ньяме are the assistant's choice). The `scary`, `calm` and `ending_hint` values are judgement calls.
14. **Repetition thresholds (0009):** `REPEAT_*` in `harness/guard.py` were chosen by reasoning (toddler tales use refrains on purpose),
    not by looking at real model output. Unknown: how often a real model trips it, and whether it misses loops inside a single long
    paragraph (only paragraphs are compared). Watch `repetition` in `generation_runs.issues` after the first real-key runs.
15. **Avatar (0009):** drawn as SVG by the assistant and rendered with cairosvg in the sandbox; looked at as a PNG and as a circular crop
    down to 40 px, never on a real Telegram client or in BotFather. The PNG is not in the repository (the patch builder is text-only):
    it is handed over with the patch, or re-render from `assets/luna/avatar.svg`. The offline model's tale text was read by the assistant only.

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
| D20 | Sonnet 5.5 runs `between_tools` at `medium` effort (`LLM_THINKING=auto`, `LLM_EFFORT=medium`); the critic runs Haiku 5.5 at `low` | Claude 5.5 thinks by default at `high`; tales are latency-sensitive streamed text and up-front thinking would show nothing for seconds. Needs the effort sweep (item 1 above) |
| D21 | `assistant_content` keeps every reply block, thinking blocks verbatim; the history is append-only | The API requires thinking blocks back with tool results and rejects edits to earlier turns |
| D22 | A model refusal is `ModelRefused` (category only), run outcome `refused`, same gentle message as a guard block; the critic still fails open but a failed critic leaves `critic_used=False` | No new user copy; no refusal content or explanation is stored; deterministic checks always ran |
| D23 | World folk plots enter the repo as own-word synopses cut into beats, never as chunked source text; collections are cited as provenance only; authored (non-folk) works are not added; `scary >= 2` needs an `ending_hint` | The supplied books are retellings and translations with living rights holders; `AGENTS.md` already limits the knowledge base to synopses of folk or out-of-copyright material. A "chunk" is a beat (one event), which is also the right unit for retelling |
| D24 | World folk plots live in their own file and API (`world_folk.yaml`, `folk_sources.py`), not in `classics.yaml` | The `classic` skill lists every eligible classic as a button; hundreds of plots would flood that menu and change behaviour without a decision. `FolkSource` also has fields classics lack (origin, kind, motifs, `calm`) |
| D25 | (superseded by D26) Folk sources are data and retrieval only | - |
| D26 | The harness, not the model, picks the folk plot (`TaleHarness._folk_source_for`): offered in "surprise me" and in skills whose metadata says `folk-source: open|motif`; a parent's idea wins (only `motif` skills, i.e. `values`, let a named value steer by motif); never on sensitive topics; `FOLK_SOURCES_ENABLED=false` switches it off | The owner asked for a bot that selects the right plot automatically. Code-side choice is deterministic, testable, free of a tool turn and uses the child's history; the model keeps the creative work |
| D27 | The plot id is stored in the existing `Tale.seed_id` (mode `folk`), only when the format that was written can use a plot; no migration | Classic history, likes and "do not repeat" then work for folk plots unchanged. In "surprise me" the model picks the format after the plot is offered, so recording is by the loaded format |
| D28 | Plots from outside the supplied books are written from general knowledge of the tradition and filed in `oral_*` collections (no publisher, no year); plots of living peoples are told as tales of that people, never mixed, never sacred rites; authored picture-book retellings are not reproduced | The owner asked for more plots from many cultures. Only folk material is allowed, and honesty about provenance matters more than a fake citation |
| D29 | Luna's avatar is original art, not a likeness of any game or film character (the owner first asked for the DotA 2 hero Luna "as a fairy-tale hero") | `AGENTS.md` bans copyrighted characters and third-party IP; a recognisable Valve character, repainted, is still that character. The persona (kind, understanding, responsive; `soul.md`) is the brief instead: a moon girl, folk-tale style, a book and a small star |
| D30 | Repetition is a `fix`-severity guard check (one revision), never a block; only paragraphs of 5+ words count, thresholds lenient for refrains | Toddler tales rely on repeated lines; a looping tale should be rewritten once, not refused. The fake model used to pad by looping and nothing noticed |

## 5. Next steps (prioritized)

1. After patches 0003 and 0004: `uv lock --upgrade && uv sync --all-extras && make check`, commit `uv.lock` with the patch, rebuild the
   Codespace container (Python 3.14 image), delete finished patch scripts (`docs/MODUS_OPERANDI.md`), watch the first CI run.
2. `make run` (fake LLM is fine) and click through: first profile → invitation, `/cheer`, Settings → warm words, small talk phrases.
3. `docker compose up --build -d` once: PostgreSQL 18 and Redis 8 have never been started with this stack (item 7 below).
4. BotFather: set the bot's name to «Луна» and upload the avatar PNG with `/setuserpic` (the SVG source is `assets/luna/avatar.svg`; description/commands refresh at startup). Look at it on a phone: the circle crop is checked only in the sandbox.
5. With a real key: `make smoke` first (two tales in about a minute: explicit format and "surprise me", critic included; it fails if the critic silently did not run), then `make eval` for the effort sweep (item 1, D20); read the tales; adjust persona or prompts.
6. With a real key, compare tales with and without the folk plot (`FOLK_SOURCES_ENABLED=false` for the control): does the model retell the plot in its own words, vary names and details, keep the persona, stay within length and cost, and how often does "surprise me" load a format that ignores the plot (`make eval`, read the tales). Tune `FOLK_SOURCE_INTRO` and the task wording in `harness/prompts.py` from what you read.
7. More folk plots, batch by batch (`docs/FOLK_SOURCES.md`: catalog tables and ideas for later batches): the rest of the Hungarian, Azerbaijani (curated), reader and byliny tales from the supplied books, and more cultures (Georgian, Armenian, Persian, Mongolian, Central Asian, Sami, more Native American tales). Have the second batch read by someone who knows the cultures first (unverified item 13).
8. Native-speaker read-through of Russian copy (now including `world_folk.yaml`); extend the KBs (target: 100+ compliments).
9. Per-user timezone for warm words (store an offset or IANA name; ask during onboarding).
10. Decide on a LICENSE and add it.
11. Optional LLM "personalizing" mode for warm words, bounded by the same guard checks.
12. Roadmap items in `docs/PLAN.md` section 7.

## 6. Manual steps for the owner

- Run the patch from the repo root in Codespaces (`docs/MODUS_OPERANDI.md`), then `make check`. If it changed dependencies,
  run `uv lock --upgrade` first and commit `uv.lock` too (exports and patches never carry it).
- Commit (suggested message is printed by the script); do **not** commit the patch script.
- Codespaces secrets: `BOT_TOKEN`, `ANTHROPIC_API_KEY`.
- BotFather: `/setname` Луна, `/setuserpic` (the PNG delivered with patch 0009).

## 7. Session log

Newest first. Entries are inserted by the patch scripts.

<!-- HANDOFF:LOG:BEGIN -->

### 2026-11-01 — patch 0009-fake-tale-repeats-and-avatar

**Goal:** the owner ran the bot offline and got a tale that repeated the same five paragraphs about 40 times, with the name in the wrong case («у Рома»); fix it. Also give Luna an avatar for Telegram.

**Cause:** the repetition was `FakeLLM._story` (`LLM_PROVIDER=fake`), not a real model: it cycled five filler lines until 80% of the word target. The real guard had no way to notice a looping model either.

**Decisions (D29, D30)**
- The avatar is original art. The owner asked for the DotA 2 hero Luna painted as a fairy-tale hero; that is a third-party character (`AGENTS.md` bans such IP), so the avatar is a moon girl in a folk-tale style that follows `soul.md` (kind, understanding, responsive).
- Repetition is a `fix` check (one revision), never a block, lenient for refrains (toddler tales use them).

**Changed**
- `llm/fake.py`: 50 distinct beats used once each (a shorter tale beats a looping one), name only as a nominative subject, title «Рома и добрая звёздочка», verbs and «Жила-была/Жил-был» follow the child's gender.
- `harness/guard.py`: `repeated_paragraphs`, `REPEAT_*` constants, issue code `repetition` with a Russian revision message (no tale text in it).
- `tests/fakes.py::make_story`: varied paragraphs, identical word counts. New tests: 5 in `test_guard.py`, 1 in `test_harness.py` (looping tale gets a revision), `tests/test_fake_llm.py` (38).
- `assets/luna/avatar.svg` (24 KB). Docs: AGENTS.md (map, look rule, pitfall), README, PLAN, CHANGELOG, HANDOFF.

**Verified (authoring sandbox, Python 3.14.4):** `make check` green on the pristine export before (376 tests) and after (420); the offline tale was read at several targets; the avatar was rendered with cairosvg and viewed as a square and as circular crops down to 40 px.

**Unverified:** see section 3, items 14-15: repetition thresholds never met a real model; the avatar was never seen in Telegram or BotFather; the fake tale's Russian was read by the assistant only.

**Next:** upload the PNG with BotFather `/setuserpic` and look at it on a phone; `make smoke` and `make eval` with a real key and watch `repetition` in the issues.


### 2026-10-27 — patch 0008-world-folk-plots-batch-2

**Goal:** more plots from different cultures for the automatic folk-plot pick (owner: add more, find interesting stories and plots in the folklore of different cultures). Requires 0006 and 0007.

**What:** 46 new plots (81 in total, 491 beats, 35 origins) written from general knowledge of each tradition: Africa (Ananse and the Sky God's stories, the pot of wisdom, the tortoise at the feast in the sky, why the sun and the moon live in the sky, the mosquito chain, Unanana, the tug of war), India (Panchatantra, Jataka, Birbal), China (Nian, the cowherd and the weaver, Nüwa, Hou Yi), Japan (Kasa Jizo, Momotaro, Issun-boshi, the mouse's wedding), Korea, Vietnam, Indonesia, the Philippines, Turkey (three Nasreddin anecdotes), Ireland, Norway, Finland (the kantele), Greece (Midas, Demeter and Persephone, the North Wind and the Sun), Portugal (stone soup), the Pacific Northwest (Raven and the light), the Cherokee, the Aztecs, the Maori (Maui and the Sun) and the Gunai (Tiddalik).

**Decisions (D28):** plots not taken from the supplied books go into `oral_*` collections (no publisher, no year; `Collection` needs both or neither) instead of a fake citation; plots of living peoples are told as tales of that people, never mixed, never sacred rites; authored picture-book retellings are not reproduced. Harsh originals carry an `ending_hint` (18 plots have `scary` 2).

**Changed:** `world_folk.yaml` (6 oral collections, 46 plots), `folk_sources.py` (wider `Origin`, optional publisher/year), `tests/test_folk_sources.py` (80+ plots, 30+ origins, oral collections; two retrieval tests no longer rely on one specific plot), docs (FOLK_SOURCES.md second-batch catalog and cultural-care rules, KNOWLEDGE, PLAN, AGENTS, CHANGELOG, HANDOFF).

**Verified (authoring sandbox, Python 3.14.4):** `make check` green on the post-0007 tree before and after (375, then 376 tests, ruff, mypy `--strict`, skills and knowledge checks). Two plots were checked against public sources (Anansi's stories; Tiddalik).

**Unverified:** see section 3, item 13: the other 44 plots come from general knowledge and have not been read by someone who knows the cultures; names, attributions and details may be off; Russian transliterations are the assistant's choice; `scary`/`calm`/`ending_hint` are judgement calls; still nothing run against a real model. Thin spots: age 2 has only 2 eligible plots and age 3 has 7 (bedtime: 2 and 5), so toddlers repeat sooner; add toddler-friendly plots next.

**Next:** have the second batch read by a person who knows the cultures; `make smoke` and `make eval` with a real key; more toddler plots; further cultures (Georgian, Armenian, Persian, Mongolian, Central Asian, Sami).


### 2026-10-27 — patch 0007-folk-source-auto-pick

**Goal:** make the bot choose the right folk plot for the child on its own and use it as the basis of the tale (owner's instruction: decide autonomously, the bot must select and use the source automatically). Requires 0006.

**Decisions (D26, D27)**
- The harness, not the model, picks the plot, in code before the model runs: age and `scary` limit, bedtime (calm plots only), interests, tale history, likes and dislikes; the choice is a weighted random among the top 3 so children do not all get the same plot; its own random generator leaves classic selection unchanged.
- Where: "surprise me" and skills with metadata `folk-source: open` (`original`, `rhyme`, `bedtime`) or `motif` (`values`). Skills with their own structure (cumulative, funny, riddles, celebration, sequel, educational, life-event, metaphorical, meditation, classic) get none.
- A parent's own idea wins and is kept as is. The one exception: the `values` format, where the value named in the idea ("Делиться", "Говорить правду") steers the choice by motif (`folk_idea_hints.yaml`).
- No plot on sensitive topics; `FOLK_SOURCES_ENABLED=false` switches it off.
- The plot id is saved in `Tale.seed_id` with mode `folk`, only if the written format can use a plot (in "surprise me" the model picks the format after seeing the plot). No migration: classic history, likes and no-repeat just work.

**Changed**
- `knowledge/folk_sources.py`: history-aware scoring (Counter history, liked, disliked), `pick_folk_source`, `IdeaHint`, `hints_for_idea`, `load_idea_hints`; new `knowledge/tales/folk_idea_hints.yaml` (15 hints); `make kb-check` validates it.
- `harness`: `TaleHarness._folk_source_for`, `<folk_source>` block and task wording in `prompts.py`, `RunResult.mode`, skill metadata `folk-source`, setting `folk_sources_enabled`; four skills opted in. `tale_service` stores `result.mode`.
- `FakeLLM` routing ignores the `<folk_source>` block (it routes by keywords in the request); the auto-mode flow test now expects mode `folk`.
- Tests: `tests/test_folk_wiring.py` (formats, parent idea, value motifs, sensitive and kill switch, "surprise me" recording, age and bedtime for every age 2-10, history, classic unchanged, hints).
- Docs: FOLK_SOURCES.md (decision table), KNOWLEDGE.md, SKILLS.md, PLAN.md, AGENTS.md, README env table, `.env.example`, CHANGELOG, HANDOFF.

**Verified (authoring sandbox, Python 3.14.4):** `make check` green on the post-0006 tree before and after (344, then 375 tests, ruff, mypy `--strict`, skills and knowledge checks).

**Unverified:** everything runs on fakes; see section 3, item 12 (real model following the block, `pick_classic` still called in "surprise me", format choice, cost, keyword hints vs real parent ideas).

**Next:** with a real key, `make smoke`, then `make eval` with and without `FOLK_SOURCES_ENABLED`, and read the tales; then more plots (`docs/FOLK_SOURCES.md`).


### 2026-10-27 — patch 0006-world-folk-sources

**Goal:** turn a set of folk-tale books supplied by the owner into reusable source material for composing new tales: extract the tales, cut them into minimal chunks, keep short summaries.

**Why:** the bot retells only 25 classic plots; more folk plots (Chinese, Hungarian, Kalmyk, Cossack, Japanese, French, Baltic, Russian epic) give variety. The books are commercial editions (retellings and translations, 2003-2026), and `AGENTS.md` allows only synopses of folk or out-of-copyright material, so the "chunks" are story beats written in our own words, not pieces of the books (D23).

**Changed**
- `knowledge/tales/world_folk.yaml`: 8 collections, 35 plots, 217 beats; each plot has summary, beats, moral, themes, motifs, ages, `scary`, `calm`, `child_role` and (required for `scary >= 2`) an `ending_hint` that softens harsh originals.
- `knowledge/folk_sources.py`: pydantic models, `load_folk_sources`, `eligible_sources`, `find_folk_sources` (age, bedtime, themes, motifs, unseen first, seedable), `folk_source_block` (Russian prompt block). Exported from `skazki_bot.knowledge`; `make kb-check` prints a folk sources line.
- `tests/test_folk_sources.py`: 17 tests (schema and links, authoring rules, every age served by day and at bedtime, deterministic and safe retrieval, prompt block, rejection of broken entries, kb-check).
- Docs: new `docs/FOLK_SOURCES.md` (rules, schema, how to add, catalog of what was read, skipped and why), `docs/KNOWLEDGE.md`, `AGENTS.md` (map, rule, recipe), CHANGELOG, HANDOFF (snapshot, D23-D25, unverified 10-11, next steps 6-7).

**Skipped on purpose:** the 2003 collection of New Year plays by named modern authors (authored, protected), the poetry and Russian-classics parts of the school reader, authored works (Perrault, Grimm, Andersen, Kipling are mostly in `classics.yaml` already), and the dark ethnographic Eskimo legends. Reasons per book are in `docs/FOLK_SOURCES.md`.

**Verified (authoring sandbox, Python 3.14.4):** `make check` green on the pristine tree before and after (327 then 344 tests, ruff, mypy `--strict`, skills and knowledge checks).

**Unverified:** the plots were not read by a human; plots of 1,500+ words were summarized from sampled passages, so some middle beats may differ from the books; Russian wording not reviewed by a native speaker; `scary`/`calm`/`ending_hint` are judgement calls; nothing reaches the model yet, so no real-model run exists.

**Next:** decide how the plots reach the model (HANDOFF next step 6: prompt block, tool or a new format), then a real-key `make eval`; send more books or tale names for further batches.


### 2026-10-26 — patch 0005-live-smoke-check

**Goal:** make the one thing still unverified after 0004, the live API accepting the new request shapes, cheap to check.

**Why:** the critic fails open by design, so a rejected schema or parameter on the live API would have looked like a healthy run in `make eval`. And a full eval is 40+ paid calls for what is a yes/no question.

**Changed**
- `python -m skazki_bot.evals --smoke` (`make smoke`): the first sample child, one explicit format (single turn) and "surprise me" (the `load_skill` tool loop with thinking blocks and strict tools); prints a settings line (model, resolved thinking, effort, strict tools, critic model and effort); exits 1 if the critic was enabled and did not run. `run_evals(..., smoke=False)` keeps its old signature for existing callers.
- The eval table gained a critic column (`крит.`) for every run.
- Docs: AGENTS.md and README (command), HANDOFF (next step 5, unverified item 8), PLAN, CHANGELOG.

**Verified (authoring sandbox, Python 3.14.4):** `make check` green (327 tests, ruff, mypy `--strict`, skills and knowledge checks); two new tests (smoke runs two tales for one child with the critic column, and smoke fails loudly when the critic is made to fail); the offline smoke output was read; the patch was applied to a fresh copy of the post-0004 export (dry run, apply, second run, rollback, anchor drift) and the chain 0003, 0004, 0005 was applied to the original export, followed by `uv lock --upgrade`, `uv sync` and `make check`.

**Unverified:** `make smoke` against the real API has not run (no key in the sandbox); that run is the verification of 0004's request shapes.

**Next:** with a real `ANTHROPIC_API_KEY`: `make smoke`; if it prints a 400, send the exact line; then `make eval` for the effort sweep.


### 2026-10-25 — patch 0004-claude-5-5-llm-layer

**Goal:** make the harness's LLM layer native to the current Claude 5.5 API (autonomous decision by the owner's brief: "the most modern harness").

**Why:** the Claude Platform docs for Sonnet 5.5 and Haiku 5.5 (read 2026-10-25) say that a request without `thinking` runs adaptive thinking at `high` effort, that thinking blocks must come back unmodified in tool loops with an append-only history, that forced `tool_choice`, prefill, sampling parameters and `budget_tokens` are gone, and that thinking tokens count toward `max_tokens`. The adapter sent none of the new fields and filtered every block except text and tool_use, so against the live API it would have been slow, costly and likely rejected in the `load_skill` loop and in revisions. It had only ever run against a fake transport.

**Changed**
- `llm/anthropic_llm.py` rewritten: `thinking` (`between_tools` on Sonnet 5.5, adaptive elsewhere, `LLM_THINKING=auto`) and `output_config.effort` (`LLM_EFFORT=medium`, `GUARD_EFFORT=low`) on every request; adaptive gets `THINKING_HEADROOM` on `max_tokens`; all reply blocks kept in order, non-text/tool_use blocks verbatim; `strict: true` on tools flagged `ToolSpec.strict` (kill switch `LLM_STRICT_TOOLS`); `complete(schema=...)` sends `output_config.format` (structured outputs) and raises on refusal or `max_tokens` instead of returning text that may not match; `model_context_window_exceeded` is an error.
- `ModelRefusal` (category from `stop_details`, never content) → `ModelRefused` (a `HarnessError`) → service outcome `refused` and the existing `GUARD_BLOCKED` message in the handler (no new user copy). The critic still fails open on any `LLMError`, now visibly (`critic_used=False`).
- Skill tools got strict-compatible schemas (closed objects, no `minimum`/`maximum`; ranges moved into descriptions, the executor already clamps). `CRITIC_SCHEMA` and `CRITIC_CODES` live in `harness/prompts.py`; `parse_critic` accepts any capitalisation. Critic `max_tokens` 700 → 1200.
- Settings: `llm_effort`, `llm_thinking`, `guard_effort`, `llm_strict_tools`; startup error for `between_tools` with `xhigh`/`max`.
- Docs: AGENTS.md (LLM layer, recipe, pitfalls), README env table, `.env.example`, PLAN, CHANGELOG, HANDOFF (unverified item 8, D20-D22).

**Verified (authoring sandbox, Python 3.14.4):** `make check` green (325 tests, ruff, mypy `--strict`, skills and knowledge checks); 6 consecutive full-suite runs and a warnings-as-errors run green. New tests drive the real adapter through a mock HTTP transport with SSE: request shape for both thinking modes and headroom, thinking and redacted-thinking blocks passed through and replayed unmodified, strict flag and kill switch, refusal category (and that the explanation text is not kept), context overflow, structured `complete()` (format, effort, headroom, cut-off, refusal). Harness tests: thinking blocks survive the tool loop and a revision, history stays append-only, critic receives the schema, refusal mapping, refusing critic. A validator test keeps every strict schema inside the documented JSON Schema subset and under the 20-tool / 24-optional-parameter limits. A service test and a bot-flow test cover the `refused` outcome and message. The patch itself was applied to a fresh copy of the post-0003 export (dry run, apply, second run, rollback, anchor drift).

**Unverified:** the live API has never accepted these request shapes (see section 3, item 8); the effort level and `between_tools` choice need the sweep in item 1; strict-tool and structured-output grammar compilation adds first-request latency. The critic schema and tool schemas were checked against the documented subset only locally.

**Next:** `make eval` with a real key and read the tales; run effort low / medium / high; if the first live request returns a 400, send the exact error text.


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
