"""Shared test set-up. Every test runs against a throwaway folder: its own
config.json, its own database, its own fake home. Nothing real is touched."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.db import Store  # noqa: E402
from engine.rules import Roles  # noqa: E402

HUMAN = "you"
ORCH = "orchestrator"
MANAGER = "content-lead"
WORKER = "writer-bot"


@pytest.fixture
def roles():
    return Roles(human=HUMAN, orchestrator=ORCH, managers=[MANAGER],
                 outward_owners=["social-poster"],
                 federate_sources=["crm-today", "tracker"])


@pytest.fixture
def store(tmp_path, roles):
    s = Store(tmp_path / "test.db", roles=roles)
    yield s
    s.close()


@pytest.fixture
def cfg_env(tmp_path, monkeypatch):
    """A config.json in a temp folder, with FORGE_CONFIG pointing at it."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
    cfg = {"human": HUMAN, "orchestrator": ORCH, "managers": [MANAGER],
           "db_path": "data/forge.db", "summary_note": "",
           "departments": [{"id": "content", "name": "Content",
                            "lead": ""}]}
    p = tmp_path / "config.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setenv("FORGE_CONFIG", str(p))
    return p


def new_card(store, status="ready", owner=WORKER, dept="content"):
    pid = store.add_project("Spring launch", dept, actor=HUMAN)
    return store.add_task(pid, "Draft 3 posts", status=status,
                          assignee_agent=owner, actor=HUMAN)
