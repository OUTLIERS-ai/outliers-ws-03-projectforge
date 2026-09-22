---
title: ProjectForge — A Work Board For All Your Agents
subtitle: Cards with an owner, written work reports, and a single orchestrator that moves the cards
repo: https://github.com/OUTLIERS-ai/outliers-ws-03-projectforge
piece: 3
---

## What it is

ProjectForge is a work board, like a Trello board, that runs on your own computer and is written for AI agents. Each card is a single piece of work. Each card has an owner: one of your Claude Code agents, or you.

The board has 8 columns: Backlog, Ready, In Progress, Blocked, Review, Awaiting You, Done and Tracking. On the right is a live list of who did what and when.

![The board with made-up work for a made-up bookkeeping business. 8 columns, the activity list on the right.](img/board.png)

Click a card and you see its full record: notes, checklist, a link to a person in your CRM vault, every work report an agent wrote against it (what it did, which files it made, the result, the next step), and every handover from agent to agent.

The board itself contains no AI. It stores the work and it enforces 3 rules:

1. **Managers open cards.** You choose which of your agents are managers. Everyone else is a worker.
2. **Workers only add to a card.** A worker can write a work report, a handover or a comment. It can never open a card or move one.
3. **Only the orchestrator moves cards.** A single Claude Code session, started by the `/forge-run` command, is the only agent allowed to move a card between columns. You can move cards too.

A handover between agents is refused unless it carries 5 fields: what was done, the decisions and why, where the work stands, what to do first, and warnings.

![The life of a card: who may do what at each step.](img/card-life.png)

## Why you would want it

Once you have more than a handful of agents, 3 problems appear.

- **Nobody can see what happened.** An agent finished a job on Tuesday. On Friday you, or another agent, have no written record of which files it made or what it left undone. The board keeps that record on the card.
- **Agents trip over each other.** 2 sessions pick up the same job, or an agent marks another agent's work as finished. The single-writer rule stops that: only the orchestrator moves cards, so there is a single place where "this is now done" gets decided.
- **Handovers are empty.** "Handed over to the editor" tells the editor nothing. The 5-field handover makes the first agent write down what the second agent needs.

It also gives you a column that is yours: **Awaiting You**. No agent ever moves a card out of it. Anything that would reach another person, such as a post, an email or a message, is stopped in Review for you to check.

## How we built it

Ashley built the original for his own agents. Every date and number below comes from his build records.

### 2026-06-12: the board in 1 day

Ashley built ProjectForge in a single day as a "work operating system" for his agents. It had a SQLite database (a single file on disk), a web server on port 3020 written in plain Python with no extra libraries, a hand-written JavaScript board, and a markdown copy of the board saved into his vault. He kept the engine code apart from his own settings so it could one day be packaged for other people. This download is that packaging.

The same day he added an always-on background program that checked the board every 15 minutes for overdue, stale, stuck and unowned cards, and archived cards done more than 14 days earlier. It used no AI.

### 2026-06-13: other systems feed in, and the orchestrator loop

Small scripts, called adapters, read Ashley's other systems and pushed their work onto the board every 30 minutes. Re-running never created copies: each card was matched on the source program plus that program's own ID.

Then the orchestrator loop: `/api/next` ranks the ready cards, `/api/dispatch` claims a card (Ready to In Progress), and `/api/commit` records the agent's report and moves the card. The `/forge-run` command in Claude Code runs that loop.

He also switched on an autonomous mode: a Windows Scheduled Task that started `claude -p "/forge-run"` with no window every 15 minutes.

2 bugs appeared that day and were fixed:

- The limit of 10 cards in progress was filled by 18 cards that only mirrored facts from other systems, so no real card could ever be handed out. The fix was an 8th column, **Tracking**, that never counts against the limit.
- A card the orchestrator had just claimed could be dragged back to its old column by the next 30-minute sync. The fix was a flag on the card: once the orchestrator has claimed it, a sync may no longer change its column.

### 2026-06-14: git, a desktop app, and the single-writer ruling

The code went into git (33 files, 5,011 lines) and was packaged as a desktop app. Ashley then set the rule this download is built around: managers open cards, workers only add reports, handovers and comments, and only the orchestrator moves a card. The shared tool `forge_agent.py` was built so every agent writes to the board the same way.

He also measured a 7-day starting point: **3 cards done, 18 times Ashley stepped in, 4 cards handed out**. That told him the automatic loop was not yet earning its keep.

### 2026-07-08: the timer was switched off

The board cost nothing to run. The timer did. Every 15 minutes Windows started a fresh Claude session to run `/forge-run`, whether or not there was work, and each start paid for a full session before looking at the board. The board was usually empty.

The surviving log shows **304 passes between 2026-07-04 and 2026-07-08, about 69 a day, and every one found 0 cards to hand out**. Of 40 passes sampled, 0 handed out any work. Ashley's records put the total at about 230 million input tokens over 30 days (that figure is from his notes, not re-measured). On 2026-07-08 he switched it off completely.

His one-line summary: a free board wearing an expensive alarm clock. The fix: never start Claude unless a cheap check shows a card is ready.

> **Note:** On 2026-07-19 a single orchestrator pass was measured on Anthropic's smallest model at that time, run from a folder with no list of agents loaded: it cost $0.094. The cost of a pass depends heavily on how many agents and instructions each session loads.

### 2026-07-19: the rebuild plan and the handover standard

Ashley wrote a new plan in a single day, in 3 rounds: version 1, a critique, version 2, a critique, version 3. The aim: agents that work like independent employees, with Ashley needed "barely ever". The same evening he ruled that "handoff occurred at [time]" is not a handover, and set the 5 fields. The first stage of the plan made timestamps honest (a sync no longer counts as activity) and made every write name who made it.

The plan said the database should refuse a thin handover. **That refusal was never built** in the original. The rule only worked when the person recording the work remembered it.

### 2026-09-22: what changed for this download

- **The handover refusal is built.** The board now refuses a handover missing any of the 5 fields, and the decisions field must say why (it must contain "because", or say "none").
- **The single-writer rule is checked inside the database code**, not only in the agents' instructions. A worker that tries to open or move a card gets a clear refusal.
- **No timer by default.** You run `/forge-run` when you want it. The optional schedule runs a Python check first and exits without starting Claude when nothing is ready.
- **Agents write straight into the database**, so their reports are kept even when the web board is closed. In the original, a report sent while the board was down was not recorded: the tool printed a warning and carried on.
- The "Awaiting Ashley" column is now "Awaiting You". Every folder path comes from a single settings file the installer writes. The desktop app, the adapters written for Ashley's own systems and the self-repair step were left out.

![A worker trying to open a card, a worker trying to move its own card, and a thin handover. The board refuses all 3.](img/refusals.png)

## Pros and cons

| | For | Against |
|---|---|---|
| Cost | The board, the health check and the CRM reader use no AI and cost nothing to run. | Each `/forge-run` is a full Claude Code session. Ashley's timer ran about 69 of them a day for no work. Only run it when something is ready. |
| Visibility | A single place to see what every agent did, on which job, with which files and what comes next. | Agents only write to it if their instructions say so. Before 2026-06-14, 0 of Ashley's 77 agent files wrote to his board. |
| Safety | Only the orchestrator moves cards; Awaiting You is never touched by an agent; outward work stops in Review. | It is a guard rail, not a lock. An agent that gives a false name gets through. |
| Handovers | Thin handovers are refused at the database. | Agents need a few extra lines of instruction to write good ones. |
| Busy-work | A queue makes waiting work obvious. | A board that hands out work invites agents to create work. Ashley's first week: 3 cards done against 18 times he stepped in. |
| Size | About 4,300 lines of plain Python and plain JavaScript. Your own Claude can read and change all of it. | With 3 to 5 agents, a simple list in your vault may be enough. The board pays off when agents hand work to each other. |
| Time | Install takes about 5 minutes. | Wiring your agents in (the lines for CLAUDE.md and each agent file) takes 20 to 30 minutes. |

## Before you start

| You need | How to check |
|---|---|
| Python 3.9 or newer (tested on 3.13) | Open a terminal and type `python --version`. On a Mac use `python3 --version`. |
| Git | `git --version` |
| Claude Code, logged in | `claude --version`. Tested on version 2.1.278 on 2026-09-22. |
| Your second brain vault | You know its folder, for example `C:\Users\<you>\Documents\Second Brain`. |
| Your agents folder | Usually `C:\Users\<you>\.claude\agents` (Windows) or `~/.claude/agents` (Mac). |
| Optional: your CRM vault | The folder that contains `Today.md` and `People/`. |
| Optional, for the tests: pytest | `python -m pytest --version`. If missing: `python -m pip install pytest`. |

Node.js is not needed. Nothing is installed from the internet: the board uses only the Python standard library.

## Install it

1. Open a terminal in the folder where you keep your tools, for example your Documents folder.
2. Download the code and start the installer:

```
git clone https://github.com/OUTLIERS-ai/outliers-ws-03-projectforge && cd outliers-ws-03-projectforge && python install.py
```

3. Answer the 8 questions. Each one offers a default in square brackets; press Enter to accept it.
   - Your second brain vault folder.
   - Your CRM vault folder, or `none`.
   - Your agents folder. The installer lists every agent it finds.
   - Which agents are **managers** (may open cards). Leave blank and only you open cards.
   - Which agents send work to other people. Their finished cards stop in Review.
   - What the board calls you (default `you`).
   - Where the `/forge-run` command goes: `user` (every Claude Code session) or `vault` (only sessions in your second brain).
   - Where to write the board summary note in your vault, or `none`.
4. The installer shows every file it is about to write and asks "Go ahead?". Type `y`.
5. When it worked you see a list of `done:` lines like this:

![What a finished install looks like (made-up test folders).](img/install-output.png)

6. Open the board: `python forge.py serve`, then visit `http://127.0.0.1:3020` in your browser. There is no login and no wait. The board is empty: the installer creates a fresh database with no cards.
7. Open the file `data/CLAUDE-snippet.md` inside the download folder. Paste the first part into your `CLAUDE.md` and the second part into each worker agent's file. This is what makes your agents log their work.
8. In Claude Code, type `/forge-run dry`. It reports what it would do and changes nothing.

> **Tip:** Want to see a full board first? Run `python tools/demo_board.py --out demo --serve` and open `http://127.0.0.1:3029`. It builds a separate demo board of made-up work and does not touch your real one.

> **Note:** If a file called `forge-run.md` already exists in your commands folder, the installer copies it to `forge-run.md.bak-<date>` before replacing it. Running the installer a second time with the same answers changes nothing. `python install.py --uninstall` removes the command and the agents' tool, puts your old command back, and leaves your board data alone.

## Using it day to day

**Adding work.** Click "+ Add card" at the foot of a column, or "+ Project" at the top. From the terminal: `python forge.py add-task <project-id> "Draft 3 posts" --status ready --agent writer-bot`. A manager agent uses `forge_agent.py open`.

**Letting the agents work.** When cards are sitting in Ready, type `/forge-run` in Claude Code. The orchestrator:

1. checks how many cards can be handed out, and stops straight away if the answer is 0;
2. gives ownerless Backlog cards an owner and moves owned Backlog cards to Ready;
3. for each ready card: claims it, starts the owner agent with the card's full history, records the agent's report, and moves the card to the column its result points to.

**Reading a card.** Click it. The top shows the owner, the CRM person link and the checklist. Further down are the work reports and the handovers, each with its 5 fields.

![A card open: the work report, the files it made, and a full 5-field handover.](img/card-handover.png)

**The Queue tab** shows the ready cards in the order they would be handed out (priority, then due date, then age) and says why a card cannot go: it has no owner, it is yours, or the in-progress limit is reached.

![The queue: 2 cards can be handed out, 1 is yours, 1 has no owner.](img/queue.png)

**The Agents tab** shows each agent's open cards and its last 8 results.

![Work grouped by agent.](img/agents.png)

**Your column.** Check Awaiting You once a day. Everything there needs you: a decision, a call, a sign-off.

**Health check.** `python forge.py hygiene` lists overdue, stale, stuck and unowned cards. It uses no AI. `python forge.py daemon` keeps the board open and runs that check every 60 minutes.

**Useful commands.**

| Command | What it does |
|---|---|
| `python forge.py list` | Open cards in the terminal. |
| `python forge.py waiting` | How many cards a `/forge-run` could hand out now. Writes nothing. |
| `python forge.py show <card>` | A card in full. |
| `python forge.py metrics` | Cards finished, cards sent backwards, how often you stepped in, over 7 days. |
| `python tools/run_if_ready.py` | Starts `/forge-run` only if a card is ready. |

## Fit it to your own AI system

Each idea below comes with a prompt you can paste into Claude Code, opened in the ProjectForge folder.

### 1. Cards from your CRM's Today page

The download includes `adapters/crm_today.py`. It reads the ranked table on `Today.md` in your CRM vault and makes a card for each person in Awaiting You, linked to that person's note in `People/`. Running it again updates the same cards instead of copying them. It never sends anything. On the card, the person's note opens in Obsidian with a click.

![A card in Awaiting You, linked to a person note in the CRM vault.](img/card-crm.png)

```
Run python adapters/crm_today.py --dry-run and show me the result. If it looks right, run it for real. Then add one line to my CRM's morning routine so that after Today.md is rebuilt, crm_today.py runs straight after it.
```

### 2. Your second brain agents as owners and managers

```
Read config.json. Then read every agent file in my agents folder. Suggest which agents should be managers (they plan work and hand it out) and which are workers (they do one kind of job). Show me the list, and when I agree, re-run python install.py with --managers set to the ones I approve.
```

### 3. Teach each agent to leave a proper report

```
Open data/CLAUDE-snippet.md. For each worker agent file in my agents folder, add the WORK REPORT paragraph at the end if it is not already there, and add one line telling it to log that report with forge_agent.py pass. Show me the change for each file before saving it, and back up each file first.
```

### 4. Content engine runs as cards

```
Read my content engine folder at <path to your content engine>. Write adapters/content_engine.py, modelled on adapters/crm_today.py, that creates one card per content piece the engine has made in the last 7 days, with the draft's file path in context_ref, owned by my editor agent, starting in Review. It must never publish anything. Add a test in tests/ and run python -m pytest -q.
```

### 5. "Awaiting You" in your daily note

```
Write tools/daily_block.py. It reads the board and writes a section called "Waiting for me" into today's daily note in my second brain (find the daily notes folder by looking at my vault), listing every card in Awaiting You and every card in Review. Replace only that section, never the rest of the note, and write via a temporary file and os.replace. No AI.
```

### 6. Route cards by keyword

```
In config.json, fill intake.routing so that a card with "podcast" in its title goes to my podcast agent, "invoice" goes to my admin agent, and "thumbnail" goes to my design agent. Use the real agent names from config.json "agents". Then add a test to tests/test_store.py proving one card is routed correctly, and run the tests.
```

### 7. Every card must name the number it moves

Ashley's worry about busy-work was agents creating work to stay busy. A cure is to refuse any card that does not say which goal it serves.

```
Add a "goal" field to cards in engine/db.py (with a migration like the others). Make open_card refuse a card whose goal is empty, with a clear message. Show the goal on the card in the viewer. Add tests for the refusal and run python -m pytest -q.
```

### 8. The optional schedule, set up safely

```
Run python tools/schedule.py --print and explain each line to me. Then set schedule.model in config.json to "sonnet" and schedule.every_min to 120. Do not install the schedule until I say yes.
```

### 9. Limits per agent

```
For my 3 busiest worker agents, create a file in cards/ modelled on cards/example-agent.json.example. Limit each to its own department and to 5 hand-outs a day. Run python forge.py cards --validate and show me the result.
```

## When it goes wrong

These are the real faults from Ashley's build and from testing this download, with the fix for each.

| What you see | Why | Fix |
|---|---|---|
| Your Claude usage climbs while nothing gets done. | A timer is starting Claude on an empty board. This was Ashley's biggest automatic cost in July 2026. | Never put `claude -p "/forge-run"` on a timer. Use `tools/run_if_ready.py`, which exits without starting Claude when nothing is ready. |
| Nothing is ever handed out, but cards sit in Ready. | The in-progress limit (default 10) is full. In the original this happened because 18 mirror cards filled it. | Put cards that only report a fact from another system in Tracking, which never counts. Check with `python forge.py next`. |
| A card jumps back to an older column. | Another program re-sent it with its old column. | Already fixed: once the orchestrator claims a card, a re-send can no longer change its column. |
| "refused: ... is a worker and may not move a card" | The single-writer rule. An agent tried to move a card. | Working as intended. The agent should log a report with `forge_agent.py pass`; `/forge-run` moves the card. |
| "handover refused - a handover must carry all 5 fields" | A thin handover. | Fill in `--done`, `--decisions` (with "because"), `--state`, `--next-first` and `--warnings` ("none" is fine). |
| Your vault note was overwritten by a demo board. | During research on 2026-09-22, a copied settings file still pointed at a real vault note. It was restored from git. | The summary note is now off unless you confirm its path in the installer, and the demo board never writes one. |
| The orchestrator reports "bad json". | In the original, an em dash typed into a command's text broke the request. | `/forge-run` now uses `forge.py` commands instead of web requests. Still type hyphens, not em dashes. |
| "address already in use" when you run `serve`. | Another program, or a second copy of the board, is using port 3020. | `python forge.py serve --port 3021`, or change `port` in config.json. |
| An agent says the board was not found. | `forge_agent.json` is missing next to the tool. | Re-run `python install.py`. Or set the environment variable `FORGE_DIR` to the download folder. |

## Download

The code: https://github.com/OUTLIERS-ai/outliers-ws-03-projectforge

Clone and install with a single command:

```
git clone https://github.com/OUTLIERS-ai/outliers-ws-03-projectforge && cd outliers-ws-03-projectforge && python install.py
```
