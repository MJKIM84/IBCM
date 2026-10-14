"""모듈 작성자가 기록을 빠뜨리지 않도록 실행 수명 주기를 관리합니다."""

import asyncio
import logging

from modules import ModuleContext, ModuleResult
from server.db import now
from server.events import emit
from server.workflow import WorkflowError, actor_for, get_project

logger = logging.getLogger(__name__)


def execute_module(db, project_id, module, actor_role):
    project = get_project(db, project_id)
    actor = actor_for(project, actor_role)
    if module.category == "stage_task" and module.stage != project["current_stage"]:
        raise WorkflowError("현재 단계의 업무 카드만 실행할 수 있습니다.", 409)
    started = now()
    run_id = db.execute('''
        INSERT INTO module_runs(project_id,module_key,started_at,status,executed_by)
        VALUES(?,?,?,'running',?)
    ''', (project_id, module.key, started, actor["name"])).lastrowid
    context = ModuleContext(project, project["current_stage"], actor, db,
                            lambda event_type, payload: emit(db, project_id, event_type, payload,
                                                             actor=actor["name"]))
    artifact_ids = []
    if module.status == "planned":
        status, summary = "skipped", "준비 중인 모듈입니다. 실행 없이 확인 기록만 남겼습니다."
    else:
        # 모듈 내부 오류가 나도 실패 이력은 남기고 부분 산출물은 되돌립니다.
        db.execute("SAVEPOINT module_work")
        try:
            result = asyncio.run(module.run(context))
            if not isinstance(result, ModuleResult) or not isinstance(result.summary, str):
                raise ValueError("모듈 결과는 ModuleResult여야 합니다.")
            for artifact in result.artifacts:
                if not isinstance(artifact, dict) or not all(
                    isinstance(artifact.get(key), str) and artifact[key].strip()
                    for key in ("kind", "title", "location")
                ):
                    raise ValueError("산출물에는 kind, title, location이 필요합니다.")
                artifact_id = db.execute('''
                    INSERT INTO artifacts(project_id,stage,module_key,kind,title,location,version,created_at)
                    VALUES(?,?,?,?,?,?,?,?)
                ''', (project_id, artifact.get("stage", project["current_stage"]), module.key,
                      artifact["kind"], artifact["title"], artifact["location"],
                      artifact.get("version", 1), now())).lastrowid
                artifact_ids.append(artifact_id)
                context.emit("artifact.created", {
                    "artifact_id": artifact_id, "module_key": module.key,
                    "title": artifact["title"], "kind": artifact["kind"],
                })
            status, summary = "completed", result.summary
        except Exception:
            db.execute("ROLLBACK TO SAVEPOINT module_work")
            artifact_ids.clear()
            status, summary = "failed", "모듈 실행에 실패했습니다. 모듈 구현을 확인해 주세요."
            logger.error("모듈 실행 실패: %s, 실행 기록 %s", module.key, run_id)
        finally:
            db.execute("RELEASE SAVEPOINT module_work")
    db.execute('''UPDATE module_runs SET finished_at=?,status=?,result_summary=?,artifact_id=?
                  WHERE id=?''', (now(), status, summary, artifact_ids[0] if artifact_ids else None, run_id))
    context.emit("module.executed", {
        "run_id": run_id, "module_key": module.key, "status": status,
        "executed_by": actor["name"], "artifact_ids": artifact_ids,
    })
    return {"message": summary, "run_id": run_id, "status": status, "artifact_ids": artifact_ids}
