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

- **State as of 2026-10-24:** Luna persona, two knowledge bases and the warm-words skill are
  implemented on top of the 0.1.0 harness (patch `0001-luna-foundation`).
- **Quality gate:** `make check` green in the authoring sandbox (294 tests, ruff, mypy `--strict`,
  skills check, knowledge check).
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
5. **Infra files created only if missing:** `.github/workflows/ci.yml`,
   `.devcontainer/devcontainer.json`, `.env.example`, `.dockerignore` were not in the repomix
   export (dotfiles may have been excluded). First CI run and first Codespace rebuild will tell
   whether they match what already exists. Pinned action versions (`checkout@v4`, `setup-uv@v6`)
   may need bumping.
6. **Crisis text for adults:** free-text crisis wording now routes to `texts.CRISIS_SUPPORT`,
   whose contacts are written for child safety (112 and the children's helpline). Owner to decide
   whether adults in distress need a different message.
7. **Docker build** and webhook mode with the scheduler running in several replicas.

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
| D15 | `.python-version` pins 3.12 | A Codespace ships Python 3.14; the project, Docker image and CI target 3.12 |

## 5. Next steps (prioritized)

1. Apply the patch (if `uv` is missing in the Codespace: `pip install uv`), `make check`, then `make run` (fake LLM is fine) and click through: first
   profile → invitation, `/cheer`, Settings → warm words, small talk phrases.
2. BotFather: set the bot's name to «Луна» and an avatar (description/commands refresh at startup).
3. `make eval` with a real key; read the tales; adjust persona or prompts.
4. Native-speaker read-through of Russian copy; extend the KBs (target: 100+ compliments).
5. Per-user timezone for warm words (store an offset or IANA name; ask during onboarding).
6. Decide on a LICENSE and add it.
7. Optional LLM "personalizing" mode for warm words, bounded by the same guard checks.
8. Roadmap items in `docs/PLAN.md` section 7.

## 6. Manual steps for the owner

- Run the patch from the repo root in Codespaces (`docs/MODUS_OPERANDI.md`), then `make check`.
- Commit (suggested message is printed by the script); do **not** commit the patch script.
- Codespaces secrets: `BOT_TOKEN`, `ANTHROPIC_API_KEY`.
- BotFather: `/setname` Луна, `/setuserpic`.

## 7. Session log

Newest first. Entries are inserted by the patch scripts.

<!-- HANDOFF:LOG:BEGIN -->

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
