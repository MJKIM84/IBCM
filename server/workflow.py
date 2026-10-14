"""순차 단계 이동과 담당 역할에 따른 승인 게이트."""

from server.db import now
from server.events import emit

STAGES = (
    {"key": "A", "name": "사전 영업"},
    {"key": "B", "name": "제안과 견적"},
    {"key": "C", "name": "계약과 착수"},
    {"key": "D", "name": "수행"},
    {"key": "E", "name": "검수와 종료"},
)
ROLE_FIELDS = {
    "executive": ("executive", "총괄 임원"),
    "sales": ("sales_owner", "영업"),
    "delivery": ("delivery_owner", "수행"),
    "pmo": ("pmo_owner", "관리"),
}


class WorkflowError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def get_project(db, project_id):
    row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if row is None:
        raise WorkflowError("프로젝트를 찾을 수 없습니다.", 404)
    return dict(row)


def actors_for(project):
    return [{"role": role, "name": project[field], "label": label}
            for role, (field, label) in ROLE_FIELDS.items()]


def actor_for(project, role):
    if not isinstance(role, str) or role not in ROLE_FIELDS:
        raise WorkflowError("행동할 담당자를 선택해 주세요.")
    return next(actor for actor in actors_for(project) if actor["role"] == role)


def request_transition(db, project_id, data):
    project = get_project(db, project_id)
    actor = actor_for(project, data.get("actor"))
    current = project["current_stage"]
    if current == "E":
        raise WorkflowError("검수와 종료는 마지막 단계입니다.")
    next_stage = chr(ord(current) + 1)
    if data.get("to_stage") != next_stage:
        raise WorkflowError("바로 다음 단계로만 승인 요청을 할 수 있습니다.")
    if db.execute("SELECT 1 FROM stage_transitions WHERE project_id=? AND status='requested'",
                  (project_id,)).fetchone():
        raise WorkflowError("이미 승인 대기 중인 요청이 있습니다.", 409)
    transition_id = db.execute('''
        INSERT INTO stage_transitions(project_id,from_stage,to_stage,status,requested_by,requested_at)
        VALUES(?,?,?,'requested',?,?)
    ''', (project_id, current, next_stage, actor["name"], now())).lastrowid
    emit(db, project_id, "stage.approval_requested", {
        "transition_id": transition_id, "from_stage": current,
        "to_stage": next_stage, "requested_by": actor["name"],
    })
    return {"message": "총괄 임원에게 단계 승인을 요청했습니다.", "transition_id": transition_id}


def decide_transition(db, project_id, transition_id, data):
    project = get_project(db, project_id)
    actor = actor_for(project, data.get("actor"))
    if actor["role"] != "executive":
        raise WorkflowError("승인과 거절은 총괄 임원만 할 수 있습니다.", 403)
    transition = db.execute("SELECT * FROM stage_transitions WHERE id=? AND project_id=?",
                            (transition_id, project_id)).fetchone()
    if transition is None:
        raise WorkflowError("승인 요청을 찾을 수 없습니다.", 404)
    if transition["status"] != "requested" or project["current_stage"] != transition["from_stage"]:
        raise WorkflowError("이미 처리되었거나 현재 단계와 맞지 않는 요청입니다.", 409)
    decision = data.get("decision")
    if decision not in ("approved", "rejected"):
        raise WorkflowError("승인 또는 거절을 선택해 주세요.")
    reason = data.get("reason", "")
    if not isinstance(reason, str):
        raise WorkflowError("사유는 글로 입력해 주세요.")
    reason = reason.strip()
    if decision == "rejected" and not reason:
        raise WorkflowError("거절 사유를 입력해 주세요.")
    if len(reason) > 2000:
        raise WorkflowError("사유는 2,000자 이내로 입력해 주세요.")
    timestamp = now()
    db.execute('''UPDATE stage_transitions SET status=?,decided_by=?,decided_at=?,reason=?
        WHERE id=?''', (decision, actor["name"], timestamp, reason or None, transition_id))
    if decision == "approved":
        db.execute("UPDATE projects SET current_stage=?,updated_at=? WHERE id=?",
                   (transition["to_stage"], timestamp, project_id))
    emit(db, project_id, f"stage.{decision}", {
        "transition_id": transition_id, "from_stage": transition["from_stage"],
        "to_stage": transition["to_stage"], "decided_by": actor["name"], "reason": reason,
    })
    return {"message": "승인하여 다음 단계로 이동했습니다." if decision == "approved"
            else "요청을 거절했습니다. 현재 단계가 유지됩니다."}
