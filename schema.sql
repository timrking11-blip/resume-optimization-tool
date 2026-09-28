-- Resume Optimization Tool · schema v0.2 (SQLite) · v0.2 adds the source-template sections A–D
-- Conventions borrowed from SWAT Engine: one enums table; every row points at a source;
-- append-only supersession on bullets/answers (never UPDATE facts in place); AI/artifact
-- output is a draft until accepted.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS enums (
  domain TEXT NOT NULL, code TEXT NOT NULL, label TEXT NOT NULL, sort INTEGER DEFAULT 0,
  PRIMARY KEY (domain, code)
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);   -- length band, ingest stamp

-- ============ SOURCES ============
CREATE TABLE IF NOT EXISTS sources (
  id          TEXT PRIMARY KEY,          -- R1_base_2026 …
  file        TEXT NOT NULL,
  md5         TEXT,
  target_role TEXT,                      -- what the version was written for
  kind        TEXT,                      -- docx | pdf_resume | pdf_liminal | linkedin_md
  headline    TEXT,
  ingested_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS roles (
  key             TEXT PRIMARY KEY,      -- psp, liminal, tek_lead …
  sort            INTEGER,
  employer        TEXT NOT NULL,         -- rendered name
  employer_private TEXT,                 -- never rendered
  confidential    INTEGER DEFAULT 0,
  title           TEXT NOT NULL,
  title_variants  TEXT,                  -- JSON array
  location        TEXT,
  start           TEXT, end TEXT,        -- YYYY or YYYY-MM; NULL end = present
  engagement      TEXT,
  hidden_by_default INTEGER DEFAULT 0,
  date_note       TEXT,
  context_line    TEXT
);

-- Every bullet exactly as written in every source. Never edited.
CREATE TABLE IF NOT EXISTS raw_bullets (
  id        INTEGER PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(id),
  role_key  TEXT REFERENCES roles(key),
  section   TEXT,
  text      TEXT NOT NULL,
  chars     INTEGER,
  norm      TEXT                         -- lowercase alnum, for dedupe
);

-- ============ CURATED LAYER ============
CREATE TABLE IF NOT EXISTS achievements (
  id         TEXT PRIMARY KEY,           -- psp-closed-deals …
  role_key   TEXT NOT NULL REFERENCES roles(key),
  confidence TEXT NOT NULL DEFAULT 'asserted',   -- verified | asserted | conflict
  notes      TEXT,
  metrics    TEXT                        -- JSON [{label,value,unit}]
);

-- Which raw bullets evidence which achievement (many-to-many; a raw bullet may
-- evidence several). Coverage rule: every raw bullet has >= 1 row here.
CREATE TABLE IF NOT EXISTS achievement_evidence (
  achievement_id TEXT NOT NULL REFERENCES achievements(id),
  raw_bullet_id  INTEGER NOT NULL REFERENCES raw_bullets(id),
  PRIMARY KEY (achievement_id, raw_bullet_id)
);

-- Bare-bone bullets. kind='canonical' is the Resume-1-length default; kind='variant'
-- carries an angle label. Append-only: edits insert a successor and set superseded_by.
CREATE TABLE IF NOT EXISTS bullets (
  id             INTEGER PRIMARY KEY,
  achievement_id TEXT NOT NULL REFERENCES achievements(id),
  kind           TEXT NOT NULL,          -- canonical | variant | learned
  angle          TEXT,                   -- fundraising, media, player-coach … (variants/learned)
  text           TEXT NOT NULL,
  chars          INTEGER,
  status         TEXT DEFAULT 'accepted',-- accepted | draft | rejected
  origin         TEXT DEFAULT 'curated', -- curated | artifact | gate1 | gate2
  score_adj      REAL DEFAULT 0,         -- learned preference (+keep / -reject)
  created_at     TEXT DEFAULT (datetime('now')),
  superseded_by  INTEGER REFERENCES bullets(id),
  supersede_why  TEXT
);

CREATE TABLE IF NOT EXISTS tags (
  id       TEXT PRIMARY KEY,
  family   TEXT NOT NULL,
  label    TEXT NOT NULL,
  synonyms TEXT                          -- JSON array of JD phrases
);

CREATE TABLE IF NOT EXISTS achievement_tags (
  achievement_id TEXT NOT NULL REFERENCES achievements(id),
  tag_id         TEXT NOT NULL REFERENCES tags(id),
  weight         REAL NOT NULL DEFAULT 1.0,
  PRIMARY KEY (achievement_id, tag_id)
);

-- ============ PROFILE FACTS ============
-- competencies = the Section B areas-of-expertise line (JD-ranked; baseline order in baseline.json)
CREATE TABLE IF NOT EXISTS competencies (id INTEGER PRIMARY KEY, text TEXT NOT NULL UNIQUE, tags TEXT, sort INTEGER, origin TEXT);
CREATE TABLE IF NOT EXISTS technologies (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, category TEXT, tags TEXT, sort INTEGER, origin TEXT);
CREATE TABLE IF NOT EXISTS domain_fluency (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, tags TEXT);
CREATE TABLE IF NOT EXISTS certifications (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, issuer TEXT, date TEXT, credential_id TEXT,
  status TEXT, source TEXT, tags TEXT, sort INTEGER, hidden_by_default INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS education (
  id INTEGER PRIMARY KEY, school TEXT, degree TEXT, degree_variants TEXT, location TEXT, year TEXT,
  date_note TEXT, bullet_ids TEXT, date_display TEXT
);
CREATE TABLE IF NOT EXISTS summaries (
  id INTEGER PRIMARY KEY, source_id TEXT REFERENCES sources(id), tags TEXT, text TEXT NOT NULL,
  origin TEXT DEFAULT 'curated', status TEXT DEFAULT 'accepted'
);

-- ============ TEMPLATE SECTIONS (source template, 2026-09-27) ============
-- Section A: tagline phrases, JD-ranked; answers and Claude proposals from the Match Desk add more.
CREATE TABLE IF NOT EXISTS tagline_phrases (
  id INTEGER PRIMARY KEY, text TEXT NOT NULL UNIQUE, tags TEXT, sort INTEGER,
  status TEXT DEFAULT 'accepted', origin TEXT DEFAULT 'template'
);
-- Section C: consulting engagements; their bullets print the achievement's 'longform' variant.
CREATE TABLE IF NOT EXISTS engagements (
  key TEXT PRIMARY KEY, role_key TEXT REFERENCES roles(key), client TEXT NOT NULL, location TEXT,
  start TEXT, end TEXT, commitment TEXT, subtitle TEXT, sort INTEGER,
  confidential INTEGER DEFAULT 1,
  needs_details INTEGER DEFAULT 0,       -- 1 = hidden until the Match Desk collects dates and a description
  notes TEXT
);
CREATE TABLE IF NOT EXISTS engagement_achievements (
  engagement_key TEXT NOT NULL REFERENCES engagements(key),
  achievement_id TEXT NOT NULL REFERENCES achievements(id),
  sort INTEGER,
  PRIMARY KEY (engagement_key, achievement_id)
);
-- Section D: categorized core competencies (area order fixed; items JD-ranked within an area).
CREATE TABLE IF NOT EXISTS core_competencies (
  id INTEGER PRIMARY KEY, area TEXT NOT NULL, area_sort INTEGER, text TEXT NOT NULL, tags TEXT, sort INTEGER
);

-- ============ LEARNING LOOP ============
CREATE TABLE IF NOT EXISTS job_descriptions (
  id         TEXT PRIMARY KEY,           -- jd_<timestamp> or artifact doc id
  company    TEXT, title TEXT,
  text       TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now')),
  origin     TEXT DEFAULT 'cli'          -- cli | artifact
);
CREATE TABLE IF NOT EXISTS jd_requirements (
  id INTEGER PRIMARY KEY, jd_id TEXT NOT NULL REFERENCES job_descriptions(id),
  tag_id TEXT REFERENCES tags(id), phrase TEXT, weight REAL DEFAULT 1.0, covered INTEGER
);
CREATE TABLE IF NOT EXISTS followups (
  id INTEGER PRIMARY KEY, jd_id TEXT REFERENCES job_descriptions(id),
  gate INTEGER NOT NULL,                 -- 1 = baseline gate, 2 = per-JD gate
  question TEXT NOT NULL, answer TEXT, tag_id TEXT REFERENCES tags(id),
  resulting_bullet_id INTEGER REFERENCES bullets(id),
  asked_at TEXT DEFAULT (datetime('now')), answered_at TEXT,
  ext_key TEXT,                          -- dedupe key for synced answers
  section TEXT,                          -- experience | tagline | expertise | technology | engagement | competency
  engagement_key TEXT                    -- Section C engagement an answer belongs to
);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY, jd_id TEXT REFERENCES job_descriptions(id),
  bullet_id INTEGER REFERENCES bullets(id), action TEXT NOT NULL,   -- keep | reject | edit
  edited_text TEXT, created_at TEXT DEFAULT (datetime('now')),
  ext_id TEXT                            -- Match Desk feedback doc id (dedupe)
);
CREATE TABLE IF NOT EXISTS generated_resumes (
  id INTEGER PRIMARY KEY, jd_id TEXT REFERENCES job_descriptions(id), version TEXT,
  json TEXT NOT NULL, html_path TEXT, pdf_path TEXT, created_at TEXT DEFAULT (datetime('now'))
);

-- ============ VIEWS ============
CREATE VIEW IF NOT EXISTS current_bullets AS
  SELECT b.*, a.role_key, a.confidence FROM bullets b JOIN achievements a ON a.id = b.achievement_id
  WHERE b.superseded_by IS NULL AND b.status = 'accepted';

CREATE VIEW IF NOT EXISTS unassigned_raw AS
  SELECT r.* FROM raw_bullets r LEFT JOIN achievement_evidence e ON e.raw_bullet_id = r.id
  WHERE e.raw_bullet_id IS NULL;

CREATE VIEW IF NOT EXISTS bullet_tag_view AS
  SELECT b.id AS bullet_id, b.achievement_id, t.tag_id, t.weight
  FROM bullets b JOIN achievement_tags t ON t.achievement_id = b.achievement_id
  WHERE b.superseded_by IS NULL AND b.status = 'accepted';

CREATE TABLE IF NOT EXISTS expertise_areas (
  id INTEGER PRIMARY KEY, area TEXT NOT NULL, area_sort INTEGER, text TEXT NOT NULL, tags TEXT, sort INTEGER
);
