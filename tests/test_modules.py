"""모듈 실행과 산출물 저장이 공통 규격을 지키는지 검증합니다."""

from dataclasses import replace
import json
from unittest.mock import AsyncMock

from modules.base import ModuleResult
from server.db import now, sync_modules, transaction
from tests.support import AppTestCase


class ModuleExecutionTests(AppTestCase):
    def install_definition(self, definition):
        self.app.config["MODULES"][definition.key] = definition
        with transaction(self.db):
            sync_modules(self.db, [definition])

    def run_module(self, key="minutes", project_id=1, actor="sales"):
        return self.client.post(f"/api/projects/{project_id}/modules/{key}/run", json={"actor": actor})

    def test_planned_module_records_skipped_without_calling_run(self):
        definition = self.app.config["MODULES"]["minutes"]
        implementation = AsyncMock(side_effect=AssertionError("준비 중 모듈을 실행했습니다."))
        self.install_definition(replace(definition, run=implementation))
        response = self.run_module()
        self.assertEqual(response.status_code, 200, response.get_json())
        implementation.assert_not_called()
        run = self.row("SELECT * FROM module_runs ORDER BY id DESC LIMIT 1")
        self.assertEqual(run["status"], "skipped")
        self.assertEqual(run["module_key"], "minutes")
        self.assertEqual(run["executed_by"], self.row("SELECT sales_owner FROM projects WHERE id=1")["sales_owner"])
        self.assertTrue(run["started_at"])
        self.assertTrue(run["finished_at"])
        self.assertIn("준비 중", run["result_summary"])
        self.assertIsNone(run["artifact_id"])
        self.assertEqual(self.count("artifacts"), 0)
        event = self.events("module.executed")[0]
        self.assertEqual(json.loads(event["payload"])["status"], "skipped")

    def test_current_stage_and_common_cards_are_usable(self):
        for key in ("proposal_strategy", "quote_builder", "minutes", "keyman_register"):
            with self.subTest(key=key):
                response = self.run_module(key)
                self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.count("module_runs"), 4)

    def test_other_stage_card_is_rejected_without_run_or_event(self):
        expected = self.counts()
        response = self.run_module("wbs_builder")
        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertEqual(self.counts(), expected)

    def test_common_card_run_belongs_only_to_selected_project(self):
        response = self.run_module(project_id=2, actor="delivery")
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.count("module_runs"), 1)
        self.assertEqual(self.row("SELECT project_id FROM module_runs")["project_id"], 2)
        self.assertFalse(self.events("module.executed", 1))
        self.assertEqual(len(self.events("module.executed", 2)), 1)
        self.assertEqual(self.client.get("/api/projects/1").get_json()["module_runs"], [])

    def test_active_module_receives_context_and_persists_multiple_artifacts(self):
        async def implementation(ctx):
            self.assertEqual(ctx.project["id"], 1)
            self.assertEqual(ctx.stage, "B")
            self.assertEqual(ctx.user["role"], "delivery")
            self.assertIs(ctx.actor, ctx.user)
            self.assertIs(ctx.store, ctx.db)
            self.assertEqual(ctx.actor["name"], ctx.project["delivery_owner"])
            self.assertEqual(ctx.db.execute("SELECT current_stage FROM projects WHERE id=1").fetchone()[0], "B")
            ctx.emit("test.module_context", {"checked": True})
            return ModuleResult("검증용 산출물 두 개를 저장했습니다.", [
                {"kind": "minutes", "title": "검증용 회의록", "location": "/tmp/ibcm-test-minutes.txt"},
                {"kind": "sheet", "title": "검증용 목록", "location": "https://example.test/list", "version": 2},
            ])

        self.install_definition(replace(self.app.config["MODULES"]["minutes"], status="active", run=implementation))
        response = self.run_module(actor="delivery")
        self.assertEqual(response.status_code, 200, response.get_json())
        run = self.row("SELECT * FROM module_runs")
        self.assertEqual(run["status"], "completed")
        artifacts = self.rows("SELECT * FROM artifacts ORDER BY id")
        self.assertEqual(len(artifacts), 2)
        self.assertEqual(run["artifact_id"], artifacts[0]["id"])
        self.assertEqual([artifact["version"] for artifact in artifacts], [1, 2])
        self.assertTrue(all(artifact["project_id"] == 1 and artifact["stage"] == "B" for artifact in artifacts))
        self.assertEqual(len(self.events("artifact.created")), 2)
        self.assertEqual(len(self.events("test.module_context")), 1)
        actor = self.row("SELECT delivery_owner FROM projects WHERE id=1")["delivery_owner"]
        self.assertTrue(all(event["actor"] == actor for event in self.events("artifact.created")))
        self.assertEqual(self.events("test.module_context")[0]["actor"], actor)
        self.assertEqual(self.events("module.executed")[0]["actor"], actor)
        self.assertEqual(json.loads(self.events("module.executed")[0]["payload"])["status"], "completed")
        notion_deliveries = self.rows("""
            SELECT o.* FROM outbox o JOIN events e ON e.id=o.event_id
            WHERE e.type='artifact.created' AND o.adapter='notion'
        """)
        self.assertEqual(len(notion_deliveries), 2)
        self.assertTrue(all(row["status"] == "sent" for row in notion_deliveries))

    def test_module_skill_is_saved_and_exposed_with_registry_updates(self):
        definition = replace(self.app.config["MODULES"]["minutes"], skill="시험 스킬")
        self.install_definition(definition)
        stored = self.row("SELECT skill FROM module_registry WHERE key='minutes'")
        self.assertEqual(stored["skill"], "시험 스킬")
        detail = self.client.get("/api/projects/1").get_json()
        module = next(module for module in detail["modules"] if module["key"] == "minutes")
        self.assertEqual(module["skill"], "시험 스킬")
        self.install_definition(replace(definition, skill=None))
        self.assertIsNone(self.row("SELECT skill FROM module_registry WHERE key='minutes'")["skill"])

    def test_module_failure_rolls_back_partial_work_but_keeps_failed_run(self):
        async def implementation(ctx):
            ctx.db.execute("UPDATE projects SET title='되돌릴 변경' WHERE id=?", (ctx.project["id"],))
            ctx.db.execute("""
                INSERT INTO artifacts(project_id,stage,module_key,kind,title,location,version,created_at)
                VALUES(1,'B','minutes','minutes','되돌릴 산출물','/tmp/incomplete',1,?)
            """, (now(),))
            ctx.emit("artifact.created", {"title": "되돌릴 산출물"})
            raise RuntimeError("검증용 실패")

        before = self.row("SELECT * FROM projects WHERE id=1")
        self.install_definition(replace(self.app.config["MODULES"]["minutes"], status="ready", run=implementation))
        with self.assertLogs("server.runner", level="ERROR"):
            response = self.run_module()
        self.assertEqual(response.status_code, 500, response.get_json())
        self.assertEqual(self.row("SELECT * FROM projects WHERE id=1"), before)
        self.assertEqual(self.count("artifacts"), 0)
        self.assertFalse(self.events("artifact.created"))
        run = self.row("SELECT * FROM module_runs")
        self.assertEqual(run["status"], "failed")
        self.assertTrue(run["finished_at"])
        self.assertIsNone(run["artifact_id"])
        event = self.events("module.executed")[0]
        self.assertEqual(json.loads(event["payload"])["status"], "failed")

    def test_invalid_artifact_does_not_leave_earlier_artifact_behind(self):
        async def implementation(ctx):
            return ModuleResult("일부 산출물에 오류가 있습니다.", [
                {"kind": "document", "title": "정상 형식", "location": "/tmp/complete"},
                {"kind": "document", "title": "경로가 빠진 형식"},
            ])

        self.install_definition(replace(self.app.config["MODULES"]["minutes"], status="active", run=implementation))
        with self.assertLogs("server.runner", level="ERROR"):
            response = self.run_module()
        self.assertEqual(response.status_code, 500, response.get_json())
        self.assertEqual(self.count("artifacts"), 0)
        self.assertFalse(self.events("artifact.created"))
        self.assertEqual(self.row("SELECT status FROM module_runs")["status"], "failed")

    def test_missing_module_project_and_actor_return_errors_without_run(self):
        for key, project, actor, status in (("missing", 1, "sales", 404),
                                            ("minutes", 999, "sales", 404),
                                            ("minutes", 1, "missing", 400)):
            with self.subTest(key=key, project=project, actor=actor):
                response = self.run_module(key, project, actor)
                self.assertEqual(response.status_code, status, response.get_json())
                self.assertIn("error", response.get_json())
        self.assertEqual(self.count("module_runs"), 0)
