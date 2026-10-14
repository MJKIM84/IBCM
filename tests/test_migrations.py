"""이전 데이터 파일의 이력을 유지하면서 새 메타데이터를 추가하는지 검증합니다."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules import get_modules
from server.db import connect, initialize, sync_modules, transaction
from server.events import dispatch_outbox, emit


# 이전 배포본의 테이블입니다. 새 스키마를 이용해 시험 데이터를 만들지 않습니다.
LEGACY_SCHEMA = '''
CREATE TABLE projects (
    id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, customer_name TEXT NOT NULL,
    title TEXT NOT NULL, current_stage TEXT NOT NULL, executive TEXT NOT NULL,
    sales_owner TEXT NOT NULL, delivery_owner TEXT NOT NULL, pmo_owner TEXT NOT NULL,
    slack_channel_id TEXT, notion_page_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE module_registry (
    key TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, stage TEXT,
    "order" INTEGER NOT NULL, main_role TEXT, status TEXT NOT NULL, description TEXT NOT NULL
);
CREATE TABLE events (
    id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id),
    type TEXT NOT NULL, payload TEXT NOT NULL CHECK(json_valid(payload)), created_at TEXT NOT NULL
);
CREATE TABLE outbox (
    id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(id),
    adapter TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT, created_at TEXT NOT NULL, sent_at TEXT, UNIQUE(event_id,adapter)
);
'''


class LegacyDatabaseMigrationTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory(prefix="ibcm-migration-")
        self.addCleanup(folder.cleanup)
        self.db = connect(Path(folder.name) / "legacy.sqlite3")
        self.addCleanup(self.db.close)
        self.db.executescript(LEGACY_SCHEMA)
        self.db.execute('''
            INSERT INTO projects VALUES
            (9,'기존-프로젝트','기존 고객사','사용자가 저장한 제목','C',
             '기존 임원','기존 영업','기존 수행','기존 관리',NULL,NULL,'생성 시각','수정 시각')
        ''')
        self.db.execute('''
            INSERT INTO module_registry VALUES
            ('minutes','회의록','common',NULL,1,NULL,'planned','기존 설명')
        ''')
        fixtures = [
            (31, "stage.approval_requested", {"requested_by": "기존 영업"}, "slack", "sent", 1, None),
            (32, "stage.approved", {"decided_by": "기존 임원"}, "notion", "failed", 2, "기존 전송 오류"),
            (33, "module.executed", {"executed_by": "기존 수행"}, "slack", "pending", 0, None),
            (34, "project.created", {"source": "seed"}, "notion", "sent", 1, None),
        ]
        for event_id, kind, payload, adapter, status, attempts, error in fixtures:
            self.db.execute("INSERT INTO events VALUES(?,9,?,?,?)",
                            (event_id, kind, json.dumps(payload, ensure_ascii=False), "기존 발행 시각"))
            self.db.execute("INSERT INTO outbox VALUES(?,?,?, ?,?,?,?,?)",
                            (event_id + 100, event_id, adapter, status, attempts, error,
                             "기존 예약 시각", "기존 전송 시각" if status == "sent" else None))

    def snapshot(self, table):
        return [dict(row) for row in self.db.execute(f"SELECT * FROM {table} ORDER BY 1")]

    def test_upgrade_preserves_every_existing_value_and_backfills_metadata(self):
        originals = {table: self.snapshot(table)
                     for table in ("projects", "module_registry", "events", "outbox")}
        initialize(self.db)
        for table, old_rows in originals.items():
            new_rows = self.snapshot(table)
            self.assertEqual(len(new_rows), len(old_rows))
            for old_row, new_row in zip(old_rows, new_rows):
                self.assertEqual(old_row, {key: new_row[key] for key in old_row})
        self.assertEqual([row["actor"] for row in self.snapshot("events")],
                         ["기존 영업", "기존 임원", "기존 수행", "시스템"])
        outbox = self.snapshot("outbox")
        self.assertTrue(all(row["project_id"] == 9 for row in outbox))
        self.assertEqual([row["event_type"] for row in outbox],
                         [row["type"] for row in self.snapshot("events")])
        self.assertEqual([row["log"] for row in outbox], [
            "slack 어댑터가 stage.approval_requested 이벤트를 받았음",
            "기존 전송 오류", "전송 대기 중", "notion 어댑터가 project.created 이벤트를 받았음",
        ])
        self.assertIsNone(self.snapshot("module_registry")[0]["skill"])
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(self.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_reinitialization_keeps_existing_actor_and_delivery_log(self):
        initialize(self.db)
        self.db.execute("UPDATE events SET actor='보존할 담당자' WHERE id=31")
        self.db.execute("UPDATE outbox SET log='보존할 기록' WHERE id=131")
        before = {table: self.snapshot(table) for table in ("events", "outbox", "projects", "module_registry")}
        initialize(self.db)
        self.assertEqual(before, {table: self.snapshot(table) for table in before})

    def test_upgraded_database_accepts_modules_events_and_retries(self):
        initialize(self.db)
        minutes = next(module for module in get_modules() if module.key == "minutes")
        with transaction(self.db):
            sync_modules(self.db, [minutes])
            event_id = emit(self.db, 9, "stage.approved", {"decided_by": "새 임원"})
        dispatch_outbox(self.db)
        event = self.db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        self.assertEqual(event["actor"], "새 임원")
        rows = self.db.execute("SELECT * FROM outbox WHERE event_id=?", (event_id,)).fetchall()
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["status"] == "sent" and row["project_id"] == 9 for row in rows))
        self.assertEqual(self.db.execute("SELECT attempts FROM outbox WHERE id=132").fetchone()[0], 3)
        self.assertEqual(self.db.execute("SELECT title FROM projects WHERE id=9").fetchone()[0],
                         "사용자가 저장한 제목")
