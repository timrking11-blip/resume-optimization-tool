# Data Profile: resume.db
Generated 2026-10-01 by `rot.py profile`.

## The four tiers

| Tier | Tables | Rows |
|---|---|---|
| 1. Evidence: what actually happened | `evidence`, `sources`, `raw_bullets`, `followups` | 1234 |
| 2. Derived knowledge: what the system infers | `claims`, `claim_evidence`, `claim_relations`, `claim_confidence_history`, `achievements`, `achievement_tags`, `achievement_evidence`, `bullets`, `tags`, `competencies`, `technologies`, `certifications`, `education`, `tagline_phrases`, `core_competencies`, `engagements`, `engagement_achievements`, `roles`, `summaries`, `job_descriptions`, `jd_requirements` | 4787 |
| 3. Generation: what was written | `generation_events`, `prompt_versions`, `generated_resumes` | 313 |
| 4. Feedback: what happened afterwards | `feedback`, `outcomes` | 19 |

## Claims

| Kind | Active | Disputed | Retired | Mean confidence |
|---|---|---|---|---|
| achievement | 79 | 0 | 1 | 0.939 |
| contact | 3 | 0 | 0 | 0.9 |
| core_item | 40 | 0 | 0 | 0.95 |
| credential | 14 | 0 | 0 | 0.869 |
| education | 3 | 0 | 0 | 0.97 |
| engagement_fact | 11 | 0 | 0 | 0.955 |
| expertise | 34 | 0 | 0 | 0.884 |
| metric | 53 | 0 | 0 | 0.888 |
| role_fact | 44 | 0 | 2 | 0.867 |
| tagline | 9 | 0 | 0 | 0.944 |
| tool | 28 | 0 | 1 | 0.941 |

| Evidence source type | Rows |
|---|---|
| HISTORICAL_RESUME | 632 |
| USER_ENTERED | 67 |
| MASTER_RESUME | 56 |
| PUBLIC_PROFILE | 55 |

Disputed claims: **0**

## Overview

| Table | Rows | Grain |
|---|---|---|
| `sources` | 19 | one resume version / capture |
| `raw_bullets` | 372 | one bullet as written in one source |
| `achievements` | 80 | one real accomplishment |
| `bullets` | 163 | one bare-bone rendering of an achievement (all versions) |
| `tags` | 84 | one niche skill/keyword |
| `achievement_tags` | 318 | achievement × tag (one-to-many) |
| `achievement_evidence` | 395 | achievement × raw bullet |
| `competencies` | 34 | one competency phrase |
| `technologies` | 28 | one tool |
| `certifications` | 5 | one credential |
| `summaries` | 1 | one summary variant |
| `tagline_phrases` | 9 | one Section A tagline phrase |
| `engagements` | 2 | one Section C consulting engagement |
| `engagement_achievements` | 13 | engagement × achievement (long-form bullet) |
| `core_competencies` | 40 | one Section D item |
| `job_descriptions` | 14 | one JD processed |
| `followups` | 33 | one gate question |
| `feedback` | 19 | one keep/reject/edit |

Current (non-superseded, accepted) bullets: **131**.

## Bullet length vs. the Resume 1 standard

Resume 1 band: p10 **97**, median **143**, p90 **167** characters (ceiling 170).

| Layer | n | min | median | max | over ceiling |
|---|---|---|---|---|---|
| Raw bullets (all sources) | 372 | 79 | 161 | 482 | 143 |
| Canonical bare-bone | 79 | 104 | 143 | 163 | 0 |
| Angle variants | 38 | 121 | 150 | 340 | 11 |

## Achievements by role and confidence

| Role | Achievements | verified | asserted | conflict | raw bullets evidencing |
|---|---|---|---|---|---|
| liminal | 35 | 17 | 18 | 0 | 81 |
| psp | 16 | 10 | 6 | 0 | 96 |
| nyl | 2 | 0 | 2 | 0 | 2 |
| tek_lead | 15 | 8 | 7 | 0 | 76 |
| tek_recruiter | 6 | 5 | 1 | 0 | 69 |
| demanddrive | 3 | 2 | 1 | 0 | 36 |
| yri | 1 | 0 | 1 | 0 | 3 |
| massdot | 1 | 0 | 1 | 0 | 4 |
| education | 1 | 1 | 0 | 0 | 5 |

## Tag coverage by family

| Family | Tags | Tags used | Achievement links | Thin tags (0–1 achievements) |
|---|---|---|---|---|
| Change & Enablement | 5 | 5 | 18 | — |
| Customer & Account Growth | 4 | 4 | 8 | customer-success |
| Data, AI & Technology | 6 | 6 | 24 | — |
| Finance & Unit Economics | 4 | 4 | 17 | — |
| Fundraising & Nonprofit | 4 | 3 | 7 | board-trustee-engagement, moves-management |
| Go-To-Market | 8 | 8 | 25 | territory-design |
| Leadership & Coaching | 4 | 4 | 8 | player-coach |
| Legal, Risk & Governance | 3 | 3 | 16 | — |
| Marketing & Demand | 6 | 5 | 13 | demand-generation, campaign-development, abm |
| Media, Advertising & AdTech | 7 | 7 | 29 | — |
| Operations & Process | 4 | 4 | 16 | — |
| Partnerships & Channel | 3 | 3 | 10 | — |
| Research & Insight | 3 | 3 | 16 | — |
| Sales & Revenue | 16 | 16 | 79 | full-cycle-sales, proof-of-value |
| Strategy & Advisory | 7 | 7 | 32 | exit-path-modeling |

## Most-reused raw bullets (how often each achievement was rewritten)

| Achievement | Sources | Distinct wordings |
|---|---|---|
| tekl-coaching | 18 | 14 |
| psp-funding-source-qualification | 18 | 12 |
| psp-closed-deals | 18 | 10 |
| tekr-vertex | 18 | 10 |
| psp-125-leads | 18 | 9 |
| tekr-wayfair-disney | 18 | 9 |
| tekr-nike | 18 | 8 |
| dd-territory-proposal | 18 | 7 |
| tekl-universal-poc | 18 | 7 |
| tekr-750k | 18 | 5 |
| dd-200-quota | 18 | 4 |
| tekl-solution-scoping | 17 | 10 |

## Data quality flags

- **Dates · liminal**: source template 2026-09-27: title and employer from the source template (was 'Founder, Business Consultant, and GTM Engineer | Strategic Market Insights'). Dates July 2026 – Present.
- **Dates · psp**: Gate 1: ended August 2026 (matches LinkedIn and the source template).
- **Dates · nyl**: Fundraising resume only; not in LinkedIn experience.
- **Dates · tek_lead**: source template 2026-09-27: 2024 – November 2025 (LinkedIn: Nov 2024 – Oct 2025).
- **Dates · tek_recruiter**: LinkedIn: Mar 2021 – Nov 2024.
- **Dates · demanddrive**: source template 2026-09-27: 2018 – 2021 (resumes and the template); LinkedIn says Aug 2018 – Sep 2020.
- **Dates · yri**: LinkedIn only.
- **Dates · massdot**: LinkedIn only.
- Unassigned raw bullets: **0**.
