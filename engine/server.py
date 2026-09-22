"""The web board. Python standard library only; nothing to install.

Serves the viewer (viewer/) and a small JSON API over the store. Listens on
127.0.0.1 only, so nothing outside your own computer can reach it.
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import cards as cards_mod
from . import mirror
from .rules import NotAllowed


def make_handler(store, config, base_dir: Path):
    viewer_dir = Path(base_dir) / "viewer"
    ctypes = {".html": "text/html; charset=utf-8",
              ".js": "application/javascript; charset=utf-8",
              ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
              ".png": "image/png"}

    def public_config():
        return {
            "workspace": config.get("workspace", "ProjectForge"),
            "departments": config.get("departments", []),
            "human": config.get("human", "you"),
            "agents": config.get("agents", []),
            "managers": config.get("managers", []),
            "crm_vault": config.get("crm_vault", ""),
        }

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else \
                json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control",
                             "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlparse(self.path)
            path, q = url.path, parse_qs(url.query)
            if path == "/api/state":
                state = store.state()
                state["config"] = public_config()
                return self._send(200, state)
            if path == "/api/events":
                return self._send(200, store.recent_events())
            if path == "/api/agents":
                return self._send(200, store.agents_summary())
            if path == "/api/alerts":
                return self._send(200, store.open_alerts())
            if path == "/api/metrics":
                return self._send(200, store.metrics(
                    int(q.get("days", ["7"])[0])))
            if path == "/api/cards":
                return self._send(200, cards_mod.load_cards(base_dir))
            if path == "/api/next":
                wip = config.get("hygiene", {}).get("wip_limits", {})
                return self._send(200, store.next_actionable(
                    int(q.get("limit", ["5"])[0]), wip,
                    cards=cards_mod.load_cards(base_dir)))
            if path == "/api/waiting":
                return self._send(200, store.work_waiting(
                    config, cards=cards_mod.load_cards(base_dir)))
            if path.startswith("/api/task/"):
                try:
                    return self._send(200, store.task_detail(
                        path.rsplit("/", 1)[-1]))
                except KeyError:
                    return self._send(404, {"error": "not found"})
            if path == "/":
                path = "/index.html"
            fp = (viewer_dir / path.lstrip("/")).resolve()
            root = viewer_dir.resolve()
            if (root in fp.parents or fp == root) and fp.is_file():
                return self._send(200, fp.read_bytes(),
                                  ctypes.get(fp.suffix, "text/plain"))
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            try:
                p = json.loads(self.rfile.read(length) or b"{}")
            except (json.JSONDecodeError, UnicodeDecodeError):
                return self._send(400, {"error": "bad json"})
            path = urlparse(self.path).path
            actor = p.get("actor")
            if path not in ("/api/federate", "/api/pass", "/api/handoff") \
                    and not actor:
                return self._send(400, {
                    "error": "actor is required - name yourself"})
            result = {"ok": True}
            try:
                if path == "/api/federate":
                    result = store.federate(p)
                elif path == "/api/intake":
                    leads = {d["id"]: d.get("lead", "")
                             for d in config.get("departments", [])}
                    ic = config.get("intake", {})
                    result = store.run_intake(leads, ic.get("hold_tags", []),
                                              ic.get("routing", []),
                                              actor=actor)
                elif path == "/api/dispatch":
                    result = store.dispatch(
                        p["task_id"], agent=p.get("agent"), actor=actor,
                        cards=cards_mod.load_cards(base_dir))
                elif path == "/api/commit":
                    result = store.commit_pass(
                        p["task_id"], p["agent"], p["summary"],
                        result=p.get("result", "progressed"),
                        outputs=p.get("outputs"),
                        next_step=p.get("next_step", ""),
                        dedup_key=p.get("key", ""), actor=actor,
                        intent=p.get("intent"))
                elif path == "/api/task/move":
                    store.move_task(p["task_id"], p["status"], actor=actor)
                elif path == "/api/task/reorder":
                    store.reorder(p["status"], p["ids"], actor=actor)
                elif path == "/api/task/update":
                    store.update_task(p["task_id"], p, actor=actor)
                elif path == "/api/task/tags":
                    result["tags"] = store.set_tags(
                        p["task_id"], p.get("tags", []), actor=actor)
                elif path == "/api/alert/dismiss":
                    store.dismiss_alert(p["id"], actor=actor)
                elif path == "/api/project/update":
                    store.update_project(p["project_id"], p, actor=actor)
                elif path == "/api/task/archive":
                    store.set_archived(p["task_id"], p.get("archived", True),
                                       actor=actor)
                elif path == "/api/task/checklist":
                    result["items"] = store.set_checklist(
                        p["task_id"], p.get("items", []), actor=actor)
                elif path == "/api/pass":
                    store.add_pass(p["task_id"], p.get("agent", ""),
                                   p.get("summary", ""),
                                   outputs=p.get("outputs", []),
                                   result=p.get("result", "progressed"),
                                   next_step=p.get("next_step", ""),
                                   dedup_key=p.get("key", ""),
                                   intent=p.get("intent"))
                elif path == "/api/task/comment":
                    store.comment(p["task_id"], p.get("text", ""),
                                  actor=actor)
                elif path == "/api/project/add":
                    result["id"] = store.add_project(
                        p["title"], p["department"],
                        summary=p.get("summary", ""), actor=actor)
                elif path == "/api/task/add":
                    result["id"] = store.add_task(
                        p["project_id"], p["title"],
                        status=p.get("status", "backlog"),
                        assignee_agent=p.get("assignee_agent", ""),
                        context_ref=p.get("context_ref", ""),
                        notes=p.get("notes", ""), actor=actor,
                        crm_person=p.get("crm_person", ""))
                elif path == "/api/open":
                    result["id"] = store.open_card(
                        actor, p["project_title"], p["department"],
                        p["title"], assignee_agent=p.get("assignee_agent", ""),
                        status=p.get("status", "backlog"),
                        context_ref=p.get("context_ref", ""),
                        notes=p.get("notes", ""),
                        crm_person=p.get("crm_person", ""))
                elif path == "/api/handoff":
                    store.handoff(
                        p["task_id"], p.get("from_agent", ""),
                        p.get("to_agent", ""), done=p.get("done", ""),
                        decisions=p.get("decisions", ""),
                        state=p.get("state", ""),
                        next_first=p.get("next_first", ""),
                        warnings=p.get("warnings", ""),
                        context=p.get("context", ""),
                        intent=p.get("intent", "DELEGATE"))
                else:
                    return self._send(404, {"error": "not found"})
            except NotAllowed as e:
                return self._send(403, {"error": str(e)})
            except KeyError as e:
                return self._send(400, {"error": f"missing or unknown: {e}"})
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            try:
                mirror.write_mirrors(store, config, base_dir)
            except OSError:
                pass  # the summary note is a courtesy; never fail a write
            return self._send(200, result)

        def log_message(self, *args):
            pass  # keep quiet

    return Handler


def make_server(store, config, base_dir: Path, port=3020):
    return ThreadingHTTPServer(("127.0.0.1", port),
                               make_handler(store, config, base_dir))


def serve(store, config, base_dir: Path, port=3020):
    httpd = make_server(store, config, base_dir, port)
    print(f"ProjectForge board: http://127.0.0.1:{port}  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
