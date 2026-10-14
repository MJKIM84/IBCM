"""각 검증에서 별도의 데이터 파일을 사용합니다."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from server.app import create_app
from server.db import connect


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory(prefix="ibcm-test-")
        self.addCleanup(self.folder.cleanup)
        self.database = Path(self.folder.name) / "ibcm.sqlite3"
        self.app = create_app(database_path=self.database, testing=True)
        self.client = self.app.test_client()
        self.db = connect(self.database)
        self.addCleanup(self.db.close)

    def rows(self, statement, parameters=()):
        return [dict(row) for row in self.db.execute(statement, parameters).fetchall()]

    def row(self, statement, parameters=()):
        result = self.db.execute(statement, parameters).fetchone()
        return dict(result) if result else None

    def count(self, table):
        return self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def counts(self):
        return {
            table: self.count(table)
            for table in ("projects", "stage_transitions", "module_registry",
                          "module_runs", "artifacts", "events", "outbox")
        }

    def request_transition(self, project_id=1, to_stage="C", actor="sales"):
        response = self.client.post(
            f"/api/projects/{project_id}/transitions",
            json={"actor": actor, "to_stage": to_stage},
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        return self.row(
            "SELECT * FROM stage_transitions WHERE project_id=? ORDER BY id DESC LIMIT 1",
            (project_id,),
        )

    def decide(self, transition_id, decision="approved", actor="executive",
               reason="", project_id=1):
        return self.client.post(
            f"/api/projects/{project_id}/transitions/{transition_id}/decision",
            json={"actor": actor, "decision": decision, "reason": reason},
        )

    def events(self, event_type, project_id=1):
        return self.rows(
            "SELECT * FROM events WHERE project_id=? AND type=? ORDER BY id",
            (project_id, event_type),
        )
