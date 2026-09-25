# LinkedIn cross-reference · Phase-1 baseline (v1)

Compared `out/baseline_v1` and all 17 resume sources against linkedin.com/in/timothy-king1124, captured 2026-09-25 and saved to `sources/linkedin_2026-09-25.md`.

## Added to the database from LinkedIn (missing from resumes)

| Item | Where it went | Rendered in baseline? |
|---|---|---|
| ~$115K active PSP pipeline | `psp-pipeline-discovery` canonical bullet | No (ranked 8th for PSP; cap is 5) |
| Liminal: ~$2.15M non-dilutive federal funding route | `lim-non-dilutive-capital` canonical bullet | No (ranked 11th) |
| Liminal: business roadmap spanning architecture, SOC 2, IP, governance | `lim-feasibility-roadmap` variant `linkedin` | Picked when the JD stresses healthcare/regulatory |
| Liminal: scenario planning and second-/third-order analysis | new achievement `lim-scenario-planning` | No |
| NYS DFS Insurance Broker license: Accident, Health, Life, Variable Life & Variable Annuity (Dec 2025) | certifications | Yes |
| Claude 101 credential ID `xid9zxhxo3mw` (Aug 2026) | certifications | Yes (ID omitted from print) |
| YRI Custom Designs internship (Aug 2016–May 2017) | role `yri`, hidden by default | Only if a JD scores it ≥ 4 |
| MassDOT EZ Pass internship (May–Sep 2016) | role `massdot`, hidden by default | Only if a JD scores it ≥ 4 |

## Merged certifications (Resume 1 + Resume 2 + role-specific versions + LinkedIn)
1. Claude 101, Anthropic, Aug 2026
2. Claude Code 101, Anthropic, 2026 (resumes only; not on LinkedIn)
3. Claude for CoWork, Anthropic, in progress (resumes only)
4. Insurance Broker License, NYS DFS, Dec 2025 (LinkedIn only)
5. Data Analytics & Insights: Data Insights, TEKsystems, Dec 2023

## Merged technologies (Resume 1 + Resume 2 base, extended)
Salesforce · LinkedIn Sales Navigator · ZoomInfo · Tableau (beginner) · Microsoft Excel & Office · Microsoft Copilot · Claude (Opus 5, Sonnet 5, Fable 5) · Claude Code · OpenAI (GPT-5.6, Sol, Terra, Luna) · Trello · Canva · Miro.
Client-side platforms (Azure, Adobe Enterprise Suite, graph databases, computer vision, CDP/clean rooms, HIPAA/SOC 2) are stored as **domain fluency**, not tools you operate.

## Conflicts between LinkedIn and the resumes

| Topic | Resumes | LinkedIn | Baseline v1 uses | Status |
|---|---|---|---|---|
| PSP end date | March 2026 – Present | Mar 2026 – Aug 2026 | Present | **Gate-1 Q1** |
| PSP signed deals | 5 (R1, R2, R3–R8, R15) · 3 (R9–R14, R16) | 3 | 5 | **Gate-1 Q1** |
| PSP revenue | $14,035 over 4 months (R11, R12 only) | — | not shown | **Gate-1 Q3** |
| TEK leadership scope | "coached recruiters" (R1) → "direct-report team of quota-carrying sellers" (R5) | "coached… recruiters" | coached sellers | **Gate-1 Q2** |
| Liminal verbs | "Restructured / Blocked" (S17) · "Recommended" (R8) | "recommended" | Restructured / Authored | **Gate-1 Q4** |
| Liminal title | CSO (R1) · Chief Strategy Consultant (R8–R16) | "Principle Business Strategy Consultant" | Founder, Business Consultant, and GTM Engineer, Strategic Market Insights (changed 2026-09-25) | Decided |
| Liminal start | Aug 2026 (R1, R6) · Jul 2026 (R8–R16) | Jul 2026 | July 2026 | Default |
| TEK Specialized Lead | "Data Analytics & Data Insights", 2024 – Nov 2025 | "Cloud Applications & Data Analytics", Nov 2024 – Oct 2025 | resume title, 2024 – 2025 | Default |
| TEK Recruiter | "Enterprise Recruiter – Global Services", 2021 – 2024 | "National Recruiter – Data Analytics & Insights", Mar 2021 – Nov 2024 | resume title, 2021 – 2024 | Default |
| demandDrive | 2018 – 2021 | Aug 2018 – Sep 2020 | 2018 – 2020 | Default |
| New York Life | Dec 2025 – Mar 2026 (fundraising resume) | not in Experience | hidden | Default |
| Education | B.S. double major, 2018 (Spring 2018 / Sept 2014 – Dec 2018) | BS Finance + BBA Marketing, 2013 – 2018 | B.S., Finance & Marketing, 2018 | Default |
| Southern Company Gas | "Southern Gas Company" (R1, R8+) | "Southern Gas Company" | Southern Company Gas (legal name) | Corrected |

## Recommended LinkedIn edits
1. **Add an About section.** The profile has none. Paste the Professional Summary from the baseline.
2. Fix the typos in the PSP entry: "Co-up" → "co-op"; "with new prior purchase history" → "with no prior purchase history"; "Sonnett" → "Sonnet".
3. Rename the LinkedIn project "Healthcare Tech & Research Innovation Start-Up | Principle Business Strategy Consultant" to match the resume: **Founder, Business Consultant, and GTM Engineer | Strategic Market Insights**, with the healthcare start-up as its key engagement. This also fixes the "Principle" typo.
4. Align the TEKsystems titles with the resumes, or the resumes with LinkedIn. Recruiters compare the two.
5. The Skills section renders empty. Add the top 10 competencies from the baseline.
6. Add Claude Code 101 to Licenses & Certifications. It appears on 9 resumes but not on LinkedIn.
7. Rephrase "Exceeded company-wide sales contest" as "Won the company-wide sales contest".
