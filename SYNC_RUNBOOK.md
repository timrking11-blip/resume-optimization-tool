# Match Desk sync runbook

The Resume Match Desk (https://claude.ai/artifact/MjpDTLqwPWSc9ujB4A3uUh) marks a posting `sync_status: "pending"` when its PDF or Word file is downloaded. This runbook folds pending postings into `resume.db`, updates the page's bullet bank in its database (never republishing the page), and pushes to GitHub (private repo `timrking11-blip/resume-optimization-tool`). The scheduled task `resume-desk-sync` runs it hourly. Asking Claude to "sync the Resume Match Desk" runs it on demand.

Working folder: `C:\Users\timrk\OneDrive\Desktop\Career Finder Folder\Resume Optimization Tool`

Every resume renders in the source template (`TIM KING SOURCE RESUME.docx`, Sections A–D). Besides bullets, a posting can now teach the bank four other kinds of entry. Each one arrives as a `bullet_inbox` document with a `section`:

| `section` | What it is | Lands in |
|---|---|---|
| `experience` (or missing) | a Resume 1 bullet for a role; each bullet carries its own `role`, so one answer can feed several roles | an achievement or a learned bullet |
| `engagement` | a Section C bullet for a consulting engagement (`engagement_key`); may carry a `longform` version, and edits of a Section C bullet arrive with `angle: "longform"` | an achievement tied to that engagement |
| `engagement_details` | client name as printed, location, dates, commitment, one-line description (`details`) | `learned.json` → `engagement_updates` (the engagement stops waiting for details) |
| `tagline` / `expertise` / `technology` / `competency` | a short phrase for Section A, the Section B line, the Technologies line, or a Section D category | `learned.json` → `tagline_phrases` / `competencies` / `technologies` / `core_competencies` |

## Steps

1. **Anything pending?** ArtifactData `query` on the artifact URL: collection `jd_runs`, query `{"where": [["sync_status", "==", "pending"]], "limit": 50}` (no `out_dir`). If nothing matches, stop and report "Nothing to sync."
2. **Fresh dump folder:** `rm -rf sync/dump && mkdir -p sync/dump`.
3. **Dump the store:** run ArtifactData `query` three times with `out_dir` set to the absolute path of `sync\dump`: `jd_runs` (limit 300), `bullet_inbox` (limit 1000), `feedback` (limit 1000).
4. **Prepare:** `python rot.py sync-prepare`. It writes `sync/pending.json` with `bullets`, `phrases` and `engagement_updates`, and lists every entry flagged `POLISH`. A bullet that states a number its answer never states is flagged `numbers not in the answer`.
5. **Polish** (this is the Claude step): read `sync/pending.json`. Write `sync/polished.json`, a JSON object keyed by each entry's `key`.
   - **Bullets:** `{"text": "...", "tags": [...]}` for a rewritten bullet. Use tag ids from `curation/taxonomy.json`. Add `"achievement_id": "<existing id>"` only when the answer clearly enriches that same accomplishment; check with `python rot.py query --tags "<label>"`. For a bullet with `"engagement"`, also return `"longform"` (170–340 characters, same facts with scope, method and result) when the answer supports it. For an entry with `angle: "longform"`, the `text` itself is the long form (170–340 characters).
   - **Phrases:** a plain string (the cleaned phrase) or `null` to skip. Tagline: a noun phrase of 60 characters or fewer, like "Process Engineer". Expertise: Title Case, 70 or fewer, like "Lead Generation & Prospecting". Technology: the tool as a resume lists it, like "Salesforce Apex (basic)". Competency: a short lowercase phrase. No first person and no closing period.
   - `null` skips a duplicate or anything with nothing resume-worthy. Entries not flagged may be left out, and they are then learned as written. Engagement details are applied as given.

   **Resume 1 standard (bullets):** start with a verb and lead with the outcome. Stay within 97–170 characters. Write in implied first person, never "I", "my", "we" or "Tim". Use past tense for past roles.

   **Facts:** use only facts stated in the answer. You may merge in facts already present in the bullet being enriched. Never invent numbers, names, tools or results. `sync-apply` refuses any bullet whose numbers are not in its answer (or in the bank bullet it enriches), even after polishing, so remove the number or return `null`.

   **Confidentiality:** never name the healthcare client (Liminal), the partner counterparty (Therapy Companion) or its contact (Kamal).
6. **Apply:** `python rot.py sync-apply`. This runs learn (answers, edits, phrases and engagement details go to `curation/evidence/answers.jsonl` first; application outcomes go to the `outcomes` table and `data/feedback/outcomes.jsonl`; each run's traced lines go to `generation_events`), ingest (evidence, claims, confidence), export, the data profile, a Word document, PDF and QA trace of each downloaded posting under `out/runs/` (Word renders the PDF; headless Chrome is the fallback; QA findings are reported, never block a sync), then commit and push. Keep the printed JSON, which has `mark_synced`, `synced_map`, `commit` and `synced_at`. If it prints `PUSH FAILED`, report that and continue. The commit is still local.
7. **Update the page's bullet bank through the database. Never republish the page during a sync**, because a new page version would reload any copy Tim has open. Run ArtifactData `set` on the URL with collection `library`, doc_id `current`, and `file_path` set to the absolute path of `data\library.json`. The page loads this document on open and applies it only before Tim starts working. Otherwise it waits for his next posting.
8. **Mark synced** with ArtifactData `batch`, 50 writes per call at most. Pin each entry's `if_version` to the version shown for that document in step 3's dump output.
   - Each `mark_synced.jd_runs` id gets an `update` of `{"sync_status": "synced", "synced": true, "synced_at": <synced_at>, "sync_commit": <commit>, "synced_map": <synced_map[run id] or {}>}`. `synced_map` tells the page which bank bullet replaced each answer bullet, so saved sessions show the polished versions.
   - Each `bullet_inbox` and `feedback` id gets an `update` of `{"synced": true}`. That includes phrase and engagement-details documents.
   - Then `set` the document `meta/sync` to `{"last_synced_at": <synced_at>, "commit": <commit>, "runs": n, "new_bullets": n, "template_items": learned.sections, "feedback": n}`.
   - If a pinned entry fails because the document changed since the dump, drop that entry and retry the rest. The changed document stays pending, and the next sync picks it up.
9. **Report** in one line: postings synced, bullets learned, template entries learned, evidence rows added, outcomes recorded, commit hash.

## Why the page stays consistent
Once a document is marked synced, the page ignores it for scoring, the inbox, and its section stores, because its content now lives in the bank (`library/current` in the page database, mirrored in `data/library.json`). Nothing is counted twice. `rot.py learn` is idempotent: follow-ups and feedback carry dedupe keys, phrases dedupe against the stores, and a re-run after a crash does not double-apply.
