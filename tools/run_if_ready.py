"""Start the orchestrator ONLY if a card is ready to hand out.

The lesson this exists for: the original board had a Claude session start
every 15 minutes whether or not there was work. Its log shows 304 passes in
about 4.4 days (2026-07-04 to 2026-07-08) and every one of them found
nothing to hand out. Each start paid for a full Claude session to look at an
empty board.

This script is the cheap check that goes first. It counts, straight from the
database and with no AI, how many cards a pass could hand out. If the answer
is 0 it writes one line to data/run_if_ready.log and exits. Claude is never
started. Only when a card is ready does it run:

    claude -p "/forge-run"

Run it by hand, or let tools/schedule.py run it on a timer (off by default).

  python tools/run_if_ready.py            check, and start Claude if needed
  python tools/run_if_ready.py --dry-run  check only; never start Claude
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from engine import cards as cards_mod  # noqa: E402
from engine.config import load_config  # noqa: E402
from engine.db import open_store  # noqa: E402

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def log_line(cfg, text):
    log = Path(cfg["_path"]).parent / "data" / "run_if_ready.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:  # append-only log
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {text}\n")


def count_work(cfg):
    store = open_store(cfg)
    try:
        return store.work_waiting(cfg, cards=cards_mod.load_cards(BASE))
    finally:
        store.close()


def claude_command(cfg):
    exe = shutil.which("claude")
    if not exe:
        return None
    cmd = [exe, "-p", "/forge-run"]
    model = (cfg.get("schedule") or {}).get("model") or ""
    if model:
        cmd += ["--model", model]
    return cmd


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="count only; never start Claude")
    a = ap.parse_args(argv)
    cfg = load_config()
    w = count_work(cfg)
    if w["total"] == 0:
        why = ("in-progress limit reached" if w["at_cap"]
               else "no card ready")
        msg = f"0 cards to hand out ({why}) - Claude not started"
        print(msg)
        log_line(cfg, msg)
        return 0
    msg = (f"{w['total']} card(s) to hand out ({w['ready']} ready, "
           f"{w['from_backlog']} from backlog)")
    if a.dry_run:
        print(msg + " - dry run, Claude not started")
        return 0
    cmd = claude_command(cfg)
    if not cmd:
        print(msg + " - but the `claude` command was not found on PATH")
        log_line(cfg, msg + " - claude not found")
        return 2
    cwd = cfg.get("orchestrator_cwd") or cfg.get("second_brain") or str(BASE)
    log_line(cfg, msg + " - starting Claude")
    try:
        r = subprocess.run(cmd, cwd=cwd if os.path.isdir(cwd) else None,
                           capture_output=True, text=True, timeout=45 * 60,
                           creationflags=NO_WINDOW)
        tail = (r.stdout or "").strip().splitlines()[-1:] or [""]
        log_line(cfg, f"Claude finished, exit {r.returncode}: {tail[0][:200]}")
        return r.returncode
    except subprocess.TimeoutExpired:
        log_line(cfg, "Claude pass stopped after 45 minutes")
        return 5


if __name__ == "__main__":
    sys.exit(main())
