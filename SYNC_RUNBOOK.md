# Match Desk sync runbook

The Resume Match Desk (https://claude.ai/artifact/MjpDTLqwPWSc9ujB4A3uUh) marks a posting `sync_status: "pending"` when its PDF is downloaded. This runbook folds pending postings into `resume.db`, republishes the page's `data/library.json`, and pushes to GitHub (private repo `timrking11-blip/resume-optimization-tool`). The scheduled task `resume-desk-sync` runs it hourly. Asking Claude to "sync the Resume Match Desk" runs it on demand.

Working folder: `C:\Users\timrk\OneDrive\Desktop\Career Finder Folder\Resume Optimization Tool`

## Steps

1. **Anything pending?** ArtifactData `query` on the artifact URL: collection `jd_runs`, query `{"where": [["sync_status", "==", "pending"]], "limit": 50}` (no `out_dir`). If nothing matches, stop and report "Nothing to sync."
2. **Fresh dump folder:** `rm -rf sync/dump && mkdir -p sync/dump`.
3. **Dump the store:** run ArtifactData `query` three times with `out_dir` set to the absolute path of `sync\dump`: `jd_runs` (limit 300), `bullet_inbox` (limit 1000), `feedback` (limit 1000).
4. **Prepare:** `python rot.py sync-prepare`. It writes `sync/pending.json` and lists every bullet flagged `POLISH`.
5. **Polish** (this is the Claude step): read `sync/pending.json`. Write `sync/polished.json`, a JSON object keyed by each bullet's `key`:
   - `{"text": "...", "tags": [...]}` for a rewritten bullet. Use tag ids from `curation/taxonomy.json`.
   - Add `"achievement_id": "<existing id>"` only when the answer clearly enriches that same accomplishment. Check with `python rot.py query --tags "<label>"`.
   - `null` to skip a duplicate or an answer with nothing resume-worthy.
   - Bullets not flagged may be left out, and they are then learned as written.

   **Resume 1 standard:** start with a verb and lead with the outcome. Stay within 97–170 characters. Write in implied first person, never "I", "my", "we" or "Tim". Use past tense for past roles.

   **Facts:** use only facts stated in the answer. You may merge in facts already present in the bullet being enriched. Never invent numbers, names or results.

   **Confidentiality:** never name the healthcare client (Liminal), the partner counterparty (Therapy Companion) or its contact (Kamal).
6. **Apply:** `python rot.py sync-apply`. This runs learn, ingest, export, the data profile, a full-typography PDF of each downloaded posting under `out/runs/`, then commit and push. Keep the printed JSON, which has `mark_synced`, `commit` and `synced_at`. If it prints `PUSH FAILED`, report that and continue. The commit is still local.
7. **Republish the page library:**
   - Artifact `list` with `scope: "files"` on the URL.
   - Artifact `read` on the URL.
   - Artifact `publish` with `url` set to the artifact URL, `file_path` set to `artifact\index.html`, and `files` set to `{"data/library.json": "data/library.json"}`.
8. **Mark synced:** ArtifactData `batch`, 50 writes per call at most, using `op: "update"`:
   - each `mark_synced.jd_runs` id gets `{"sync_status": "synced", "synced": true, "synced_at": <synced_at>, "sync_commit": <commit>}`;
   - each `bullet_inbox` and `feedback` id gets `{"synced": true}`;
   - then `set` the document `meta/sync` to `{"last_synced_at": <synced_at>, "commit": <commit>, "runs": n, "new_bullets": n, "feedback": n}`.
9. **Report** in one line: postings synced, bullets learned, commit hash.

## Why the page stays consistent
Once a document is marked synced, the page ignores it for scoring and the bullet inbox, because its content now lives in `library.json`. Nothing is counted twice. `rot.py learn` is idempotent: follow-ups and feedback carry dedupe keys, so a re-run after a crash does not double-apply.
