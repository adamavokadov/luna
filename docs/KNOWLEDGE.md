# Knowledge bases

Everything Luna draws on lives in `src/skazki_bot/knowledge/` as plain YAML, validated when it
loads and again by `make kb-check` and the test-suite. Edit a file, run `make check`, done: no
code changes are needed to add material.

```
knowledge/
├── tales/                       # a) fairy-tale knowledge base (used while generating tales)
│   ├── classics.yaml            #    25 classic plots: synopses and beats, NOT texts
│   └── folk_toolkit.yaml        #    folk poetics: openings, closings, refrains, helpers, objects, lullabies
└── cheer/                       # b) warm-words knowledge base (used by the cheer skill)
    ├── compliments.yaml         #    50 compliments (ids cm01..)
    ├── encouragements.yaml      #    36 words of encouragement (en01..)
    ├── proverbs.yaml            #    36 folk proverbs with a gentle gloss (pr01..)
    └── frames.yaml              #    Luna's openers and closers
```

Loaders: `knowledge/tale_kb.py`, `knowledge/cheer_kb.py` (pydantic models, `extra="forbid"`).
Validate everything: `make kb-check`.

## a) Fairy tales

### How the tale knowledge reaches the model

| Piece | When | How |
|---|---|---|
| `classics.yaml` | the `classic` skill ("classic, retold") | `stories/library.py` + `stories/selector.py` pick a plot for the child's age and interests; the plot's beats go into the prompt; the model retells it for this child. |
| `folk_toolkit.yaml` | every tale request except heavy topics | `harness/runner.py` picks an opening, a closing, a refrain (age <= 7), a helper and a magic object (`knowledge/tale_kb.pick_toolkit`) and adds them to the user message as an optional `<folk_toolkit>` block. The model may use, rework or ignore them. |

Design choices worth knowing:

- The toolkit is **data in the prompt, not a tool**. An explicit format stays a single model turn
  with no tools (the project's cost and safety principle).
- Toolkit picks use their **own random generator**, so they never shift classic selection.
- **Bedtime** requests only get calm entries (`calm: true`); closings may be lullaby lines.
- **Sensitive topics** (grief, illness...) get no toolkit: playful formulas would be out of tune.
- Entries are traditional formulas or short original lines. Never paste text from protected works.

### Adding a classic plot (`classics.yaml`)

Fields: `id` (a-z0-9_, <= 40 chars, becomes part of a callback), `title`, `summary`, `beats`
(>= 3), `moral`, `themes`, `min_age`, `max_age`, `scary` (0-3), `child_role`, `ending_hint`.
Only works that are folk or out of copyright. Soften frightening endings in `ending_hint`
(see `snegurochka`, `krasnaya_shapochka`). Themes come from the vocabulary in the file header
(`tests/test_knowledge.py::KNOWN_THEMES` enforces it).

### Adding toolkit entries (`folk_toolkit.yaml`)

Fields: `id` (unique across the whole file), `text` (Russian), `min_age`/`max_age` (default 2-10),
`calm` (default true), `themes` (optional; matching themes are preferred ~60% of the time).
Tests check that every age 2-10 can be served in both bedtime and daytime modes.

## b) Warm words (compliments, encouragement, proverbs)

Every item is `id`, `text`, optional `moods`, `times`, `child`, `tags`; proverbs also need `note`.

| Field | Values | Meaning |
|---|---|---|
| `moods` | `any` (default), `tired`, `anxious`, `stuck`, `proud` | Items with a specific mood are used **only when the reader asks** for that mood via `/cheer`. Scheduled messages use `any` items only. |
| `times` | `any` (default), `morning`, `day`, `evening` | Local time of day the item fits. |
| `child` | `true` when the text contains `{child}` | Used only if the user has a child profile. |

### Authoring rules (enforced by `tests/test_knowledge.py`)

1. **Russian**, one to three short sentences, up to 280 characters, no emoji in items (emoji live
   in `frames.yaml`, at most one per line).
2. **Address the reader as polite «вы» in gender-neutral forms.** The bot does not know whether
   the reader is a mother, father, grandparent or nanny.
   - Fine: «вы справляетесь», «у вас получилось», «вы молодец», «вы вправе передохнуть»,
     «для ребёнка вы — самый нужный человек».
   - Rejected by tests: «вы добрая/добрый», «вы очень заботливая», «вы устал(а)».
3. **No role words**: мама, папа, мать, отец (use «родитель», «взрослый», or nothing).
4. **`{child}` only as a nominative subject, without gendered pronouns or adjectives**:
   «{child} засыпает спокойнее, когда рядом ваш голос». Never «для {child}», «у {child}».
5. **Honest and specific**, never a comparison with other people, never pressure («надо»).
6. **No medical or psychological advice.** A breath, a pause, a small step: yes. Treating anxiety: no.
7. **Proverbs: traditional only**, with a one-line `note` that reads as support, not as a lecture.
8. **Luna speaks in the feminine** in `frames.yaml` («заглянула», «хотела»); tests reject
   masculine forms there.

See `docs/CHEER.md` for how the skill chooses and sends items.
