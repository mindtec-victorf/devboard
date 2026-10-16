"""Read-only adapter: a rollout ledger (STATUS.json) shown as a board, one card per unit.

The ledger is {"meta": {"phases"|"fases": [...], "project"|"projeto": ...},
"units"|"unidades": {id: {"phase"|"fase", "status", "blockers"|"bloqueios", "result"|"resultado", "ts"}}}.
Both the English keys and the Portuguese ones written by the original rollout kit are read.

Sources, in this order: <dir>/*/STATUS.json for each dir in rollout_dirs() (sorted), then the paths in
<board home>/_rollouts.json (written by `devboard.py link-rollout`). Board id =
"rollout-<folder slug>", with -2, -3 on collisions. Writes go through the command-center's
own scripts/lib/ledger.py, never through here.
"""
import json
import os
import re
from pathlib import Path

from . import store

STATUS_TAGS = {"falhou": "failed", "failed": "failed", "revisar_humano": "needs human", "needs_human": "needs human",
               "held": "held"}
PENDING = ("pendente", "pending")


def _get(d, *keys, default=None):
    for k in keys:
        if k in d:
            return d[k]
    return default


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30].strip("-") or "x"


def rollout_dirs():
    """Folders scanned for <rollout>/STATUS.json: $DEVBOARD_ROLLOUTS (os.pathsep-separated), default <home>/rollouts."""
    raw = os.environ.get("DEVBOARD_ROLLOUTS")
    return [Path(p).expanduser() for p in raw.split(os.pathsep) if p] if raw else [store.home() / "rollouts"]


def _extra_file():
    return store.home() / "_rollouts.json"


def _extra_paths():
    f = _extra_file()
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return []
    return [Path(p) for p in data if isinstance(p, str)]


def sources():
    paths = []
    for base in rollout_dirs():
        paths += sorted(base.glob("*/STATUS.json")) if base.exists() else []
    paths += [p for p in _extra_paths() if p.exists()]
    out, seen = {}, set()
    for p in paths:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        bid = base_id = store.ROLLOUT_PREFIX + _slug(rp.parent.name)
        n = 2
        while bid in out:
            bid, n = f"{base_id}-{n}", n + 1
        out[bid] = rp
    return out


def link(path):
    p = Path(path).expanduser().resolve()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise store.BoardError(f"cannot read {p}: {e}") from None
    if not isinstance(data, dict) or not ("units" in data or "unidades" in data):
        raise store.BoardError(f"{p} is not a ledger STATUS.json (no 'units'/'unidades')")
    current = [str(x) for x in _extra_paths()]
    if str(p) not in current:
        store.atomic_write(_extra_file(), json.dumps(current + [str(p)], ensure_ascii=False, indent=2) + "\n")
    return next(bid for bid, sp in sources().items() if sp == p)


def open_rollout(bid):
    src = sources()
    if bid not in src:
        raise store.NotFound(f"rollout board {bid!r} not found (devboard.py boards lists them)")
    return RolloutBoard(bid, src[bid])


class RolloutBoard:
    readonly = True
    kind = "rollout"

    def __init__(self, bid, path):
        self.id, self.path = bid, path
        self.data = json.loads(path.read_text(encoding="utf-8"))
        meta = self.data.get("meta") or {}
        self.units = _get(self.data, "units", "unidades", default={}) or {}
        self.fases = list(_get(meta, "phases", "fases", default=[]) or [])
        extra = [_get(u, "phase", "fase") for u in self.units.values()
                 if _get(u, "phase", "fase") and _get(u, "phase", "fase") not in self.fases]
        columns = list(dict.fromkeys(self.fases + extra))  # unknown phases go last, never hidden
        self.meta = {"id": bid, "title": _get(meta, "project", "projeto") or path.parent.name, "repos": [],
                     "columns": {f: f.replace("_", " ").capitalize() for f in columns},
                     "source": str(path), "objective": _get(meta, "goal", "objetivo")}

    def card_ids(self):
        return sorted(self.units)

    def card(self, cid):
        u = self.units.get(cid)
        if u is None:
            raise store.NotFound(f"unit {cid!r} not found in {self.id!r}")
        fase = _get(u, "phase", "fase") or (self.fases[0] if self.fases else "")
        prog = None
        if fase in self.fases and len(self.fases) > 1:
            prog = round(self.fases.index(fase) * 100 / (len(self.fases) - 1))
        status = u.get("status") or "pending"
        tags = [STATUS_TAGS[status]] if status in STATUS_TAGS else []
        if _get(u, "needs_human", "revisar_humano") and "needs human" not in tags:
            tags.append("needs human")
        res = _get(u, "result", "resultado", default={}) or {}
        return {"id": cid, "title": cid, "column": fase, "progress": prog, "progress_source": "phase",
                "status": status, "started": status not in PENDING, "tags": tags,
                "blocked": "; ".join(_get(u, "blockers", "bloqueios", default=[]) or []) or None,
                "situation": ", ".join(f"{k}={v}" for k, v in sorted(res.items())) or None,
                "updated": u.get("ts"), "etag": ""}

    def cards(self):
        return [self.card(c) for c in self.card_ids()]

    def history(self, limit=50):
        evs = [{"ts": u.get("ts") or "", "by": "ledger", "kind": "state", "card": cid, "seq": 0,
                "note": f"phase {_get(u, 'phase', 'fase')} · {u.get('status') or 'pending'}"}
               for cid, u in self.units.items()]
        evs.sort(key=lambda e: (store._ts(e["ts"]), e["card"]), reverse=True)
        return evs[:limit] if limit else evs

    def events(self, cid):
        return [e for e in self.history(0) if e["card"] == cid]

    def detail(self, cid, events=5):
        view = self.card(cid)
        view["md"] = ""
        view["events"] = self.events(cid)
        view["messages"], view["files"] = [], []
        return view

    def pending(self):
        return [c for c in self.cards() if c["blocked"] or c["tags"]]

    def rev(self):
        st = self.path.stat()
        return f"{st.st_mtime_ns:x}-{st.st_size:x}"

    def validate(self):
        return []

    def audit(self):
        return {}

    def _read_only(self, *args, **kwargs):
        raise store.ReadOnly("rollout boards are read-only; write through the command-center's scripts/lib/ledger.py")

    add = set = note = check = move = message = reply = attach = attach_stream = detach = _read_only

    def messages(self, cid):
        return []

    def inbox(self):
        return []

    def files(self, cid):
        return []

    def file_path(self, cid, name):
        raise store.NotFound("rollout boards have no attachments")
