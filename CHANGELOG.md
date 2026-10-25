# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/) once releases are tagged.

## [Unreleased]

### Added
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
- 108 new tests (294 total).

### Fixed
- Patch scripts: `--verify` now reports a missing `uv`/`make` with install hints instead of crashing, and the
  next steps mention installing `uv` when it is not on PATH.
- `.python-version` pins Python 3.12 so uv does not pick a newer interpreter (e.g. 3.14 in a Codespace).

### Changed
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
