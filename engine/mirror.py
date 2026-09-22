"""The board summary note: a markdown copy of the board in your second brain.

Off unless config "summary_note" names a file (the installer asks, and you
confirm the path). Rewritten in full after every change, via a temporary
file and os.replace, so Obsidian never sees half a note.
"""
import time
from pathlib import Path
from urllib.parse import quote

from .config import atomic_write
from .db import STATUSES

STATUS_LABEL = {
    "backlog": "Backlog", "ready": "Ready", "in_progress": "In Progress",
    "blocked": "Blocked", "review": "Review",
    "awaiting_you": "Awaiting You", "done": "Done",
    "tracking": "Tracking",
}

NOTE_HEADER = """---
date: {date}
type: dashboard
tags: [projectforge, board, auto-generated]
---

> Auto-generated copy of the ProjectForge board. Do not edit by hand:
> it is rewritten after every change. Regenerate with `python forge.py mirror`.

"""


def crm_link(rel, config):
    """A link that opens the person's note in the CRM vault. The summary
    note lives in your second brain, so a [[wiki link]] would look in the
    wrong vault; an obsidian:// link names the file by its full path."""
    vault = (config.get("crm_vault") or "").replace("\\", "/").rstrip("/")
    name = Path(rel).stem
    if not vault:
        return f"{name} ({rel} in your CRM vault)"
    full = f"{vault}/{rel.replace(chr(92), '/').lstrip('/')}"
    return f"[{name}](obsidian://open?path={quote(full, safe='')})"


def render(state, config) -> str:
    by_project = {}
    for t in state["tasks"]:
        if not t.get("archived"):
            by_project.setdefault(t["project_id"], []).append(t)
    lines = [f"# ProjectForge Board - {config.get('workspace', '')}",
             f"_Generated {time.strftime('%Y-%m-%d %H:%M')}_", ""]
    open_tasks = [t for t in state["tasks"]
                  if t["status"] not in ("done", "tracking")
                  and not t.get("archived")]
    waiting = [t for t in open_tasks if t["status"] == "awaiting_you"]
    blocked = [t for t in open_tasks if t["status"] == "blocked"]
    lines += [f"**Active projects:** "
              f"{sum(1 for p in state['projects'] if p['status'] == 'active')}"
              f" · **Open cards:** {len(open_tasks)}"
              f" · **Awaiting you:** {len(waiting)}"
              f" · **Blocked:** {len(blocked)}", ""]
    alerts = state.get("alerts", [])
    if alerts:
        lines += ["## Alerts", ""]
        for a in alerts:
            lines.append(f"- **{a['kind']}** - {a['message']}")
        lines.append("")
    if waiting:
        lines += ["## Awaiting you", ""]
        for t in waiting:
            person = f" - person: {crm_link(t.get('crm_person'), config)}" \
                if t.get("crm_person") else ""
            lines.append(f"- **{t['title']}** ({t['id']}) - agent: "
                         f"{t['assignee_agent'] or '-'}{person}")
        lines.append("")
    dept_ids = [d["id"] for d in config.get("departments", [])]
    extra = sorted({p["department"] for p in state["projects"]} -
                   set(dept_ids))
    depts = list(config.get("departments", [])) + [
        {"id": x, "name": x, "lead": ""} for x in extra]
    order = {s: i for i, s in enumerate(STATUSES)}
    for dept in depts:
        projects = [p for p in state["projects"]
                    if p["department"] == dept["id"]]
        if not projects:
            continue
        lead = f"  _(lead: {dept['lead']})_" if dept.get("lead") else ""
        lines += [f"## {dept['name']}{lead}", ""]
        for p in projects:
            badge = "" if p["status"] == "active" else f" `[{p['status']}]`"
            lines += [f"### {p['title']}{badge}"]
            if p["summary"]:
                lines.append(f"_{p['summary']}_")
            tasks = by_project.get(p["id"], [])
            if tasks:
                lines += ["", "| Card | Column | Owner |", "|---|---|---|"]
                for t in sorted(tasks, key=lambda t: order[t["status"]]):
                    lines.append(f"| {t['title']} | "
                                 f"{STATUS_LABEL[t['status']]} | "
                                 f"{t['assignee_agent'] or '-'} |")
            lines.append("")
    return "\n".join(lines) + "\n"


def write_mirrors(store, config, base_dir=None):
    """Write the summary note if one is configured. Returns paths written."""
    target = (config.get("summary_note") or "").strip()
    if not target:
        return []
    state = store.state()
    state["alerts"] = store.open_alerts()
    text = NOTE_HEADER.format(date=time.strftime("%Y-%m-%d")) + \
        render(state, config)
    atomic_write(Path(target), text)
    return [target]
