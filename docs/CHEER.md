# The cheer skill: Luna's warm words

Luna says something kind to the adult who reads the tales: a compliment, a word of encouragement
or a folk proverb. She does it **on request** (`/cheer`) and, **if the user agreed**, from time to
time on her own.

Skill file (methodology + schedule metadata): `src/skazki_bot/cheer/skills/cheer/SKILL.md`.
Material: `src/skazki_bot/knowledge/cheer/` (see `docs/KNOWLEDGE.md`).

## What the user sees

| Entry point | What happens |
|---|---|
| After the first child profile | One invitation (sent exactly once, tracked in `users.cheer_asked`): **Раз в неделю / Чаще / Не сейчас**. |
| `/cheer` or **💛 Тёплые слова** in the menu | Mood picker: тяжёлый день / тревожно / что-то не получается / я молодец / просто подбодри, then a message with **Ещё**. |
| Settings → **💛 Тёплые слова** | Frequency picker: не присылать / раз в неделю / несколько раз в неделю / каждый день. |
| Free text such as «мне тревожно», «устала», «спасибо», «привет» | Small talk (`bot/smalltalk.py`): Luna answers; for a hard day she offers a warm word. Crisis wording gets the support text instead. |
| Under every scheduled message | **Ещё · Сказку · Не присылать**. |

A message is composed as: **opener** (by time of day or mood) → **the word** → **closer**, with at
most two emojis in total. Example:

```
Добрый вечер. Заглянула с тёплым словом 💛

«Дорогу осилит идущий»
Не нужно идти быстро — важно просто не останавливаться.

Я рядом, если захочется сказку 🌙
```

## Rules of the road

- **Opt-in.** Default `off`. Existing users are never messaged until they choose a frequency.
- **Daytime only**: local window `CHEER_WINDOW_START`..`CHEER_WINDOW_END` (default 10-21) in the
  bot's `TIMEZONE`. Each user has a stable personal hour inside the window
  (`user_id % window_length`), so messages do not all go out at once. If the bot was down at that
  hour it catches up later the same day, inside the window.
- **Minimum gaps** from the skill metadata: daily 20 h, few (about every other day) 46 h,
  weekly 156 h. An on-demand message also delays the next scheduled one.
- **No repeats**: the last 30 item ids are kept per user (`users.cheer_recent`).
- **Mood-specific items** are never sent unprompted.
- **Stops cleanly**: a user who blocks the bot is switched to `off`; flood control is retried once.
- **At most once across replicas**: a slot is claimed with an atomic `UPDATE ... WHERE
  cheer_last_at IS NULL OR cheer_last_at <= cutoff`, so several bot instances cannot double-send.
- **Privacy**: the only personal data used is the child's first name (as a nominative subject, and
  only when a profile exists). Logs contain the kind and item id, never names or text.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `CHEER_ENABLED` | `true` | Master switch for the scheduler (on-demand `/cheer` still works). |
| `CHEER_TICK_S` | `300` | How often the scheduler looks for due users. |
| `CHEER_WINDOW_START` / `CHEER_WINDOW_END` | `10` / `21` | Local hours; end must be greater than start. |
| `CHEER_BATCH_SIZE` | `40` | Max scheduled messages per tick (the rest go on the next tick). |
| `TIMEZONE` | `Europe/Moscow` | Shared with the daily tale limit. |

## Code map

| Module | Role |
|---|---|
| `cheer/skill.py` | Loads and validates `SKILL.md` (companion-skill validator; not part of the tale catalog). |
| `cheer/schedule.py` | Pure rules: dayparts, personal hour, `is_due`. |
| `cheer/compose.py` | Picks and renders a message (mood, time of day, child, history, kind rotation). |
| `cheer/service.py` | Database-aware: preferences, history, claiming due users. No Telegram. |
| `cheer/scheduler.py` | Background loop and delivery (started from `app.run`). |
| `bot/handlers/cheer.py` | `/cheer`, frequency screens, the one-time invitation. |
| `bot/smalltalk.py` | Thanks, greetings, hard-day phrases, crisis routing. |
| `db/repo.py` (cheer section) | `set_cheer_freq`, `claim_cheer_slot`, `cheer_context`, ... |
| `migrations/versions/0003_luna_cheer.py` | `users.cheer_freq/asked/last_at/recent`. |

## Known limits and next steps

- One timezone for everyone (`TIMEZONE`). A per-user timezone is on the roadmap.
- Messages come from the curated knowledge base, not from the LLM. An optional LLM "personalizing"
  mode is possible later: it must follow the methodology in `SKILL.md` and pass the same guard
  checks as tales.
- Scheduling polls the database (one indexed-free query over opted-in users per tick). Fine for
  thousands of users; add an index on `users.cheer_freq` if it grows well beyond that.
