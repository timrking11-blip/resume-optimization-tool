# Resume Optimization Tool

A tagged database of every resume bullet Tim King has written. It matches the bullets against any job description, produces a bare-boned tailored resume in Tim's source template, and learns from each posting and each answer.

**Live front end:** [Resume Match Desk](https://claude.ai/artifact/MjpDTLqwPWSc9ujB4A3uUh) (private). It runs in four steps: paste a JD, review the draft, answer five questions, then download the final PDF or Word file.

## The template

Every resume the tool produces follows `TIM KING SOURCE RESUME.docx` (copied to `sources/`, the default since 2026-09-27). The yellow "Section A–D" labels in that file are annotations and never print.

| Order | Section | Filled from |
|---|---|---|
| 1 | Name, contact line with LinkedIn / GitHub / Website links | `profile.json` identity |
| 2 | **Professional Summary & Areas of Expertise**: tagline (**A**), expertise line (**B**), Technologies | `tagline_phrases`, `competencies`, `technologies`, JD-ranked. There is no summary paragraph. |
| 3 | Education | `education` |
| 4 | Professional Experience: title, employer and right-aligned dates, a gray context line, bullets | `roles` + selected bullets |
| 5 | Credentialing & Certifications | `certifications` (hidden ones skipped) |
| 6 | **Business Consulting Engagements** (**C**): client, location, dates, commitment, italic description, long-form bullets | `engagements` + each achievement's `longform` wording |
| 7 | **Core Competencies** (**D**): five categories | `core_competencies` |

The short and long versions of the same work can both print: short under the role, long in Section C. The identical sentence never prints twice. An achievement with no long form prints once, in Section C. An engagement still missing its dates and description (`needs_details`) stays hidden. The Match Desk asks for those details the first time a posting values consulting work.

`templates/docx_template.json` (built by `make_template.py`) holds the source file's own Word styles, numbering, theme and page setup, plus one paragraph definition per element. The CLI and the Match Desk both build Word documents from it, so the two produce the same `document.xml`. PDFs come from Word itself (`tools/docx2pdf.ps1`) on this PC, from headless Chrome as a fallback, and from jsPDF with the bundled Carlito font in the Match Desk. Carlito is metrically identical to Calibri and ships under the SIL Open Font License (`fonts/OFL.txt`).

## What's in the database

| Layer | Rows | What it is |
|---|---|---|
| `sources` | 19 | 16 resume versions, the Liminal work summary, a LinkedIn capture and the source template |
| `raw_bullets` | 372 | Every bullet exactly as written, never edited |
| `achievements` | 61 | One per real accomplishment. Every raw bullet maps to at least one; ingest fails otherwise |
| `bullets` | 100+ | Bare-bone renderings: one canonical per achievement plus angle variants, including the Section C `longform`. Append-only, so edits supersede old rows |
| `tags` | 84 in 15 families | Niche keywords with JD synonyms, now including tool names such as HubSpot, Marketo and GitHub |
| `achievement_tags` | 259 | One-to-many weighted links between achievements and tags |
| `tagline_phrases` | 7+ | Section A identity phrases, tagged |
| `competencies` | 34+ | Section B expertise items (the template's 16 in its order, plus the rest of the bank) |
| `technologies` | 22+ | The template's Technologies line, tagged |
| `engagements`, `engagement_achievements` | 2, 10 | Section C clients and the achievements each shows |
| `core_competencies` | 40 | Section D items in five categories |
| learning tables | growing | `job_descriptions`, `jd_requirements`, `followups` (with `section`), `feedback`, `generated_resumes` |

**Bullet standard ("Resume 1"):** role bullets stay inside Resume 1's length band. That band is p10 97, median 143, p90 167 characters, with a ceiling of 170. They are verb-first and outcome-driven. Section C bullets have their own band from the template: 170 to 340 characters.

## Layout

```
extract.py            sources -> sources/raw_extract.json (docx, pdf, LinkedIn capture, source template)
make_template.py      source template -> templates/docx_template.json (Word parts + paragraph definitions)
rot.py                CLI: ingest | query | match | build | export | learn | profile | sync-prepare | sync-apply
schema.sql            SQLite schema (SWAT Engine conventions: enums, append-only, source pointers)
curation/
  taxonomy.json       tag families, tags, JD synonyms
  achievements.json   canonical bullets, variants (incl. longform), tags, metrics, evidence patterns
  profile.json        identity + links, roles, education, certifications, technologies,
                      tagline phrases (A), competencies (B), engagements (C), core competencies (D)
  baseline.json       template id, section order, caps, priorities, Section C caps, B order, scoring knobs
  learned.json        Gate answers and Match Desk syncs (overrides, new bullets, template-section entries)
templates/            docx_template.json (Word) and resume.html (HTML/Chrome fallback)
tools/docx2pdf.ps1    Word -> PDF export (read-only open; never touches documents Tim has open)
fonts/                Carlito (OFL) for the Match Desk's PDFs
resume.db             the database (committed)
data/library.json     export consumed by the web artifact (confidential names scrubbed)
data/dump.sql         text dump for readable diffs
artifact/index.html   Resume Match Desk source
reports/              LinkedIn cross-reference, data profile
out/                  generated resumes (DOCX, PDF, HTML, MD, JSON); out/runs/ = synced postings
```

## Commands

```bash
python make_template.py                                # rebuild templates/docx_template.json from sources/
python make_template.py "path/to/updated source.docx"  # copy an updated source template in, then rebuild
python extract.py                                      # re-read all source resumes
python rot.py ingest                                   # rebuild curated tables, verify coverage + lengths
python rot.py query --tags "Channel Strategy"          # bullets for a tag (label or id)
python rot.py match samples/jd_sample_director_gtm_adtech.txt   # requirements, coverage, tagline, expertise, bullets, Section C
python rot.py build --version v4                       # baseline -> out/baseline_v4.{docx,pdf,html,md,json}
python rot.py build --jd path/to/jd.txt --version v1   # tailored resume
python rot.py export                                   # data/library.json + data/dump.sql
python rot.py learn learnings.json                     # merge the artifact's learnings
python rot.py profile                                  # reports/db_profile.md
python rot.py sync-prepare [--all]                     # from sync/dump (ArtifactData out_dir) -> sync/pending.json
python rot.py sync-apply                               # + sync/polished.json -> learn/ingest/export/DOCX+PDF/commit/push
```

## Saved work
The Match Desk saves your working state as you go: the posting, company and title, Claude's tagline and expertise order, your answers, answer bullets and entries, engagement details, Keep/Swap/Drop choices, line and bullet edits, and the final draft.
- **Where it's saved:** instantly in the browser, and in your private area of the page database (`data/users/<you>/workspace`).
- **On open:** the page reopens exactly where you left off. The sample posting only appears on a first-ever visit. Sessions saved before the template change open with the template's tagline and expertise line.
- **Past postings:** **Saved postings** reopens any earlier posting. **New posting** starts a blank one, and nothing is lost.
- **Syncs don't reload the page.** The hourly sync updates the bullet bank through the page database (`library/current`) and never republishes the page. A newer bank applies on open, before you start working. Otherwise it waits for your next posting.
- **Synced answers show polished.** Once a posting's answers are synced, reopening it shows their polished bank versions, using the sync's `synced_map`.

## The learning loop

1. **Gate 1 (baseline):** five questions asked after the phase-1 draft. The answers are stored in `followups` (gate 1) and applied through `curation/learned.json`, which supersedes rows and never overwrites them.
2. **Gate 2 (per JD, in the artifact):** Claude weighs the posting against the taxonomy, orders the tagline (and may propose up to two new phrases the bank supports), orders the expertise line, and asks five questions. Each question has a `section`:
   - **Experience:** a weakly proven requirement becomes a Resume 1 bullet.
   - **Consulting engagement:** asked when the posting values consulting and an engagement still lacks details. A short form collects the client name as it should print, location, dates, commitment and a one-line description; the answer becomes Section C bullets (short and long form).
   - **Technology:** asked when the posting names tools your list doesn't have. Tools you've used join the Technologies line.
   - **Tagline / Expertise:** asked when the posting stresses an identity or strength no stored phrase covers.

   The page stores every run, answer, entry and Keep/Drop/Edit click in its own database, and future matches use them right away. Editing the tagline, expertise, Technologies or a Section D line on the sheet also records any new items.
3. **Sync, automatic:** downloading a PDF or Word file marks that posting *pending*. The scheduled task **Resume Match Desk sync** runs at 5 past every hour, 8 AM to 11 PM, while the Claude app is open, and follows [SYNC_RUNBOOK.md](SYNC_RUNBOOK.md):
   - it dumps the page database and runs `rot.py sync-prepare`;
   - Claude polishes any bullet or phrase that breaks its section's rules;
   - `rot.py sync-apply` learns, re-ingests, exports, renders a Word file and PDF per downloaded posting under `out/runs/`, commits and pushes;
   - the task updates the page library and marks the documents synced.

   Ask Claude to "sync the Resume Match Desk" to run it now. Offline fallback: "Download learnings JSON", then `python rot.py learn learnings.json`.
4. **Answer polishing:** in the page, **Turn into bullets with Claude** (per answer) and **Polish all answers** convert bulleted or rambling answers into Resume 1 bullets, Section C bullets, or short entries you can preview and edit. Anything over its ceiling gets an automatic tighten pass. **Polish** on any resume bullet rewrites it with the same facts, to the Resume 1 standard for roles or the Section C standard for engagements.

Scoring: requirement weight × tag weight, plus a 25% roll-up of family matches, a learned Keep/Drop adjustment, a curated priority prior (the template's picks first) and a metric bonus. A variant replaces the canonical text only when its angle is a strong requirement and clearly beats the canonical's own relevance. Tagline phrases, expertise items, technologies and Section D items are ranked by the same requirement weights, with the template's order breaking ties.

## Privacy

This repo is private. The current role renders as *Business Consultant - GTM Engineer & Strategic Advisor | Strategic Market Insights (self-employed)*. The healthcare AI start-up appears only as "Healthcare Technology Start-Up (Confidential)". The internal role key is aliased on export, and `rot.py` refuses to write any output (Word, PDF, HTML, Markdown or JSON) containing the confidential name, the partner counterparty, or the old typos.
