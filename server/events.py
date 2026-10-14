"""업무 변경과 발행 예약은 한 트랜잭션에 저장합니다."""

import json
import logging

from adapters import ADAPTERS, EVENT_ROUTES
from server.db import now, transaction

logger = logging.getLogger(__name__)


def emit(db, project_id, event_type, payload, actor=None):
    timestamp = now()
    if actor is None:
        actor = next((payload[key] for key in ("decided_by", "requested_by", "executed_by")
                      if isinstance(payload, dict) and isinstance(payload.get(key), str)
                      and payload[key].strip()), "시스템")
    event_id = db.execute(
        "INSERT INTO events(project_id,type,payload,actor,created_at) VALUES(?,?,?,?,?)",
        (project_id, event_type, json.dumps(payload, ensure_ascii=False), actor, timestamp),
    ).lastrowid
    for adapter in EVENT_ROUTES.get(event_type, ()):
        db.execute(
            """INSERT INTO outbox(event_id,project_id,adapter,event_type,status,log,created_at)
               VALUES(?,?,?,?,'pending','전송 대기 중',?)""",
            (event_id, project_id, adapter, event_type, timestamp),
        )
    return event_id


def dispatch_outbox(db):
    """미전송 건을 전달합니다. 실패는 보존하고 다음 호출에서 최대 3회 시도합니다."""
    # 현재 스텁은 로컬 로그만 씁니다. 실제 API 교체 시 id를 중복 방지 키로 쓰세요.
    with transaction(db):
        rows = db.execute('''
            SELECT o.id AS outbox_id, o.adapter, e.* FROM outbox o
            JOIN events e ON e.id=o.event_id
            WHERE o.status IN ('pending','failed') AND o.attempts < 3
            ORDER BY o.id
        ''').fetchall()
        for row in rows:
            event = {k: row[k] for k in ("id", "project_id", "type", "actor", "created_at")}
            event["payload"] = json.loads(row["payload"])
            try:
                ADAPTERS[row["adapter"]].handle(event)
            except Exception:
                # 외부 API의 오류 문자열에는 인증 정보가 포함될 수 있습니다.
                logger.error("%s 어댑터 전송 실패: 이벤트 %s", row["adapter"], event["id"])
                db.execute("""
                    UPDATE outbox SET status='failed', attempts=attempts+1,
                    last_error='어댑터 처리에 실패했습니다',
                    log='어댑터 처리에 실패했습니다' WHERE id=?
                """, (row["outbox_id"],))
            else:
                db.execute("""
                    UPDATE outbox SET status='sent', attempts=attempts+1,
                    last_error=NULL, log=?, sent_at=? WHERE id=?
                """, (f'{row["adapter"]} 어댑터가 {event["type"]} 이벤트를 받았음',
                      now(), row["outbox_id"]))
