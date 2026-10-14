"""발행 기록과 어댑터 전달, 재시도, 트랜잭션을 검증합니다."""

from unittest.mock import patch

from adapters import ADAPTERS, EVENT_ROUTES
from server.db import transaction
from server.events import dispatch_outbox, emit
from tests.support import AppTestCase


class EventDeliveryTests(AppTestCase):
    def queue(self, event_type="stage.approval_requested"):
        with transaction(self.db):
            return emit(self.db, 1, event_type, {"테스트": "전달 확인"})

    def test_emit_saves_pending_delivery_before_dispatch(self):
        event_id = self.queue()
        pending = self.row("SELECT * FROM outbox WHERE event_id=?", (event_id,))
        self.assertEqual((pending["adapter"], pending["status"], pending["attempts"]), ("slack", "pending", 0))
        self.assertEqual((pending["project_id"], pending["event_type"]), (1, "stage.approval_requested"))
        self.assertEqual(pending["log"], "전송 대기 중")
        self.assertIsNone(pending["sent_at"])
        with self.assertLogs("adapters.slack", level="INFO") as logs:
            dispatch_outbox(self.db)
        self.assertTrue(any("stage.approval_requested" in line for line in logs.output))
        sent = self.row("SELECT * FROM outbox WHERE event_id=?", (event_id,))
        self.assertEqual((sent["status"], sent["attempts"]), ("sent", 1))
        self.assertTrue(sent["sent_at"])
        self.assertEqual(sent["log"], "slack 어댑터가 stage.approval_requested 이벤트를 받았음")
        self.assertIn(sent["log"], logs.output[0])

    def test_routes_deliver_only_detached_event_objects_to_each_adapter(self):
        event_id = self.queue("stage.approved")
        received = {}
        patches = []
        try:
            for name in EVENT_ROUTES["stage.approved"]:
                replacement = patch.object(ADAPTERS[name], "handle", side_effect=lambda event, adapter=name: received.setdefault(adapter, event))
                patches.append(replacement)
                replacement.start()
            dispatch_outbox(self.db)
        finally:
            for replacement in reversed(patches):
                replacement.stop()
        self.assertEqual(set(received), set(EVENT_ROUTES["stage.approved"]))
        for event in received.values():
            self.assertEqual(set(event), {"id", "project_id", "type", "payload", "actor", "created_at"})
            self.assertEqual(event["id"], event_id)
            self.assertEqual(event["payload"], {"테스트": "전달 확인"})
            self.assertEqual(event["actor"], "시스템")

    def test_actor_is_derived_or_explicitly_supplied(self):
        for payload, explicit, expected in (
            ({"requested_by": "영업 담당자"}, None, "영업 담당자"),
            ({"requested_by": "영업 담당자", "decided_by": "총괄 임원"}, None, "총괄 임원"),
            ({"executed_by": "수행 담당자"}, None, "수행 담당자"),
            ({"requested_by": "영업 담당자"}, "대리 담당자", "대리 담당자"),
            ({"executed_by": " "}, None, "시스템"),
        ):
            with self.subTest(payload=payload, explicit=explicit):
                with transaction(self.db):
                    event_id = emit(self.db, 1, "test.actor", payload, actor=explicit)
                event = self.row("SELECT * FROM events WHERE id=?", (event_id,))
                self.assertEqual(event["actor"], expected)

    def test_sent_events_are_not_delivered_again(self):
        event_id = self.queue()
        with patch.object(ADAPTERS["slack"], "handle") as handle:
            dispatch_outbox(self.db)
            dispatch_outbox(self.db)
        handle.assert_called_once()
        self.assertEqual(self.row("SELECT attempts FROM outbox WHERE event_id=?", (event_id,))["attempts"], 1)

    def test_adapter_failure_is_recorded_and_can_be_retried(self):
        event_id = self.queue()
        with patch.object(ADAPTERS["slack"], "handle", side_effect=RuntimeError("검증용 실패")):
            with self.assertLogs("server.events", level="ERROR"):
                dispatch_outbox(self.db)
        failed = self.row("SELECT * FROM outbox WHERE event_id=?", (event_id,))
        self.assertEqual((failed["status"], failed["attempts"]), ("failed", 1))
        self.assertTrue(failed["last_error"])
        self.assertEqual(failed["log"], failed["last_error"])
        self.assertIsNone(failed["sent_at"])
        with patch.object(ADAPTERS["slack"], "handle") as handle:
            dispatch_outbox(self.db)
        handle.assert_called_once()
        sent = self.row("SELECT * FROM outbox WHERE event_id=?", (event_id,))
        self.assertEqual((sent["status"], sent["attempts"]), ("sent", 2))
        self.assertIsNone(sent["last_error"])
        self.assertEqual(sent["log"], "slack 어댑터가 stage.approval_requested 이벤트를 받았음")

    def test_three_failed_attempts_stop_automatic_retry(self):
        event_id = self.queue()
        with patch.object(ADAPTERS["slack"], "handle", side_effect=RuntimeError("검증용 실패")) as handle:
            with self.assertLogs("server.events", level="ERROR"):
                for _ in range(4):
                    dispatch_outbox(self.db)
        self.assertEqual(handle.call_count, 3)
        failed = self.row("SELECT * FROM outbox WHERE event_id=?", (event_id,))
        self.assertEqual((failed["status"], failed["attempts"]), ("failed", 3))

    def test_transaction_failure_rolls_back_state_event_and_delivery_together(self):
        before = self.counts()
        project = self.row("SELECT * FROM projects WHERE id=1")
        with self.assertRaisesRegex(RuntimeError, "검증용 롤백"):
            with transaction(self.db):
                self.db.execute("UPDATE projects SET current_stage='C' WHERE id=1")
                emit(self.db, 1, "stage.approved", {"to_stage": "C"})
                raise RuntimeError("검증용 롤백")
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.row("SELECT * FROM projects WHERE id=1"), project)

    def test_approval_emit_failure_rolls_back_decision_and_stage(self):
        transition = self.request_transition()
        before = self.counts()
        with patch("server.workflow.emit", side_effect=RuntimeError("검증용 발행 실패")):
            with self.assertRaisesRegex(RuntimeError, "검증용 발행 실패"):
                self.decide(transition["id"])
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.row("SELECT current_stage FROM projects WHERE id=1")["current_stage"], "B")
        persisted = self.row("SELECT * FROM stage_transitions WHERE id=?", (transition["id"],))
        self.assertEqual(persisted["status"], "requested")
        self.assertIsNone(persisted["decided_by"])
