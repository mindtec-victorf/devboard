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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boardlib import apply as batch  # noqa: E402
from boardlib import rollout, store  # noqa: E402
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
    for key in ("blocked", "waiting", "next"):
        if c.get(key):
            s += f" | {key}: {c[key]}"
    if c.get("messages_open"):
        s += f" | inbox: {c['messages_open']}"
    if c.get("files_count"):
        s += f" | files: {c['files_count']}"
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
    ch = changes_from(a, b.card(a.card).get("tags") or [])
    if not ch and not a.note:
        raise store.BoardError("nothing to change (see devboard.py set --help)")
    print(line(b.set(a.card, ch, note=a.note, by=a.by)))


def cmd_note(a):
    print(line(pick(a).note(a.card, a.text, by=a.by)))


def cmd_check(a):
    print(line(pick(a).check(a.card, a.item, done=not a.undo, by=a.by)))


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


def cmd_move(a):
    print(line(pick(a).move(a.card, a.status, by=a.by)))


def cmd_inbox(a):
    msgs = pick(a).inbox()
    if a.json:
        return out_json(msgs)
    for m in msgs:
        print(f"{m['card']}#{m['n']} {m['ts'][:16].replace('T', ' ')} {m['by']}: {m['text']}  ({m['title']})")
    print(f"{len(msgs)} message(s) waiting; answer with devboard.py reply <card> <n> \"...\"" if msgs
          else "nothing waiting for the agent")


def cmd_reply(a):
    m = pick(a).reply(a.card, a.n, a.text, by=a.by)
    print(f"{a.card}#{m['n']} answered")


def cmd_attach(a):
    f = pick(a).attach(a.card, a.path, link=a.link, by=a.by)
    print(f"{a.card}: attached {f['name']} ({f['mode']}, {f['size']} B, sha1 {f['sha1'][:12]})")


def cmd_detach(a):
    pick(a).detach(a.card, a.name, by=a.by)
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


def hint_line(bid, cs):
    doing = sum(c["column"] in ("doing", "final") for c in cs)
    blocked = sum(c["column"] == "blocked" for c in cs)
    waiting = sum(c.get("messages_open", 0) for c in cs)
    inbox = f" · {waiting} messages for the agent (devboard.py inbox; answer them before moving on)" if waiting else ""
    return (f"Board {bid}: {len(cs)} cards ({doing} in progress, {blocked} blocked){inbox} — "
            f"python3 {Path(__file__).resolve()} summary")


def cmd_hook(a):
    """SessionStart hook: reads the hook JSON on stdin; prints additionalContext only inside a board's repo."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        bid = store.resolve(payload.get("cwd") or os.getcwd())
        if not bid:
            return
        line = hint_line(bid, store.Board(bid).cards())
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": f"<devboard>\n{line}\n</devboard>"}}))
    except Exception:  # noqa: BLE001 — a hook must never break session start
        return


def cmd_hint(a):
    """One line for the SessionStart hook; prints nothing (exit 0) when there is no board."""
    try:
        bid = store.resolve(a.cwd)
        if not bid:
            return
        cs = store.Board(bid).cards()
        doing = sum(c["column"] in ("doing", "final") for c in cs)
        blocked = sum(c["column"] == "blocked" for c in cs)
        waiting = sum(c.get("messages_open", 0) for c in cs)
        print(hint_line(bid, cs))
    except Exception:  # noqa: BLE001 — a hint must never break session start
        return


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--board", help="board id (default: found from the current folder)")
    common.add_argument("--by", default=os.environ.get("BOARD_ACTOR", "agent"), help="who writes (default agent)")
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
    sp.add_argument("--template", help="board template (default: stages; etapas when DEVBOARD_LANG=pt-BR)")
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
    sp = cmd("move", cmd_move, "move a card to a column (leaving blocked clears the reason)")
    sp.add_argument("card")
    sp.add_argument("status", choices=COLUMNS)
    cmd("inbox", cmd_inbox, "messages the humans left for the agent (read at the start of a round)")
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
    sp = cmd("hint", cmd_hint, "one-line hint for a SessionStart hook")
    sp.add_argument("--cwd", required=True)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a) or 0
    except store.Conflict as e:
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
