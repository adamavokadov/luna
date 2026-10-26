# Modus operandi

How we change this project: **repomix export → plan → build and verify in a sandbox → one patch
script → run in Codespaces → `make check` → commit → refreshed export.** Every step is boring on
purpose, so the project stays reproducible no matter who (or what) writes the code.

## 1. Roles

| Who | Does |
|---|---|
| **Owner** (Adam) | Decides what to build, runs patches in GitHub Codespaces, tries the bot, commits, sends the next export. |
| **Claude** (Claude Project "Luna") | Reads the export, plans, writes and verifies code in its sandbox, delivers one patch script and short notes, keeps `HANDOFF.md` honest. |
| **Any other agent** | Follows `AGENTS.md`; ships changes the same way. |

## 2. The session loop

```
 Owner                                   Claude
 ─────                                   ──────
 1. npx repomix  ───────────────────────► 2. read AGENTS.md + HANDOFF.md from the export
    (repomix-output.xml + the ask)           plan in a few lines; ask only blocking questions
                                          3. make unpack → rebuild the repo in the sandbox
                                             implement; run `make check`; fix until green
                                          4. build ONE patch script (+ HANDOFF/CHANGELOG/docs inside)
 5. drop patch_NNNN_<slug>.py at the  ◄── deliver: script + notes (what/why, how to verify,
    repo root in Codespaces                  what is unverified)
 6. --dry-run → apply → make check
 7. try the bot, commit (not the patch)
 8. send a fresh export + feedback  ────► next session starts from HANDOFF.md
```

Why patches rather than archives: they change only what must change, fail loudly when your files
drifted, are re-runnable, and can be undone. Nothing is overwritten silently.

## 3. The patch script contract

Every patch is **one self-contained Python file** (standard library only, Python 3.10+) named
`patch_NNNN_<slug>.py` (`NNNN` increments by one; the `PATCH_ID` inside is `NNNN-<slug>`).

| Requirement | Meaning |
|---|---|
| **Idempotent** | Re-running skips steps that are already applied; the second run reports "Already applied". |
| **Atomic** | Everything is computed in memory first; if any anchor fails, **nothing** is written. |
| **Anchored edits** | Existing files change through exact-text hunks that must match exactly once. A miss means "your file differs from the export": the script stops and says so. |
| **New files** | Created if absent. If present and different, left untouched with a warning. Infra dotfiles use "create only if missing". `.gitignore` is merged (only missing entries are added). |
| **Backups** | Originals go to `.patch-backups/<PATCH_ID>/<timestamp>/` (git-ignored) with a manifest. |
| **Rollback** | `--rollback` restores the last application: modified files back, created files removed. |
| **Dry run** | `--dry-run` prints the plan (create / edit / move / warnings) and writes nothing. |
| **Verify** | `--verify` runs `uv sync --all-extras` and `make check` after applying. |
| **Project guard** | Refuses to run unless `pyproject.toml` says `name = "skazki-bot"`. |
| **No side effects** | No network, no secrets, no running the bot, no deleting user data, no `git` writes. |
| **Carries its own bookkeeping** | The patch adds the dated entry to `HANDOFF.md` and ships doc and CHANGELOG changes. |
| **Prints next steps** | `make check`, review, commit message, how to undo. |

Anatomy (source in `tools/patchkit/`): engine (operations, workspace, backups, CLI) → `OPS` list (what to do, in order) →
payload (file contents and hunks, stored as `#` comment lines so the file stays valid Python).
Flags: `--dry-run`, `--verify`, `--rollback`, `--archive`, `--root PATH`, `-v`.

## 4. Running a patch in Codespaces

```bash
# 1. put the script at the repo root (drag it into the Explorer), then:
git status                                   # ideally clean, so `git diff` shows exactly the patch
python3 patch_0001_luna_foundation.py --dry-run
python3 patch_0001_luna_foundation.py        # apply (or add --verify)
make check                                   # skip if you used --verify
git add -A && git commit -m "<message printed by the script>"
rm patch_0001_luna_foundation.py             # or keep it locally: /patch_*.py is git-ignored
```

Undo before committing: `python3 patch_0001_luna_foundation.py --rollback`
(or `git checkout -- . && git clean -fd` if you committed nothing else).

**Cleanup.** Patches never delete anything, themselves included, so finished scripts pile up in the repo root
(git-ignored, hence harmless to the repository). After the commit, delete them; the script prints the exact
`rm` line for the finished ones (applied, not rolled back) in its next steps; scripts you have not applied yet are never listed. Do not re-run an old patch: an overwrite-mode step (a rewritten
`README.md`, say) would put its content back over later edits. `.patch-backups/` is only needed for `--rollback`;
remove it too once the change is committed and checked.

### If something goes wrong

| Symptom | Meaning | What to do |
|---|---|---|
| `anchor not found` | A file differs from the export the patch was built from | Nothing was changed. Send a fresh export (and say what you edited); Claude rebuilds the patch. |
| `anchor is ambiguous` | Same, with repeated code | Same. |
| `warn ... exists with different content` | You already have a file at a path the patch wanted to create | Kept yours. Compare by hand if it matters. |
| `uv not found` / `make not found` with `--verify` | The environment lacks the tool (a Codespace created before the devcontainer existed) | `pip install uv`, then `uv sync --all-extras && make check`. The patch itself was already applied. |
| `uv sync --locked` fails in CI | `uv.lock` does not match `pyproject.toml` (exports and patches never carry the lock) | `uv lock`, commit `uv.lock`. After a dependency change always run `uv lock --upgrade` locally first. |
| `make check` fails after applying | A real problem or an environment difference | Send the failing output. Do not hand-fix and re-run: that creates drift. |
| `does not look like the skazki-bot repository` | Wrong directory | `cd` to the repo root or pass `--root`. |

## 5. Repomix export

```bash
npx repomix            # uses repomix.config.json → repomix-output.xml
```

The config skips `uv.lock`, patch scripts and backups, and honors `.gitignore`. Send the XML to
the Claude Project chat. Claude can rebuild the tree with
`python3 tools/unpack_repomix.py repomix-output.xml /tmp/repo` and run the real checks.
A fresh export after every applied patch keeps the next patch anchored to reality.

## 6. Quality gates (definition of done)

1. `make check` green: ruff, ruff format, mypy `--strict`, pytest, skills check, knowledge check.
2. New behaviour has tests; new data passes `make kb-check`.
3. Docs and `CHANGELOG.md` updated; `AGENTS.md` if rules changed.
4. `HANDOFF.md` updated (the patch inserts the log entry; snapshot, decisions, next steps and the
   unverified list are refreshed by hand/AI in the same patch).
5. Claude states plainly what it ran and what it did not (real LLM, live Telegram, Postgres...).

## 7. Conventions

- **Language:** think, code, comments, docs and commit messages in English; everything the bot
  says is Russian.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`,
  `docs:`, `refactor:`, `test:`, `chore:`), one patch = one commit.
- **Patches are not committed.** History lives in git, `CHANGELOG.md` and `HANDOFF.md`.
- **Migrations** accompany every model change; never edit an applied migration.
- **Secrets** stay in Codespaces secrets or `.env`; never in patches, exports or chat.
- **Check the export first:** `repomix.config.json` excludes lock files; make sure no `.env`
  is ever included (`.gitignore` already prevents it).

## 8. HANDOFF protocol

`HANDOFF.md` is the memory between sessions. Each patch: add the session-log entry (automatic),
refresh *Snapshot* and *Unverified*, record new *Decisions*, re-order *Next steps*. At the start
of a session Claude reads it right after `AGENTS.md` and trusts it only as far as the export
agrees with it.

## 9. Writing a new patch (for Claude and other agents)

1. Rebuild the repo from the export; run `make check` first to confirm a green baseline.
2. Implement in the working tree; run `make fmt` and `make check`.
3. Update docs, `CHANGELOG.md`, `HANDOFF.md` (everything except the session-log entry).
4. Generate the script from the diff between the pristine tree and the working tree with
   `tools/patchkit/build_patch.py` (new files as whole blocks, existing files as anchored hunks,
   moves as moves, wholesale rewrites such as `README.md` as "overwrite with backup"; the engine
   template is `tools/patchkit/engine.py.tmpl`, and the example config documents the knobs).
   The kit is part of the repository, so every repomix export carries it.
5. **Test the patch itself** on a pristine copy: `--dry-run`, apply, `make check` on the result,
   second run (idempotent), `--rollback` (tree equals pristine), anchor drift (fails with no
   writes).
6. Deliver the script and a short note: what changed and why, how to verify, what is unverified.
7. If dependencies changed, say so in the note: `uv.lock` is skipped by the exporter and the builder, so the owner
   runs `uv lock --upgrade` and commits the lock together with the patch.
