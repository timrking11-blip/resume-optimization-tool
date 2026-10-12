# Data Profile: resume.db
Generated 2026-10-12 by `rot.py profile`.

## The four tiers

| Tier | Tables | Rows |
|---|---|---|
| 1. Evidence: what actually happened | `evidence`, `sources`, `raw_bullets`, `followups` | 1267 |
| 2. Derived knowledge: what the system infers | `claims`, `claim_evidence`, `claim_relations`, `claim_confidence_history`, `achievements`, `achievement_tags`, `achievement_evidence`, `bullets`, `tags`, `competencies`, `technologies`, `certifications`, `education`, `tagline_phrases`, `core_competencies`, `engagements`, `engagement_achievements`, `roles`, `summaries`, `job_descriptions`, `jd_requirements` | 5316 |
| 3. Generation: what was written | `generation_events`, `prompt_versions`, `generated_resumes` | 558 |
| 4. Feedback: what happened afterwards | `feedback`, `outcomes` | 20 |

## Claims

| Kind | Active | Disputed | Retired | Mean confidence |
|---|---|---|---|---|
| achievement | 98 | 0 | 1 | 0.951 |
| contact | 3 | 0 | 0 | 0.9 |
| core_item | 40 | 0 | 0 | 0.95 |
| credential | 14 | 0 | 0 | 0.869 |
| education | 3 | 0 | 0 | 0.97 |
| engagement_fact | 11 | 0 | 0 | 1.0 |
| expertise | 34 | 0 | 0 | 0.884 |
| metric | 53 | 0 | 0 | 0.888 |
| role_fact | 44 | 0 | 2 | 0.867 |
| tagline | 12 | 0 | 0 | 0.958 |
| tool | 28 | 0 | 1 | 0.941 |

| Evidence source type | Rows |
|---|---|
| HISTORICAL_RESUME | 632 |
| USER_ENTERED | 86 |
| MASTER_RESUME | 56 |
| PUBLIC_PROFILE | 55 |

Disputed claims: **0**

## Overview

| Table | Rows | Grain |
|---|---|---|
| `sources` | 19 | one resume version / capture |
| `raw_bullets` | 372 | one bullet as written in one source |
| `achievements` | 99 | one real accomplishment |
| `bullets` | 192 | one bare-bone rendering of an achievement (all versions) |
| `tags` | 84 | one niche skill/keyword |
| `achievement_tags` | 388 | achievement × tag (one-to-many) |
| `achievement_evidence` | 395 | achievement × raw bullet |
| `competencies` | 34 | one competency phrase |
| `technologies` | 28 | one tool |
| `certifications` | 5 | one credential |
| `summaries` | 1 | one summary variant |
| `tagline_phrases` | 12 | one Section A tagline phrase |
| `engagements` | 2 | one Section C consulting engagement |
| `engagement_achievements` | 16 | engagement × achievement (long-form bullet) |
| `core_competencies` | 40 | one Section D item |
| `job_descriptions` | 21 | one JD processed |
| `followups` | 47 | one gate question |
| `feedback` | 20 | one keep/reject/edit |

Current (non-superseded, accepted) bullets: **154**.

## Bullet length vs. the Resume 1 standard

Resume 1 band: p10 **97**, median **143**, p90 **167** characters (ceiling 170).

| Layer | n | min | median | max | over ceiling |
|---|---|---|---|---|---|
| Raw bullets (all sources) | 372 | 79 | 161 | 482 | 143 |
| Canonical bare-bone | 98 | 104 | 146 | 169 | 0 |
| Angle variants | 41 | 121 | 150 | 340 | 14 |

## Achievements by role and confidence

| Role | Achievements | verified | asserted | conflict | raw bullets evidencing |
|---|---|---|---|---|---|
| liminal | 41 | 17 | 24 | 0 | 81 |
| psp | 19 | 10 | 9 | 0 | 96 |
| nyl | 2 | 0 | 2 | 0 | 2 |
| tek_lead | 24 | 8 | 16 | 0 | 76 |
| tek_recruiter | 6 | 5 | 1 | 0 | 69 |
| demanddrive | 4 | 2 | 2 | 0 | 36 |
| yri | 1 | 0 | 1 | 0 | 3 |
| massdot | 1 | 0 | 1 | 0 | 4 |
| education | 1 | 1 | 0 | 0 | 5 |

## Tag coverage by family

| Family | Tags | Tags used | Achievement links | Thin tags (0–1 achievements) |
|---|---|---|---|---|
| Change & Enablement | 5 | 5 | 24 | — |
| Customer & Account Growth | 4 | 4 | 14 | — |
| Data, AI & Technology | 6 | 6 | 26 | — |
| Finance & Unit Economics | 4 | 4 | 22 | — |
| Fundraising & Nonprofit | 4 | 3 | 10 | board-trustee-engagement, moves-management |
| Go-To-Market | 8 | 8 | 29 | — |
| Leadership & Coaching | 4 | 4 | 12 | player-coach |
| Legal, Risk & Governance | 3 | 3 | 21 | — |
| Marketing & Demand | 6 | 5 | 17 | abm |
| Media, Advertising & AdTech | 7 | 7 | 35 | — |
| Operations & Process | 4 | 4 | 16 | — |
| Partnerships & Channel | 3 | 3 | 12 | — |
| Research & Insight | 3 | 3 | 20 | — |
| Sales & Revenue | 16 | 16 | 93 | full-cycle-sales, proof-of-value |
| Strategy & Advisory | 7 | 7 | 37 | exit-path-modeling |

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
