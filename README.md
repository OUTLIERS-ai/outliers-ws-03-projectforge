# ProjectForge - one work board for all your agents

```
git clone https://github.com/OUTLIERS-ai/outliers-ws-03-projectforge; cd outliers-ws-03-projectforge; python install.py
```

A Trello-style board that runs on your own computer, written for Claude Code
agents. Each card is one piece of work with an owner. Agents write work
reports and handovers onto the card, so the next agent (or you, after a week
away) starts from a written record.

The board itself has no AI in it. It enforces 3 rules, in the database code:

1. **Managers open cards.** You choose which agents are managers.
2. **Workers only add to a card**: a work report, a handover, a comment.
   They never open or move a card.
3. **Only the orchestrator moves cards.** That is the `/forge-run` command in
   Claude Code. You can move cards too.

A handover is refused unless it carries 5 fields: what was done, decisions
and why, where the work stands, what to do first, warnings.

Nothing runs on a timer. See the guide for why (a 15-minute timer on the
original board started Claude 304 times in about 4.4 days and found work 0
times).

## What the installer does

It asks where your second brain vault, CRM vault and agents folder are, lists
your agents so you can pick the managers, then - after you say yes - writes
`config.json`, creates an empty board at `data/forge.db`, installs the agents'
tool into `<your .claude folder>/projectforge/`, and installs the `/forge-run`
command (backing up any file of that name first). Run it twice and the second
run changes nothing. `python install.py --uninstall` takes it out again and
leaves your board data alone.

## Everyday commands

| Command | What it does |
|---|---|
| `python forge.py serve` | Opens the board at http://127.0.0.1:3020 (leave the window open; Ctrl+C stops it) |
| `python forge.py list` | Open cards in the terminal |
| `python forge.py projects` | Every project and its id |
| `python forge.py add-project "Content week 39" --dept content --actor you` | A new project; prints its id |
| `python forge.py add-task <project-id> "Draft 3 posts" --status ready --agent writer-bot --actor you` | A new card |
| `python forge.py waiting` | How many cards a `/forge-run` could hand out now |
| `/forge-run dry` (in Claude Code) | A preview of a pass; changes nothing |
| `/forge-run` | Hands ready cards to their owner agents and records the results |
| `python adapters/crm_today.py` | One card per person on your CRM's Today page |
| `python tools/run_if_ready.py` | Starts `/forge-run` only if a card is ready |
| `python tools/schedule.py --print` | Shows the optional schedule; off by default |
| `python tools/demo_board.py --out demo --serve` | A separate demo board of made-up work |

Every `forge.py` command that changes the board needs `--actor <your name>`
(the name from `human` in config.json). There is no default, so an agent that
runs forge.py without naming itself is stopped instead of counting as you.

Agents use `forge_agent.py`, which the installer puts in
`<your .claude folder>/projectforge/` (on Windows
`%USERPROFILE%\.claude\projectforge\forge_agent.py`):

```
python forge_agent.py mywork <agent>
python forge_agent.py card <id>
python forge_agent.py pass --card <id> --agent <name> --summary "..." --outputs a.md --result needs-review --next "..."
python forge_agent.py handoff --card <id> --from <me> --to <next> --done "..." --decisions "... because ..." --state "..." --next-first "..." --warnings "none"
python forge_agent.py escalate --card <id> --agent <name> --note "what I need"
python forge_agent.py open --agent <manager> --dept content --project "..." --title "..." --assignee <agent>
```

## Safety

- The board listens on 127.0.0.1 only, and refuses any write that does not
  come from its own page (Host, Origin and Content-Type checks), so a website
  you visit cannot add or move cards.
- Only programs named in `federate_sources` in config.json may push cards in.
- Awaiting You is yours: the orchestrator may put a card in it, never take one out.
- A card in Ready can be claimed once; a second `/forge-run` cannot take it.
- A second copy of the board on the same port fails with a clear message.
- The optional unattended run (`tools/run_if_ready.py`) starts Claude in
  "dontAsk" mode with exactly the board commands it needs allowed; anything
  else, unless you already allowed it in your own Claude Code settings, is
  refused. The list is in `allowed_tools()` in that file.

## Needs

Python 3.9 or newer, Git, Claude Code. No extra Python packages to run it;
`pytest` only to run the tests (`python -m pytest -q`).

## Files

- `engine/` the database rules (`db.py`, `rules.py`), web server, health check, summary note
- `viewer/` the web board (plain JavaScript)
- `adapters/` the agents' tool, a client for your own programs, the CRM Today reader
- `commands/forge-run.md` the orchestrator command (the installer fills in your paths)
- `tools/` the ready-check, the optional schedule, the demo board
- `cards/` optional per-agent limits (see the example file)
- `guide/GUIDE.md` the full guide: how it was built, how to install, how to fit it to your setup

MIT licence. See `WHAT-I-STOLE.md` for where the ideas came from.
