#!/usr/bin/env python3
"""devboard.py — local project board (cards + checklist + history) for agents and humans.

Data: $DEVBOARD_HOME/<board>/ (default ~/.devboard). Never inside a repo.
The board is found from --board, or from the current folder (board.json "repos").
Exit codes: 0 ok · 1 findings (validate/audit) · 2 usage error · 3 conflict.
Run `devboard.py <command> --help` for the flags of each command.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boardlib import apply as batch  # noqa: E402
from boardlib import agents, rollout, store  # noqa: E402
from boardlib.derive import COLUMNS  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def _fmt(v):
    if v is None or v == []:
        return "—"
    return ", ".join(v) if isinstance(v, list) else str(v)


def line(c):
    pct = "—" if c.get("progress") is None else f"{c['progress']}%"
    prio = f"P{c['priority']}" if c.get("priority") else "-"
    s = f"{c['id']:>4} {c['column']:<7} {pct:>4} {prio:<3} {c['title']}"
    for key in ("assignee", "blocked", "waiting", "next"):
        if c.get(key):
            s += f" | {'for' if key == 'assignee' else key}: {c[key]}"
    if c.get("messages_open"):
        s += f" | inbox: {c['messages_open']}"
    if c.get("requests_open"):
        s += f" | asked the user: {c['requests_open']}"
    if c.get("files_count"):
        s += f" | files: {c['files_count']}"
    if c.get("claimed_by"):
        s += f" | claimed: {c['claimed_by']['agent']} (until {store.short_time(c['claimed_by']['until'])})"
    return s


def ev_line(e):
    changes = "; ".join(f"{k}: {_fmt(p[0])} → {_fmt(p[1])}" for k, p in (e.get("changes") or {}).items())
    head = [e.get("ts", "")[:16].replace("T", " ")]
    if e.get("card") is not None:
        head.append(f"#{e['card']}")
    head += [e.get("by", ""), e.get("kind", "")]
    return " ".join(head + [x for x in (changes, e.get("note")) if x])


def out_json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def pick(a):
    bid = a.board or store.resolve(os.getcwd())
    if not bid:
        names = ", ".join(b for b, _ in store.list_boards()) or "none yet (devboard.py init)"
        raise store.BoardError(f"no board for {os.getcwd()}; pass --board (boards: {names})")
    return store.open_board(bid)


def changes_from(a, current_tags=()):
    ch = {}
    if a.cmd == "set" and a.title is not None:
        ch["title"] = a.title
    if getattr(a, "status", None) is not None:
        ch["status"] = None if a.status == "auto" else a.status
    if a.progress is not None:
        ch["progress"] = a.progress
    if a.start:
        ch["started"] = True
    if a.block is not None:
        ch["blocked"] = a.block
    if a.unblock:
        ch["blocked"] = None
    if a.wait is not None:
        ch["waiting"] = a.wait
    if a.unwait:
        ch["waiting"] = None
    if a.assignee is not None:
        ch["assignee"] = a.assignee
    if a.unassign:
        ch["assignee"] = None
    if a.priority is not None:
        ch["priority"] = a.priority
    if a.no_priority:
        ch["priority"] = None
    if a.tag or a.untag:
        ch["tags"] = [t for t in dict.fromkeys([*current_tags, *a.tag]) if t not in a.untag]
    for key in ("estimate", "due", "situation", "next"):
        if getattr(a, key) is not None:
            ch[key] = getattr(a, key)
    return ch


# --- commands (return an exit code or None for 0) ---

def cmd_boards(a):
    rows = [r for r in store.overview() if a.all or not r["archived"]]
    if a.json:
        return out_json(rows)
    for r in rows:
        if r["archived"]:
            print(f"{r['id']}  {r['kind']}  archived — {r['title']}")
            continue
        if r.get("error"):
            print(f"{r['id']}  {r['kind']}  error: {r['error']}")
            continue
        print(f"{r['id']}  {r['kind']}  {r['cards']} cards, {r['done']} done — {r['title']}")
    if not rows:
        print("no boards yet (devboard.py init <id> --title ... --repo <folder>)")


def cmd_archive(a):
    store.archive(a.id, by=a.by)
    print(f"board {a.id} archived (devboard.py unarchive {a.id} brings it back)")


def cmd_unarchive(a):
    store.unarchive(a.id, by=a.by)
    print(f"board {a.id} is active again")


def cmd_init(a):
    b = store.Board.init(a.id, a.title, a.repo, a.template)
    print(f"board {b.id} created at {b.dir}")


def cmd_add(a):
    b = pick(a)
    md = Path(a.md_file).read_text(encoding="utf-8") if a.md_file else None
    print(line(b.add(a.card, a.title, changes_from(a), md, by=a.by)))


def cmd_set(a):
    b = pick(a)
    warn_claim(b, a.card, a.by)
    ch = changes_from(a, b.card(a.card).get("tags") or [])
    if not ch and not a.note:
        raise store.BoardError("nothing to change (see devboard.py set --help)")
    print(line(b.set(a.card, ch, note=a.note, by=a.by)))


def cmd_note(a):
    b = pick(a)
    warn_claim(b, a.card, a.by)
    print(line(b.note(a.card, a.text, by=a.by)))


def cmd_check(a):
    b = pick(a)
    warn_claim(b, a.card, a.by)
    print(line(b.check(a.card, a.item, done=not a.undo, by=a.by)))


def cmd_summary(a):
    b = pick(a)
    cs = b.cards()
    if a.column:
        cs = [c for c in cs if c["column"] == a.column]
    if a.json:
        return out_json({"board": b.meta, "cards": cs})
    known = [c["progress"] for c in cs if c.get("progress") is not None]
    avg = f"{round(sum(known) / len(known))}%" if known else "—"
    counts = " · ".join(f"{k} {sum(1 for c in cs if c['column'] == k)}" for k in b.meta.get("columns", {}))
    waiting = sum(c.get("messages_open", 0) for c in cs)
    print(f"{b.id} — {b.meta.get('title', '')} · {len(cs)} cards · avg {avg} · {counts}"
          + (f" · inbox {waiting} (devboard.py inbox)" if waiting else ""))
    for c in cs:
        print(line(c))


def cmd_show(a):
    d = pick(a).detail(a.card, a.events)
    if a.json:
        return out_json(d)
    print(line(d))
    for key in ("situation", "estimate", "due", "tags", "updated", "etag"):
        if d.get(key):
            print(f"  {key}: {_fmt(d[key])}")
    if d.get("md", "").strip():
        print("---")
        print(d["md"].rstrip())
    for f in d.get("files") or []:
        print(f"  file: {f['name']} ({f['mode']}, {f['size']} B)")
    for m in d.get("messages") or []:
        state = "OPEN" if m["open"] else f"answered: {m['reply']['text']}"
        print(f"  message #{m['n']} {m['by']}: {m['text']} [{state}]")
    if d["events"]:
        print("--- events")
        for e in d["events"]:
            print("  " + ev_line(e))


def cmd_history(a):
    evs = pick(a).history(a.limit)
    if a.json:
        return out_json(evs)
    for e in evs:
        print(ev_line(e))


def cmd_pending(a):
    cs = pick(a).pending()
    if a.json:
        return out_json(cs)
    for c in cs:
        print(line(c))
    if not cs:
        print("nothing blocked or waiting")


def cmd_validate(a):
    probs = pick(a).validate()
    for p in probs:
        print(p)
    print(f"{len(probs)} problem(s)" if probs else "ok")
    return 1 if probs else 0


def cmd_audit(a):
    drift = pick(a).audit()
    for cid, fields in drift.items():
        print(f"{cid}: {', '.join(fields)}")
    print(f"{len(drift)} card(s) edited outside devboard.py" if drift else "ok: every card matches its history")
    return 1 if drift else 0


def cmd_apply(a):
    spec, src = batch.load(a.file)
    bid = a.board or spec.get("board") or store.resolve(os.getcwd())
    if not bid:
        raise store.BoardError("no board: set \"board\" in the file or pass --board")
    b = store.open_board(bid)
    ops = batch.plan(b, spec["ops"])
    if a.dry_run:
        print(f"ok: {len(ops)} op(s) valid for board {b.id} (dry run, nothing written)")
        return
    print(f"applied {batch.run(b, ops, src, by=a.by)} op(s) to board {b.id} (src {src})")


def agent_name(a):
    name = getattr(a, "as_", None) or os.environ.get("DEVBOARD_AGENT")
    if not name:
        raise store.BoardError("say who you are: --as <agent-name> or DEVBOARD_AGENT=<agent-name> (e.g. codex-1)")
    return name


def warn_claim(b, cid, by):
    """Writes on a card another agent claimed go through, with a warning: claims coordinate, never block."""
    try:
        c = b.card(cid).get("claimed_by")
    except store.BoardError:
        return
    if c and c["agent"] != by:
        print(f"warning: card {cid} is claimed by {c['agent']} until {store.short_time(c['until'])}"
              + (f" ({c['note']})" if c.get("note") else ""), file=sys.stderr)


def cmd_claim(a):
    print(line(pick(a).claim(a.card, agent_name(a), ttl=a.ttl, note=a.note, force=a.force)))


def cmd_release(a):
    print(line(pick(a).release(a.card, agent_name(a), note=a.note)))


def cmd_who(a):
    cs = pick(a).claims()
    if a.json:
        return out_json(cs)
    for c in cs:
        print(f"{c['card']:>4} {c['agent']} until {store.short_time(c['until'])}"
              + (f" — {c['note']}" if c.get("note") else "") + f"  ({c['title']})")
    if not cs:
        print("nobody has claimed a card")


def cmd_move(a):
    b = pick(a)
    warn_claim(b, a.card, a.by)
    print(line(b.move(a.card, a.status, by=a.by, rank=a.rank)))


def cmd_inbox(a):
    msgs = pick(a).inbox()
    if a.json:
        return out_json(msgs)
    for m in msgs:
        print(f"{m['card']}#{m['n']} {m['ts'][:16].replace('T', ' ')} {m['by']}: {m['text']}  ({m['title']})")
    print(f"{len(msgs)} message(s) waiting; answer with devboard.py reply <card> <n> \"...\"" if msgs
          else "nothing waiting for the agent")


def cmd_ask(a):
    b = pick(a)
    m = b.ask(a.card, a.text, by=a.by)
    print(f"{a.card}#{m['n']} asked the user; the card is assigned to user until they answer "
          f"(devboard.py requests shows what is open)")


def cmd_requests(a):
    b = store.open_board(store.USER_BOARD) if a.all else pick(a)
    msgs = b.requests()
    if a.json:
        return out_json(msgs)
    for m in msgs:
        print(f"{m['card']}#{m['n']} {m['ts'][:16].replace('T', ' ')} {m['by']}: {m['text']}  ({m['title']})")
    print(f"{len(msgs)} request(s) waiting for the user" if msgs else "nothing waiting for the user")


def cmd_reply(a):
    m = pick(a).reply(a.card, a.n, a.text, by=a.by)
    print(f"{a.card}#{m['n']} answered")


def cmd_attach(a):
    b = pick(a)
    warn_claim(b, a.card, a.by)
    f = b.attach(a.card, a.path, link=a.link, by=a.by)
    print(f"{a.card}: attached {f['name']} ({f['mode']}, {f['size']} B, sha1 {f['sha1'][:12]})")


def cmd_detach(a):
    b = pick(a)
    warn_claim(b, a.card, a.by)
    b.detach(a.card, a.name, by=a.by)
    print(f"{a.card}: detached {a.name}")


def cmd_files(a):
    fs = pick(a).files(a.card)
    if a.json:
        return out_json(fs)
    for f in fs:
        print(f"{f['name']}  {f['mode']}  {f['size']} B  {f.get('path') or ''}")
    if not fs:
        print("no attachments")


def cmd_link_rollout(a):
    print(f"linked as {rollout.link(a.path)}")


def cmd_serve(a):
    from boardlib import server
    server.serve(a.port, a.open)


def hint_line(bid, cs, cwd=None):
    doing = sum(c["column"] in ("doing", "final") for c in cs)
    blocked = sum(c["column"] == "blocked" for c in cs)
    waiting = sum(c.get("messages_open", 0) for c in cs)
    claimed = sum(1 for c in cs if c.get("claimed_by"))
    agent = os.environ.get("DEVBOARD_AGENT")
    mine = sum(1 for c in cs if c["column"] != "done" and store.assignee_for(c.get("assignee"), cwd, agent))
    for_user = sum(1 for c in cs if c["column"] != "done" and c.get("assignee") == "user")
    inbox = f" · {waiting} messages for the agent (devboard.py inbox; answer them before moving on)" if waiting else ""
    inbox += f" · {mine} assigned to agents here" if mine else ""
    inbox += f" · {for_user} waiting for the user (devboard.py requests)" if for_user else ""
    inbox += f" · {claimed} claimed by agents (devboard who)" if claimed else ""
    return (f"Board {bid}: {len(cs)} cards ({doing} in progress, {blocked} blocked){inbox} — "
            f"python3 {Path(__file__).resolve()} summary")


SESSION_RE = re.compile(r"[^A-Za-z0-9_-]")


def _news(b, cwd):
    """{key: line} of what an agent working in cwd should hear about: messages from people, cards assigned
    to agents here, and the person's answers to agents' requests. Keys are stable, so each is told once."""
    agent = os.environ.get("DEVBOARD_AGENT")
    out = {}
    for c in b.cards():
        if c["column"] != "done" and store.assignee_for(c.get("assignee"), cwd, agent):
            out[f"a:{c['id']}:{c['assignee']}"] = f"card {c['id']} is assigned to {c['assignee']}: {c['title']}"
        for m in b.messages(c["id"]):
            if m["to"] == "agent" and m["open"]:
                out[f"m:{c['id']}:{m['n']}"] = f"{c['id']}#{m['n']} {m['by']} asks the agent: {m['text']}"
            elif m["to"] == "user" and not m["open"]:
                out[f"r:{c['id']}:{m['n']}"] = (f"{c['id']}#{m['n']} the user answered {m['by']}'s request "
                                                f"(\"{m['text']}\"): {m['reply']['text']}")
    return out


def _seen_file(session):
    name = SESSION_RE.sub("", str(session or ""))[:80]
    return store.home() / ".seen" / f"{name}.json" if name else None


def _load_seen(path):
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return set()


def cmd_hook(a):
    """Claude Code hook (SessionStart and UserPromptSubmit): reads the hook JSON on stdin and prints
    additionalContext only inside a board's repo. SessionStart gives the one-line summary; each prompt
    after that adds only what is new since the agent last heard (messages, assignments, answers)."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        event = payload.get("hook_event_name") or "SessionStart"
        cwd = payload.get("cwd") or os.getcwd()
        bid = store.resolve(cwd)
        if not bid:
            return
        b = store.Board(bid)
        seen_path = _seen_file(payload.get("session_id"))
        news = _news(b, cwd)
        if event == "UserPromptSubmit":
            if seen_path is None:
                return
            seen = _load_seen(seen_path)
            fresh = [line for key, line in news.items() if key not in seen]
            store.atomic_write(seen_path, json.dumps(sorted(seen | set(news))))
            if not fresh:
                return
            text = "New on board " + bid + " since your last turn:\n- " + "\n- ".join(fresh)
        else:
            if seen_path is not None:
                store.atomic_write(seen_path, json.dumps(sorted(news)))
            text = hint_line(bid, b.cards(), cwd)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event,
                                                 "additionalContext": f"<devboard>\n{text}\n</devboard>"}}))
    except Exception:  # noqa: BLE001 — a hook must never break a session or a prompt
        return


def cmd_setup_agent(a):
    cli = Path(__file__).resolve()
    if a.print:
        print(agents.snippet(cli))
        return
    path = agents.setup(a.agent, Path.home(), a.project or os.getcwd(), cli)
    print(f"devboard instructions written to {path}")


def cmd_hint(a):
    """One line for the SessionStart hook; prints nothing (exit 0) when there is no board."""
    try:
        bid = store.resolve(a.cwd or os.getcwd())
        if not bid:
            return
        cs = store.Board(bid).cards()
        doing = sum(c["column"] in ("doing", "final") for c in cs)
        blocked = sum(c["column"] == "blocked" for c in cs)
        waiting = sum(c.get("messages_open", 0) for c in cs)
        print(hint_line(bid, cs, a.cwd or os.getcwd()))
    except Exception:  # noqa: BLE001 — a hint must never break session start
        return


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--board", help="board id (default: found from the current folder)")
    common.add_argument("--by", default=os.environ.get("DEVBOARD_AGENT") or os.environ.get("BOARD_ACTOR", "agent"),
                        help="who writes (default: $DEVBOARD_AGENT, else agent)")
    common.add_argument("--json", action="store_true", help="machine-readable output")

    p = argparse.ArgumentParser(prog="devboard.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def cmd(name, fn, help_):
        sp = sub.add_parser(name, parents=[common], help=help_)
        sp.set_defaults(fn=fn)
        return sp

    def fields(sp, title_required):
        sp.add_argument("--title", required=title_required)
        sp.add_argument("--progress", type=int, help="0-100 (refused when the card has a checklist)")
        sp.add_argument("--start", action="store_true", help="mark as started")
        g = sp.add_mutually_exclusive_group()
        g.add_argument("--block", metavar="TEXT")
        g.add_argument("--unblock", action="store_true")
        g = sp.add_mutually_exclusive_group()
        g.add_argument("--wait", metavar="TEXT", help="waiting on a third party")
        g.add_argument("--unwait", action="store_true")
        g = sp.add_mutually_exclusive_group()
        g.add_argument("--for", "--para", dest="assignee", metavar="WHO",
                       help="who the card is for: user, agent, agent:<name>, agent@<repo>, agent:<name>@<repo>")
        g.add_argument("--unassign", action="store_true", help="the card is for nobody in particular")
        g = sp.add_mutually_exclusive_group()
        g.add_argument("--priority", type=int)
        g.add_argument("--no-priority", action="store_true")
        sp.add_argument("--tag", action="append", default=[])
        sp.add_argument("--untag", action="append", default=[])
        sp.add_argument("--estimate")
        sp.add_argument("--due", help="YYYY-MM-DD")
        sp.add_argument("--situation")
        sp.add_argument("--next", help="the next action (what makes the card delegable)")
        sp.add_argument("--status", choices=[*COLUMNS, "auto"], help="pin the column (auto = derived again)")

    sp = cmd("boards", cmd_boards, "list boards, rollouts included (archived ones with --all)")
    sp.add_argument("--all", action="store_true", help="include archived boards")
    sp = cmd("archive", cmd_archive, "hide a board from the page, boards and the session hint (data stays)")
    sp.add_argument("id")
    sp = cmd("unarchive", cmd_unarchive, "bring an archived board back")
    sp.add_argument("id")
    sp = cmd("init", cmd_init, "create a board")
    sp.add_argument("id")
    sp.add_argument("--title", required=True)
    sp.add_argument("--repo", action="append", default=[], help="folder linked to the board (repeatable)")
    sp.add_argument("--template", help="board template from templates/boards/ (default: stages)")
    sp = cmd("add", cmd_add, "create a card")
    sp.add_argument("card")
    sp.add_argument("--md-file", help="initial .md (default: the board's card template)")
    fields(sp, title_required=True)
    sp = cmd("set", cmd_set, "change card fields")
    sp.add_argument("card")
    sp.add_argument("--note")
    fields(sp, title_required=False)
    sp = cmd("note", cmd_note, "log a milestone on a card")
    sp.add_argument("card")
    sp.add_argument("text")
    sp = cmd("check", cmd_check, "tick checklist item N (1-based)")
    sp.add_argument("card")
    sp.add_argument("item", type=int)
    sp.add_argument("--undo", action="store_true", help="untick instead")
    sp = cmd("summary", cmd_summary, "one line per card")
    sp.add_argument("--column")
    sp = cmd("show", cmd_show, "card + .md + last events")
    sp.add_argument("card")
    sp.add_argument("--events", type=int, default=5, help="how many events (0 = all)")
    sp = cmd("history", cmd_history, "board timeline, newest first")
    sp.add_argument("--limit", type=int, default=30)
    cmd("pending", cmd_pending, "blocked and waiting cards")
    cmd("validate", cmd_validate, "check files and schema (exit 1 on problems)")
    cmd("audit", cmd_audit, "replay history vs files (exit 1 on drift)")
    sp = cmd("apply", cmd_apply, "run a batch of ops from a JSON file")
    sp.add_argument("file")
    sp.add_argument("--dry-run", action="store_true")
    sp = cmd("claim", cmd_claim, "tell other agents you are working on a card (renew by claiming again)")
    sp.add_argument("card")
    sp.add_argument("--as", dest="as_", help="your agent name (default: $DEVBOARD_AGENT)")
    sp.add_argument("--ttl", default=store.DEFAULT_TTL, help="how long the claim lasts: 30m, 2h, 1d (default 2h)")
    sp.add_argument("--note", help="what you are doing, for the others")
    sp.add_argument("--force", action="store_true", help="take over another agent's active claim (logged)")
    sp = cmd("release", cmd_release, "drop your claim on a card")
    sp.add_argument("card")
    sp.add_argument("--as", dest="as_", help="your agent name (default: $DEVBOARD_AGENT)")
    sp.add_argument("--note", help="handoff note for whoever picks it up")
    cmd("who", cmd_who, "active claims: which agent works on which card")
    sp = cmd("move", cmd_move, "move a card to a column (leaving blocked clears the reason)")
    sp.add_argument("card")
    sp.add_argument("status", choices=COLUMNS)
    sp.add_argument("--rank", type=float, help="place in the column (lower goes first); in the same column only the place changes")
    cmd("inbox", cmd_inbox, "messages the humans left for the agent (read at the start of a round)")
    sp = cmd("ask", cmd_ask, "ask the user for something; the card is for the user until they answer")
    sp.add_argument("card")
    sp.add_argument("text")
    sp = cmd("requests", cmd_requests, "requests the agents left for the user (--all: every board)")
    sp.add_argument("--all", action="store_true", help="across all boards (the automatic 'user' board)")
    sp = cmd("reply", cmd_reply, "answer message N of a card (closes it)")
    sp.add_argument("card")
    sp.add_argument("n", type=int)
    sp.add_argument("text")
    sp = cmd("attach", cmd_attach, "attach a file to a card (copied; --link keeps it in place)")
    sp.add_argument("card")
    sp.add_argument("path")
    sp.add_argument("--link", action="store_true", help="reference the file in place (live PRD, big video)")
    sp = cmd("detach", cmd_detach, "remove an attachment")
    sp.add_argument("card")
    sp.add_argument("name")
    sp = cmd("files", cmd_files, "list a card's attachments")
    sp.add_argument("card")
    sp = cmd("link-rollout", cmd_link_rollout, "show a STATUS.json outside the rollout folders ($DEVBOARD_ROLLOUTS)")
    sp.add_argument("path")
    sp = cmd("serve", cmd_serve, "serve the page on 127.0.0.1")
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--open", action="store_true", help="open the browser")
    cmd("hook", cmd_hook, "SessionStart hook entry point (reads the hook JSON on stdin)")
    sp = cmd("hint", cmd_hint, "one line about the board of this folder (prints nothing when there is none)")
    sp.add_argument("--cwd", help="folder to check (default: the current one)")
    sp = cmd("setup-agent", cmd_setup_agent, "write devboard instructions for another agent (idempotent)")
    sp.add_argument("agent", choices=sorted(agents.TARGETS), help="codex/gemini: global file; cursor/copilot/agents: per project")
    sp.add_argument("--project", help="project folder for cursor, copilot and agents (default: current folder)")
    sp.add_argument("--print", action="store_true", help="print the block instead of writing it")
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a) or 0
    except (store.Conflict, store.Claimed) as e:
        print(f"conflict: {e}", file=sys.stderr)
        return 3
    except store.BoardError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
