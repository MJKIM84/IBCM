CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    customer_name TEXT NOT NULL,
    title TEXT NOT NULL,
    current_stage TEXT NOT NULL CHECK(current_stage IN ('A','B','C','D','E')),
    executive TEXT NOT NULL,
    sales_owner TEXT NOT NULL,
    delivery_owner TEXT NOT NULL,
    pmo_owner TEXT NOT NULL,
    slack_channel_id TEXT,
    notion_page_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stage_transitions (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    from_stage TEXT NOT NULL CHECK(from_stage IN ('A','B','C','D')),
    to_stage TEXT NOT NULL CHECK(to_stage IN ('B','C','D','E')),
    status TEXT NOT NULL CHECK(status IN ('requested','approved','rejected')),
    requested_by TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    decided_by TEXT,
    decided_at TEXT,
    reason TEXT,
    CHECK((from_stage='A' AND to_stage='B') OR
          (from_stage='B' AND to_stage='C') OR
          (from_stage='C' AND to_stage='D') OR
          (from_stage='D' AND to_stage='E')),
    CHECK(status != 'rejected' OR (reason IS NOT NULL AND length(trim(reason)) > 0)),
    CHECK((status='requested' AND decided_by IS NULL AND decided_at IS NULL) OR
          (status!='requested' AND decided_by IS NOT NULL AND decided_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS one_pending_transition
    ON stage_transitions(project_id) WHERE status='requested';

CREATE TABLE IF NOT EXISTS module_registry (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('stage_task','common')),
    stage TEXT,
    "order" INTEGER NOT NULL CHECK("order" > 0),
    main_role TEXT,
    status TEXT NOT NULL CHECK(status IN ('planned','ready','active')),
    description TEXT NOT NULL,
    skill TEXT,
    CHECK((category='common' AND stage IS NULL AND main_role IS NULL) OR
          (category='stage_task' AND stage IS NOT NULL AND main_role IS NOT NULL
            AND stage IN ('A','B','C','D','E') AND main_role IN ('sales','delivery','pmo')))
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    stage TEXT NOT NULL CHECK(stage IN ('A','B','C','D','E')),
    module_key TEXT NOT NULL REFERENCES module_registry(key),
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS module_runs (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    module_key TEXT NOT NULL REFERENCES module_registry(key),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('running','completed','failed','skipped')),
    result_summary TEXT,
    artifact_id INTEGER REFERENCES artifacts(id),
    executed_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    type TEXT NOT NULL,
    payload TEXT NOT NULL CHECK(json_valid(payload)),
    actor TEXT NOT NULL DEFAULT '시스템',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(id),
    project_id INTEGER NOT NULL REFERENCES projects(id),
    adapter TEXT NOT NULL CHECK(adapter IN ('slack','notion','email')),
    event_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending','sent','failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    log TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT,
    UNIQUE(event_id, adapter)
);
CREATE INDEX IF NOT EXISTS project_events ON events(project_id, id);
