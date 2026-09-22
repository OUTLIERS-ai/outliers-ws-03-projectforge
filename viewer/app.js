/* ProjectForge viewer: plain JavaScript, no dependencies, fully local, no AI.
   Create projects and cards, edit, comment, tag, drag between columns.
   Your moves are sent under your own name (config "human"); the board
   refuses moves from anyone who is not you or the orchestrator. */

const STATUS_LABEL = {
  backlog: "Backlog", ready: "Ready", in_progress: "In Progress",
  blocked: "Blocked", review: "Review",
  awaiting_you: "Awaiting You", done: "Done",
  tracking: "Tracking",
};

let STATE = null;
let activeDept = "all";
let openTask = null; // task id of the open dossier, to refresh in place
let viewMode = "board";
let searchQ = "";

function HUMAN() { return (STATE && STATE.config && STATE.config.human) || "you"; }

async function api(path, body) {
  const r = await fetch(path, { method: "POST", body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok || j.error) toast(j.error || ("error " + r.status));
  return j;
}

function toast(msg) {
  let el = document.getElementById("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 6000);
}

function crmLink(rel) {
  if (!rel) return "";
  const vault = (STATE.config.crm_vault || "").replace(/[\/]+$/, "");
  const full = vault ? vault + "/" + rel : rel;
  return `<div class="crm-link">CRM person: <a href="obsidian://open?path=${
    encodeURIComponent(full)}">${esc(rel)}</a></div>`;
}

async function load() {
  STATE = await (await fetch("/api/state")).json();
  renderHeader();
  renderView();
  renderEvents();
  renderAlerts();
}

function setAlertsPanel(open) {
  localStorage.setItem("pf-alerts-open", open ? "1" : "0");
  document.getElementById("alerts-panel").classList.toggle("hidden", !open);
  document.getElementById("alerts-reopen").classList.toggle("hidden", open);
}

function wireAlertsPanel() {
  const closeBtn = document.getElementById("alerts-close");
  const reopenBtn = document.getElementById("alerts-reopen");
  if (closeBtn && !closeBtn.dataset.wired) {
    closeBtn.dataset.wired = "1";
    closeBtn.onclick = () => setAlertsPanel(false);
    reopenBtn.onclick = () => setAlertsPanel(true);
    // restore last state (default: CLOSED — open only if explicitly reopened)
    setAlertsPanel(localStorage.getItem("pf-alerts-open") === "1");
  }
}

async function renderAlerts() {
  wireAlertsPanel();
  const alerts = await (await fetch("/api/alerts")).json();
  document.getElementById("stat-alerts").textContent = alerts.length;
  document.getElementById("alerts-reopen-count").textContent =
    alerts.length ? `(${alerts.length})` : "";
  const box = document.getElementById("alerts");
  box.innerHTML = alerts.length ? "" :
    `<div class="dimtext">All clear.</div>`;
  for (const a of alerts) {
    const el = document.createElement("div");
    el.className = `alert-item ${a.level}`;
    el.innerHTML = `
      <div class="al-body">
        <span class="al-kind">${esc(a.kind)}</span> ${esc(a.message)}
        <div class="ts">${esc(a.created)}</div>
      </div>
      <button class="al-x" title="Dismiss">×</button>`;
    if (a.task_id && a.task_id.indexOf("lane:") !== 0)
      el.querySelector(".al-body").onclick = () => openDetail(a.task_id);
    el.querySelector(".al-x").onclick = async e => {
      e.stopPropagation();
      await api("/api/alert/dismiss", { id: a.id, actor: HUMAN() });
      renderAlerts();
    };
    box.appendChild(el);
  }
}
function renderView() {
  if (viewMode === "agents") renderAgents();
  else if (viewMode === "queue") renderQueue();
  else renderBoard();
}

/* ---------- helpers ---------- */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function projOf(id) { return STATE.projects.find(p => p.id === id); }
function deptColor(deptId) {
  const d = STATE.config.departments.find(d => d.id === deptId);
  return d ? d.color : "#8a90a3";
}
function tagsOf(t) { try { return JSON.parse(t.tags || "[]"); } catch { return []; } }
function confBadge(t) {
  const m = /confidence=(\d+)/.exec(t.context_ref || "");
  if (!m) return "";
  const n = +m[1];
  const band = n >= 70 ? "hi" : n >= 55 ? "mid" : "lo";
  return `<div class="conf ${band}" title="forecast confidence">
    <span class="conf-bar"><span style="width:${n}%"></span></span>
    <span class="conf-n">${n}%</span></div>`;
}
function agentList() {
  const set = new Set(STATE.config.departments.map(d => d.lead).filter(Boolean));
  (STATE.config.agents || []).forEach(a => set.add(a));
  set.add(HUMAN());
  STATE.tasks.forEach(t => t.assignee_agent && set.add(t.assignee_agent));
  return [...set].sort();
}
function allTags() {
  const set = new Set();
  STATE.tasks.forEach(t => tagsOf(t).forEach(x => set.add(x)));
  return [...set].sort();
}
function ts2date(ts) { return new Date(String(ts).replace(" ", "T")); }
function checklistOf(t) {
  try { return JSON.parse(t.checklist || "[]"); } catch { return []; }
}
function dueClass(due, status) {
  if (!due || status === "done") return "";
  const days = (ts2date(due + " 23:59:59") - Date.now()) / 864e5;
  if (days < 0) return "over";
  if (days <= 2) return "soon";
  return "ok";
}
function matches(t) {
  if (t.archived) return false;
  const proj = projOf(t.project_id) || {};
  if (activeDept !== "all" && proj.department !== activeDept) return false;
  if (!searchQ) return true;
  const hay = [t.title, t.assignee_agent, proj.title,
    ...tagsOf(t)].join(" ").toLowerCase();
  return searchQ.toLowerCase().split(/\s+/).every(w => hay.includes(w));
}
function ago(ts) {
  const d = (Date.now() - ts2date(ts)) / 864e5;
  if (d < 1 / 24) return "just now";
  if (d < 1) return `${Math.round(d * 24)}h ago`;
  return `${Math.floor(d)}d ago`;
}
function evText(ev) {
  const d = JSON.parse(ev.detail || "{}");
  switch (ev.action) {
    case "moved": return `<b>${esc(ev.actor)}</b> moved ${esc(d.from)} → ${esc(d.to)}`;
    case "handoff": return `<b>${esc(d.from)}</b> handed to <b>${esc(d.to)}</b> — ${esc(d.summary || "")}`;
    case "created": return `<b>${esc(ev.actor)}</b> created this`;
    case "comment": return `<b>${esc(ev.actor)}</b>: ${esc(d.text || "")}`;
    case "tagged": return `<b>${esc(ev.actor)}</b> set tags: ${esc((d.tags || []).join(", ") || "none")}`;
    case "pass": return `<b>${esc(ev.actor)}</b> logged a pass (${esc(d.result)}) — ${esc(d.summary || "")}`;
    case "updated": return `<b>${esc(ev.actor)}</b> edited ${esc((d.fields || []).join(", "))}`;
    default: return `<b>${esc(ev.actor)}</b> ${esc(ev.action)}`;
  }
}

/* ---------- header ---------- */
function renderHeader() {
  document.getElementById("workspace").textContent = STATE.config.workspace;
  const open = STATE.tasks.filter(
    t => t.status !== "done" && t.status !== "tracking");
  document.getElementById("stat-projects").textContent =
    STATE.projects.filter(p => p.status === "active").length;
  document.getElementById("stat-open").textContent = open.length;
  document.getElementById("stat-waiting").textContent =
    open.filter(t => t.status === "awaiting_you").length;

  const pills = document.getElementById("dept-pills");
  pills.innerHTML = "";
  const mk = (id, name, color) => {
    const el = document.createElement("div");
    el.className = "pill" + (activeDept === id ? " active" : "");
    el.style.setProperty("--pc", color);
    el.textContent = name;
    el.onclick = () => { activeDept = id; renderHeader(); renderBoard(); };
    pills.appendChild(el);
  };
  mk("all", "All", "#ff3c00");
  STATE.config.departments.forEach(d => mk(d.id, d.name, d.color));

  const np = document.createElement("div");
  np.className = "pill new";
  np.textContent = "+ Project";
  np.onclick = openNewProject;
  pills.appendChild(np);
}

/* ---------- board ---------- */
function renderBoard() {
  const board = document.getElementById("board");
  board.innerHTML = "";

  for (const status of STATE.statuses) {
    const col = document.createElement("div");
    col.className = "col";
    col.dataset.status = status;

    const tasks = STATE.tasks.filter(t => t.status === status && matches(t));

    col.innerHTML = `<div class="col-head"><h3>${STATUS_LABEL[status]}</h3>
      <span class="count">${tasks.length}</span></div>`;

    const zone = document.createElement("div");
    zone.className = "col-cards";
    zone.ondragover = e => { e.preventDefault(); zone.classList.add("drag-over"); };
    zone.ondragleave = () => zone.classList.remove("drag-over");
    zone.ondrop = async e => {
      e.preventDefault();
      zone.classList.remove("drag-over");
      await api("/api/task/move", {
        task_id: e.dataTransfer.getData("text/plain"),
        status, actor: HUMAN(),
      });
      load();
    };

    for (const t of tasks) zone.appendChild(cardEl(t));
    col.appendChild(zone);

    // + add card footer
    const add = document.createElement("div");
    add.className = "add-card";
    add.textContent = "+ Add card";
    add.onclick = () => addCardForm(add, status);
    col.appendChild(add);
    board.appendChild(col);
  }
}

function cardEl(t) {
  const proj = projOf(t.project_id) || {};
  const card = document.createElement("div");
  card.className = "card";
  card.draggable = true;
  card.style.setProperty("--dc", deptColor(proj.department));
  const tags = tagsOf(t);
  const cl = checklistOf(t);
  const clDone = cl.filter(i => i.done).length;
  const dc = dueClass(t.due, t.status);
  card.innerHTML = `
    <div class="title">${t.priority !== "normal" && t.priority ?
      `<span class="prio p-${esc(t.priority)}" title="${esc(t.priority)}"></span>` : ""}${esc(t.title)}</div>
    ${t.status === "in_progress" ? `<div class="working" title="dispatched to an agent">
      <span class="wdot"></span>${esc(t.assignee_agent || "agent")} working…</div>` : ""}
    ${tags.length ? `<div class="card-tags">${tags.slice(0, 4).map(x =>
      `<span class="chip mini">${esc(x)}</span>`).join("")}${
      tags.length > 4 ? `<span class="chip mini">+${tags.length - 4}</span>` : ""}</div>` : ""}
    ${confBadge(t)}
    ${(t.due || cl.length) ? `<div class="card-meta">
      ${t.due ? `<span class="due ${dc}">${dc === "over" ? "⚠ " : ""}${esc(t.due)}</span>` : ""}
      ${cl.length ? `<span class="cl-progress">
        <span class="cl-count">${clDone}/${cl.length}</span>
        <span class="bar"><span class="fill" style="width:${
          Math.round(100 * clDone / cl.length)}%"></span></span></span>` : ""}
    </div>` : ""}
    <div class="proj" title="Edit project">${esc(proj.title || "")}</div>
    <div class="foot">
      <span class="agent ${t.assignee_agent ? "" : "none"}">
        ${esc(t.assignee_agent || "unassigned")}</span>
      <span class="src">${t.pass_count ? `⟳${t.pass_count} · ` : ""}${esc(ago(t.updated))}</span>
    </div>`;
  card.ondragstart = e => {
    e.dataTransfer.setData("text/plain", t.id);
    card.classList.add("dragging");
  };
  card.ondragend = () => card.classList.remove("dragging");
  card.onclick = () => openDetail(t.id);
  const projLine = card.querySelector(".proj");
  if (projLine && proj.id) projLine.onclick = e => {
    e.stopPropagation();
    openProject(proj.id);
  };
  return card;
}

function addCardForm(anchor, status) {
  if (anchor.querySelector("form")) return;
  const projs = STATE.projects.filter(p => p.status === "active" &&
    (activeDept === "all" || p.department === activeDept));
  anchor.innerHTML = "";
  const f = document.createElement("form");
  f.innerHTML = `
    <input name="title" placeholder="Card title…" autocomplete="off" required>
    <select name="project">${projs.map(p =>
      `<option value="${esc(p.id)}">${esc(p.title)}</option>`).join("")}</select>
    <div class="form-row">
      <button type="submit">Add</button>
      <button type="button" class="ghost" data-x>Cancel</button>
    </div>`;
  f.onsubmit = async e => {
    e.preventDefault();
    await api("/api/task/add", {
      project_id: f.project.value, title: f.title.value.trim(),
      status, actor: HUMAN(),
    });
    load();
  };
  f.querySelector("[data-x]").onclick = e => { e.stopPropagation(); load(); };
  anchor.onclick = null;
  anchor.appendChild(f);
  f.title.focus();
}

function openNewProject() {
  const body = document.getElementById("modal-body");
  body.innerHTML = `
    <h2>New project</h2>
    <form id="np-form" class="stack">
      <label>Title <input name="title" required autocomplete="off"></label>
      <label>Department <select name="department">${
        STATE.config.departments.map(d =>
          `<option value="${esc(d.id)}">${esc(d.name)}</option>`).join("")
      }</select></label>
      <label>Summary <textarea name="summary" rows="3"></textarea></label>
      <div class="form-row"><button type="submit">Create</button></div>
    </form>`;
  document.getElementById("np-form").onsubmit = async e => {
    e.preventDefault();
    const f = e.target;
    await api("/api/project/add", {
      title: f.title.value.trim(), department: f.department.value,
      summary: f.summary.value.trim(), actor: HUMAN(),
    });
    closeModal();
    load();
  };
  showModal();
}

/* ---------- project editor ---------- */
function openProject(projectId) {
  const p = projOf(projectId);
  if (!p) return;
  const pTasks = STATE.tasks.filter(t => t.project_id === p.id && !t.archived);
  const openT = pTasks.filter(t => t.status !== "done");
  const archived = STATE.tasks.filter(t =>
    t.project_id === p.id && t.archived).length;
  const body = document.getElementById("modal-body");
  body.innerHTML = `
    <input id="p-title" class="title-edit" value="${esc(p.title)}">
    <div class="mono">${esc(p.id)} · via ${esc(p.source_app)} ·
      ${openT.length} open / ${pTasks.length} cards${
      archived ? ` · ${archived} archived` : ""}</div>
    <div class="grid2">
      <label>Department
        <select id="p-dept">${STATE.config.departments.map(d =>
          `<option value="${esc(d.id)}" ${d.id === p.department ? "selected" : ""}>
           ${esc(d.name)}</option>`).join("")}</select>
      </label>
      <label>Status
        <select id="p-status">${["active", "paused", "done", "archived"].map(s =>
          `<option value="${s}" ${s === p.status ? "selected" : ""}>${s}</option>`).join("")}
        </select>
      </label>
    </div>
    <h4>Summary</h4>
    <textarea id="p-summary" rows="3">${esc(p.summary)}</textarea>
    <div class="form-row"><button id="p-save">Save changes</button>
      <span id="p-saved" class="saved"></span></div>
    <h4>Cards</h4>
    <div class="proj-tasks">${pTasks.length ? pTasks.map(t => `
      <div class="proj-task" data-id="${esc(t.id)}">
        <span class="badge-lane">${STATUS_LABEL[t.status]}</span>
        <span class="pt-title">${esc(t.title)}</span>
        <span class="agent ${t.assignee_agent ? "" : "none"}">
          ${esc(t.assignee_agent || "—")}</span>
      </div>`).join("") : `<div class="dimtext">No cards yet.</div>`}</div>`;
  document.getElementById("p-save").onclick = async () => {
    await api("/api/project/update", {
      project_id: p.id, actor: HUMAN(),
      title: document.getElementById("p-title").value.trim(),
      department: document.getElementById("p-dept").value,
      status: document.getElementById("p-status").value,
      summary: document.getElementById("p-summary").value.trim(),
    });
    document.getElementById("p-saved").textContent = "saved ✓";
    await load();
    setTimeout(() => openProject(p.id), 300);
  };
  document.querySelectorAll(".proj-task").forEach(el =>
    el.onclick = () => openDetail(el.dataset.id));
  showModal();
}

/* ---------- agents view ---------- */
async function renderAgents() {
  const ag = await (await fetch("/api/agents")).json();
  const board = document.getElementById("board");
  board.innerHTML = "";
  const names = Object.keys(ag).sort((a, b) =>
    ag[b].open.length - ag[a].open.length || a.localeCompare(b));
  if (!names.length) {
    board.innerHTML = `<div class="dimtext" style="padding:30px">
      No agent activity yet.</div>`;
    return;
  }
  for (const name of names) {
    const info = ag[name];
    const col = document.createElement("div");
    col.className = "col agent-col";
    col.innerHTML = `
      <div class="col-head">
        <h3>${esc(name)}</h3>
        <span class="count">${info.open.length}</span>
      </div>
      <div class="agent-meta">
        ${info.results.length ? `<div class="streak" title="recent pass results, newest first">
          ${info.results.map(r => `<span class="s-dot r-${esc(r)}"></span>`).join("")}
        </div>` : ""}
        ${info.last_pass ? `<div class="lastpass">
          <span class="badge r-${esc(info.last_pass.result)}">${esc(info.last_pass.result)}</span>
          <span class="ts">${esc(ago(info.last_pass.ts))}</span>
          <div class="lp-sum">${esc(info.last_pass.summary)}</div>
          <div class="lp-task">on: ${esc(info.last_pass.task_title || info.last_pass.task_id)}</div>
        </div>` : `<div class="dimtext">No passes logged yet.</div>`}
      </div>
      <div class="col-cards"></div>`;
    const zone = col.querySelector(".col-cards");
    for (const o of info.open) {
      const mini = document.createElement("div");
      mini.className = "card mini-card";
      const dc = dueClass(o.due, o.status);
      mini.innerHTML = `
        <div class="title">${o.priority !== "normal" && o.priority ?
          `<span class="prio p-${esc(o.priority)}"></span>` : ""}${esc(o.title)}</div>
        <div class="foot">
          <span class="src">${esc(STATUS_LABEL[o.status] || o.status)}</span>
          ${o.due ? `<span class="due ${dc}">${esc(o.due)}</span>` : ""}
        </div>`;
      mini.onclick = () => openDetail(o.id);
      zone.appendChild(mini);
    }
    board.appendChild(col);
  }
}

/* ---------- orchestrator dispatch queue (Layer 5, read-only) ---------- */
async function renderQueue() {
  const board = document.getElementById("board");
  board.innerHTML = "";
  const q = await (await fetch("/api/next?limit=25")).json();
  const w = q.wip || {};
  const cap = w.cap ? `/${w.cap}` : "";

  const wrap = document.createElement("div");
  wrap.className = "queue-wrap";
  wrap.innerHTML = `
    <div class="queue-head">
      <div>
        <h2 class="q-title">Dispatch queue</h2>
        <div class="q-sub">ranked ready cards an owner agent can start now
          — priority → due → age</div>
      </div>
      <div class="q-wip ${w.at_cap ? "at-cap" : ""}">
        <div class="q-wip-num">${w.in_progress ?? "–"}${cap}</div>
        <label>in progress${w.at_cap ? " · AT CAP" : ""}</label>
      </div>
      <div class="q-wip">
        <div class="q-wip-num">${q.ready_count ?? 0}</div>
        <label>ready</label>
      </div>
    </div>
    <div class="queue-list"></div>`;
  const list = wrap.querySelector(".queue-list");

  if (!q.next || !q.next.length) {
    list.innerHTML = `<div class="dimtext" style="padding:24px">
      Nothing ready to dispatch. Cards move to <b>Ready</b> when queued for an
      agent.</div>`;
  }
  let rank = 0;
  for (const n of (q.next || [])) {
    rank++;
    const flag = n.dispatchable
      ? `<span class="q-flag go">▶ dispatchable</span>`
      : `<span class="q-flag hold">⏸ ${esc(
          n.hold_reason === "wip_cap" ? "WIP at cap" :
          n.hold_reason === "no_owner" ? "needs an owner" :
          n.hold_reason === "yours" ? "yours - not for an agent" :
          n.hold_reason === "out_of_scope" ? "outside its departments" :
          n.hold_reason === "cap_exhausted" ? "daily limit reached" : "hold")}</span>`;
    const dc = dueClass(n.due, "ready");
    const item = document.createElement("div");
    item.className = "q-item" + (n.dispatchable ? " is-go" : "");
    item.style.setProperty("--dc", deptColor(n.department));
    item.innerHTML = `
      <div class="q-rank">${rank}</div>
      <div class="q-main">
        <div class="q-line">
          ${n.priority && n.priority !== "normal"
            ? `<span class="prio p-${esc(n.priority)}"></span>` : ""}
          <span class="q-name">${esc(n.title)}</span>
        </div>
        <div class="q-meta">
          <span class="proj">${esc(n.project || "—")}</span>
          ${n.due ? `<span class="due ${dc}">${esc(n.due)}</span>` : ""}
          ${n.source_app && n.source_app !== "manual"
            ? `<span class="src">via ${esc(n.source_app)}</span>` : ""}
        </div>
      </div>
      <div class="q-right">
        <span class="agent ${n.assignee_agent ? "" : "none"}">${
          esc(n.assignee_agent || "no owner")}</span>
        ${flag}
      </div>`;
    item.onclick = () => openDetail(n.task_id);
    list.appendChild(item);
  }
  board.appendChild(wrap);
}

/* ---------- activity feed ---------- */
async function renderEvents() {
  const events = await (await fetch("/api/events")).json();
  const box = document.getElementById("events");
  box.innerHTML = "";
  for (const ev of events) {
    const el = document.createElement("div");
    el.className = "ev";
    el.innerHTML = `<div class="dot ${ev.action}"></div>
      <div class="body">${evText(ev)}<div class="ts">${esc(ev.ts)}</div></div>`;
    box.appendChild(el);
  }
}

/* ---------- dossier modal ---------- */
async function openDetail(taskId) {
  openTask = taskId;
  const d = await (await fetch("/api/task/" + taskId)).json();
  const t = d.task, proj = d.project || {};
  const tags = tagsOf(t);
  const events = d.events; // oldest first

  /* health flags — spot what could be going wrong */
  const flags = [];
  const idleDays = (Date.now() - ts2date(t.updated)) / 864e5;
  if (t.status !== "done" && idleDays >= 5)
    flags.push(`Stale — no activity for ${Math.floor(idleDays)} days`);
  if (t.status === "blocked") flags.push("Blocked — needs unblocking");
  if (!t.assignee_agent && ["ready", "in_progress", "review"].includes(t.status))
    flags.push("In an active lane with no agent assigned");
  let backMoves = 0;
  for (const ev of events.filter(e => e.action === "moved")) {
    const det = JSON.parse(ev.detail || "{}");
    if (STATE.statuses.indexOf(det.to) < STATE.statuses.indexOf(det.from)) backMoves++;
  }
  if (backMoves)
    flags.push(`Moved backwards ${backMoves}× — possible rework loop`);

  /* agent track — origination → every handoff → current owner */
  const created = events.find(e => e.action === "created");
  const track = [{
    agent: created ? created.actor : "?", note: "originated",
    ts: created ? created.ts : t.created,
  }];
  for (const h of d.handoffs)
    track.push({ agent: h.to_agent, note: h.summary, ts: h.ts, ctx: h.context });
  if (t.assignee_agent && track[track.length - 1].agent !== t.assignee_agent)
    track.push({ agent: t.assignee_agent, note: "current owner", ts: t.updated });

  /* time in current lane */
  const lastMove = [...events].reverse().find(e => e.action === "moved");
  const laneSince = lastMove ? lastMove.ts : t.created;

  const comments = events.filter(e => e.action === "comment");

  const body = document.getElementById("modal-body");
  body.innerHTML = `
    <input id="d-title" class="title-edit" value="${esc(t.title)}">
    <div class="mono">${esc(t.id)} · ${STATUS_LABEL[t.status]} ·
      ${esc(proj.title || "?")} · in lane ${esc(ago(laneSince))}</div>

    ${crmLink(t.crm_person)}
    ${flags.length ? `<div class="flagbox">${flags.map(f =>
      `<div>⚠ ${esc(f)}</div>`).join("")}</div>` : ""}

    <div class="grid2">
      <label>Agent
        <input id="d-agent" value="${esc(t.assignee_agent)}" list="agents"
          placeholder="unassigned">
        <datalist id="agents">${agentList().map(a =>
          `<option value="${esc(a)}">`).join("")}</datalist>
      </label>
      <label>Context ref
        <input id="d-ctx" value="${esc(t.context_ref)}"
          placeholder="path / url / inbox entry">
      </label>
      <label>CRM person note
        <input id="d-crm" value="${esc(t.crm_person || "")}"
          placeholder="People/Name.md (inside your CRM vault)">
      </label>
      <label>Due date
        <input id="d-due" type="date" value="${esc(t.due || "")}">
      </label>
      <label>Priority
        <select id="d-prio">${["low", "normal", "high", "urgent"].map(p =>
          `<option value="${p}" ${p === (t.priority || "normal") ? "selected" : ""}>${p}</option>`).join("")}
        </select>
      </label>
      <label>Project
        <select id="d-proj">${STATE.projects.filter(p =>
          p.status !== "archived" || p.id === t.project_id).map(p =>
          `<option value="${esc(p.id)}" ${p.id === t.project_id ? "selected" : ""}>
           ${esc(p.title)}</option>`).join("")}</select>
      </label>
      <label>Lane
        <select id="d-lane">${STATE.statuses.map(s =>
          `<option value="${s}" ${s === t.status ? "selected" : ""}>${STATUS_LABEL[s]}</option>`).join("")}
        </select>
      </label>
    </div>

    <h4>Tags</h4>
    <div class="chips" id="d-chips">
      ${tags.map(x => `<span class="chip">${esc(x)}
        <button data-tag="${esc(x)}">×</button></span>`).join("")}
      <input id="d-newtag" list="taglist" placeholder="+ tag, Enter">
      <datalist id="taglist">${allTags().map(x =>
        `<option value="${esc(x)}">`).join("")}</datalist>
    </div>

    <h4>Notes</h4>
    <textarea id="d-notes" rows="4"
      placeholder="What this card is about, decisions, anything worth keeping…">${esc(t.notes)}</textarea>
    <div class="form-row"><button id="d-save">Save changes</button>
      <button id="d-archive" class="ghost danger">
        ${t.archived ? "Restore" : "Archive"}</button>
      <span id="d-saved" class="saved"></span></div>

    <h4>Checklist${(() => {
      const cl = checklistOf(t);
      return cl.length ? ` — ${cl.filter(i => i.done).length}/${cl.length}` : "";
    })()}</h4>
    <div class="checklist" id="d-checklist">
      ${checklistOf(t).map((i, n) => `
        <div class="check-item">
          <input type="checkbox" data-n="${n}" ${i.done ? "checked" : ""}>
          <span class="${i.done ? "done" : ""}">${esc(i.text)}</span>
          <button class="rm" data-rm="${n}">×</button>
        </div>`).join("")}
      <input id="d-newcheck" placeholder="+ checklist item, Enter">
    </div>

    <h4>Work reports — what each agent did</h4>
    <div class="passes">${d.passes.length ? d.passes.map(p => {
      let outs = []; try { outs = JSON.parse(p.outputs || "[]"); } catch {}
      return `<div class="pass">
        <div class="pass-head">
          <span class="agent">${esc(p.agent)}</span>
          <span class="badge r-${esc(p.result)}">${esc(p.result)}</span>
          <span class="ts">${esc(p.ts)}</span>
        </div>
        <div class="pass-sum">${esc(p.summary)}</div>
        ${outs.length ? `<div class="pass-outs">${outs.map(o =>
          `<code>${esc(o)}</code>`).join("")}</div>` : ""}
        ${p.next_step ? `<div class="pass-next">→ next: ${esc(p.next_step)}</div>` : ""}
      </div>`;
    }).join("") : `<div class="dimtext">No work reports yet. Agents log one
      per piece of work: what was done, files made, result, what's next.</div>`}</div>

    <h4>Handovers — 5 fields each</h4>
    <div class="handovers">${d.handoffs.length ? d.handoffs.map(h => `
      <div class="handover">
        <div class="ho-head"><span class="agent">${esc(h.from_agent)}</span> →
          <span class="agent">${esc(h.to_agent)}</span>
          <span class="ts">${esc(h.ts)}</span></div>
        <dl>
          <dt>Done</dt><dd>${esc(h.done)}</dd>
          <dt>Decisions</dt><dd>${esc(h.decisions)}</dd>
          <dt>Where it stands</dt><dd>${esc(h.state)}</dd>
          <dt>Do first</dt><dd>${esc(h.next_first)}</dd>
          <dt>Warnings</dt><dd>${esc(h.warnings)}</dd>
        </dl>
      </div>`).join("") : `<div class="dimtext">No handovers yet. A handover
      is refused unless it says what was done, the decisions and why, where
      it stands, what to do first, and any warnings.</div>`}</div>

    <h4>Agent track</h4>
    <div class="track">${track.map((s, i) => `
      <div class="hop">
        ${i ? `<div class="arrow">↓</div>` : ""}
        <div class="hop-body">
          <span class="agent">${esc(s.agent || "—")}</span>
          <span class="hop-note">${esc(s.note || "")}</span>
          <span class="ts">${esc(s.ts)}</span>
          ${s.ctx ? `<div class="hop-ctx">${esc(s.ctx)}</div>` : ""}
        </div>
      </div>`).join("")}</div>

    <h4>Comments</h4>
    <div class="comments">${comments.length ? comments.map(c => {
      const det = JSON.parse(c.detail || "{}");
      return `<div class="comment"><b>${esc(c.actor)}</b>
        <span class="ts">${esc(c.ts)}</span>
        <div>${esc(det.text || "")}</div></div>`;
    }).join("") : `<div class="dimtext">No comments yet.</div>`}</div>
    <div class="comment-box">
      <textarea id="d-comment" rows="2" placeholder="Write a comment…"></textarea>
      <button id="d-comment-btn">Comment</button>
    </div>

    <h4>Timeline</h4>
    <div class="timeline">${events.map(ev =>
      `<div class="tl"><span class="ts">${esc(ev.ts)}</span>
       <span>${evText(ev)}</span></div>`).join("")}</div>`;

  /* wiring */
  document.getElementById("d-save").onclick = async () => {
    await api("/api/task/update", {
      task_id: t.id, actor: HUMAN(),
      title: document.getElementById("d-title").value.trim(),
      assignee_agent: document.getElementById("d-agent").value.trim(),
      context_ref: document.getElementById("d-ctx").value.trim(),
      crm_person: document.getElementById("d-crm").value.trim(),
      notes: document.getElementById("d-notes").value,
      due: document.getElementById("d-due").value,
      priority: document.getElementById("d-prio").value,
      project_id: document.getElementById("d-proj").value,
    });
    const lane = document.getElementById("d-lane").value;
    if (lane !== t.status)
      await api("/api/task/move", { task_id: t.id, status: lane, actor: HUMAN() });
    document.getElementById("d-saved").textContent = "saved ✓";
    setTimeout(() => openDetail(t.id), 350);
    load();
  };
  document.getElementById("d-archive").onclick = async () => {
    await api("/api/task/archive", {
      task_id: t.id, archived: !t.archived, actor: HUMAN() });
    closeModal();
    load();
  };
  /* checklist wiring */
  const clItems = checklistOf(t);
  const saveChecklist = async items => {
    await api("/api/task/checklist", { task_id: t.id, items, actor: HUMAN() });
    openDetail(t.id);
    load();
  };
  document.querySelectorAll("#d-checklist input[type=checkbox]").forEach(cb =>
    cb.onchange = () => {
      clItems[+cb.dataset.n].done = cb.checked;
      saveChecklist(clItems);
    });
  document.querySelectorAll("#d-checklist .rm").forEach(b =>
    b.onclick = () => saveChecklist(
      clItems.filter((_, n) => n !== +b.dataset.rm)));
  const newCheck = document.getElementById("d-newcheck");
  newCheck.onkeydown = e => {
    if (e.key === "Enter" && newCheck.value.trim())
      saveChecklist([...clItems, { text: newCheck.value.trim(), done: false }]);
  };
  const setTags = async next => {
    await api("/api/task/tags", { task_id: t.id, tags: next, actor: HUMAN() });
    openDetail(t.id);
    load();
  };
  document.querySelectorAll("#d-chips .chip button").forEach(b =>
    b.onclick = () => setTags(tags.filter(x => x !== b.dataset.tag)));
  const newtag = document.getElementById("d-newtag");
  newtag.onkeydown = e => {
    if (e.key === "Enter" && newtag.value.trim())
      setTags([...tags, newtag.value.trim()]);
  };
  document.getElementById("d-comment-btn").onclick = async () => {
    const text = document.getElementById("d-comment").value.trim();
    if (!text) return;
    await api("/api/task/comment", { task_id: t.id, text, actor: HUMAN() });
    openDetail(t.id);
    load();
  };
  showModal();
}

/* ---------- modal plumbing ---------- */
function showModal() {
  document.getElementById("modal-backdrop").classList.remove("hidden");
}
function closeModal() {
  openTask = null;
  document.getElementById("modal-backdrop").classList.add("hidden");
}
document.getElementById("modal-close").onclick = closeModal;
document.getElementById("modal-backdrop").onclick = e => {
  if (e.target.id === "modal-backdrop") closeModal();
};
document.addEventListener("keydown", e => {
  if (e.key === "Escape") closeModal();
});

/* ---------- header controls ---------- */
const searchBox = document.getElementById("search");
searchBox.oninput = () => { searchQ = searchBox.value.trim(); renderView(); };
document.querySelectorAll(".toggle button").forEach(b =>
  b.onclick = () => {
    viewMode = b.dataset.v;
    document.querySelectorAll(".toggle button").forEach(x =>
      x.classList.toggle("active", x === b));
    renderView();
  });

/* ---------- theme switcher (persisted) ---------- */
const THEMES = ["command-deck", "synthwave", "terminal", "paper", "minimal"];
function applyTheme(t) {
  if (!THEMES.includes(t)) t = "command-deck";
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("pf-theme", t); } catch (e) { /* ignore */ }
  const sel = document.getElementById("theme");
  if (sel) sel.value = t;
}
(function initTheme() {
  let saved = "command-deck";
  try { saved = localStorage.getItem("pf-theme") || saved; } catch (e) { /* ignore */ }
  applyTheme(saved);
  const sel = document.getElementById("theme");
  if (sel) sel.onchange = () => applyTheme(sel.value);
})();

load();
setInterval(() => { if (!openTask) load(); }, 10000);
