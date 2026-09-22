"""Install ProjectForge into your own setup.

    python install.py              the interview (about 2 minutes)
    python install.py --uninstall  take it out again (your board data stays)

What it does, in order, and only after you say yes:
  1. asks where your second brain vault, CRM vault and agents folder are
  2. lists your real agents so you can pick which ones are managers
  3. writes config.json (the only settings file)
  4. creates an EMPTY board database at data/forge.db
  5. installs the agents' tool, forge_agent.py, into <claude folder>/projectforge/
  6. installs the /forge-run command into your Claude Code commands folder
     (backing up any file already there first)
  7. optionally writes a board summary note into your second brain

It never starts anything on a timer. Running it twice changes nothing the
second time. If something it needs is missing it says so and changes nothing.

For scripts and tests: --yes takes every default without asking, and each
question has a flag (see --help).
"""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

MIN_PY = (3, 9)


def say(msg=""):
    print(msg, flush=True)


def claude_home():
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env) if env else Path.home() / ".claude"


# ---------------------------------------------------------------- finding

def find_vaults():
    """Folders under your home (and Documents) that contain .obsidian."""
    roots = [Path.home(), Path.home() / "Documents"]
    found = []
    for r in roots:
        try:
            for child in sorted(r.iterdir()):
                if child.is_dir() and (child / ".obsidian").is_dir():
                    if child not in found:
                        found.append(child)
        except OSError:
            continue
    return found


def guess_second_brain(vaults):
    for v in vaults:
        if "brain" in v.name.lower():
            return v
    for v in vaults:
        if "crm" not in v.name.lower():
            return v
    return None


def guess_crm(vaults, second_brain):
    for v in vaults:
        if v != second_brain and ("crm" in v.name.lower() or
                                  (v / "Today.md").is_file()):
            return v
    return None


def read_agents(folders):
    """Every agent file (*.md) in the folders, by the name Claude Code uses:
    the `name:` line in its front matter, else the file name."""
    names = []
    for folder in folders:
        f = Path(folder)
        if not f.is_dir():
            continue
        for md in sorted(f.glob("*.md")):
            if md.name.lower() == "readme.md":
                continue
            name = md.stem
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if text.startswith("---"):
                for line in text.split("\n")[1:40]:
                    if line.strip() == "---":
                        break
                    if line.lower().startswith("name:"):
                        name = line.split(":", 1)[1].strip().strip("'\"")
                        break
            if name and name not in names:
                names.append(name)
    return names


# ---------------------------------------------------------------- asking

class Asker:
    def __init__(self, yes):
        self.yes = yes

    def ask(self, prompt, default=""):
        if self.yes:
            say(f"{prompt}: {default}")
            return default
        shown = f" [{default}]" if default not in ("", None) else ""
        try:
            got = input(f"{prompt}{shown}: ").strip()
        except EOFError:
            got = ""
        return got or default

    def confirm(self, prompt, default=True):
        if self.yes:
            return True
        d = "Y/n" if default else "y/N"
        try:
            got = input(f"{prompt} [{d}]: ").strip().lower()
        except EOFError:
            got = ""
        return default if not got else got.startswith("y")


def split_names(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


# ---------------------------------------------------------------- writing

def atomic_write(path, text):
    from engine.config import atomic_write as aw
    aw(path, text)


def write_if_changed(path, text, backup=False):
    """Returns 'created', 'updated', or 'unchanged'. Backs up first when
    asked and the file is different."""
    path = Path(path)
    if path.is_file():
        old = path.read_text(encoding="utf-8", errors="replace")
        if old == text:
            return "unchanged"
        if backup:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            shutil.copy2(path, path.with_name(f"{path.name}.bak-{stamp}"))
        atomic_write(path, text)
        return "updated"
    atomic_write(path, text)
    return "created"


def render_command(cfg, adapter_path):
    tpl = (BASE / "commands" / "forge-run.md").read_text(encoding="utf-8")
    return (tpl.replace("{{FORGE_DIR}}", BASE.as_posix())
               .replace("{{ADAPTER}}", Path(adapter_path).as_posix())
               .replace("{{HUMAN}}", cfg["human"])
               .replace("{{ORCH}}", cfg["orchestrator"]))


def claude_snippet(cfg, adapter_path):
    a = Path(adapter_path).as_posix()
    mgr = ", ".join(cfg["managers"]) or "(none yet - only you open cards)"
    return f"""## ProjectForge - the work board (paste into your CLAUDE.md)

Agent work is recorded on the ProjectForge board. The tool is
`python "{a}"`.

- Before project work, an agent reads its card: `python "{a}" card <card_id>`.
- After the work, it logs a work report:
  `python "{a}" pass --card <id> --agent <name> --summary "..." --outputs "files" --result <completed|progressed|blocked|failed|needs-review> --next "..."`.
- Handing work to another agent needs all 5 fields or the board refuses it:
  `python "{a}" handoff --card <id> --from <me> --to <next> --done "..." --decisions "... because ..." --state "..." --next-first "..." --warnings "none"`.
- Workers only append (pass, handoff, comment, escalate). Managers ({mgr})
  may also `open` cards. Only the orchestrator (/forge-run) moves cards.

## Paste into each worker agent's file

End every task with a WORK REPORT: what you did, the files you made,
decisions and why, where it stands (including what is not done), what the
next agent should do first, and warnings.
"""


# ---------------------------------------------------------------- install

def interview(args, ask, existing):
    ch = claude_home()
    vaults = find_vaults()
    sb_default = args.second_brain or existing.get("second_brain") or \
        str(guess_second_brain(vaults) or "")
    say("\n1. Your second brain vault (the Obsidian folder your agents work in).")
    sb = ask.ask("   Path", sb_default)
    if not sb or not Path(sb).is_dir():
        return None, f"Second brain folder not found: {sb or '(blank)'}"
    sb = str(Path(sb).resolve())
    if not (Path(sb) / ".obsidian").is_dir():
        say("   (no .obsidian folder inside - fine if it is still a vault)")

    crm_default = args.crm if args.crm is not None else \
        existing.get("crm_vault") or str(guess_crm(vaults, Path(sb)) or "")
    say("\n2. Your CRM vault (type 'none' if you do not have one).")
    crm = ask.ask("   Path", crm_default or "none")
    if crm.lower() == "none":
        crm = ""
    if crm and not Path(crm).is_dir():
        return None, f"CRM folder not found: {crm}"
    crm = str(Path(crm).resolve()) if crm else ""

    ad_default = args.agents_dir or existing.get("agents_dirs") or \
        [str(ch / "agents")] + ([str(Path(sb) / ".claude" / "agents")]
                                if (Path(sb) / ".claude" / "agents").is_dir()
                                else [])
    say("\n3. Your agents folder(s). Separate several with ;")
    ad = ask.ask("   Folders", ";".join(ad_default))
    agents_dirs = [str(Path(x.strip()).resolve()) for x in ad.split(";")
                   if x.strip()]
    agents = read_agents(agents_dirs)
    if agents:
        say(f"   Found {len(agents)} agent(s) who can own cards:")
        for i in range(0, len(agents), 4):
            say("     " + ", ".join(agents[i:i + 4]))
    else:
        say("   No agent files found there. You can still use the board; "
            "add agents later and re-run the installer.")

    say("\n4. Managers: which agents may OPEN new cards? Everyone else may "
        "only add work reports.\n   Names separated by commas, or blank for "
        "none (then only you open cards).")
    mgr_default = args.managers if args.managers is not None else \
        ",".join(existing.get("managers", []))
    managers = split_names(ask.ask("   Managers", mgr_default))
    unknown = [m for m in managers if m not in agents]
    if unknown:
        say(f"   Note: not in your agents folder: {', '.join(unknown)} "
            f"(kept anyway)")

    say("\n5. Which agents' work reaches other people (posts, emails, "
        "messages)?\n   Their finished cards stop in Review for you to check. "
        "Commas, or blank.")
    out_default = args.outward if args.outward is not None else \
        ",".join(existing.get("outward_owners", []))
    outward = split_names(ask.ask("   Outward agents", out_default))

    say("\n6. What should the board call you?")
    human = ask.ask("   Your name on the board",
                    args.name or existing.get("human") or "you")

    say("\n7. Where should the /forge-run command go?\n   user = every Claude "
        "Code session on this computer;\n   vault = only sessions opened in "
        "your second brain.")
    where = (args.commands or ask.ask("   user or vault",
                                      existing.get("_commands_to", "user"))
             ).lower()
    if where not in ("user", "vault"):
        return None, "answer user or vault"
    cmd_dir = (ch / "commands") if where == "user" else \
        (Path(sb) / ".claude" / "commands")

    say("\n8. A board summary note in your second brain (a markdown copy of "
        "the board,\n   rewritten after every change). Type 'none' to skip.")
    note_default = args.summary_note if args.summary_note is not None else \
        (existing.get("summary_note") or
         str(Path(sb) / "ProjectForge Board.md"))
    note = ask.ask("   Note path", note_default or "none")
    if note.lower() == "none":
        note = ""
    if note:
        note = str(Path(note).resolve())

    port = int(args.port or existing.get("port") or 3020)
    answers = {
        "second_brain": sb, "crm_vault": crm, "agents_dirs": agents_dirs,
        "agents": agents, "managers": managers, "outward_owners": outward,
        "human": human, "summary_note": note, "port": port,
        "command_path": str(cmd_dir / "forge-run.md"),
        "adapter_dir": str(ch / "projectforge"),
        "_commands_to": where,
    }
    return answers, None


def do_install(args):
    from engine.config import config_path, load_config
    ask = Asker(args.yes)
    say("ProjectForge installer - a work board for your agents.")
    if sys.version_info < MIN_PY:
        say(f"Refused: Python {MIN_PY[0]}.{MIN_PY[1]} or newer is needed "
            f"(you have {sys.version.split()[0]}). Nothing changed.")
        return 1
    cpath = config_path()
    existing = {}
    if cpath.is_file():
        existing = json.loads(cpath.read_text(encoding="utf-8"))
    answers, err = interview(args, ask, existing)
    if err:
        say(f"\nStopped: {err}. Nothing changed.")
        return 1

    new_cfg = dict(existing)
    new_cfg.update(answers)
    new_cfg.setdefault("workspace", "My AI Workforce")
    new_cfg.setdefault("orchestrator", "orchestrator")
    new_cfg.setdefault("db_path", "data/forge.db")

    say("\nAbout to:")
    say(f"  write   {cpath}")
    say(f"  create  an empty board in {cpath.parent / 'data'} "
        f"(if not already there)")
    say(f"  install {answers['adapter_dir']}{os.sep}forge_agent.py")
    say(f"  install {answers['command_path']}  (backup first if different)")
    if answers["summary_note"]:
        say(f"  write   {answers['summary_note']}  (only if it does not exist)")
    if not ask.confirm("Go ahead?"):
        say("Nothing changed.")
        return 1

    changes = []
    text = json.dumps(new_cfg, indent=2) + "\n"
    r = write_if_changed(cpath, text)
    if r != "unchanged":
        changes.append(f"config.json {r}")

    cfg = load_config()
    from engine.config import db_path
    dbp = db_path(cfg)
    fresh = not dbp.is_file()
    from engine.db import open_store
    st = open_store(cfg)
    st.close()
    if fresh:
        changes.append(f"empty board created at {dbp}")

    adir = Path(answers["adapter_dir"])
    for fname in ("forge_agent.py", "forge_client.py"):
        src = (BASE / "adapters" / fname).read_text(encoding="utf-8")
        r = write_if_changed(adir / fname, src)
        if r != "unchanged":
            changes.append(f"{fname} {r}")
    r = write_if_changed(adir / "forge_agent.json",
                         json.dumps({"forge_dir": str(BASE)}, indent=2) + "\n")
    if r != "unchanged":
        changes.append(f"forge_agent.json {r}")

    adapter = adir / "forge_agent.py"
    r = write_if_changed(answers["command_path"],
                         render_command(cfg, adapter), backup=True)
    if r != "unchanged":
        changes.append(f"/forge-run command {r}")

    snippet = dbp.parent / "CLAUDE-snippet.md"
    r = write_if_changed(snippet, claude_snippet(cfg, adapter))
    if r != "unchanged":
        changes.append(f"{snippet} {r}")

    if answers["summary_note"] and not Path(answers["summary_note"]).is_file():
        from engine import mirror
        st = open_store(cfg)
        try:
            mirror.write_mirrors(st, cfg, BASE)
        finally:
            st.close()
        changes.append(f"summary note written: {answers['summary_note']}")

    say("")
    if not changes:
        say("Already installed exactly like this. Nothing changed.")
    else:
        for c in changes:
            say(f"  done: {c}")
    say(f"""
Next:
  1. Open the board:      python forge.py serve
     then visit          http://127.0.0.1:{cfg['port']}
  2. Paste the lines in  {snippet}
     into your CLAUDE.md so your agents know to log their work.
  3. In Claude Code, try  /forge-run dry  (a preview that changes nothing).
Nothing runs on a timer. To add the optional schedule later:
     python tools/schedule.py --print""")
    return 0


def do_uninstall(args):
    from engine.config import config_path, load_config
    ask = Asker(args.yes)
    cpath = config_path()
    if not cpath.is_file():
        say("Not installed (no config.json). Nothing changed.")
        return 0
    cfg = load_config()
    if not ask.confirm("Remove the /forge-run command and the agents' tool? "
                       "Your board data and config stay.", default=False):
        say("Nothing changed.")
        return 1
    stamp = time.strftime("%Y%m%d-%H%M%S")
    cmd = Path(cfg.get("command_path", ""))
    if cmd.is_file():
        body = cmd.read_text(encoding="utf-8", errors="replace")
        if "installed by outliers-ws-03-projectforge" in body:
            os.replace(cmd, cmd.with_name(f"{cmd.name}.removed-{stamp}"))
            baks = sorted(cmd.parent.glob(f"{cmd.name}.bak-*"))
            if baks:
                shutil.copy2(baks[-1], cmd)
                say(f"  restored your earlier {cmd.name} from {baks[-1].name}")
            say(f"  removed /forge-run ({cmd})")
        else:
            say(f"  left {cmd} alone - it is not the one we installed")
    adir = Path(cfg.get("adapter_dir", ""))
    if adir.is_dir() and (adir / "forge_agent.json").is_file():
        os.replace(adir, adir.with_name(f"{adir.name}.removed-{stamp}"))
        say(f"  moved the agents' tool aside: {adir}.removed-{stamp}")
    if (cfg.get("schedule") or {}).get("installed"):
        import subprocess
        subprocess.run([sys.executable, str(BASE / "tools" / "schedule.py"),
                        "--remove"],
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW",
                                             0))
    say(f"Done. Your board is still in {BASE / 'data'} and your settings in "
        f"{cpath}.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Install ProjectForge")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--yes", action="store_true",
                    help="take every default without asking")
    ap.add_argument("--second-brain", dest="second_brain")
    ap.add_argument("--crm", help="CRM vault path, or 'none'")
    ap.add_argument("--agents-dir", dest="agents_dir", action="append",
                    help="an agents folder (repeat for several)")
    ap.add_argument("--managers", help="comma-separated agent names")
    ap.add_argument("--outward", help="comma-separated agent names")
    ap.add_argument("--name", help="what the board calls you")
    ap.add_argument("--commands", choices=["user", "vault"])
    ap.add_argument("--summary-note", dest="summary_note",
                    help="path of the summary note, or 'none'")
    ap.add_argument("--port", type=int)
    args = ap.parse_args(argv)
    return do_uninstall(args) if args.uninstall else do_install(args)


if __name__ == "__main__":
    sys.exit(main())
