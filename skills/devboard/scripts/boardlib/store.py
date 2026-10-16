"""The single write door for boards and cards.

Every write: lock the board -> validate -> compare etag -> atomic replace -> append one
event. The page (server.py) and the CLI (devboard.py) both call this module; nothing else
writes. Data lives in $DEVBOARD_HOME/<board>/ (default ~/.devboard), never in a repo.
"""
import contextlib
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import unicodedata
from datetime import date, datetime
from pathlib import Path

from . import derive

try:
    import fcntl
except ImportError:  # Windows: no advisory lock; one writer at a time is still safe
    fcntl = None

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ROLLOUT_PREFIX = "rollout-"
TEXT_FIELDS = ("title", "blocked", "waiting", "estimate", "situation", "next")
FIELD_ORDER = ("id", "title", "status", "started", "progress", "blocked", "waiting", "priority",
               "tags", "estimate", "due", "situation", "next", "updated")
FIELDS = frozenset(FIELD_ORDER) - {"id", "updated"}
TEMPLATES = Path(__file__).resolve().parents[2] / "templates"


class BoardError(Exception):
    """Bad input or state; str(e) is the user-facing message."""


class NotFound(BoardError):
    pass


class ReadOnly(BoardError):
    pass


class Claimed(BoardError):
    """Another agent holds an active claim on the card."""


class Conflict(BoardError):
    def __init__(self, current):
        super().__init__("card changed since you read it; reload and retry")
        self.current = current


def default_template():
    """$DEVBOARD_TEMPLATE, else the Portuguese `etapas` when DEVBOARD_LANG is pt-*, else `stages`."""
    lang = os.environ.get("DEVBOARD_LANG", "").lower()
    return os.environ.get("DEVBOARD_TEMPLATE") or ("etapas" if lang.startswith("pt") else "stages")


AGENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
TTL_RE = re.compile(r"^(\d+)([mhd])$")
DEFAULT_TTL = "2h"


def _now_ts():
    return time.time()


def _iso(ts):
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def check_agent(name):
    if not isinstance(name, str) or not AGENT_RE.match(name):
        raise BoardError("agent name must be 1-40 letters, digits, '.', '_' or '-' (e.g. codex-1, claude-review)")
    return name


def parse_ttl(ttl):
    m = TTL_RE.match(str(ttl or "").strip())
    if not m or int(m.group(1)) <= 0:
        raise BoardError("ttl must look like 30m, 2h or 1d")
    return int(m.group(1)) * {"m": 60, "h": 3600, "d": 86400}[m.group(2)]


def _claim(evs):
    """The active claim of a card (agent, since, until, note), replayed from claim/release events."""
    cur = None
    for ev in evs:
        if ev.get("kind") == "claim":
            same = cur and cur["agent"] == ev.get("agent") and cur["until_ts"] > _ts(ev.get("ts"))
            cur = {"agent": ev.get("agent"), "since": cur["since"] if same else ev.get("ts"),
                   "until": ev.get("until"), "until_ts": ev.get("until_ts", 0), "note": ev.get("note")}
        elif ev.get("kind") == "release":
            cur = None
    if cur and cur["until_ts"] > _now_ts():
        return {k: v for k, v in cur.items() if k != "until_ts"}
    return None


def home():
    """Where boards live: $DEVBOARD_HOME, default ~/.devboard. Never inside a repo."""
    return Path(os.environ.get("DEVBOARD_HOME") or Path.home() / ".devboard").expanduser()


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _ts(value):
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return 0.0


def check_id(kind, value):
    if not isinstance(value, str) or not ID_RE.match(value):
        raise BoardError(f"invalid {kind} id {value!r}: lowercase letters, digits and '-', max 41 chars")
    return value


def check_by(by):
    if not isinstance(by, str) or not by.strip() or len(by) > 40:
        raise BoardError("by must be a short non-empty text (agent, human, ...)")
    return by.strip()


def canonical(card):
    """Fixed key order, no empty values: same card -> same bytes -> same etag."""
    out = {k: card[k] for k in FIELD_ORDER if k in card and card[k] is not None and card[k] != []}
    return json.dumps(out, ensure_ascii=False, indent=2) + "\n"


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def _int_or_none(v, low):
    return v is None or (isinstance(v, int) and not isinstance(v, bool) and v >= low)


def validate_changes(changes):
    """Normalize and validate {field: value}. Raises BoardError on the first problem."""
    if not isinstance(changes, dict):
        raise BoardError("changes must be an object")
    out = {}
    for k, v in changes.items():
        if k not in FIELDS:
            raise BoardError(f"unknown field {k!r}; allowed: {', '.join(sorted(FIELDS))}")
        if k in TEXT_FIELDS:
            if v is not None and not isinstance(v, str):
                raise BoardError(f"{k} must be text")
            v = (v or "").strip() or None
            if k == "title" and v is None:
                raise BoardError("title cannot be empty")
        elif k == "status":
            if v is not None and v not in derive.COLUMNS:
                raise BoardError(f"status must be one of {', '.join(derive.COLUMNS)} (or null for automatic)")
        elif k == "started":
            if not isinstance(v, bool):
                raise BoardError("started must be true/false")
        elif k == "progress":
            if not _int_or_none(v, 0) or (v is not None and v > 100):
                raise BoardError("progress must be an integer 0-100 or null")
        elif k == "priority":
            if not _int_or_none(v, 1):
                raise BoardError("priority must be an integer >= 1 or null")
        elif k == "tags":
            if not isinstance(v, list) or not all(isinstance(t, str) and t.strip() for t in v):
                raise BoardError("tags must be a list of non-empty texts")
            v = list(dict.fromkeys(t.strip() for t in v))
        elif k == "due" and v is not None:
            try:
                if not DATE_RE.match(v):
                    raise ValueError
                date.fromisoformat(v)
            except (TypeError, ValueError):
                raise BoardError("due must be a date YYYY-MM-DD") from None
        out[k] = v
    return out


def _messages(evs):
    """Messages to the agent and their replies, replayed from a card's events."""
    out = {}
    for ev in evs:
        if ev.get("kind") == "message":
            out[ev["n"]] = {"n": ev["n"], "ts": ev.get("ts"), "by": ev.get("by"), "text": ev.get("note", ""),
                            "open": True, "reply": None}
        elif ev.get("kind") == "reply" and ev.get("reply_to") in out:
            m = out[ev["reply_to"]]
            m["open"], m["reply"] = False, {"ts": ev.get("ts"), "by": ev.get("by"), "text": ev.get("note", "")}
    return list(out.values())


def _files(evs):
    """Current attachments, replayed from attach/detach events (last write of a name wins)."""
    out = {}
    for ev in evs:
        if ev.get("kind") == "attach":
            out[ev["name"]] = {k: ev.get(k) for k in ("name", "size", "sha1", "mode", "path", "ts", "by")}
        elif ev.get("kind") == "detach":
            out.pop(ev.get("name"), None)
    return list(out.values())


FILENAME_BAD = re.compile(r"[\x00-\x1f\x7f/\\:*?\"<>|]")


RESERVED = re.compile(r"^(con|prn|aux|nul|com\d|lpt\d)(\..*)?$", re.I)
NAME_BYTES = 200  # under the 255-byte NAME_MAX of Linux, with room for a "-N" suffix


def safe_name(name):
    """Basename only, no control/format/reserved characters, no leading dots, no trailing dots or
    spaces, no Windows device names, at most NAME_BYTES of UTF-8 (the extension is kept)."""
    base = re.split(r"[/\\]", str(name or ""))[-1]
    base = "".join(ch for ch in base if unicodedata.category(ch) != "Cf")  # e.g. U+202E hides ".exe"
    base = FILENAME_BAD.sub("", base).strip().lstrip(".").rstrip(". ")
    if RESERVED.match(base):
        base = "_" + base
    if len(base.encode("utf-8")) > NAME_BYTES:
        stem, dot, ext = base.rpartition(".")
        suffix = f".{ext}" if dot and stem and len(ext) <= 16 else ""
        stem = stem if suffix else base
        room = NAME_BYTES - len(suffix.encode("utf-8"))
        base = stem.encode("utf-8")[:room].decode("utf-8", "ignore") + suffix
    return base or "file"


class Board:
    readonly = False
    kind = "board"

    def __init__(self, bid):
        self.id = check_id("board", bid)
        self.dir = home() / bid
        f = self.dir / "board.json"
        if not f.exists():
            raise NotFound(f"board {bid!r} not found (devboard.py boards lists them)")
        self.meta = json.loads(f.read_text(encoding="utf-8"))

    @classmethod
    def init(cls, bid, title, repos=(), template=None):
        check_id("board", bid)
        if bid.startswith(ROLLOUT_PREFIX):
            raise BoardError(f"board ids starting with {ROLLOUT_PREFIX!r} are reserved for rollouts")
        d = home() / bid
        if (d / "board.json").exists():
            raise BoardError(f"board {bid!r} already exists")
        template = template or default_template()
        tpl = TEMPLATES / "boards" / f"{template}.json"
        if not tpl.exists():
            names = ", ".join(sorted(p.stem for p in (TEMPLATES / "boards").glob("*.json")))
            raise BoardError(f"unknown template {template!r}; available: {names}")
        spec = json.loads(tpl.read_text(encoding="utf-8"))
        meta = {"id": bid, "title": (title or "").strip() or bid,
                "repos": [str(Path(r).expanduser().resolve()) for r in repos],
                "columns": spec["columns"], "template": template, "created": now()}
        atomic_write(d / "card.md.tmpl", (TEMPLATES / "cards" / spec["card_md"]).read_text(encoding="utf-8"))
        (d / "cards").mkdir(parents=True, exist_ok=True)
        atomic_write(d / "board.json", json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
        return cls(bid)

    @contextlib.contextmanager
    def _lock(self):
        if fcntl is None:
            yield
            return
        with open(self.dir / ".lock", "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    # --- read ---
    def paths(self, cid):
        check_id("card", cid)
        c = self.dir / "cards"
        return c / f"{cid}.json", c / f"{cid}.md", c / f"{cid}.jsonl"

    def card_ids(self):
        ids = [p.stem for p in (self.dir / "cards").glob("*.json") if ID_RE.match(p.stem)]
        return sorted(ids, key=lambda i: (0, int(i), "") if i.isdigit() else (1, 0, i))

    def _read(self, cid):
        j, m, _ = self.paths(cid)
        if not j.exists():
            raise NotFound(f"card {cid!r} not found in board {self.id!r}")
        jb = j.read_bytes()
        mb = m.read_bytes() if m.exists() else b""
        return json.loads(jb), mb.decode("utf-8"), hashlib.sha1(jb + b"\0" + mb).hexdigest()[:12]

    def card(self, cid):
        card, md, etag = self._read(cid)
        prog = derive.progress(card, md)
        evs = self.events(cid)
        return dict(card, progress=prog, progress_source=derive.progress_source(md),
                    checklist=[len(items), sum(1 for _, done, _ in items if done)] if (items := derive.checklist(md)) else None,
                    column=derive.column(card, prog), etag=etag,
                    messages_open=sum(1 for m in _messages(evs) if m["open"]), files_count=len(_files(evs)),
                    claimed_by=_claim(evs))

    def cards(self):
        return [self.card(c) for c in self.card_ids()]

    def detail(self, cid, events=5):
        view = self.card(cid)
        view["md"] = self._read(cid)[1]
        evs = self.events(cid)
        view["events"] = evs[-events:] if events else evs
        view["messages"] = _messages(evs)
        view["files"] = _files(evs)
        return view

    def events(self, cid):
        f = self.paths(cid)[2]
        if not f.exists():
            return []
        out = []
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a torn line never breaks the reader; validate() reports it
        return out

    def render_template(self, title):
        t = self.dir / "card.md.tmpl"
        return t.read_text(encoding="utf-8").replace("{title}", title) if t.exists() else ""

    def history(self, limit=50):
        evs = [dict(ev, card=cid, seq=i) for cid in self.card_ids() for i, ev in enumerate(self.events(cid))]
        evs.sort(key=lambda e: (_ts(e.get("ts")), e["card"], e["seq"]), reverse=True)
        return evs[:limit] if limit else evs

    def pending(self):
        return [c for c in self.cards() if c.get("blocked") or c.get("waiting") or c["column"] == "blocked"]

    def rev(self):
        """Cheap change token for the page's 3 s poll: names, mtimes and sizes of the board files."""
        h = hashlib.sha1()
        files = [self.dir / "board.json", *(self.dir / "cards").iterdir()]
        for p in sorted(files):
            if p.name.startswith("."):
                continue
            with contextlib.suppress(FileNotFoundError):
                st = p.stat()
                h.update(f"{p.name}:{st.st_mtime_ns}:{st.st_size};".encode())
        return h.hexdigest()[:12]

    def validate(self):
        """Problems on disk as readable lines. Empty list = healthy."""
        probs, stems = [], {}
        cards = self.dir / "cards"
        for p in sorted(cards.iterdir()):
            if p.name.startswith("."):
                continue
            if p.suffix not in (".json", ".md", ".jsonl") or not ID_RE.match(p.stem):
                probs.append(f"unexpected file cards/{p.name}")
                continue
            stems.setdefault(p.stem, set()).add(p.suffix)
        for stem, exts in sorted(stems.items()):
            if ".json" not in exts:
                probs.append(f"orphan cards/{stem}{sorted(exts)[0]} (no {stem}.json)")
                continue
            try:
                card = json.loads((cards / f"{stem}.json").read_text(encoding="utf-8"))
            except ValueError as e:
                probs.append(f"cards/{stem}.json: invalid JSON ({e})")
                continue
            if card.get("id") != stem:
                probs.append(f"cards/{stem}.json: id {card.get('id')!r} differs from the file name")
            try:
                validate_changes({k: v for k, v in card.items() if k not in ("id", "updated")})
            except BoardError as e:
                probs.append(f"cards/{stem}.json: {e}")
            ev = cards / f"{stem}.jsonl"
            if ev.exists():
                for i, line in enumerate(ev.read_text(encoding="utf-8").splitlines(), 1):
                    try:
                        json.loads(line)
                    except ValueError:
                        probs.append(f"cards/{stem}.jsonl:{i}: unreadable event line")
        for stem in sorted(s for s, e in stems.items() if ".json" in e):
            for f in _files(self.events(stem)):
                p = Path(f["path"]) if f["mode"] == "link" else self.files_dir(stem) / f["name"]
                if not p.is_file():
                    probs.append(f"cards/{stem}: attachment {f['name']} is missing ({p})")
        for r in self.meta.get("repos", []):
            if not Path(r).exists():
                probs.append(f"board.json: repo {r} does not exist")
        return probs

    def audit(self):
        """Replay create/set events and compare with each card file.
        {card_id: [fields]} lists the cards edited outside this module."""
        drift = {}
        for cid in self.card_ids():
            card = self._read(cid)[0]
            state = {}
            for ev in self.events(cid):
                if ev.get("kind") in ("create", "set"):
                    for k, pair in (ev.get("changes") or {}).items():
                        state[k] = pair[1] if isinstance(pair, list) and len(pair) == 2 else object()
            stored = {k: v for k, v in card.items() if k not in ("id", "updated")}
            replay = {k: v for k, v in state.items() if v is not None and v != []}
            bad = sorted(k for k in set(stored) | set(replay) if stored.get(k) != replay.get(k))
            if bad:
                drift[cid] = bad
        return drift

    def messages(self, cid):
        self._read(cid)
        return _messages(self.events(cid))

    def inbox(self):
        """Open messages to the agent across the board, oldest first."""
        out = []
        for cid in self.card_ids():
            title = self._read(cid)[0].get("title")
            out += [dict(m, card=cid, title=title) for m in _messages(self.events(cid)) if m["open"]]
        return sorted(out, key=lambda m: (_ts(m["ts"]), m["card"], m["n"]))

    def claims(self):
        """Active claims across the board: who is working on what, until when."""
        out = []
        for cid in self.card_ids():
            c = _claim(self.events(cid))
            if c:
                out.append(dict(c, card=cid, title=self._read(cid)[0].get("title")))
        return out

    def files(self, cid):
        self._read(cid)
        return _files(self.events(cid))

    def files_dir(self, cid):
        check_id("card", cid)
        return self.dir / "files" / cid

    def file_path(self, cid, name):
        f = next((f for f in self.files(cid) if f["name"] == name), None)
        if f is None:
            raise NotFound(f"no attachment {name!r} on card {cid!r}")
        return Path(f["path"]) if f["mode"] == "link" else self.files_dir(cid) / f["name"]

    # --- write ---
    def _event(self, cid, by, kind, changes=None, note=None, src=None, **extra):
        ev = {"ts": now(), "by": by, "kind": kind}
        if changes:
            ev["changes"] = changes
        if note:
            ev["note"] = note
        ev.update(extra)
        if src:
            ev["src"] = src
        with open(self.paths(cid)[2], "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    def _guard(self, cid, etag):
        if etag is not None and etag != self._read(cid)[2]:
            raise Conflict(self.card(cid))

    def add(self, cid, title, fields=None, md=None, by="agent", src=None):
        by = check_by(by)
        data = validate_changes({**(fields or {}), "title": title})
        if md is not None and not isinstance(md, str):
            raise BoardError("md must be text")
        text = self.render_template(data["title"]) if md is None else md
        if data.get("progress") is not None and derive.checklist(text):
            raise BoardError("progress comes from the checklist; use check")
        j, m, _ = self.paths(cid)
        with self._lock():
            if j.exists():
                raise BoardError(f"card {cid!r} already exists")
            atomic_write(m, text)
            atomic_write(j, canonical({"id": cid, **data, "updated": now()}))
            created = {k: [None, v] for k, v in data.items() if v is not None and v != []}
            self._event(cid, by, "create", changes=created, src=src)
        return self.card(cid)

    def set(self, cid, changes, note=None, by="agent", etag=None, src=None):
        by = check_by(by)
        changes = validate_changes(changes)
        note = (note or "").strip() or None
        with self._lock():
            self._guard(cid, etag)
            card, md, _ = self._read(cid)
            if changes.get("progress") is not None and derive.checklist(md):
                raise BoardError("progress comes from the checklist; use check")
            if (changes.get("blocked") or changes.get("waiting")) and "status" not in changes \
                    and card.get("status") not in (None, "blocked"):
                changes["status"] = None  # a new block from the agent unpins a dragged card, so it shows as blocked
            diff = {}
            for k, v in changes.items():
                old = card.get(k)
                if old != v and not (v in (None, []) and old in (None, [])):
                    diff[k] = [old, v]
            if not diff and not note:
                return self.card(cid)
            if diff:
                card.update({k: new for k, (_, new) in diff.items()})
                card["updated"] = now()
                atomic_write(self.paths(cid)[0], canonical(card))
            self._event(cid, by, "set" if diff else "note", changes=diff or None, note=note, src=src)
        return self.card(cid)

    def note(self, cid, text, by="agent", src=None):
        by = check_by(by)
        text = (text or "").strip() if isinstance(text, str) else ""
        if not text:
            raise BoardError("note is empty")
        with self._lock():
            self._read(cid)
            self._event(cid, by, "note", note=text, src=src)
        return self.card(cid)

    def check(self, cid, n, done=True, by="agent", etag=None, src=None):
        by = check_by(by)
        if isinstance(n, bool) or not isinstance(n, int):
            raise BoardError("item must be an integer (1 = first checklist line)")
        if not isinstance(done, bool):
            raise BoardError("done must be true/false")
        with self._lock():
            self._guard(cid, etag)
            card, md, _ = self._read(cid)
            try:
                new_md, text = derive.toggle(md, n, done)
            except IndexError as e:
                raise BoardError(str(e)) from None
            if new_md == md:
                return self.card(cid)
            before = derive.progress(card, md)
            atomic_write(self.paths(cid)[1], new_md)
            card["updated"] = now()
            atomic_write(self.paths(cid)[0], canonical(card))
            self._event(cid, by, "check", note=f"[{'x' if done else ' '}] {text}", item=n, done=done,
                        progress=[before, derive.progress(card, new_md)], src=src)
        return self.card(cid)


    def move(self, cid, status, by="human", etag=None, src=None):
        """A drag on the page: sets the status; leaving Bloqueada clears blocked/waiting in the same event."""
        if status not in derive.COLUMNS:
            raise BoardError(f"status must be one of {', '.join(derive.COLUMNS)}")
        changes = {"status": status}
        if status != "blocked" and self.card(cid)["column"] == "blocked":
            changes.update(blocked=None, waiting=None)
        return self.set(cid, changes, by=by, etag=etag, src=src)

    def claim(self, cid, agent, ttl=DEFAULT_TTL, note=None, force=False, src=None):
        """Tell other agents you are working on this card. Renewing your own claim extends it; another
        agent's active claim refuses (Claimed) unless force=True, which is logged as forced_from."""
        agent = check_agent(agent)
        seconds = parse_ttl(ttl)
        note = (note or "").strip() or None
        with self._lock():
            self._read(cid)
            cur = _claim(self.events(cid))
            extra = {}
            if cur and cur["agent"] != agent:
                if not force:
                    raise Claimed(f"card {cid!r} is claimed by {cur['agent']} until {cur['until']}"
                                  + (f" ({cur['note']})" if cur.get("note") else "") + "; pick another card or use --force")
                extra["forced_from"] = cur["agent"]
            until = _now_ts() + seconds
            self._event(cid, agent, "claim", note=note, src=src, agent=agent, ttl=ttl,
                        until=_iso(until), until_ts=until, **extra)
        return self.card(cid)

    def release(self, cid, agent, note=None, src=None):
        agent = check_agent(agent)
        with self._lock():
            self._read(cid)
            cur = _claim(self.events(cid))
            if cur is None:
                raise BoardError(f"card {cid!r} is not claimed")
            if cur["agent"] != agent:
                raise Claimed(f"card {cid!r} is claimed by {cur['agent']}, not {agent}")
            self._event(cid, agent, "release", note=(note or "").strip() or None, src=src, agent=agent)
        return self.card(cid)

    def message(self, cid, text, by="human", src=None):
        by = check_by(by)
        text = text.strip() if isinstance(text, str) else ""
        if not text:
            raise BoardError("message is empty")
        with self._lock():
            self._read(cid)
            n = 1 + max((m["n"] for m in _messages(self.events(cid))), default=0)
            self._event(cid, by, "message", note=text, src=src, n=n)
        return next(m for m in self.messages(cid) if m["n"] == n)

    def reply(self, cid, n, text, by="agent", src=None):
        by = check_by(by)
        text = text.strip() if isinstance(text, str) else ""
        if not text:
            raise BoardError("reply is empty")
        with self._lock():
            self._read(cid)
            m = next((m for m in _messages(self.events(cid)) if m["n"] == n), None)
            if m is None:
                raise NotFound(f"message {n} not found on card {cid!r}")
            if not m["open"]:
                raise BoardError(f"message {n} already answered")
            self._event(cid, by, "reply", note=text, src=src, reply_to=n)
        return next(m for m in self.messages(cid) if m["n"] == n)

    def _commit_file(self, cid, tmp, name, size, sha1, by, src):
        """Give the uploaded temp file a free name and log it; runs under the board lock."""
        stem, dot, ext = name.rpartition(".")
        if not dot or not stem:
            stem, ext = name, ""
        # casefold: "Foto.png" and "foto.png" are one file on Windows and macOS
        taken = {f["name"].casefold() for f in _files(self.events(cid))} | \
            {p.name.casefold() for p in self.files_dir(cid).iterdir()}
        final, k = name, 2
        while final.casefold() in taken:
            final, k = f"{stem}-{k}{'.' + ext if ext else ''}", k + 1
        os.replace(tmp, self.files_dir(cid) / final)
        self._event(cid, by, "attach", src=src, name=final, size=size, sha1=sha1, mode="copy")
        return next(f for f in _files(self.events(cid)) if f["name"] == final)

    def attach_stream(self, cid, filename, stream, length, by="agent", src=None):
        """Copy `length` bytes from a stream into the card (page uploads). Partial bodies are discarded."""
        by = check_by(by)
        self._read(cid)
        d = self.files_dir(cid)
        d.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".up.", suffix=".tmp")
        h, left = hashlib.sha1(), length
        try:
            with os.fdopen(fd, "wb") as out:
                while left > 0:
                    chunk = stream.read(min(1 << 20, left))
                    if not chunk:
                        raise BoardError("upload ended early; nothing was attached")
                    out.write(chunk)
                    h.update(chunk)
                    left -= len(chunk)
            with self._lock():
                return self._commit_file(cid, tmp, safe_name(filename), length, h.hexdigest(), by, src)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp)
            raise

    def attach(self, cid, path, link=False, by="agent", src=None):
        """Attach a local file: copied into the board (default) or linked in place (--link)."""
        p = Path(path).expanduser()
        if not p.is_file():
            raise BoardError(f"{p} is not a file")
        if not link:
            with open(p, "rb") as fh:
                return self.attach_stream(cid, p.name, fh, p.stat().st_size, by=by, src=src)
        by = check_by(by)
        p = p.resolve()
        h = hashlib.sha1()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        with self._lock():
            self._read(cid)
            name = safe_name(p.name)
            if name in {f["name"] for f in _files(self.events(cid))}:
                raise BoardError(f"card {cid!r} already has an attachment named {name!r}; detach it first")
            self._event(cid, by, "attach", src=src, name=name, size=p.stat().st_size, sha1=h.hexdigest(),
                        mode="link", path=str(p))
        return next(f for f in self.files(cid) if f["name"] == name)

    def detach(self, cid, name, by="agent", src=None):
        by = check_by(by)
        with self._lock():
            f = next((f for f in self.files(cid) if f["name"] == name), None)
            if f is None:
                raise NotFound(f"no attachment {name!r} on card {cid!r}")
            if f["mode"] == "copy":
                with contextlib.suppress(FileNotFoundError):
                    (self.files_dir(cid) / name).unlink()
            self._event(cid, by, "detach", src=src, name=name)
        return self.card(cid)


def list_boards():
    """[(id, kind)] for every local board plus every rollout, sorted by id."""
    from . import rollout
    root = home()
    out = [(p.parent.name, "board") for p in root.glob("*/board.json") if ID_RE.match(p.parent.name)] \
        if root.exists() else []
    out += [(rid, "rollout") for rid in rollout.sources()]
    return sorted(out)


def open_board(bid):
    from . import rollout
    if isinstance(bid, str) and bid.startswith(ROLLOUT_PREFIX):
        return rollout.open_rollout(bid)
    return Board(bid)


def resolve(cwd):
    """The local board whose repos contain cwd; the deepest repo path wins; None if none."""
    cwd = Path(cwd).expanduser().resolve()
    best, depth = None, -1
    hidden = archived()
    for bid, kind in list_boards():
        if kind != "board" or bid in hidden:
            continue
        try:
            repos = Board(bid).meta.get("repos", [])
        except (BoardError, ValueError):
            continue
        for r in repos:
            rp = Path(r)
            if (cwd == rp or rp in cwd.parents) and len(rp.parts) > depth:
                best, depth = bid, len(rp.parts)
    return best


ARCHIVE_LOG = "_archive.jsonl"


def _tilde(path):
    home_dir = str(Path.home())
    return "~" + path[len(home_dir):] if path == home_dir or path.startswith(home_dir + os.sep) else path


def archived():
    """Ids of archived boards, replayed from the append-only _archive.jsonl."""
    f = home() / ARCHIVE_LOG
    state = {}
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(line)
                state[ev["board"]] = bool(ev["archived"])
            except (ValueError, KeyError, TypeError):
                continue
    return {b for b, on in state.items() if on}


def _set_archived(bid, on, by):
    by = check_by(by)
    open_board(bid)  # NotFound for an unknown board
    home().mkdir(parents=True, exist_ok=True)
    with open(home() / ARCHIVE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now(), "by": by, "board": bid, "archived": on}, ensure_ascii=False) + "\n")
    return {"id": bid, "archived": on}


def archive(bid, by="agent"):
    """Hide a board from the home screen, `boards` and the SessionStart hint. Data stays."""
    return _set_archived(bid, True, by)


def unarchive(bid, by="agent"):
    return _set_archived(bid, False, by)


def overview():
    """One row per board for the home screen: grouped by origin repo, with column counts and activity."""
    out, hidden = [], archived()
    for bid, kind in list_boards():
        row = {"id": bid, "kind": kind, "archived": bid in hidden}
        try:
            b = open_board(bid)
            cs = b.cards()
        except Exception as e:  # noqa: BLE001 — a malformed board shows as an error row
            out.append(dict(row, title=bid, cards=0, done=0, group=None, group_name=None,
                            counts={}, avg=None, messages_open=0, updated=None, error=f"{type(e).__name__}: {e}"))
            continue
        cols = list(b.meta.get("columns") or {})
        last = cols[-1] if cols else None
        repos = b.meta.get("repos") or []
        known = [c["progress"] for c in cs if c.get("progress") is not None]
        stamps = [c.get("updated") for c in cs if c.get("updated")]
        out.append(dict(row, title=b.meta.get("title", bid), cards=len(cs),
                        done=sum(1 for c in cs if c["column"] == last),
                        group=repos[0] if repos else None, group_name=Path(repos[0]).name if repos else None,
                        group_label=_tilde(repos[0]) if repos else None,
                        counts={k: sum(1 for c in cs if c["column"] == k) for k in cols},
                        avg=round(sum(known) / len(known)) if known else None,
                        messages_open=sum(c.get("messages_open", 0) for c in cs),
                        updated=max(stamps, key=_ts) if stamps else b.meta.get("created")))
    return out
