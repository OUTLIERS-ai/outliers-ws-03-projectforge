"""The installer, run against a fake home and fake vaults."""
import json
from pathlib import Path

import pytest

import install


def fake_setup(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ch = home / ".claude"
    agents = ch / "agents"
    agents.mkdir(parents=True)
    for name in ("content-lead", "writer-bot", "research-bot"):
        (agents / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: made-up test agent\n---\nBody\n",
            encoding="utf-8")
    sb = home / "Documents" / "Second Brain"
    (sb / ".obsidian").mkdir(parents=True)
    crm = home / "Documents" / "CRM"
    (crm / ".obsidian").mkdir(parents=True)
    (crm / "People").mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(ch))
    cfgp = tmp_path / "install" / "config.json"
    monkeypatch.setenv("FORGE_CONFIG", str(cfgp))
    monkeypatch.setattr(install.Path, "home", classmethod(lambda c: home))
    return home, ch, sb, crm, cfgp


def run(sb, crm, extra=()):
    return install.main(["--yes", "--second-brain", str(sb), "--crm",
                         str(crm), "--managers", "content-lead",
                         *extra])


def test_install_fresh_then_idempotent(tmp_path, monkeypatch, capsys):
    home, ch, sb, crm, cfgp = fake_setup(tmp_path, monkeypatch)
    assert run(sb, crm) == 0
    cfg = json.loads(cfgp.read_text(encoding="utf-8"))
    assert cfg["managers"] == ["content-lead"]
    assert set(cfg["agents"]) == {"content-lead", "writer-bot",
                                  "research-bot"}
    assert cfg["second_brain"] == str(sb.resolve())
    # empty database
    import sqlite3
    db = cfgp.parent / "data" / "forge.db"
    n = sqlite3.connect(db).execute("SELECT COUNT(*) FROM tasks").fetchone()
    assert n[0] == 0
    cmd = ch / "commands" / "forge-run.md"
    body = cmd.read_text(encoding="utf-8")
    assert "{{" not in body and "installed by outliers-ws-03" in body
    assert (ch / "projectforge" / "forge_agent.py").is_file()
    assert (sb / "ProjectForge Board.md").is_file()
    capsys.readouterr()
    # second run changes nothing
    assert run(sb, crm) == 0
    assert "Nothing changed" in capsys.readouterr().out
    assert not list((ch / "commands").glob("*.bak-*"))


def test_existing_command_backed_up(tmp_path, monkeypatch):
    home, ch, sb, crm, cfgp = fake_setup(tmp_path, monkeypatch)
    (ch / "commands").mkdir(parents=True)
    (ch / "commands" / "forge-run.md").write_text("my old command",
                                                  encoding="utf-8")
    assert run(sb, crm) == 0
    baks = list((ch / "commands").glob("forge-run.md.bak-*"))
    assert len(baks) == 1
    assert baks[0].read_text(encoding="utf-8") == "my old command"


def test_vault_commands_and_no_note(tmp_path, monkeypatch):
    home, ch, sb, crm, cfgp = fake_setup(tmp_path, monkeypatch)
    assert run(sb, crm, ["--commands", "vault", "--summary-note",
                         "none"]) == 0
    assert (sb / ".claude" / "commands" / "forge-run.md").is_file()
    assert not (sb / "ProjectForge Board.md").exists()


def test_missing_vault_changes_nothing(tmp_path, monkeypatch):
    home, ch, sb, crm, cfgp = fake_setup(tmp_path, monkeypatch)
    assert install.main(["--yes", "--second-brain",
                         str(tmp_path / "nope")]) == 1
    assert not cfgp.exists()
    assert not (ch / "commands").exists()


def test_uninstall(tmp_path, monkeypatch):
    home, ch, sb, crm, cfgp = fake_setup(tmp_path, monkeypatch)
    (ch / "commands").mkdir(parents=True)
    (ch / "commands" / "forge-run.md").write_text("my old command",
                                                  encoding="utf-8")
    assert run(sb, crm) == 0
    assert install.main(["--uninstall", "--yes"]) == 0
    # their old command is back, ours is set aside, the tool is set aside
    assert (ch / "commands" / "forge-run.md").read_text(
        encoding="utf-8") == "my old command"
    assert list((ch / "commands").glob("forge-run.md.removed-*"))
    assert not (ch / "projectforge").exists()
    assert list(ch.glob("projectforge.removed-*"))
    assert cfgp.is_file()  # settings and data stay


def test_read_agents_uses_frontmatter_name(tmp_path):
    d = tmp_path / "agents"
    d.mkdir()
    (d / "file-name.md").write_text("---\nname: real-name\n---\n",
                                    encoding="utf-8")
    (d / "README.md").write_text("not an agent", encoding="utf-8")
    assert install.read_agents([d]) == ["real-name"]
