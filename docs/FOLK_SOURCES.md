# Folk sources: world folk plots as raw material for new tales

`src/skazki_bot/knowledge/tales/world_folk.yaml` holds traditional plots from many peoples (Chinese,
Hungarian, Kalmyk, Cossack, Japanese, French, Baltic, Russian epic, and more) as **our own synopses**,
cut into the smallest meaningful story units. The bot can retell a whole plot for a child, or take
one unit as the seed of an original tale. Loader and retrieval: `knowledge/folk_sources.py`.

## What is stored, and what is deliberately not

The plots are traditional; the Russian *texts* of the collections they were read in are
retellings, translations and editions with their own authors and publishers. So:

- **Stored:** a short summary, 5-7 `beats` (one event per line, the "chunks"), the moral, themes
  and motifs, an age range, a `scary` level, a `calm` flag, how to weave a child in, and, where the
  original is harsh, an `ending_hint` that softens it. All written in our words.
- **Never stored:** passages, dialogue lines, quotations or close paraphrase from any collection.
  The extracted source texts are not in the repository, not in patches, not in the package.
- **Provenance only:** each plot names the `collection` (title, publisher, year) it was read in, so
  a human can find the original. A collection is never a source of text for the bot.
- Tests reject quotation marks and dialogue dashes (the signature of pasted text), emoji, plots
  with fewer than 4 or more than 9 beats, and any `scary >= 2` plot without an `ending_hint`.
- Authored literary works (a modern author's plays or stories, poems of 20th-century poets) are
  not folk material and are not included; see the catalog below.

## Schema (`world_folk.yaml`)

Top level: `collections` (`id`, `title`, `publisher`, `year`) and `tales`. A tale has:
`id` (a-z0-9_, <= 40), `title`, `origin`, `kind` (animal, wonder, everyday, trickster, legend,
epic, parable), `collection`, `summary`, `beats` (4-9, 15-180 characters each), `moral`, `themes`
(the vocabulary of `classics.yaml`), `motifs` (see the header of the file), `min_age`, `max_age`,
`scary` (0-3), `calm` (fine for bedtime; requires `scary <= 1`), `child_role`, `ending_hint`.

## Using it

```python
import random

from skazki_bot.knowledge import find_folk_sources, folk_source_block, load_folk_sources

plots = find_folk_sources(
    load_folk_sources().tales,
    age=6,
    themes=["animals"],
    motifs=["kindness_rewarded"],
    bedtime=False,
    seen=["chinese_zheltyy_aist"],
    limit=3,
    rng=random.Random(),
)
# Russian prompt block: summary, numbered beats, moral, ending hint
print(folk_source_block(plots[0]))
```

Selection filters by age, `scary` (the age profile's limit, and at most 1 at bedtime, calm plots
only), then ranks by theme overlap, motif overlap and "not seen yet". It is deterministic for a
seeded `random.Random`. **It is not wired into the harness yet**: see HANDOFF, next steps.

## Adding plots

1. Read the tale. Write the summary and beats from memory of the *plot*, not from the sentences.
2. Append to `world_folk.yaml` (add a `collections` entry if the book is new), keep `id` short.
3. Soften harsh places in `ending_hint` (and set `scary` honestly). Avoid appearance-based morals.
4. `make kb-check && make test`.

## Catalog of the first batch (patch 0006)

35 plots from 8 collections. Plots of 1,500+ words were summarized from sampled passages
(opening, three places in the middle, ending), the rest from a full read; a human read-through of
the longer ones is on the unverified list.

| Collection | Plots now | Not included yet / why |
|---|---|---|
| Chukchi tale "Чей дом лучше?" (АСТ 2026) | 1 (all) | - |
| Казачьи сказки. Волшебная бусинка (2024) | 3 | the parable about a Cossack potter (reads as authored, not folk) |
| Мангас и трое смелых братьев. Калмыцкие сказки (2024) | 2 | two epic-style tales (Овше, Бюрюн-Тегес): to read |
| Мудрые китайские сказки (2024) | 8 (all) | - |
| Дерево-до-небес. Венгерские сказки (2017) | 8 | 23 more, mostly long (2,000-5,000 words): next batches |
| Хрестоматия 1-2 кл. Зарубежная литература (2022), folk section | 9 | about 12 folk tales of 1,300-2,800 words; Aladdin (6,900 words) |
| Азербайджанские сказки, сост. А. Ахундов (1955) | 1 | 29 more; many are adult satire (clergy, officials) or violent: needs curation, two short ones skipped for their moral |
| Былины (2025) | 3 | 17 more byliny; the violent ones need `ending_hint` care |

Not included, with reasons:

- **Отпуск Деда Мороза** (2003): six New Year plays by named modern authors. Authored and protected, not folk.
- **Полная хрестоматия, книга 1** (2023), authored parts: Russian classics and poetry. Folk tales in it (Колобок, Теремок, Гуси-лебеди...) are already in `classics.yaml`.
- **Хрестоматия, зарубежная**, authored parts (Perrault, Grimm, Andersen, Kipling): public-domain originals, mostly already in `classics.yaml`; the Russian translations in the book are not used.
- **Мифы и легенды эскимосов** (Rink, Russian edition 2007): ethnographic, mostly dark (revenge, shamans, death). Skipped for children; a few gentle legends may be picked later after a careful read.
- **Былины** exists twice in the archive (identical files); one was read.
