"""화면과 API를 하나의 Flask 서버로 제공합니다."""

import json
import os
from pathlib import Path

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

from modules import ModuleContext, get_modules
from seed import seed_projects
from server.db import connect, initialize, sync_modules, transaction
from server.events import dispatch_outbox
from server.runner import execute_module
from server.workflow import (STAGES, WorkflowError, actors_for, decide_transition,
                             get_project, request_transition)

ROOT = Path(__file__).resolve().parent.parent


def create_app(database_path=None, testing=False):
    app = Flask(__name__, static_folder=str(ROOT / "public"), static_url_path="")
    app.config.update(TESTING=testing, MAX_CONTENT_LENGTH=64 * 1024,
                      DATABASE_PATH=str(database_path or os.environ.get("IBCM_DB_PATH")
                                        or ROOT / "data" / "ibcm.sqlite3"))
    app.json.ensure_ascii = False
    app.config["MODULES"] = {module.key: module for module in get_modules()}
    db = connect(app.config["DATABASE_PATH"])
    try:
        initialize(db)
        with transaction(db):
            sync_modules(db, app.config["MODULES"].values())
            seed_projects(db)
        dispatch_outbox(db)
    finally:
        db.close()

    def database():
        if "db" not in g:
            g.db = connect(app.config["DATABASE_PATH"])
        return g.db

    @app.teardown_appcontext
    def close_database(error=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.errorhandler(WorkflowError)
    def workflow_error(error):
        return jsonify(error=str(error)), error.status

    @app.errorhandler(HTTPException)
    def request_error(error):
        messages = {400: "요청 내용을 확인해 주세요.", 404: "요청한 항목을 찾을 수 없습니다.",
                    405: "지원하지 않는 요청 방식입니다.", 413: "요청 내용이 너무 큽니다.",
                    415: "JSON 형식으로 요청해 주세요."}
        return jsonify(error=messages.get(error.code, "요청을 처리할 수 없습니다.")), error.code

    def body():
        data = request.get_json()
        if not isinstance(data, dict):
            raise WorkflowError("요청 내용은 JSON 객체여야 합니다.")
        return data

    @app.after_request
    def response_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        )
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/api/projects")
    def list_projects():
        return jsonify(projects=[dict(row) for row in database().execute("SELECT * FROM projects ORDER BY id")])

    @app.get("/api/projects/<int:project_id>")
    def project_detail(project_id):
        db = database()
        # 동일한 시점의 단계와 카드, 로그를 함께 읽습니다.
        db.execute("BEGIN")
        try:
            project = get_project(db, project_id)
            actors = actors_for(project)
            context = ModuleContext(project, project["current_stage"], actors[0], db,
                                    lambda *_: (_ for _ in ()).throw(RuntimeError("표시 중 이벤트를 발행할 수 없습니다.")))
            modules = [{"key": m.key, "name": m.name, "category": m.category, "stage": m.stage,
                        "order": m.order, "mainRole": m.mainRole, "description": m.description,
                        "status": m.status, "skill": m.skill, "render": m.render(context)}
                       for m in app.config["MODULES"].values()]
            transitions = [dict(row) for row in db.execute(
                "SELECT * FROM stage_transitions WHERE project_id=? ORDER BY id DESC", (project_id,))]
            events = [dict(row) for row in db.execute(
                "SELECT * FROM events WHERE project_id=? ORDER BY id DESC LIMIT 30", (project_id,))]
            for event in events:
                event["payload"] = json.loads(event["payload"])
            outbox = [dict(row) for row in db.execute('''
                SELECT * FROM outbox WHERE project_id=? ORDER BY id DESC LIMIT 30
            ''', (project_id,))]
            runs = [dict(row) for row in db.execute(
                "SELECT * FROM module_runs WHERE project_id=? ORDER BY id DESC LIMIT 30", (project_id,))]
        finally:
            db.rollback()
        return jsonify(project=project, actors=actors, stages=STAGES, modules=modules,
                       transitions=transitions, events=events, outbox=outbox, module_runs=runs,
                       pending_transition=next((t for t in transitions if t["status"] == "requested"), None))

    @app.post("/api/projects/<int:project_id>/transitions")
    def request_approval(project_id):
        data, db = body(), database()
        with transaction(db):
            result = request_transition(db, project_id, data)
        dispatch_outbox(db)
        return jsonify(result), 201

    @app.post("/api/projects/<int:project_id>/transitions/<int:transition_id>/decision")
    def decide_approval(project_id, transition_id):
        data, db = body(), database()
        with transaction(db):
            result = decide_transition(db, project_id, transition_id, data)
        dispatch_outbox(db)
        return jsonify(result)

    @app.post("/api/projects/<int:project_id>/modules/<key>/run")
    def run_module(project_id, key):
        data, db = body(), database()
        module = app.config["MODULES"].get(key)
        if module is None:
            raise WorkflowError("모듈을 찾을 수 없습니다.", 404)
        with transaction(db):
            result = execute_module(db, project_id, module, data.get("actor"))
        dispatch_outbox(db)
        return jsonify(result), 500 if result["status"] == "failed" else 200

    return app
