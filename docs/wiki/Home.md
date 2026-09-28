# Wiki · Resume Optimization Tool and Career Companion Hub

One repository, one shared engine, two editions:

| | Resume Match Desk (private) | Career Companion Hub (public) |
|---|---|---|
| Who | Tim | anyone in GTM, sales, marketing or revenue roles |
| Page | `artifact/index.html` | `hub/index.html` (+ `hub.js`, `store.js`, `intake.js`, `guide.html`) |
| Record lives in | git JSON (`curation/`, `data/library.json`) synced hourly through the page's database | the viewer's browser (`cch-backup/1` backups) |
| Claude | the viewer's `sample` capability | the viewer's `sample` capability |
| Engine | `core/rot_core.js` | `core/rot_core.js` |

Pages:

- [Architecture](architecture.md) — the four tiers, the shared core, the two editions, where the human step sits. The maintained diagram lives in Notion: [Career Companion Hub Architecture](https://app.notion.com/p/Career-Companion-Hub-Architecture-4d2447d2e7c7431e80b92d7f2a1ff97c).
- [Data contracts](data-contracts.md) — every schema and id convention the editions share.
- [Editions](editions.md) — what each edition does, publishes and never does; the Hub fact brief.
- [Glossary](glossary.md) — the words this project uses precisely, including the Empty Middle.

Working rules that apply everywhere are in the repo root: `README.md` (commands, the learning loop, privacy), `SYNC_RUNBOOK.md` (the hourly sync), and the tests (`python tests/run.py`: unit tests, page goldens, the rot.py twin check). Run the tests before any change to `core/` or the Desk page; publish the Desk only with nothing pending and outside :00–:15.
