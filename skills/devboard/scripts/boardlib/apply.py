"""Batch ops from one JSON file: validate ALL ops first (no write), then run them in order.

File: {"board": "<id>", "ops": [{"op": ..., "card": "<id>", ...}, ...]}
  add   -> title, fields?, md?        set   -> changes?, note?
  note  -> text                        check -> item (1-based), done? (default true)
Every event carries src="apply:<sha1(file)[:8]>", so the batch is traceable in history.
The same file on an empty board always builds the same board.
"""
import hashlib
import json
from pathlib import Path

from . import derive, store


def load(path):
    raw = Path(path).read_bytes()
    try:
        spec = json.loads(raw)
    except ValueError as e:
        raise store.BoardError(f"{path}: invalid JSON ({e})") from None
    if not isinstance(spec, dict) or not isinstance(spec.get("ops"), list):
        raise store.BoardError(f'{path}: expected {{"board": "<id>", "ops": [...]}}')
    return spec, "apply:" + hashlib.sha1(raw).hexdigest()[:8]


def _plan_one(board, op, known):
    if not isinstance(op, dict):
        raise store.BoardError("must be an object")
    kind, cid = op.get("op"), store.check_id("card", op.get("card"))
    if kind == "add":
        if cid in known:
            raise store.BoardError(f"card {cid!r} already exists")
        data = store.validate_changes({**(op.get("fields") or {}), "title": op.get("title")})
        md = op.get("md")
        if md is not None and not isinstance(md, str):
            raise store.BoardError("md must be text")
        known[cid] = board.render_template(data["title"]) if md is None else md
        if data.get("progress") is not None and derive.checklist(known[cid]):
            raise store.BoardError("progress comes from the checklist; use check")
        return {"op": "add", "card": cid, "title": data.pop("title"), "fields": data, "md": md}
    if kind not in ("set", "note", "check"):
        raise store.BoardError(f"unknown op {kind!r} (add, set, note, check)")
    if cid not in known:
        raise store.BoardError(f"card {cid!r} not found")
    if kind == "set":
        changes = store.validate_changes(op.get("changes") or {})
        note = (op.get("note") or "").strip() or None
        if changes.get("progress") is not None and derive.checklist(known[cid]):
            raise store.BoardError("progress comes from the checklist; use check")
        if not changes and not note:
            raise store.BoardError("set needs changes or note")
        return {"op": "set", "card": cid, "changes": changes, "note": note}
    if kind == "note":
        text = op.get("text")
        if not isinstance(text, str) or not text.strip():
            raise store.BoardError("note needs text")
        return {"op": "note", "card": cid, "text": text.strip()}
    n, done = op.get("item"), op.get("done", True)
    if isinstance(n, bool) or not isinstance(n, int) or not isinstance(done, bool):
        raise store.BoardError("check needs an integer item and a true/false done")
    try:
        known[cid] = derive.toggle(known[cid], n, done)[0]
    except IndexError as e:
        raise store.BoardError(str(e)) from None
    return {"op": "check", "card": cid, "item": n, "done": done}


def plan(board, ops):
    """Validate every op against the board plus the earlier ops. Writes nothing."""
    if board.readonly:
        raise store.ReadOnly("rollout boards are read-only")
    known = {cid: board._read(cid)[1] for cid in board.card_ids()}  # card id -> .md as it will be
    out = []
    for i, op in enumerate(ops, 1):
        try:
            out.append(_plan_one(board, op, known))
        except store.BoardError as e:
            raise store.BoardError(f"op {i}: {e}") from None
    return out


def run(board, ops, src, by="agent"):
    for op in ops:
        cid = op["card"]
        if op["op"] == "add":
            board.add(cid, op["title"], op["fields"], op["md"], by=by, src=src)
        elif op["op"] == "set":
            board.set(cid, op["changes"], note=op["note"], by=by, src=src)
        elif op["op"] == "note":
            board.note(cid, op["text"], by=by, src=src)
        else:
            board.check(cid, op["item"], op["done"], by=by, src=src)
    return len(ops)
