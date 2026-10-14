"use strict";

const state = { projects: [], detail: null, viewedStage: null, actor: "sales", busy: false, loadSequence: 0, toastTimer: null };
const $ = (selector) => document.querySelector(selector);
const store = window.IBCM_STORE;
const roleLabels = { executive: "총괄 임원", sales: "영업", delivery: "수행", pmo: "관리" };
const stageDescriptions = {
  A: "고객의 니즈와 사업 기회를 살피고, 다음 제안을 준비합니다.",
  B: "고객에게 전할 제안과 견적을 준비하고, 사업의 범위를 구체화합니다.",
  C: "합의한 내용을 계약으로 연결하고, 함께 일할 준비를 마칩니다.",
  D: "계획에 맞춰 프로젝트를 수행하고, 진행 상황과 변화를 기록합니다.",
  E: "산출물을 검수하고 인수인계를 마친 뒤, 프로젝트를 정리합니다."
};
const stageRoles = { A: "영업 주도", B: "영업 주도", C: "영업과 수행", D: "수행 주도", E: "수행과 관리" };
const stagePurposes = { A: "사업의 가능성을 발견합니다", B: "고객에게 해답을 제안합니다", C: "약속을 실행 계획으로 잇습니다", D: "계획을 성과로 만듭니다", E: "결과를 전달하고 다음을 엽니다" };
const eventLabels = {
  "project.created": "프로젝트를 만들었습니다",
  "stage.approval_requested": "다음 단계 승인을 요청했습니다",
  "stage.approved": "단계 전환이 승인되었습니다",
  "stage.rejected": "단계 전환이 거절되었습니다",
  "module.executed": "모듈 이용 기록을 남겼습니다",
  "artifact.created": "산출물을 등록했습니다"
};
const icons = {
  check: '<path d="m5 12 4 4L19 6"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7h.01"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  person: '<circle cx="12" cy="7" r="3"/><path d="M5 21v-2a7 7 0 0 1 14 0v2"/>',
  minutes: '<rect x="8" y="3" width="8" height="12" rx="4"/><path d="M5 10v1a7 7 0 0 0 14 0v-1M12 18v3m-3 0h6"/>',
  people: '<circle cx="9" cy="8" r="3"/><path d="M3 21v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6m2 4a5 5 0 0 1 3 4v2"/>',
  list: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h4"/>',
  folder: '<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Zm0 1h18"/>',
  chart: '<path d="M4 3v18h17M8 16v-5m5 5V7m5 9v-8"/>',
  history: '<path d="M3 11a9 9 0 1 1 2 7M3 4v7h7M12 7v5l3 2"/>',
  warning: '<circle cx="12" cy="12" r="9"/><path d="M12 7v6m0 4h.01"/>'
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function icon(name, extraClass = "") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.7");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", `icon ${extraClass}`.trim());
  // Only constant SVG markup from this file is used here.
  svg.innerHTML = icons[name] || icons.list;
  return svg;
}

async function api(path, options = {}) {
  let response;
  try {
    response = await store.request(path, { ...options, headers: { "Content-Type": "application/json", ...options.headers } });
  } catch {
    throw new Error(store.mode === "static" ? "앱을 불러올 수 없습니다. 화면을 다시 열어 주세요." : "서버에 연결할 수 없습니다. 서버가 실행 중인지 확인한 뒤 다시 시도해 주세요.");
  }
  let body;
  try { body = await response.json(); } catch { throw new Error("서버의 응답을 읽을 수 없습니다. 잠시 뒤 다시 시도해 주세요."); }
  if (!response.ok) throw new Error(body.error || body.message || "요청을 처리하지 못했습니다. 다시 시도해 주세요.");
  return body;
}

function notify(message, isError = false) {
  window.clearTimeout(state.toastTimer);
  const toast = element("div", `toast${isError ? " error" : ""}`);
  toast.append(icon(isError ? "warning" : "check"), element("span", "", message));
  $("#toast-region").replaceChildren(toast);
  state.toastTimer = window.setTimeout(() => $("#toast-region").replaceChildren(), isError ? 6500 : 4500);
}

function setBusy(busy) {
  state.busy = busy;
  $("#project-select").disabled = busy;
  $("#actor-select").disabled = busy;
  document.querySelectorAll("[data-module-key]").forEach((button) => { button.disabled = busy || button.dataset.preview === "true"; });
  document.querySelectorAll("[data-stage-target]").forEach((button) => { button.disabled = busy; });
  $("#return-current-stage").disabled = busy;
  $("#reject-submit").disabled = busy;
  $("#reject-cancel").disabled = busy;
  if (state.detail) renderGate();
}

async function loadProject(id, initial = false) {
  const sequence = ++state.loadSequence;
  $("#error-state").hidden = true;
  if (initial) {
    $("#loading-state").hidden = false;
    $("#project-content").hidden = true;
  }
  const detail = await api(`/api/projects/${encodeURIComponent(id)}`);
  if (sequence !== state.loadSequence) return;
  if (!state.detail || state.detail.project.id !== detail.project.id || state.detail.project.current_stage !== detail.project.current_stage) {
    state.viewedStage = detail.project.current_stage;
  }
  state.detail = detail;
  render();
  $("#project-content").hidden = false;
  $("#loading-state").hidden = true;
}

function render() {
  const { project, actors } = state.detail;
  $("#project-select").value = String(project.id);
  $("#actor-select").replaceChildren(...actors.map((actor) => {
    const option = element("option", "", `${actor.label || roleLabels[actor.role]}  ${actor.name}`);
    option.value = actor.role;
    return option;
  }));
  if (!actors.some((actor) => actor.role === state.actor)) state.actor = "sales";
  $("#actor-select").value = state.actor;
  $("#project-code").textContent = project.code;
  $("#project-title").textContent = project.title;
  $("#customer-name").textContent = project.customer_name;
  $("#project-status-copy").textContent = `${project.current_stage} 단계 ${state.detail.pending_transition ? "승인 대기" : "진행 중"}`;
  document.title = `${project.title} | IBMS`;
  $("#project-people").replaceChildren(...actors.map((actor) => {
    const person = element("div", `person ${actor.role}`);
    const avatar = element("span", "person-avatar", String(actor.name).slice(0, 1));
    avatar.setAttribute("aria-hidden", "true");
    const copy = element("div", "person-copy");
    copy.append(element("span", "person-label", actor.label || roleLabels[actor.role]), element("span", "person-name", actor.name));
    person.append(avatar, copy);
    return person;
  }));
  renderStages();
  renderGate();
  renderModules();
  renderActivity();
}

function renderStages() {
  const { project, stages, modules } = state.detail;
  const current = stages.findIndex((stage) => stage.key === project.current_stage);
  $("#stage-progress").textContent = `현재 진행: ${project.current_stage} ${stages[current].name}`;
  $("#stage-flow").replaceChildren(...stages.map((stage, index) => {
    const viewed = stage.key === state.viewedStage;
    const tone = index < 2 ? "sales" : index === 2 ? "handoff" : "delivery";
    const item = element("li", `stage-item stage-${tone}${index < current ? " complete" : index === current ? " current" : ""}${viewed ? " viewing" : ""}`);
    item.dataset.stage = stage.key;
    if (index === current) item.setAttribute("aria-current", "step");
    const button = element("button", "stage-button");
    button.type = "button";
    button.dataset.stageTarget = stage.key;
    button.disabled = state.busy;
    button.setAttribute("aria-pressed", String(viewed));
    button.setAttribute("aria-controls", "task-grid");
    button.setAttribute("aria-label", `${stage.key} ${stage.name} 업무 보기${index === current ? ", 현재 진행 단계" : ""}`);
    const circle = element("span", "stage-circle");
    circle.setAttribute("aria-hidden", "true");
    circle.textContent = stage.key;
    const head = element("span", "stage-card-head");
    head.append(circle, element("span", "stage-view-label", index === current ? "현재 진행" : viewed ? "미리보기" : index < current ? "완료" : "예정"));
    const count = modules.filter((module) => module.category === "stage_task" && module.stage === stage.key).length;
    const footer = element("span", "stage-card-footer");
    const browse = element("span", "stage-browse-label", viewed ? "보고 있는 단계" : "업무 보기");
    browse.append(icon("arrow"));
    footer.append(element("span", "stage-task-count", `업무 ${count}개`), browse);
    button.append(head, element("span", "stage-name", stage.name), element("span", "stage-purpose", stagePurposes[stage.key]), element("span", "stage-role", stageRoles[stage.key] || ""), footer);
    button.addEventListener("click", () => selectStage(stage.key));
    item.append(button);
    return item;
  }));
  requestAnimationFrame(revealViewedStage);
}

function revealViewedStage() {
  const flow = $("#stage-flow");
  const selected = flow.querySelector(".viewing");
  if (flow.scrollWidth > flow.clientWidth && selected) {
    flow.scrollLeft = Math.max(0, selected.offsetLeft - (flow.clientWidth - selected.offsetWidth) / 2);
  }
}

function selectStage(key) {
  if (state.busy || !state.detail.stages.some((stage) => stage.key === key)) return;
  state.viewedStage = key;
  renderStages();
  renderModules();
  document.querySelector(`[data-stage-target="${key}"]`).focus({ preventScroll: true });
}

function actionButton(id, label, className, handler, iconName) {
  const button = element("button", `button ${className}`, label);
  button.id = id;
  button.type = "button";
  button.disabled = state.busy;
  if (iconName) button.append(icon(iconName));
  button.addEventListener("click", handler);
  return button;
}

function renderGate() {
  const { project, pending_transition: pending, stages } = state.detail;
  const index = stages.findIndex((stage) => stage.key === project.current_stage);
  const next = stages[index + 1];
  const description = $("#gate-description");
  const actions = $("#gate-actions");
  description.replaceChildren();
  actions.replaceChildren();
  description.classList.toggle("pending", Boolean(pending));
  description.closest(".gate-bar").classList.toggle("pending", Boolean(pending));
  if (pending) {
    const target = stages.find((stage) => stage.key === pending.to_stage);
    const copy = element("span", "gate-copy");
    copy.append(element("strong", "gate-route", `${pending.from_stage} → ${pending.to_stage} ${target ? target.name : ""}`), element("span", "gate-help", "총괄 임원의 승인을 기다리고 있습니다."));
    description.append(icon("clock"), copy);
    if (state.actor === "executive") {
      actions.append(actionButton("reject-transition", "거절", "button-secondary", openRejection), actionButton("approve-transition", "승인", "button-primary", approveTransition, "check"));
    } else {
      actions.append(element("span", "gate-pending-tag", "승인 대기 중"));
    }
  } else if (!next) {
    description.append(icon("check"), element("span", "", "마지막 단계입니다. 검수와 종료에 필요한 업무를 확인해 주세요."));
    actions.append(element("span", "gate-complete", "마지막 단계 진행 중"));
  } else {
    const copy = element("span", "gate-copy");
    copy.append(element("strong", "gate-route", `${project.current_stage} → ${next.key} ${next.name}`), element("span", "gate-help", "업무를 마쳤다면 다음 단계 승인을 요청하세요."));
    description.append(icon("info"), copy);
    actions.append(actionButton("request-transition", state.busy ? "처리 중" : "다음 단계 승인 요청", "button-primary", requestTransition, "arrow"));
  }
}

function renderModules() {
  const { project, stages, modules } = state.detail;
  const viewed = stages.find((stage) => stage.key === state.viewedStage);
  const actual = stages.find((stage) => stage.key === project.current_stage);
  const preview = state.viewedStage !== project.current_stage;
  const taskModules = modules.filter((module) => module.category === "stage_task" && module.stage === state.viewedStage).sort((a, b) => a.order - b.order);
  const commonModules = modules.filter((module) => module.category === "common").sort((a, b) => a.order - b.order);
  $("#current-stage-letter").textContent = state.viewedStage;
  $("#tasks-heading").textContent = viewed.name;
  $("#task-count").textContent = `${taskModules.length}`;
  $("#task-count").setAttribute("aria-label", `업무 모듈 ${taskModules.length}개`);
  $("#tasks-description").textContent = stageDescriptions[state.viewedStage] || "";
  $("#stage-preview-note").hidden = !preview;
  $("#stage-preview-copy").textContent = `${viewed.name} 단계의 업무를 살펴보고 있습니다. 현재 진행 단계는 ${actual.key} ${actual.name}입니다. 이곳의 업무 카드는 미리보기로 표시됩니다.`;
  $("#task-action-note").hidden = preview;
  const roles = [...new Set(taskModules.map((module) => module.mainRole || module.main_role || "unassigned"))];
  roles.sort((a, b) => ["sales", "delivery", "pmo"].indexOf(a) - ["sales", "delivery", "pmo"].indexOf(b));
  $("#task-grid").dataset.roleCount = String(roles.length);
  $("#task-grid").dataset.wide = String(roles.some((role) => taskModules.filter((module) => (module.mainRole || module.main_role || "unassigned") === role).length >= 3));
  $("#task-grid").replaceChildren(...roles.map((role) => {
    const owned = taskModules.filter((module) => (module.mainRole || module.main_role || "unassigned") === role);
    const owner = state.detail.actors.find((actor) => actor.role === role);
    const lane = element("section", `role-lane ${role}`);
    lane.dataset.size = owned.length >= 3 ? "wide" : "compact";
    lane.setAttribute("aria-label", `${roleLabels[role] || "담당 미정"} 업무`);
    const heading = element("div", "lane-heading");
    const name = element("h3", "lane-title", roleLabels[role] || "담당 미정");
    name.prepend(element("span", "lane-dot"));
    name.append(element("span", "lane-count", String(owned.length)));
    heading.append(name, element("span", "lane-owner", owner ? owner.name : ""));
    const cards = element("div", "lane-cards");
    cards.append(...owned.map((module) => moduleCard(module, false)));
    lane.append(heading, cards);
    return lane;
  }));
  $("#common-count").textContent = `공통 모듈 ${commonModules.length}개`;
  $("#common-grid").replaceChildren(...commonModules.map((module) => moduleCard(module, true)));
}

function moduleCard(module, common) {
  const role = module.mainRole || module.main_role;
  const isMinutes = module.key === "minutes";
  const card = element("button", `module-card${common ? " common-card" : ""}${role ? ` ${role}` : ""}${isMinutes ? " minutes" : ""}`);
  card.type = "button";
  card.dataset.moduleKey = module.key;
  const preview = !common && module.stage !== state.detail.project.current_stage;
  card.dataset.preview = String(preview);
  card.disabled = state.busy || preview;
  if (preview) card.setAttribute("aria-describedby", "stage-preview-copy");
  const status = module.render && module.render.label ? module.render.label : { planned: "준비 중", ready: "사용 가능", active: "사용 중" }[module.status] || "준비 중";
  card.setAttribute("aria-label", `${module.name}, ${role ? `${roleLabels[role]}, ` : "공통 모듈, "}${status}`);
  const top = element("div", "card-top");
  if (common) {
    const symbol = element("span", "module-symbol");
    const commonIcons = ["minutes", "people", "list", "folder", "chart", "history"];
    symbol.append(icon(isMinutes ? "minutes" : commonIcons[(module.order - 1) % commonIcons.length] || "list"));
    top.append(symbol);
  } else {
    top.append(element("span", "card-number", String(module.order).padStart(2, "0")));
  }
  top.append(element("span", "planned-tag", status));
  const description = module.status !== "planned" && module.render && module.render.description ? module.render.description : module.description;
  card.append(top, element("span", "card-title", module.name), element("span", "card-description", description));
  if (module.skill) card.append(element("span", "skill-tag", `연결 예정: ${module.skill}`));
  if (!common) {
    const footer = element("div", "card-footer");
    const roleBadge = element("span", `role-badge ${role || ""}`);
    roleBadge.append(icon("person"), document.createTextNode(roleLabels[role] || "담당 미정"));
    const action = element("span", preview ? "card-preview-label" : "card-action", preview ? "미리보기" : module.status === "planned" ? "준비 상태 보기" : "실행하기");
    if (!preview) action.append(icon("arrow", "card-arrow"));
    footer.append(roleBadge, action);
    card.append(footer);
  }
  card.addEventListener("click", () => runModule(module));
  return card;
}

function dateLabel(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(date);
}

function newest(records) {
  return [...records].sort((a, b) => Number(b.id) - Number(a.id));
}

function renderActivity() {
  const events = newest(state.detail.events || []);
  const outbox = newest(state.detail.outbox || []);
  const list = $("#event-list");
  list.replaceChildren(...events.slice(0, 5).map((event) => {
    const row = element("li", "event-row");
    const kind = event.type === "stage.approved" ? "approved" : event.type === "stage.rejected" ? "rejected" : event.type === "stage.approval_requested" ? "requested" : event.type === "module.executed" ? "module" : "";
    const copy = element("span", "event-copy");
    copy.append(element("span", "event-name", eventLabels[event.type] || "프로젝트 상태가 변경되었습니다"), element("code", "event-type", event.type));
    const time = element("time", "event-time", dateLabel(event.created_at));
    if (event.created_at) time.dateTime = event.created_at;
    row.append(element("span", `event-dot ${kind}`), copy, time);
    return row;
  }));
  if (!events.length) list.append(element("li", "empty-note", "프로젝트에서 일어나는 변화가 이곳에 기록됩니다."));
  const statuses = { sent: "전송 완료", pending: "대기", failed: "실패" };
  $("#outbox-summary").replaceChildren(...Object.entries(statuses).map(([status, label]) => {
    const count = outbox.filter((entry) => entry.status === status).length;
    return element("span", `summary-item ${status}${count ? " has-records" : ""}`, `${label} ${count}`);
  }));
  const adapters = { slack: "슬랙", notion: "노션", email: "이메일" };
  $("#outbox-list").replaceChildren(...Object.entries(adapters).map(([adapter, name]) => {
    const latest = outbox.find((entry) => entry.adapter === adapter);
    const status = latest ? latest.status : "pending";
    const row = element("li", "outbox-row");
    row.append(element("span", `adapter-status ${status}`), element("span", "", `${name} ${latest ? statuses[status] || "확인 중" : "기록 없음"}`));
    if (latest && latest.last_error) row.title = latest.last_error;
    return row;
  }));
}

async function mutate(path, body, successMessage, afterSuccess) {
  if (state.busy) return;
  const projectId = state.detail.project.id;
  setBusy(true);
  try {
    const response = await api(path, { method: "POST", body: JSON.stringify({ actor: state.actor, ...body }) });
    if (afterSuccess) afterSuccess();
    await loadProject(projectId);
    notify(successMessage || response.message || "처리했습니다.");
  } catch (error) {
    notify(error.message, true);
  } finally {
    setBusy(false);
  }
}

function requestTransition() {
  if (state.busy || state.detail.pending_transition) return;
  const { project, stages } = state.detail;
  const next = stages[stages.findIndex((stage) => stage.key === project.current_stage) + 1];
  if (!next) return;
  mutate(`/api/projects/${project.id}/transitions`, { to_stage: next.key }, "다음 단계 승인을 요청했습니다. 총괄 임원의 승인을 기다려 주세요.");
}

function approveTransition() {
  const pending = state.detail.pending_transition;
  if (!pending || state.actor !== "executive") return;
  mutate(`/api/projects/${state.detail.project.id}/transitions/${pending.id}/decision`, { decision: "approved" }, "단계 전환을 승인했습니다. 다음 단계의 업무를 확인해 주세요.");
}

function openRejection() {
  if (state.busy || !state.detail.pending_transition || state.actor !== "executive") return;
  $("#reject-reason").value = "";
  $("#reject-reason").removeAttribute("aria-invalid");
  $("#reject-error").textContent = "";
  $("#reject-dialog").showModal();
  $("#reject-reason").focus();
}

function runModule(module) {
  if (module.category === "stage_task" && module.stage !== state.detail.project.current_stage) return;
  mutate(`/api/projects/${state.detail.project.id}/modules/${encodeURIComponent(module.key)}/run`, {}, module.status === "planned" ? `${module.name} 모듈은 준비 중입니다. 이용 기록을 남겼습니다.` : `${module.name} 모듈을 실행했습니다.`);
}

async function boot() {
  $("#mode-label").textContent = store.mode === "static" ? "정적 모드, 이 브라우저에만 저장됨" : "서버 모드";
  $("#mode-notice").hidden = store.mode !== "static";
  $("#loading-state").hidden = false;
  $("#error-state").hidden = true;
  $("#project-content").hidden = true;
  $("#project-select").disabled = true;
  $("#actor-select").disabled = true;
  try {
    const response = await api("/api/projects");
    state.projects = response.projects;
    if (!state.projects.length) throw new Error("등록된 프로젝트가 없습니다. 시드 데이터가 준비되었는지 확인해 주세요.");
    $("#project-select").replaceChildren(...state.projects.map((project) => {
      const option = element("option", "", project.title);
      option.value = String(project.id);
      return option;
    }));
    await loadProject(state.projects[0].id, true);
    setBusy(false);
  } catch (error) {
    $("#loading-state").hidden = true;
    $("#error-state").hidden = false;
    $("#error-message").textContent = error.message;
  }
}

$("#project-select").addEventListener("change", async (event) => {
  if (state.busy) return;
  const previous = state.detail.project.id;
  setBusy(true);
  try { await loadProject(event.target.value); }
  catch (error) { $("#project-select").value = String(previous); notify(error.message, true); }
  finally { setBusy(false); }
});
$("#actor-select").addEventListener("change", (event) => {
  state.actor = event.target.value;
  try { localStorage.setItem("ibcm.actor", state.actor); } catch { /* A stored role is optional. */ }
  renderGate();
});
$("#retry-button").addEventListener("click", boot);
$("#return-current-stage").addEventListener("click", () => selectStage(state.detail.project.current_stage));
window.addEventListener("resize", () => requestAnimationFrame(revealViewedStage));
$("#reject-cancel").addEventListener("click", () => $("#reject-dialog").close());
$("#reject-dialog").addEventListener("cancel", (event) => { if (state.busy) event.preventDefault(); });
$("#reject-reason").addEventListener("input", () => {
  if ($("#reject-reason").value.trim()) {
    $("#reject-reason").removeAttribute("aria-invalid");
    $("#reject-error").textContent = "";
  }
});
$("#reject-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (state.busy) return;
  const reason = $("#reject-reason").value.trim();
  if (!reason) {
    $("#reject-error").textContent = "거절 사유를 입력해 주세요.";
    $("#reject-reason").setAttribute("aria-invalid", "true");
    $("#reject-reason").focus();
    return;
  }
  const pending = state.detail.pending_transition;
  if (!pending || state.actor !== "executive") return;
  mutate(`/api/projects/${state.detail.project.id}/transitions/${pending.id}/decision`, { decision: "rejected", reason }, "단계 전환을 거절하고 사유를 남겼습니다.", () => $("#reject-dialog").close());
});

try {
  const stored = localStorage.getItem("ibcm.actor");
  if (Object.hasOwn(roleLabels, stored)) state.actor = stored;
} catch { /* The screen also works without local storage. */ }
boot();
