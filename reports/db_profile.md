# Data Profile: resume.db
Generated 2026-09-26 by `rot.py profile`.

## Overview

| Table | Rows | Grain |
|---|---|---|
| `sources` | 18 | one resume version / capture |
| `raw_bullets` | 342 | one bullet as written in one source |
| `achievements` | 60 | one real accomplishment |
| `bullets` | 114 | one bare-bone rendering of an achievement (all versions) |
| `tags` | 84 | one niche skill/keyword |
| `achievement_tags` | 253 | achievement × tag (one-to-many) |
| `achievement_evidence` | 364 | achievement × raw bullet |
| `competencies` | 33 | one competency phrase |
| `technologies` | 12 | one tool |
| `certifications` | 5 | one credential |
| `summaries` | 15 | one summary variant |
| `job_descriptions` | 7 | one JD processed |
| `followups` | 19 | one gate question |
| `feedback` | 5 | one keep/reject/edit |

Current (non-superseded, accepted) bullets: **90**.

## Bullet length vs. the Resume 1 standard

Resume 1 band: p10 **97**, median **143**, p90 **167** characters (ceiling 170).

| Layer | n | min | median | max | over ceiling |
|---|---|---|---|---|---|
| Raw bullets (all sources) | 342 | 79 | 159 | 482 | 132 |
| Canonical bare-bone | 59 | 104 | 140 | 163 | 0 |
| Angle variants | 26 | 121 | 144 | 158 | 0 |

## Achievements by role and confidence

| Role | Achievements | verified | asserted | conflict | raw bullets evidencing |
|---|---|---|---|---|---|
| liminal | 24 | 16 | 8 | 0 | 66 |
| psp | 13 | 10 | 3 | 0 | 91 |
| nyl | 2 | 0 | 2 | 0 | 2 |
| tek_lead | 10 | 8 | 2 | 0 | 72 |
| tek_recruiter | 5 | 5 | 0 | 0 | 65 |
| demanddrive | 3 | 2 | 1 | 0 | 34 |
| yri | 1 | 0 | 1 | 0 | 3 |
| massdot | 1 | 0 | 1 | 0 | 4 |
| education | 1 | 1 | 0 | 0 | 5 |

## Tag coverage by family

| Family | Tags | Tags used | Achievement links | Thin tags (0–1 achievements) |
|---|---|---|---|---|
| Change & Enablement | 5 | 5 | 14 | — |
| Customer & Account Growth | 4 | 4 | 8 | customer-success |
| Data, AI & Technology | 6 | 6 | 19 | — |
| Finance & Unit Economics | 4 | 4 | 13 | — |
| Fundraising & Nonprofit | 4 | 3 | 7 | board-trustee-engagement, moves-management |
| Go-To-Market | 8 | 8 | 21 | territory-design |
| Leadership & Coaching | 4 | 4 | 8 | player-coach |
| Legal, Risk & Governance | 3 | 3 | 10 | entity-ip-structure |
| Marketing & Demand | 6 | 5 | 7 | demand-generation, campaign-development, marketing-sales-alignment, abm, growth-efficiency |
| Media, Advertising & AdTech | 7 | 7 | 21 | cross-platform |
| Operations & Process | 4 | 4 | 14 | — |
| Partnerships & Channel | 3 | 3 | 9 | — |
| Research & Insight | 3 | 3 | 7 | — |
| Sales & Revenue | 16 | 16 | 71 | full-cycle-sales, proof-of-value |
| Strategy & Advisory | 7 | 7 | 24 | exit-path-modeling |

## Most-reused raw bullets (how often each achievement was rewritten)

| Achievement | Sources | Distinct wordings |
|---|---|---|
| tekl-coaching | 17 | 14 |
| psp-funding-source-qualification | 17 | 12 |
| psp-closed-deals | 17 | 10 |
| tekr-vertex | 17 | 10 |
| psp-125-leads | 17 | 9 |
| tekr-wayfair-disney | 17 | 9 |
| tekr-nike | 17 | 8 |
| dd-territory-proposal | 17 | 7 |
| tekl-universal-poc | 17 | 7 |
| tekr-750k | 17 | 5 |
| dd-200-quota | 17 | 4 |
| tekl-solution-scoping | 16 | 10 |

## Data quality flags

- **Dates · liminal**: Renamed 2026-09-25 from 'Chief Strategy Consultant | Confidential Healthcare AI Start-Up'. Dates kept at July 2026 – Present (the healthcare engagement start).
- **Dates · psp**: Gate 1: ended August 2026 (matches LinkedIn).
- **Dates · nyl**: Fundraising resume only; not in LinkedIn experience.
- **Dates · tek_lead**: LinkedIn: Nov 2024 – Oct 2025 under a different title. Year-only display (2024 – 2025) matches both.
- **Dates · tek_recruiter**: LinkedIn: Mar 2021 – Nov 2024.
- **Dates · demanddrive**: Resumes say 2018–2021; LinkedIn says Aug 2018 – Sep 2020. Using 2018 – 2020.
- **Dates · yri**: LinkedIn only.
- **Dates · massdot**: LinkedIn only.
- Unassigned raw bullets: **0**.
