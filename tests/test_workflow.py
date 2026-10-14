"""시드와 단계 승인 흐름의 저장 결과를 검증합니다."""

import json
import sqlite3

from server.app import create_app
from server.db import transaction
from tests.support import AppTestCase


class SeedAndSchemaTests(AppTestCase):
    def test_seed_contains_two_projects_and_one_pending_request(self):
        projects = self.rows("SELECT * FROM projects ORDER BY id")
        self.assertEqual([project["current_stage"] for project in projects], ["B", "D"])
        self.assertEqual(len({project["code"] for project in projects}), 2)
        for project in projects:
            for field in ("customer_name", "title", "executive", "sales_owner",
                          "delivery_owner", "pmo_owner", "created_at", "updated_at"):
                self.assertTrue(project[field], field)
        transitions = self.rows("SELECT * FROM stage_transitions")
        self.assertEqual(len(transitions), 1)
        self.assertEqual(
            (transitions[0]["project_id"], transitions[0]["from_stage"],
             transitions[0]["to_stage"], transitions[0]["status"]),
            (2, "D", "E", "requested"),
        )
        self.assertEqual(self.count("events"), 3)
        self.assertTrue(self.rows("SELECT * FROM outbox"))
        self.assertTrue(all(row["status"] == "sent" for row in self.rows("SELECT * FROM outbox")))

    def test_all_36_modules_are_registered_in_order_and_planned(self):
        definitions = self.rows('SELECT * FROM module_registry ORDER BY stage, "order"')
        self.assertEqual(len(definitions), 36)
        for stage, expected_count in (("A", 5), ("B", 7), ("C", 6), ("D", 6), ("E", 6)):
            cards = [row for row in definitions if row["stage"] == stage]
            self.assertEqual(len(cards), expected_count)
            self.assertEqual([row["order"] for row in cards], list(range(1, expected_count + 1)))
            self.assertTrue(all(card["category"] == "stage_task" for card in cards))
        common = [row for row in definitions if row["category"] == "common"]
        self.assertEqual(len(common), 6)
        self.assertTrue(all(card["stage"] is None and card["main_role"] is None for card in common))
        self.assertTrue(all(card["status"] == "planned" for card in definitions))
        self.assertEqual(self.row("SELECT main_role FROM module_registry WHERE key='scope_builder'")["main_role"], "delivery")
        self.assertEqual(self.row("SELECT main_role FROM module_registry WHERE key='quote_builder'")["main_role"], "pmo")

    def test_reopening_database_preserves_data_and_does_not_duplicate_seed(self):
        transition = self.request_transition()
        response = self.decide(transition["id"])
        self.assertEqual(response.status_code, 200, response.get_json())
        expected = self.counts()
        reopened = create_app(database_path=self.database, testing=True)
        self.assertEqual(self.counts(), expected)
        result = reopened.test_client().get("/api/projects/1").get_json()
        self.assertEqual(result["project"]["current_stage"], "C")

    def test_foreign_keys_and_single_pending_gate_are_enforced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(self.db):
                self.db.execute("INSERT INTO events(project_id,type,payload,created_at) VALUES(999,'project.created','{}','now')")
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(self.db):
                self.db.execute("""
                    INSERT INTO stage_transitions(project_id,from_stage,to_stage,status,
                        requested_by,requested_at)
                    VALUES(2,'D','E','requested','테스트','now')
                """)
        self.assertEqual(self.count("stage_transitions"), 1)

    def test_project_details_are_scoped_to_selected_project(self):
        projects = self.client.get("/api/projects").get_json()["projects"]
        self.assertEqual(len(projects), 2)
        first = self.client.get("/api/projects/1").get_json()
        second = self.client.get("/api/projects/2").get_json()
        self.assertIsNone(first["pending_transition"])
        self.assertEqual(second["pending_transition"]["project_id"], 2)
        for project_id, payload in ((1, first), (2, second)):
            for field in ("transitions", "events", "module_runs"):
                self.assertTrue(all(row["project_id"] == project_id for row in payload[field]), field)
            self.assertIn("modules", payload)
            self.assertIn("actors", payload)
            self.assertIn("stages", payload)
            self.assertIn("outbox", payload)

    def test_database_rejects_rejection_without_a_reason(self):
        for reason in (None, "", "   "):
            with self.subTest(reason=reason):
                with self.assertRaises(sqlite3.IntegrityError):
                    with transaction(self.db):
                        self.db.execute("""
                            UPDATE stage_transitions SET status='rejected',
                                decided_by='검증용 임원',decided_at='now',reason=?
                            WHERE project_id=2
                        """, (reason,))
        self.assertEqual(self.row("SELECT status FROM stage_transitions WHERE project_id=2")["status"], "requested")


class StageTransitionTests(AppTestCase):
    def test_sales_request_records_request_event_and_slack_delivery(self):
        transition = self.request_transition()
        project = self.row("SELECT * FROM projects WHERE id=1")
        self.assertEqual(project["current_stage"], "B")
        self.assertEqual(transition["status"], "requested")
        self.assertEqual(transition["requested_by"], project["sales_owner"])
        self.assertEqual((transition["from_stage"], transition["to_stage"]), ("B", "C"))
        self.assertIsNone(transition["decided_at"])
        event = self.events("stage.approval_requested")[0]
        self.assertEqual(json.loads(event["payload"])["transition_id"], transition["id"])
        delivery = self.row("SELECT * FROM outbox WHERE event_id=? AND adapter='slack'", (event["id"],))
        self.assertEqual(delivery["status"], "sent")
        self.assertEqual(delivery["attempts"], 1)
        self.assertTrue(delivery["sent_at"])

    def test_only_executive_can_decide(self):
        transition = self.request_transition()
        expected = self.counts()
        for actor in ("sales", "delivery", "pmo"):
            for decision in ("approved", "rejected"):
                with self.subTest(actor=actor, decision=decision):
                    response = self.decide(transition["id"], decision, actor, "범위 재확인")
                    self.assertEqual(response.status_code, 403, response.get_json())
                    self.assertIn("error", response.get_json())
        self.assertEqual(self.counts(), expected)
        self.assertEqual(self.row("SELECT status FROM stage_transitions WHERE id=?", (transition["id"],))["status"], "requested")

    def test_approval_advances_once_and_keeps_second_project_unchanged(self):
        transition = self.request_transition()
        other_before = self.row("SELECT * FROM projects WHERE id=2")
        response = self.decide(transition["id"])
        self.assertEqual(response.status_code, 200, response.get_json())
        project = self.row("SELECT * FROM projects WHERE id=1")
        self.assertEqual(project["current_stage"], "C")
        decision = self.row("SELECT * FROM stage_transitions WHERE id=?", (transition["id"],))
        self.assertEqual(decision["status"], "approved")
        self.assertEqual(decision["decided_by"], project["executive"])
        self.assertTrue(decision["decided_at"])
        self.assertEqual(len(self.events("stage.approved")), 1)
        self.assertEqual(self.row("SELECT * FROM projects WHERE id=2"), other_before)
        expected = self.counts()
        duplicate = self.decide(transition["id"])
        self.assertEqual(duplicate.status_code, 409, duplicate.get_json())
        self.assertEqual(self.counts(), expected)

    def test_rejection_requires_reason_and_allows_new_request(self):
        transition = self.request_transition()
        expected = self.counts()
        for reason in ("", "   "):
            with self.subTest(reason=reason):
                response = self.decide(transition["id"], "rejected", reason=reason)
                self.assertEqual(response.status_code, 400, response.get_json())
        self.assertEqual(self.counts(), expected)
        response = self.decide(transition["id"], "rejected", reason="  범위 재확인이 필요합니다  ")
        self.assertEqual(response.status_code, 200, response.get_json())
        rejected = self.row("SELECT * FROM stage_transitions WHERE id=?", (transition["id"],))
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(rejected["reason"], "범위 재확인이 필요합니다")
        self.assertEqual(self.row("SELECT current_stage FROM projects WHERE id=1")["current_stage"], "B")
        self.assertEqual(len(self.events("stage.rejected")), 1)
        self.assertNotEqual(self.request_transition()["id"], transition["id"])

    def test_skip_back_and_unknown_stage_are_rejected_without_changes(self):
        expected = self.counts()
        for destination in ("A", "B", "D", "E", "F", "", None):
            with self.subTest(destination=destination):
                response = self.client.post("/api/projects/1/transitions", json={"actor": "sales", "to_stage": destination})
                self.assertEqual(response.status_code, 400, response.get_json())
        self.assertEqual(self.counts(), expected)

    def test_every_consecutive_stage_is_allowed_and_e_is_terminal(self):
        with transaction(self.db):
            self.db.execute("UPDATE projects SET current_stage='A' WHERE id=1")
        for destination in ("B", "C", "D", "E"):
            transition = self.request_transition(to_stage=destination)
            response = self.decide(transition["id"])
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertEqual(self.row("SELECT current_stage FROM projects WHERE id=1")["current_stage"], destination)
        response = self.client.post("/api/projects/1/transitions", json={"actor": "sales", "to_stage": "E"})
        self.assertEqual(response.status_code, 400, response.get_json())

    def test_duplicate_requests_are_rejected(self):
        self.request_transition()
        expected = self.counts()
        duplicate = self.client.post("/api/projects/1/transitions", json={"actor": "pmo", "to_stage": "C"})
        self.assertEqual(duplicate.status_code, 409, duplicate.get_json())
        self.assertEqual(self.counts(), expected)

    def test_cannot_decide_another_projects_request(self):
        second = self.row("SELECT * FROM stage_transitions WHERE project_id=2")
        expected = self.counts()
        response = self.decide(second["id"], project_id=1)
        self.assertEqual(response.status_code, 404, response.get_json())
        self.assertEqual(self.counts(), expected)

    def test_stale_request_cannot_overwrite_current_stage(self):
        transition = self.request_transition()
        with transaction(self.db):
            self.db.execute("UPDATE projects SET current_stage='D' WHERE id=1")
        response = self.decide(transition["id"])
        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertEqual(self.row("SELECT current_stage FROM projects WHERE id=1")["current_stage"], "D")
        self.assertEqual(len(self.events("stage.approved")), 0)

    def test_invalid_requests_return_structured_errors(self):
        for body in ({}, {"actor": "unknown", "to_stage": "C"}, ["sales"], None):
            with self.subTest(body=body):
                response = self.client.post("/api/projects/1/transitions", data=json.dumps(body), content_type="application/json")
                self.assertEqual(response.status_code, 400, response.get_json())
                self.assertIn("error", response.get_json())
        for url in ("/api/projects/999", "/api/projects/999/transitions"):
            with self.subTest(url=url):
                if url.endswith("transitions"):
                    response = self.client.post(url, json={"actor": "sales", "to_stage": "C"})
                else:
                    response = self.client.get(url)
                self.assertEqual(response.status_code, 404, response.get_json())
                self.assertIn("error", response.get_json())
