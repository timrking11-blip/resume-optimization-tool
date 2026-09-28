# Glossary

**Bank** — the `rot-library/3` object an engine reads: roles, achievements with texts, claims, taxonomy, bands and baseline settings. Exported by `rot.py` for the Desk; projected from a backup by `projectLibrary` for the Hub.

**Claim** — a tier-2 fact with a confidence and a status, derived from evidence rows. Never stored; recomputed from evidence.

**Conflict / disputed** — two sources give incompatible values for one fact (`valuesConflict`). The fact is disputed until a person settles it with a resolution; a disputed achievement or metric is held back from printing.

**Corroboration** — a second source stating the same fact or accomplishment (same numbers, overlapping wording). It adds evidence and raises confidence; it never creates a duplicate entry.

**Draft (`d`)** — the working state for one posting: requirements, chosen entries, pins, exclusions, edits, extra phrases, questions and their answer entries. The engine takes it as its first argument.

**Empty Middle** — the term Tim uses (see his piece, https://claude.ai/artifact/HB753AdM1N9yzepndaijjN) for the gap between what a model can generate and what a person can actually vouch for. In this project it is a place in the flow, not a metaphor: the questions, the number check on every answer, the approval click, and the chooser when documents disagree. The tool drafts; the person owns the facts and the signature. Nothing crosses from tier 3 back into tier 1 without passing through it.

**Entry** — the Hub's word for an achievement bullet: one line the person did, in a role, with the numbers it states.

**Evidence** — a verbatim line with a source and a date (tier 1). Typed text and answers are first-hand evidence; model output never is.

**Fold** — when a downloaded resume's approved answer entries join the record as achievements with the answer as evidence, and the draft's temporary ids are swapped for the record's (`remapSynced`). The Desk does this through the hourly sync; the Hub does it in the browser on download.

**Gate2 ids** — `gate2-<runId>-<n>`: an answer entry's id while it exists only in a draft.

**Layout** — the print order, headings, labels and joins of a template (`rot-layout/1`), read by the JS and Python document builders alike.

**Neutral template** — the Hub's single ATS-safe template (`neutral-1`): single column, Summary only when written, Skills and Tools lines, Experience, Consulting & Advisory when present, Education, Certifications; Calibri/Carlito, real Word bullets.

**Persona (fixture)** — Riley Mahoney, the fictional GTM professional in `tests/fixtures/persona/`: three resumes with different layouts and deliberate disagreements, a LinkedIn export, five postings, a ground-truth `persona.json`. Used by every engine, projection and intake test.

**Readiness** — the six checks under *Your evidence*: identity, complete role headers, three entries per recent role, half the entries carrying a number, three skills and three tools, no unsettled conflicts.

**Record** — the Hub's word for the person's whole four-tier store; a backup is the record as one file.

**Session** — one posting's saved work (draft, questions, answers, final model, outcome), keyed by `runId`.

**Sync** — the Desk's hourly task that folds the page's runs into git and re-exports the bank. Not a Hub concept.

**Taxonomy** — the skill vocabulary a posting is read with; tags with synonyms grouped in families. GTM v1 for the Hub, Tim's own for the Desk.
