"""새 데이터 파일에만 예제 프로젝트를 만듭니다."""

from server.db import now
from server.events import emit


def seed_projects(db):
    if db.execute("SELECT COUNT(*) FROM projects").fetchone()[0]:
        return
    timestamp = now()
    examples = [
        ("IBCM-2026-001", "한빛리테일", "고객 경험 통합 플랫폼 구축", "B",
         "김서윤", "이도현", "박지우", "최수빈"),
        ("IBCM-2026-002", "새봄모빌리티", "스마트 물류 운영 시스템 구축", "D",
         "정하윤", "한지호", "오민서", "윤서진"),
    ]
    ids = []
    for row in examples:
        project_id = db.execute('''
            INSERT INTO projects(code,customer_name,title,current_stage,executive,
                sales_owner,delivery_owner,pmo_owner,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
        ''', (*row, timestamp, timestamp)).lastrowid
        ids.append(project_id)
        emit(db, project_id, "project.created", {
            "code": row[0], "title": row[2], "stage": row[3], "source": "seed",
        })
    transition_id = db.execute('''
        INSERT INTO stage_transitions(project_id,from_stage,to_stage,status,
            requested_by,requested_at)
        VALUES(?,'D','E','requested','오민서',?)
    ''', (ids[1], timestamp)).lastrowid
    emit(db, ids[1], "stage.approval_requested", {
        "transition_id": transition_id, "from_stage": "D", "to_stage": "E",
        "requested_by": "오민서",
    })
