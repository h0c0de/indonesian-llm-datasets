---
name: indonesian-llm-datasets
description: Use when choosing, citing, or downloading Indonesian-language datasets for training or evaluating language and multimodal models — Bahasa Indonesia plus Acehnese, Balinese, Banjarese, Buginese, Javanese, Madurese, Minangkabau, Ngaju, Sundanese, Toba Batak. Covers sentiment, MT, NER/POS, summarization, QA, speech, paraphrase, knowledge graphs, and multimodal corpora, and flags entries whose links are known dead.
---

# Indonesian LLM datasets

A markdown catalogue of Indonesian datasets, kept link-checked. Use this skill to find a corpus for a task, to check whether a listed source is still reachable, and to avoid citing a dead download.

## Layout

| path | contents |
| --- | --- |
| `data/00_dataset_categories.md` | index of all 14 categories |
| `data/01` … `data/14` | one file per task; `01` NLU, `04` web crawl, `09` speech, `11` MT, `12` lexicon, `13` pre-trained models, `14` tools |
| `scripts/check_links.py` | the link checker; the source of truth for whether a URL works |
| `ATTRIBUTION.md` | provenance and licensing status of the catalogue itself |

Entries are `##` headings with bolded fields:

```markdown
## Dataset name

- **Description**: one line
- **Size**: counts with units
- **Links**: [Download](url) | [Paper](url)
```

## Look something up

```bash
grep -n -i 'sentiment' data/*.md          # by task keyword
grep -n -i 'sundanese\|javanese' data/*.md # by language
grep -rn 'huggingface.co/datasets/' data/ | head -40   # loadable datasets
```

## Verify before citing

```bash
python3 scripts/check_links.py            # exits 1 when a link is dead
python3 scripts/check_links.py --markdown-out report.md
```

Rules that follow from how the checker classifies results:

- `dead link, Oct 2026` in an entry means the dataset was unreachable at the last audit and no replacement existed. Cite the dataset by name if you must, but do not hand the URL to a user as a download.
- A 403 or 429 is a bot wall, not a missing page. Do not record a source as gone on that basis alone.
- Before recommending a URL you have not opened, run the checker. One live call settles it; docs and READMEs do not.

## Traps that have bitten this catalogue

- **HuggingFace dataset links need the owner.** `huggingface.co/datasets/indonli` 404s; the repo is `afaji/indonli`. A missing repo answers **401**, not 404, so it looks gated when it simply does not exist.
- **NusaX on the Hub** is `indonlp/NusaX-senti` and `indonlp/NusaX-MT`; the lexicon ships only as CSVs in `IndoNLP/nusax`, not as a dataset repo.
- **SEACrowd datasets** (`SEACrowd/kopi_cc_news`, `SEACrowd/wikilingua`) need `pip install seacrowd` or `load_dataset(..., trust_remote_code=True)`.
- **OPUS corpora** moved to `opus.nlpl.eu/datasets/<Corpus>`; every old `*.php` page is gone.
- **Common Voice** is versioned (`mozilla-foundation/common_voice_17_0`); a pinned version will drift.

## Licensing

The catalogue carries no upstream licence — see `ATTRIBUTION.md`. Dataset terms are per entry and are not uniform: news corpora (Kompas, Tempo) are usually copyright-restricted, most academic sets are research-only, and translated sets inherit the original licence. Check before any commercial use.

## Maintenance

Add an entry in the existing shape, then run the checker; a pull request that adds a dead link fails CI. Releases are cut by pushing a `v*` tag, which renders notes from conventional commits via `git-cliff`.
