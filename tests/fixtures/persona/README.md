# Test person: Riley Mahoney (fictional)

Everything in this folder is invented: the person, the companies, the dates and the numbers. It exists so the shared core, the intake pipeline and Career Companion Hub can be tested without touching Tim's own data.

| File | What it is |
|---|---|
| `resume_v1_classic.docx` / `.txt` / `.pdf` | Classic layout: dates on their own line, bullets typed as `•` characters. Authored 2026-03-02. |
| `resume_v2_media_partnerships.docx` / `.txt` / `.pdf` | Media and partnerships angle: one-line role headers, real Word bullets, a skills line. Authored 2025-11-14. |
| `resume_v3_revops.docx` / `.txt` / `.pdf` | Revenue-operations angle: right-tab dates, dash bullets, a two-column skills table, the advisory engagement. Authored 2026-08-20. |
| `linkedin_profile.docx` / `.md` / `.pdf` | A LinkedIn "Save to PDF" style export (the `.md` is the paste-text path). Captured 2026-09-20. |
| `postings/*.txt` | Five postings: revenue operations, retail media sales, growth marketing, agency partnerships, GTM strategy at an AI startup. |
| `persona.json` | Ground truth: roles and dates per source, accomplishments with every wording, tools per source, and the list of deliberate traps below. |

Deliberate traps, so tests can prove the pipeline handles them:
- the same accomplishment worded differently in two or three documents (must become one accomplishment, not three);
- one metric that differs between two resumes (`hal-pipeline`: $6.1M vs $6.8M) — a disputed number that must never print until resolved;
- a role end date that differs (Kestrel: "2021 – 2024" in v1, November 2023 everywhere else);
- a title that differs (Pinecrest: Marketing Manager vs Senior Marketing Manager);
- the same amount written three ways ($1.2M, $1,200,000, "over $1M");
- numbers written as words ("three CRMs", "team of nine");
- a first-person bullet ("I partnered…") and a bullet over the 170-character ceiling;
- an early role only two sources mention (Quillstone) and a consulting engagement only the newest sources mention (Larkspur).

Regenerate with `python tests/fixtures/persona/build_persona.py` (add `--pdf` to render the PDFs with Word through `tools/docx2pdf.ps1`). Edit the script, not the outputs.
