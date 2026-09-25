# Resume Optimization Tool

A tagged database of every resume bullet Tim King has written. It matches the bullets against any job description, produces a bare-boned tailored resume, and learns from each posting and each answer.

**Live front end:** [Resume Match Desk](https://claude.ai/artifact/MjpDTLqwPWSc9ujB4A3uUh) (private). It runs in four steps: paste a JD, review the draft, answer five questions, then download the final PDF.

## What's in the database

| Layer | Rows | What it is |
|---|---|---|
| `sources` | 18 | 16 resume versions + the Liminal work summary + a LinkedIn capture |
| `raw_bullets` | 342 | Every bullet exactly as written, never edited |
| `achievements` | 52 | One per real accomplishment. Every raw bullet maps to at least one; ingest fails otherwise |
| `bullets` | 79+ | Bare-bone renderings: one canonical per achievement plus angle variants. Append-only, so edits supersede old rows |
| `tags` | 84 in 15 families | Niche keywords with JD synonyms (e.g. *Channel Strategy*, *Funding-Source Diagnostics*, *CPM/CPA Modeling*) |
| `achievement_tags` | 224 | One-to-many weighted links between achievements and tags |
| learning tables | growing | `job_descriptions`, `jd_requirements`, `followups` (Gate 1 and 2 answers), `feedback`, `generated_resumes` |

**Bullet standard ("Resume 1"):** canonical bullets stay inside Resume 1's length band. That band is p10 97, median 143, p90 167 characters, with a ceiling of 170. They are verb-first and outcome-driven. The canonical median is 142.

## Layout

```
extract.py            sources -> sources/raw_extract.json (docx + pdf + LinkedIn capture)
rot.py                CLI: ingest | query | match | build | export | learn | profile
schema.sql            SQLite schema (SWAT Engine conventions: enums, append-only, source pointers)
curation/
  taxonomy.json       tag families, tags, JD synonyms
  achievements.json   canonical bullets, variants, tags, metrics, evidence patterns
  profile.json        roles, competencies, expertise areas, technologies, certifications, education
  baseline.json       summary, caps, priorities, scoring knobs, variant angle map
  learned.json        Gate answers and artifact syncs (overrides, retired variants, new bullets)
resume.db             the database (committed)
data/library.json     export consumed by the web artifact (confidential names scrubbed)
data/dump.sql         text dump for readable diffs
artifact/index.html   Resume Match Desk source
reports/              LinkedIn cross-reference, data profile
out/                  generated resumes (JSON, MD, HTML, PDF)
```

## Commands

```bash
python extract.py                                      # re-read all source resumes
python rot.py ingest                                   # rebuild curated tables, verify coverage + lengths
python rot.py query --tags "Channel Strategy"          # bullets for a tag (label or id)
python rot.py query --family fundraising
python rot.py match samples/jd_sample_director_gtm_adtech.txt   # requirement map, coverage, ranked bullets
python rot.py build --version v2                       # baseline resume -> out/baseline_v2.{json,md,html,pdf}
python rot.py build --jd path/to/jd.txt --version v1   # tailored resume
python rot.py export                                   # data/library.json + data/dump.sql
python rot.py learn learnings.json                     # merge the artifact's learnings
python rot.py profile                                  # reports/db_profile.md
```

## The learning loop

1. **Gate 1 (baseline):** five questions asked after the phase-1 draft. The answers are stored in `followups` (gate 1) and applied through `curation/learned.json`, which supersedes rows and never overwrites them.
2. **Gate 2 (per JD, in the artifact):** Claude weighs the posting against the taxonomy, tailors the summary, and asks five questions aimed at weak coverage. The answers become new bare-bone bullets. The page stores every run, answer, new bullet and Keep/Drop/Edit click in its own database, and future matches use them right away.
3. **Sync:** ask Claude to "sync the Resume Match Desk". It reads the artifact database, runs `rot.py learn`, re-ingests, re-exports `library.json`, republishes the page and pushes here. Offline, use "Download learnings JSON" in the page, then `python rot.py learn learnings.json`.

Scoring: requirement weight × tag weight, plus a 25% roll-up of family matches, a learned Keep/Drop adjustment, a curated priority prior and a metric bonus. A variant replaces the canonical text only when its angle is a strong requirement and clearly beats the canonical's own relevance.

## Privacy

This repo is private. The Liminal engagement renders as *Chief Strategy Consultant | Confidential Healthcare AI Start-Up*. The internal role key is aliased on export, and `rot.py` refuses to write any output containing the confidential name, the partner counterparty, or the old typos.
