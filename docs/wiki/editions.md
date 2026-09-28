# Editions

## Resume Match Desk (private)

Tim's page over his own record. `artifact/index.html`, published at https://claude.ai/artifact/MjpDTLqwPWSc9ujB4A3uUh (Version 9, shared with invited people only). Capabilities `db`, `sample`, `downloads`, `user`. The record is git JSON exported to `data/library.json`; a download marks the run pending and the hourly sync (`SYNC_RUNBOOK.md`) folds answers, edits and feedback back into git and re-exports the bank into `library/current`. Never republish the page during a sync; publish only with nothing pending and outside :00–:15.

## Career Companion Hub (public)

`hub/`, published at https://claude.ai/artifact/QyjWByEDftrtDWv6cMZrRx with capabilities `sample` and `downloads` only, so the link can be public. Guide: https://claude.ai/artifact/786dD7KPL85z3Fp9v4xTz8. Files published beside the page: `hub.js`, `store.js`, `intake.js`, `core/rot_core.js`, `taxonomy/gtm_v1.json`, `template/docx_template.json`, `fonts/Carlito-*.ttf`, `vendor/pdf.worker.min.js`, `example/backup.json` (the fictional Riley Mahoney record).

### Fact brief

**What it does.** Tailors a resume to one job posting from the person's own record. Paste a posting; the page extracts weighted requirements from a GTM skill taxonomy, scores how much of them the record proves, and drafts a resume from the best-proving entries in a plain single-column template. It asks up to five questions aimed at the weak spots; answers become entries only after every number in them is found in the answer and the person approves them. Word and PDF download; downloading adds the approved entries to the record with the answer as evidence.

**How the record is built.** Upload a resume (Word, PDF, text) or paste it, or type roles and accomplishments by hand. Document lines are kept verbatim as evidence; Claude (or a layout heuristic without Claude) points at lines for roles, entries, education, certifications, skills and tools; a review screen precedes every addition. A second document corroborates matching entries and surfaces disagreements (dates, titles, figures) as choosers; an unsettled figure never prints.

**Who it is for.** People applying for go-to-market, sales, marketing, revenue operations and partnerships roles; the taxonomy (94 skills in 14 families) is tuned to those postings.

**What it never does.** Invent an employer, title, date, number, tool or outcome; print a number that is not in the evidence or the answer; treat Claude's wording as a fact; post, share, email or log anything; keep analytics. Claude runs on the viewer's own account after a one-time consent per visit, and never receives the phone number, email or backup file.

**Where the data lives.** In the viewer's browser only. Backups are JSON files (`cch-backup/1`) the person downloads and can load on any device. "Delete everything" needs the word `delete` typed.

**Without Claude** (signed out, or consent declined): keyword matching, template questions from the gap analysis, answers split into entries as typed, the layout heuristic for uploads. Everything still verifies and downloads.

### Feature registry

`hub/store.js` `Hub.register({id, label, order, mount, refresh})`; `hub/hub.js` registers `evidence`, `match`, `postings`, `backup`, `how`; `hub/intake.js` mounts into the evidence view on `Hub.on("ready")`. A new feature (the paste-based hiring-manager research brief planned for v1.1) is one more registration.

### Roadmap

- v1 (2026-09-28): manual entry, upload intake with review and conflicts, match, questions, verified entries, Word/PDF, sessions, outcomes, backups, guide.
- v1.1: research brief from pasted text; a Claude-side intake checklist run in the published page; the "same as…" picker for entries the merge could not decide.
- Pilot: 5–10 people from Tim's network; then the hosted-app decision (accounts, server storage, billing, deletion) in a written memo.
