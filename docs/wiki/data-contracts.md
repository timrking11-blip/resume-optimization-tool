# Data contracts

Schemas are named in the data (`schema` fields) and in `RotCore.SCHEMAS`. A change to a bank, model or template schema is a major version of the core.

## Tier 1 · evidence

Evidence rows: `{id, source, source_type, channel, quote, observed_at, locator}`.

- `source_type` (confidence strength): `USER_ENTERED` 1.0 · `INTERVIEW_RESPONSE` 0.95 · `MASTER_RESUME` 0.9 · `HISTORICAL_RESUME` 0.8 · `PUBLIC_PROFILE` 0.7 · `EXTERNAL_RESEARCH` 0.6 · `MODEL_INFERENCE` 0.5.
- `channel` is the finer origin: `paste`, `upload:resume`, `upload:linkedin`, `answer`.
- Ids: Desk `ev:<source>:l<n>`; Hub uploads `ev:u<k>:l<n>` (one row per document line, the whole document, first), typed text `ev:you:<what>` (`ev:you:r2:role`, `ev:you:r2-3`), answers `ev:<runId>:q<n>`.
- Sources: `{id, kind: resume|linkedin|paste|answer, label, authored_at, observed_at, source_type}`; Hub ids `src:u<k>`, `src:you`, `src:answers`.

## Tier 2 · subjects, facts, achievements, claims

Subjects: `{id, kind: role|engagement|education|credential|tool|expertise, key?, sort?, hidden?, tags?, facts}`. A fact is `{value, evidence:[ids], contradicting:[{value, evidence:[ids]}], resolution?:{value, why, at}}`. Ids: `role:<key>`, `edu:<slug>`, `cred:<slug>`, `tool:<slug>`, `expertise:<slug>`.

Achievements: `{id, role, engagement?, canonical, evidence:[ids], contradicting?, resolution?, tags:{tagId: weight}, metrics?, variants?:[{kind, angle, text}], origin, retired?}`. Hub ids: typed `<roleKey>-<n>`, folded answers `<runId>-g<n>`; draft-only ids `gate2-<runId>-<n>` never reach the record.

Claims (computed by `projectLibrary`, never stored): `{id, kind, subject, predicate, value, text, confidence, confidence_basis, status: active|disputed, evidence:{n, source_types, latest}, numbers}`. Ids `role:<key>:<pred>`, `ach:<id>`, `edu:<id>:<pred>`, `cred:<id>:<pred>`, `tool:<id>:name`, `expertise:<id>:text`.

Conflict rule (`valuesConflict`): dates are compatible at shared precision (2024 and 2024-11 agree; 2020 and 2021 do not); numbers compare numerically; text compares normalized. Unresolved contradiction → `disputed`, confidence −0.3, and a disputed achievement or metric is held back from printing.

## The bank · `rot-library/3`

What `createEngine` reads. Roles, engagements, achievements (with `texts`: canonical plus variants, `claim_ids`, `metrics`), education, certifications, technologies, competencies, core competencies, tagline phrases, claims, `families` and `tags` (the taxonomy), `length_band` and `longform_band`, `template {id, docx}`, `baseline {caps, priority, engagement_caps, scoring, competency_count, competency_order, angle_map, settings}`. `baseline.settings` carries the edition's non-personal parameters: `fallback_role`, `default_engagement_role`, `education_claim_default`, `template_id`, `edition`, `questions {consulting, consulting_regex, engagement_tag}`, `prompts {persona, bullet_example, entry_example}`.

## Tier 3 · the model · `rot-resume/2`

`resumeModel(d)` → `{schema, template, generator:{core, edition, prompt_versions}, identity, summary, tagline, expertise, technologies, education, roles:[{key, title, employer, dates, context, bullets:[{aid, tid, text, fresh, claim_ids}]}], certifications, engagements, core_competencies, trace}`. `trace` maps every printed line to claim ids.

Layout `rot-layout/1` (`core/layouts/source-2026-09.json`, `neutral-1.json`): `sections` in print order (`header`, `lines` with `blocks`, `education`, `experience`, `certifications`, `engagements`, `core_competencies`), `labels`, `joins`, `theme`, `style`. Template JSON `rot-docx-template/1` carries the Word parts, run styles, paragraph properties, PDF metrics and the `layout`.

## Taxonomy · `rot-taxonomy/1`

`{version, families:{id:{label}}, tags:{id:{label, family, synonyms:[lowercase]}}}`. Every synonym belongs to exactly one tag. The Hub ships `core/taxonomy/gtm_v1.json` (94 tags, 14 families); Tim's `curation/taxonomy.json` is untouched.

## Sessions and outcomes

Desk sessions `rmd.session.v1` (browser and `data/users/<uid>/workspace/sessions/<runId>`); Hub sessions are the same field names plus `edition`, `core`, `score`, `final_model`, stored under `sessions[runId]` in the browser store. Outcomes `{run_id, applied_at, response: pending|no_response|screen|interview|offer|rejected, note, recorded_at}`.

## The Hub backup · `cch-backup/1`

`{schema, core, exported_at, edition, identity, sources, evidence, subjects, achievements, taxonomy:{id, user_tags}, settings, sessions, feedback, outcomes, review_log, meta}` — the four tiers in the shapes above, so `projectLibrary` reads it directly and a later `rot.py import-backup` is a projection, not a translation.
