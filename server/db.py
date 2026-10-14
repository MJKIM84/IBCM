"""SQLite 연결과 파일 기반 저장소."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), isolation_level=None, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    return db


@contextmanager
def transaction(db):
    db.execute("BEGIN IMMEDIATE")
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise


def initialize(db):
    db.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
    # 이전 데이터 파일의 업무 기록을 유지하면서 새 메타데이터만 채웁니다.
    with transaction(db):
        additions = {
            "module_registry": {"skill": "TEXT"},
            "events": {"actor": "TEXT NOT NULL DEFAULT '시스템'"},
            "outbox": {
                "project_id": "INTEGER REFERENCES projects(id)",
                "event_type": "TEXT",
                "log": "TEXT",
            },
        }
        actor_added = False
        for table, columns in additions.items():
            existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
            for column, declaration in columns.items():
                if column not in existing:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
                    actor_added = actor_added or (table == "events" and column == "actor")
        missing_actor = "1" if actor_added else "actor IS NULL OR trim(actor)=''"
        for row in db.execute(f"SELECT id,payload FROM events WHERE {missing_actor}").fetchall():
            payload = json.loads(row["payload"])
            actor = next((payload[key] for key in ("decided_by", "requested_by", "executed_by")
                          if isinstance(payload, dict) and isinstance(payload.get(key), str)
                          and payload[key].strip()), "시스템")
            db.execute("UPDATE events SET actor=? WHERE id=?", (actor, row["id"]))
        db.execute("""
            UPDATE outbox SET project_id=(SELECT project_id FROM events WHERE id=outbox.event_id)
            WHERE project_id IS NULL
        """)
        db.execute("""
            UPDATE outbox SET event_type=(SELECT type FROM events WHERE id=outbox.event_id)
            WHERE event_type IS NULL OR event_type=''
        """)
        db.execute("""
            UPDATE outbox SET log=CASE status
                WHEN 'sent' THEN adapter || ' 어댑터가 ' || event_type || ' 이벤트를 받았음'
                WHEN 'failed' THEN COALESCE(last_error, '어댑터 처리에 실패했습니다')
                ELSE '전송 대기 중' END
            WHERE log IS NULL OR log=''
        """)


def sync_modules(db, definitions):
    for module in definitions:
        db.execute('''
            INSERT INTO module_registry
            (key, name, category, stage, "order", main_role, status, description, skill)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET name=excluded.name,
                category=excluded.category, stage=excluded.stage,
                "order"=excluded."order", main_role=excluded.main_role,
                status=excluded.status, description=excluded.description, skill=excluded.skill
        ''', (module.key, module.name, module.category, module.stage, module.order,
              module.mainRole, module.status, module.description, module.skill))
