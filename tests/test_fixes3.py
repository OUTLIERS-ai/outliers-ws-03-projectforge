"""Faults found by reading the download the way a member reads it, on
2026-09-23. One section per fault, each starting with what caused it."""
import threading

import pytest

from conftest import HUMAN, REPO, WORKER, new_card


# ---- 11. escalate told the next agent the wrong column -------------------
# Cause: the message was written when an escalation only left a red mark.
# The card is moved into Awaiting You now, and the message still said it
# had not moved, so every agent reading it looked in the wrong column.

def test_escalate_says_the_card_has_moved_into_awaiting_you(
        cfg_env, monkeypatch, capsys):
    monkeypatch.setenv("FORGE_DIR", str(REPO))
    from adapters import forge_agent
    from engine.config import load_config
    from engine.db import open_store
    st = open_store(load_config())
    tid = new_card(st, status="in_progress")
    st.close()

    assert forge_agent.main(["escalate", "--card", tid, "--agent", WORKER,
                             "--note", "Please ring Oakfield."]) == 0
    said = capsys.readouterr().out

    st = open_store(load_config())
    where = st.task_detail(tid)["task"]["status"]
    st.close()
    assert where == "awaiting_you"          # what the board did
    assert "has not moved" not in said      # what the agent was told
    assert "Awaiting You" in said


def test_escalate_names_the_column_the_card_is_really_in(
        cfg_env, monkeypatch, capsys):
    """A finished card is marked but not moved, and the message has to say
    so: the next agent goes looking in the column it names."""
    monkeypatch.setenv("FORGE_DIR", str(REPO))
    from adapters import forge_agent
    from engine.config import load_config
    from engine.db import open_store
    st = open_store(load_config())
    tid = new_card(st, status="done")
    st.close()

    assert forge_agent.main(["escalate", "--card", tid, "--agent", WORKER,
                             "--note", "One more read, please."]) == 0
    said = capsys.readouterr().out
    assert "Done" in said and "Awaiting You" not in said


# ---- 12. the alerts panel forgot it was open -----------------------------
# Cause: the panel was put back to its remembered state once, behind a
# "wired" mark on the close button, and the remembered state was read
# without a guard. A board refresh every 10 seconds must never take away
# the "Open this card" link a member is reaching for.

VIEWER = REPO / "viewer"


def _alerts_js():
    js = (VIEWER / "app.js").read_text(encoding="utf-8")
    return js.split("function setAlertsPanel(")[1].split(
        "\nasync function renderAlerts(")[0]


def test_the_alerts_panel_is_put_back_on_every_refresh():
    wire = _alerts_js().split("function wireAlertsPanel(")[1]
    puts_back = [ln for ln in wire.splitlines()
                 if "setAlertsPanel(alertsWanted())" in ln]
    assert puts_back, "the panel is never put back the way you left it"
    # 2 spaces of indent is the body of the function; 4 is inside the
    # branch that only runs the first time round
    assert not puts_back[0].startswith("    "), \
        "the panel is only put back on the first render, not on a refresh"


def test_the_alerts_panel_survives_a_browser_that_refuses_storage():
    """A browser with site data switched off throws on the first read. It
    used to take the whole alerts render down with it, alert items, link
    and all."""
    js = (VIEWER / "app.js").read_text(encoding="utf-8")
    for ln in js.splitlines():
        if "localStorage" in ln:
            assert "try {" in ln, \
                f"storage is touched with no guard: {ln.strip()}"


# ---- 13. a refused write looked like a write that worked -----------------
# Cause: the client turned every HTTP answer it did not like into None, so
# a program whose name is not in federate_sources was told nothing at all.

def _boot(store, cfg):
    from engine.server import make_server
    httpd = make_server(store, cfg, REPO, port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


PROJECT = {"ref": "spring-launch", "title": "Spring launch",
           "department": "content"}


def test_a_refused_write_raises_with_the_boards_own_words(store):
    from adapters.forge_client import ForgeClient, ForgeRefused
    httpd, url = _boot(store, {"human": HUMAN, "departments": [],
                               "summary_note": ""})
    try:
        forge = ForgeClient("my-script", base_url=url)
        with pytest.raises(ForgeRefused) as e:
            forge.federate(project=PROJECT)
        said = str(e.value)
        assert "refused" in said and "federate_sources" in said
    finally:
        httpd.shutdown()


def test_a_write_the_board_accepts_still_returns_the_id_map(store):
    from adapters.forge_client import ForgeClient
    httpd, url = _boot(store, {"human": HUMAN, "departments": [],
                               "summary_note": ""})
    try:
        forge = ForgeClient("tracker", base_url=url)
        r = forge.card(project=PROJECT, ref="post-1",
                       title="Draft launch post")
        assert r["tasks"][0]["created"] is True
    finally:
        httpd.shutdown()


def test_a_board_that_is_not_running_is_still_quiet(store):
    """The other half of the promise: a program carries on when the board
    is switched off. Only a refusal raises."""
    from adapters.forge_client import ForgeClient
    forge = ForgeClient("tracker", base_url="http://127.0.0.1:1", timeout=1)
    assert forge.federate(project=PROJECT) is None
    assert forge.ping() is False


def test_the_client_file_says_what_a_refusal_does():
    src = (REPO / "adapters" / "forge_client.py").read_text(encoding="utf-8")
    head = src.split("Usage")[0]
    assert "refus" in head and "None" in head
