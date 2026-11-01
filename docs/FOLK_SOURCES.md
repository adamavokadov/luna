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
- **Oral-tradition collections** (`oral_*`, no publisher and no year): plots known from many recordings and
  retellings (Panchatantra and Jataka, Anansi, Nasreddin, Maori and Aboriginal stories, Greek myths, and so on),
  written from general knowledge, not from one edition. Modern authored picture-book retellings of a folk plot
  are not reproduced: only the traditional plot is used, in our words.
- **Cultural care** for plots of living peoples (Indigenous, Aboriginal, African and others): tell them as a tale
  of that people, with the origin named in `origin`; do not mix names, creatures or customs from different
  peoples; do not retell ceremonies or sacred rites; keep the tone of a story told to children, not of a rite.
  When unsure of a detail, leave it out rather than invent it.

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
seeded `random.Random`. `pick_folk_source` chooses one plot for a tale: weighted random among the top 3, like
`select_classic`.

## How the bot uses it (automatic)

`TaleHarness._folk_source_for` decides, in code and before the model runs:

| Situation | Plot offered? |
|---|---|
| "Surprise me" (the model picks the format), no idea | yes; the task says: use it if the chosen format is plot-based, then do not call `pick_classic` |
| Format with skill metadata `folk-source: open` (`original`, `rhyme`, `bedtime`), no idea | yes |
| `values` (`folk-source: motif`) with a value in the idea ("Делиться", "Говорить правду") | yes, chosen by motif (`folk_idea_hints.yaml`); the idea stays in the prompt |
| Any parent idea in the other formats, or an idea naming no known value | no: the parent's wish is kept as is |
| `classic`, `cumulative`, `funny`, `riddles`, `celebration`, `sequel`, `educational`, `life-event`, `metaphorical`, `meditation` | no (they have their own structure or purpose) |
| Sensitive topic, or `FOLK_SOURCES_ENABLED=false` | no |

The pick uses the child's age and `scary` limit, bedtime (calm plots only), interests (themes), and the tale history:
plots already told are pushed down, liked ones up, disliked ones far down (the same `seed_id` history as classics).
When the finished tale used a plot-capable format, the plot id is saved as the tale's `seed_id` and the mode is
`folk`; in "surprise me" the model may still choose a format that ignores the plot, then nothing is recorded.
A separate random generator keeps classic selection unchanged.

## Adding plots

1. Read the tale. Write the summary and beats from memory of the *plot*, not from the sentences.
2. Append to `world_folk.yaml` (add a `collections` entry if the book is new), keep `id` short.
3. Soften harsh places in `ending_hint` (and set `scary` honestly). Avoid appearance-based morals.
4. `make kb-check && make test`.

## Catalog of the first batch (patch 0006)

The first 35 plots, from 8 collections. Plots of 1,500+ words were summarized from sampled passages
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

## Second batch (patch 0008): 46 plots from other cultures

Written from general knowledge of each tradition, not from a book (collections `oral_*`). Two were checked
against several public sources before writing (how Anansi bought the tales of the Sky God; Tiddalik, a story of the
Gunai/Kurnai people of Victoria); the rest were not checked against sources (see HANDOFF, unverified item 13).

| Region (collection) | Plots |
|---|---|
| Africa (`oral_africa`) | Как Ананси купил сказки, Горшок мудрости (ashanti); Черепаха летит на пир (igbo); Почему Солнце и Луна живут на небе (efik); Почему комар жужжит в ухо; Заяц, бегемот и слон (общеафриканские); Унанана и слон (zulu) |
| India (`oral_south_asia`) | Обезьяна и крокодил, Заяц и лев, Слон и слепцы, Бирбал и кичри, Царь обезьян, Три рыбы, Синий шакал |
| East and South-East Asia (`oral_east_se_asia`) | Chinese: Чудище Нянь, Пастух и ткачиха, Нюйва чинит небо, Хоу И и девять солнц; Japanese: Мышка ищет самого сильного жениха, Дзидзо в соломенных шляпах, Момотаро, Иссумбоси; Korean: Брат и сестра, ставшие Солнцем и Луной, Хынбу и Нольбу; Vietnamese: Пирог баньчынг, Бамбук в сто колен; Indonesian: Мышиный олень и крокодилы; Filipino: Обезьяна и черепаха |
| Turkey (`oral_middle_east`) | Три анекдота о Ходже Насреддине: Котёл, который родил; Угощение для шубы; Ключ под фонарём |
| Europe (`oral_europe`) | Irish: Финн Маккул и младенец, Лосось знания; Norwegian: Муж-хозяин, Почему море солёное; Finnish: Кантеле Вяйнямёйнена; Greek: Царь Мидас, Деметра и Персефона, Северный ветер и Солнце; Portuguese: Суп из камня |
| Americas, Oceania, Australia (`oral_americas_pacific`) | Ворон и свет (Pacific Northwest Coast); Почему у опоссума голый хвост (cherokee); Кролик на Луне, Кетцалькоатль и кукуруза (aztec); Мауи ловит Солнце (maori); Лягушка Тиддалик (gunai) |

Harsh originals are softened through `ending_hint` (swallowing, hunting, tigers, ogres, heart-eating, deaths); the
plots that remain sad (Журавлиные перья, Деметра и Персефона) say how to keep a gentle ending.

Ideas for later batches: Georgian, Armenian, Persian, Mongolian, Kazakh and Central Asian tales (Aldar Kose),
Sami and Inuit gentle tales, more Native American tales told with the people's own framing, Pacific islands, the
Arabian Nights (curated), Slavic tales that are not yet in `classics.yaml`.
