"""Derived card fields — pure functions, no I/O.

Progress comes from the card's checklist when its .md has one; otherwise from the
card's own `progress`. The column is the pinned `status` when a person dragged the card (or
the agent ran `set --status`); otherwise it is computed from blocked/waiting/progress/started.
"""
import re

# Same regexes and line rule as web/app.js, so the page's checkbox N is the item N ticked here.
CHECK_RE = re.compile(r"^([ \t]*[-*][ \t]+)\[( |x|X)\]([ \t][^\n]*)?$")
FENCE_RE = re.compile(r"^[ \t]*```")
BOM = "\ufeff"
COLUMNS = ("todo", "blocked", "doing", "final", "done")


def _lines(md):
    """Split like the page: on \\n only, minus a leading BOM and each line's trailing \\r."""
    body = md or ""
    if body.startswith(BOM):
        body = body[1:]
    return [line[:-1] if line.endswith("\r") else line for line in body.split("\n")]


def checklist(md):
    """[(line_index, done, text)] for each '- [ ]'/'- [x]' line outside fenced code, in order."""
    items, fenced = [], False
    for i, line in enumerate(_lines(md)):
        if FENCE_RE.match(line):
            fenced = not fenced
            continue
        m = None if fenced else CHECK_RE.match(line)
        if m:
            items.append((i, m.group(2) != " ", (m.group(3) or "").strip()))
    return items


def progress(card, md):
    items = checklist(md)
    if items:
        return round(sum(1 for _, done, _ in items if done) * 100 / len(items))
    return card.get("progress")


def progress_source(md):
    return "checklist" if checklist(md) else "manual"


def column(card, prog):
    if card.get("status") in COLUMNS:  # set by a drag on the page or `set --status`
        return card["status"]
    if card.get("blocked") or card.get("waiting"):
        return "blocked"
    if prog == 100:
        return "done"
    if prog is not None and prog >= 90:
        return "final"
    if card.get("started") or (prog or 0) > 0:
        return "doing"
    return "todo"


def toggle(md, n, done):
    """Return (new_md, item_text) with checklist item n (1-based) set to done/undone."""
    items = checklist(md)
    if not 1 <= n <= len(items):
        raise IndexError(f"checklist has {len(items)} item(s); got {n}")
    idx, _, text = items[n - 1]
    bom = BOM if md.startswith(BOM) else ""
    raw = md[len(bom):].split("\n")
    cr = "\r" if raw[idx].endswith("\r") else ""
    m = CHECK_RE.match(raw[idx][:len(raw[idx]) - len(cr)])
    raw[idx] = f"{m.group(1)}[{'x' if done else ' '}]{m.group(3) or ''}{cr}"
    return bom + "\n".join(raw), text
