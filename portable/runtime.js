/* 한 파일로 여는 IBCM의 브라우저 SQLite 저장소와 업무 처리 통로입니다. */
(() => {
  "use strict";

  const config = window.IBCM_PORTABLE;
  const storageKey = "ibcm.portable.db.v1";
  const lockName = "ibcm.portable.db.v1.access";
  const roles = {
    executive: ["executive", "총괄 임원"],
    sales: ["sales_owner", "영업"],
    delivery: ["delivery_owner", "수행"],
    pmo: ["pmo_owner", "관리"]
  };
  const adapters = Object.fromEntries(["slack", "notion", "email"].map((name) => [name, {
    handle: (event) => `${name} 어댑터가 ${event.type} 이벤트를 받았음`
  }]));
  let SQL;
  let database;
  let storedBase64;
  let readyPromise;
  let requestQueue = Promise.resolve();

  class AppError extends Error {
    constructor(message, status = 400) {
      super(message);
      this.status = status;
    }
  }

  function decode(value) {
    const binary = atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    return bytes;
  }

  function encode(bytes) {
    const parts = [];
    for (let index = 0; index < bytes.length; index += 32768) {
      parts.push(String.fromCharCode(...bytes.subarray(index, index + 32768)));
    }
    return btoa(parts.join(""));
  }

  function storageError() {
    return new AppError("이 브라우저에 데이터를 저장할 수 없습니다. 변경 내용은 저장되지 않았습니다. 일반 창에서 파일을 열고 브라우저의 저장 공간 허용 설정을 확인해 주세요.", 507);
  }

  function readStored() {
    try {
      return window.localStorage.getItem(storageKey);
    } catch {
      throw storageError();
    }
  }

  function writeStored(value) {
    try {
      window.localStorage.setItem(storageKey, value);
    } catch {
      throw storageError();
    }
  }

  function probeStorage() {
    const probeKey = `${storageKey}.probe.${Date.now()}.${Math.random()}`;
    try {
      window.localStorage.setItem(probeKey, "저장 확인");
      if (window.localStorage.getItem(probeKey) !== "저장 확인") throw new Error();
      window.localStorage.removeItem(probeKey);
    } catch {
      throw storageError();
    }
  }

  function openDatabase(bytes) {
    const opened = new SQL.Database(bytes);
    try {
      opened.run("PRAGMA foreign_keys = ON");
      opened.exec("SELECT id,current_stage FROM projects LIMIT 1");
      opened.exec("SELECT id FROM stage_transitions LIMIT 1");
      opened.exec("SELECT key FROM module_registry LIMIT 1");
      opened.exec("SELECT id FROM module_runs LIMIT 1");
      opened.exec("SELECT id FROM events LIMIT 1");
      opened.exec("SELECT id FROM outbox LIMIT 1");
      return { opened, changed: migrateDatabase(opened) };
    } catch (error) {
      opened.close();
      throw error;
    }
  }

  function replaceDatabase(bytes) {
    const next = openDatabase(bytes);
    if (database) database.close();
    database = next.opened;
    return next.changed;
  }

  function migrateDatabase(opened) {
    let changed = false;
    opened.run("BEGIN IMMEDIATE");
    try {
      const additions = {
        module_registry: { skill: "TEXT" },
        events: { actor: "TEXT NOT NULL DEFAULT '시스템'" },
        outbox: { project_id: "INTEGER REFERENCES projects(id)", event_type: "TEXT", log: "TEXT" }
      };
      for (const [table, fields] of Object.entries(additions)) {
        const columns = rowsFrom(opened, `PRAGMA table_info(${table})`).map((column) => column.name);
        for (const [field, definition] of Object.entries(fields)) {
          if (!columns.includes(field)) {
            opened.run(`ALTER TABLE ${table} ADD COLUMN ${field} ${definition}`);
            changed = true;
          }
        }
      }
      const update = (sql, values = []) => {
        opened.run(sql, values);
        changed = changed || opened.getRowsModified() > 0;
      };
      update(`UPDATE events SET actor=COALESCE(
        NULLIF(TRIM(json_extract(payload,'$.decided_by')),''),
        NULLIF(TRIM(json_extract(payload,'$.requested_by')),''),
        NULLIF(TRIM(json_extract(payload,'$.executed_by')),''),'시스템')
        WHERE actor IS NULL OR TRIM(actor)='' OR (actor='시스템' AND (
          json_extract(payload,'$.decided_by') IS NOT NULL OR
          json_extract(payload,'$.requested_by') IS NOT NULL OR
          json_extract(payload,'$.executed_by') IS NOT NULL))`);
      update(`UPDATE outbox SET project_id=(SELECT project_id FROM events WHERE id=outbox.event_id)
        WHERE project_id IS NULL`);
      update(`UPDATE outbox SET event_type=(SELECT type FROM events WHERE id=outbox.event_id)
        WHERE event_type IS NULL OR event_type=''`);
      update(`UPDATE outbox SET log=CASE status
        WHEN 'sent' THEN adapter || ' 어댑터가 ' || event_type || ' 이벤트를 받았음'
        WHEN 'failed' THEN COALESCE(last_error,'어댑터 처리에 실패했습니다')
        ELSE '전송 대기 중' END WHERE log IS NULL OR log=''`);
      // 새 모듈을 추가해도 기존 브라우저의 프로젝트와 실행 기록을 그대로 보존합니다.
      for (const module of config.modules) {
        update(`INSERT INTO module_registry
          (key,name,category,stage,"order",main_role,status,description,skill) VALUES(?,?,?,?,?,?,?,?,?)
          ON CONFLICT(key) DO UPDATE SET name=excluded.name,category=excluded.category,stage=excluded.stage,
          "order"=excluded."order",main_role=excluded.main_role,status=excluded.status,
          description=excluded.description,skill=excluded.skill
          WHERE name IS NOT excluded.name OR category IS NOT excluded.category OR stage IS NOT excluded.stage
            OR "order" IS NOT excluded."order" OR main_role IS NOT excluded.main_role
            OR status IS NOT excluded.status OR description IS NOT excluded.description OR skill IS NOT excluded.skill`,
        [module.key, module.name, module.category, module.stage, module.order, module.mainRole,
          module.status, module.description, module.skill ?? null]);
      }
      opened.run("COMMIT");
      return changed;
    } catch (error) {
      opened.run("ROLLBACK");
      throw error;
    }
  }

  function exportDatabase() {
    try {
      return database.export();
    } finally {
      // sql.js는 내보내기 과정에서 연결을 다시 열므로 외래 키 검사를 복구합니다.
      database.run("PRAGMA foreign_keys = ON");
    }
  }

  async function initialize() {
    if (!config || typeof window.initSqlJs !== "function") {
      throw new AppError("앱 파일이 완전하지 않습니다. 파일을 다시 내려받아 열어 주세요.", 500);
    }
    probeStorage();
    try {
      SQL = await window.initSqlJs({ wasmBinary: decode(config.wasmBase64) });
    } catch {
      throw new AppError("이 브라우저에서 앱을 시작할 수 없습니다. 최신 크롬 또는 사파리로 파일을 열어 주세요.", 500);
    }
    const saved = readStored();
    let migrated;
    try {
      migrated = replaceDatabase(decode(saved === null ? config.databaseBase64 : saved));
    } catch {
      throw new AppError(saved === null
        ? "앱의 초기 데이터를 읽을 수 없습니다. 파일을 다시 내려받아 열어 주세요."
        : "브라우저에 저장된 데이터를 읽을 수 없습니다. 기존 데이터는 덮어쓰지 않았습니다.", 500);
    }
    storedBase64 = saved;
    if (saved === null || migrated) persistMigration(saved);
  }

  function persistMigration(expectedStored) {
    const nextStored = encode(exportDatabase());
    if (readStored() !== expectedStored) {
      throw new AppError("다른 창에서 데이터가 변경되었습니다. 화면을 다시 확인하고 한 번 더 실행해 주세요.", 409);
    }
    writeStored(nextStored);
    storedBase64 = nextStored;
  }

  function refreshDatabase() {
    const saved = readStored();
    if (saved === storedBase64) return;
    if (saved === null) {
      throw new AppError("브라우저의 저장 데이터가 삭제되었습니다. 화면을 새로고침한 뒤 다시 시작해 주세요.", 409);
    }
    let migrated;
    try {
      migrated = replaceDatabase(decode(saved));
    } catch {
      throw new AppError("브라우저에 저장된 데이터를 읽을 수 없습니다. 기존 데이터는 덮어쓰지 않았습니다.", 500);
    }
    if (migrated) persistMigration(saved);
    else storedBase64 = saved;
  }

  function rows(sql, values = []) {
    return rowsFrom(database, sql, values);
  }

  function rowsFrom(source, sql, values = []) {
    const statement = source.prepare(sql);
    try {
      statement.bind(values);
      const found = [];
      while (statement.step()) found.push(statement.getAsObject());
      return found;
    } finally {
      statement.free();
    }
  }

  function execute(sql, values = []) {
    const statement = database.prepare(sql);
    try {
      statement.bind(values);
      statement.step();
    } finally {
      statement.free();
    }
  }

  function insert(sql, values) {
    execute(sql, values);
    return rows("SELECT last_insert_rowid() AS id")[0].id;
  }

  function now() {
    return new Date().toISOString();
  }

  function projectFor(id) {
    const project = rows("SELECT * FROM projects WHERE id=?", [id])[0];
    if (!project) throw new AppError("프로젝트를 찾을 수 없습니다.", 404);
    return project;
  }

  function actorsFor(project) {
    return Object.entries(roles).map(([role, [field, label]]) => ({ role, name: project[field], label }));
  }

  function actorFor(project, role) {
    if (typeof role !== "string" || !Object.hasOwn(roles, role)) {
      throw new AppError("행동할 담당자를 선택해 주세요.");
    }
    return actorsFor(project).find((actor) => actor.role === role);
  }

  function emit(projectId, type, payload) {
    const timestamp = now();
    const actor = [payload.decided_by, payload.requested_by, payload.executed_by]
      .find((value) => typeof value === "string" && value.trim()) || "시스템";
    const eventId = insert("INSERT INTO events(project_id,type,payload,actor,created_at) VALUES(?,?,?,?,?)",
      [projectId, type, JSON.stringify(payload), actor, timestamp]);
    for (const adapter of config.routes[type] || []) {
      execute(`INSERT INTO outbox(event_id,project_id,adapter,event_type,status,log,created_at)
        VALUES(?,?,?,?,'pending','전송 대기 중',?)`, [eventId, projectId, adapter, type, timestamp]);
    }
    return eventId;
  }

  function dispatchOutbox() {
    const pending = rows(`SELECT o.id AS outbox_id,o.adapter,e.id,e.project_id,e.type,e.payload,e.actor,e.created_at
      FROM outbox o JOIN events e ON e.id=o.event_id
      WHERE o.status IN ('pending','failed') AND o.attempts < 3 ORDER BY o.id`);
    for (const item of pending) {
      const event = { id: item.id, project_id: item.project_id, type: item.type,
        payload: JSON.parse(item.payload), actor: item.actor, created_at: item.created_at };
      item.log = adapters[item.adapter].handle(event);
      execute("UPDATE outbox SET status='sent',attempts=attempts+1,last_error=NULL,log=?,sent_at=? WHERE id=?",
        [item.log, now(), item.outbox_id]);
    }
    return pending;
  }

  function mutate(action) {
    probeStorage();
    const previous = exportDatabase();
    const expectedStored = storedBase64;
    let result;
    let dispatched;
    try {
      execute("BEGIN IMMEDIATE");
      result = action();
      dispatched = dispatchOutbox();
      execute("COMMIT");
      const nextStored = encode(exportDatabase());
      if (readStored() !== expectedStored) {
        throw new AppError("다른 창에서 데이터가 변경되었습니다. 화면을 다시 확인하고 한 번 더 실행해 주세요.", 409);
      }
      writeStored(nextStored);
      storedBase64 = nextStored;
    } catch (error) {
      // 저장 실패도 성공으로 표시하지 않도록 메모리의 SQLite까지 이전 상태로 돌립니다.
      replaceDatabase(previous);
      throw error;
    }
    for (const item of dispatched) {
      console.info(item.log);
    }
    return result;
  }

  function projectDetail(projectId) {
    const project = projectFor(projectId);
    const transitions = rows("SELECT * FROM stage_transitions WHERE project_id=? ORDER BY id DESC", [projectId]);
    const events = rows("SELECT * FROM events WHERE project_id=? ORDER BY id DESC LIMIT 30", [projectId]);
    for (const event of events) event.payload = JSON.parse(event.payload);
    return {
      project,
      actors: actorsFor(project),
      stages: config.stages.map((stage) => Array.isArray(stage) ? { key: stage[0], name: stage[1] } : stage),
      modules: config.modules,
      transitions,
      events,
      outbox: rows(`SELECT o.*,e.type AS event_type FROM outbox o JOIN events e ON e.id=o.event_id
        WHERE e.project_id=? ORDER BY o.id DESC LIMIT 30`, [projectId]),
      module_runs: rows("SELECT * FROM module_runs WHERE project_id=? ORDER BY id DESC LIMIT 30", [projectId]),
      pending_transition: transitions.find((transition) => transition.status === "requested") || null
    };
  }

  function requestTransition(projectId, data) {
    const project = projectFor(projectId);
    const actor = actorFor(project, data.actor);
    const current = project.current_stage;
    if (current === "E") throw new AppError("검수와 종료는 마지막 단계입니다.");
    const next = String.fromCharCode(current.charCodeAt(0) + 1);
    if (data.to_stage !== next) throw new AppError("바로 다음 단계로만 승인 요청을 할 수 있습니다.");
    if (rows("SELECT 1 FROM stage_transitions WHERE project_id=? AND status='requested'", [projectId]).length) {
      throw new AppError("이미 승인 대기 중인 요청이 있습니다.", 409);
    }
    const transitionId = insert(`INSERT INTO stage_transitions(project_id,from_stage,to_stage,status,requested_by,requested_at)
      VALUES(?,?,?,'requested',?,?)`, [projectId, current, next, actor.name, now()]);
    emit(projectId, "stage.approval_requested", {
      transition_id: transitionId, from_stage: current, to_stage: next, requested_by: actor.name
    });
    return { message: "총괄 임원에게 단계 승인을 요청했습니다.", transition_id: transitionId };
  }

  function decideTransition(projectId, transitionId, data) {
    const project = projectFor(projectId);
    const actor = actorFor(project, data.actor);
    if (actor.role !== "executive") throw new AppError("승인과 거절은 총괄 임원만 할 수 있습니다.", 403);
    const transition = rows("SELECT * FROM stage_transitions WHERE id=? AND project_id=?", [transitionId, projectId])[0];
    if (!transition) throw new AppError("승인 요청을 찾을 수 없습니다.", 404);
    if (transition.status !== "requested" || project.current_stage !== transition.from_stage) {
      throw new AppError("이미 처리되었거나 현재 단계와 맞지 않는 요청입니다.", 409);
    }
    const decision = data.decision;
    if (decision !== "approved" && decision !== "rejected") throw new AppError("승인 또는 거절을 선택해 주세요.");
    let reason = Object.hasOwn(data, "reason") ? data.reason : "";
    if (typeof reason !== "string") throw new AppError("사유는 글로 입력해 주세요.");
    reason = reason.trim();
    if (decision === "rejected" && !reason) throw new AppError("거절 사유를 입력해 주세요.");
    if (Array.from(reason).length > 2000) throw new AppError("사유는 2,000자 이내로 입력해 주세요.");
    const timestamp = now();
    execute("UPDATE stage_transitions SET status=?,decided_by=?,decided_at=?,reason=? WHERE id=?",
      [decision, actor.name, timestamp, reason || null, transitionId]);
    if (decision === "approved") {
      execute("UPDATE projects SET current_stage=?,updated_at=? WHERE id=?", [transition.to_stage, timestamp, projectId]);
    }
    emit(projectId, `stage.${decision}`, {
      transition_id: transitionId, from_stage: transition.from_stage, to_stage: transition.to_stage,
      decided_by: actor.name, reason
    });
    return { message: decision === "approved"
      ? "승인하여 다음 단계로 이동했습니다."
      : "요청을 거절했습니다. 현재 단계가 유지됩니다." };
  }

  function runModule(projectId, key, data) {
    const module = config.modules.find((entry) => entry.key === key);
    if (!module) throw new AppError("모듈을 찾을 수 없습니다.", 404);
    const project = projectFor(projectId);
    const actor = actorFor(project, data.actor);
    if (module.category === "stage_task" && module.stage !== project.current_stage) {
      throw new AppError("현재 단계의 업무 카드만 실행할 수 있습니다.", 409);
    }
    if (module.status !== "planned") {
      throw new AppError("이 모듈의 실제 실행에는 서버가 필요합니다. 한 파일 체험판에서는 준비 중 모듈의 확인 기록만 남길 수 있습니다.", 501);
    }
    const started = now();
    const runId = insert(`INSERT INTO module_runs(project_id,module_key,started_at,status,executed_by)
      VALUES(?,?,?,'running',?)`, [projectId, module.key, started, actor.name]);
    const summary = "준비 중인 모듈입니다. 실행 없이 확인 기록만 남겼습니다.";
    execute("UPDATE module_runs SET finished_at=?,status='skipped',result_summary=?,artifact_id=NULL WHERE id=?",
      [now(), summary, runId]);
    emit(projectId, "module.executed", {
      run_id: runId, module_key: module.key, status: "skipped", executed_by: actor.name, artifact_ids: []
    });
    return { message: summary, run_id: runId, status: "skipped", artifact_ids: [] };
  }

  function response(data, status = 200) {
    return new Response(JSON.stringify(data), {
      status, headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" }
    });
  }

  async function requestBody(input, options) {
    const headers = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
    const contentType = (headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase();
    if (contentType !== "application/json" && !/^application\/[^\s]+\+json$/.test(contentType)) {
      throw new AppError("JSON 형식으로 요청해 주세요.", 415);
    }
    const raw = options.body !== undefined ? options.body : input instanceof Request ? await input.clone().text() : "";
    if (typeof raw !== "string") throw new AppError("요청 내용을 확인해 주세요.");
    if (new TextEncoder().encode(raw).length > 64 * 1024) throw new AppError("요청 내용이 너무 큽니다.", 413);
    let data;
    try {
      data = JSON.parse(raw);
    } catch {
      throw new AppError("요청 내용을 확인해 주세요.");
    }
    if (data === null || typeof data !== "object" || Array.isArray(data)) {
      throw new AppError("요청 내용은 JSON 객체여야 합니다.");
    }
    return data;
  }

  async function handleFetch(input, options = {}) {
    try {
      const url = new URL(input instanceof Request ? input.url : String(input), window.location.href);
      const method = String(options.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
      const path = url.pathname;
      const detail = path.match(/^\/api\/projects\/(\d+)$/);
      const transition = path.match(/^\/api\/projects\/(\d+)\/transitions$/);
      const decision = path.match(/^\/api\/projects\/(\d+)\/transitions\/(\d+)\/decision$/);
      const moduleRun = path.match(/^\/api\/projects\/(\d+)\/modules\/([^/]+)\/run$/);
      if (path !== "/api/projects" && !detail && !transition && !decision && !moduleRun) {
        return response({ error: "요청한 항목을 찾을 수 없습니다." }, 404);
      }
      const readOnly = path === "/api/projects" || Boolean(detail);
      if (method !== (readOnly ? "GET" : "POST")) {
        return response({ error: "지원하지 않는 요청 방식입니다." }, 405);
      }
      const data = readOnly ? null : await requestBody(input, options);
      if (!readyPromise) {
        readyPromise = initialize().catch((error) => {
          readyPromise = undefined;
          throw error;
        });
      }
      await readyPromise;
      refreshDatabase();
      if (path === "/api/projects") return response({ projects: rows("SELECT * FROM projects ORDER BY id") });
      if (detail) return response(projectDetail(Number(detail[1])));
      if (transition) return response(mutate(() => requestTransition(Number(transition[1]), data)), 201);
      if (decision) return response(mutate(() => decideTransition(Number(decision[1]), Number(decision[2]), data)));
      return response(mutate(() => runModule(Number(moduleRun[1]), decodeURIComponent(moduleRun[2]), data)));
    } catch (error) {
      if (error instanceof AppError) return response({ error: error.message }, error.status);
      return response({ error: "데이터를 처리하지 못했습니다. 화면을 새로고침한 뒤 다시 시도해 주세요." }, 500);
    }
  }

  // 같은 화면을 브라우저의 SQLite에 연결하며 네트워크 요청은 보내지 않습니다.
  function request(input, options) {
    const run = () => {
      // 로컬 파일에서는 브라우저에 따라 창 간 잠금 권한이 거부될 수 있습니다.
      if (window.location.protocol !== "file:" && navigator.locks && typeof navigator.locks.request === "function") {
        return navigator.locks.request(lockName, { mode: "exclusive" }, () => handleFetch(input, options));
      }
      return handleFetch(input, options);
    };
    const pending = requestQueue.then(run, run);
    requestQueue = pending.then(() => undefined, () => undefined);
    return pending;
  }

  window.IBCM_STORE = { mode: "static", request };
})();
