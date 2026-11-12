"""Linked cards: a board can show cards of other boards next to its own (a delivery board).

board.json keeps `"links": ["<board>:<card>", ...]`; nothing else is copied. A linked card shows the
source card's status, and every write on it goes to the source board, where its history stays.
Ids look like the "For you" board's: "<board>:<card>". A manual reorder is not passed on, so the
source board keeps its own order. A source card that is gone shows in Blocked until it is unlinked.
"""
import hashlib
import json

from . import store

MISSING = "source card not found (devboard.py unlink-card removes the link)"


def parse_ref(ref):
    """'board/card' or 'board:card' -> 'board:card', both parts checked."""
    bid, sep, card = str(ref).replace("/", ":").partition(":")
    if not sep:
        raise store.BoardError(f"link {ref!r} must look like <board>/<card>")
    return f"{store.check_id('board', bid)}:{store.check_id('card', card)}"


def _edit(bid, fn):
    b = store.Board(bid)
    with b._lock():
        f = b.dir / "board.json"
        meta = json.loads(f.read_text(encoding="utf-8"))
        meta["links"] = fn(list(meta.get("links") or []))
        if not meta["links"]:
            del meta["links"]
        store.atomic_write(f, json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    return store.open_board(bid)


def link(bid, ref):
    """Add a link to an existing card of another regular board. Linking twice is a no-op."""
    ref = parse_ref(ref)
    src, card = ref.split(":")
    if src == bid or src == store.USER_BOARD or src.startswith(store.ROLLOUT_PREFIX):
        raise store.BoardError(f"cannot link {ref!r}: link a card of another regular board")
    store.Board(src)._read(card)  # NotFound: never link a card that does not exist
    return _edit(bid, lambda refs: refs if ref in refs else refs + [ref])


def unlink(bid, ref):
    ref = parse_ref(ref)

    def drop(refs):
        if ref not in refs:
            raise store.NotFound(f"{ref!r} is not linked on board {bid!r}")
        return [r for r in refs if r != ref]
    return _edit(bid, drop)


class LinkedBoard(store.Board):
    """A board with links. Own cards behave as always; "<board>:<card>" ids go to the source board."""

    def links(self):
        return list(self.meta.get("links") or [])

    def _src(self, cid):
        bid, sep, card = str(cid).partition(":")
        if not sep:
            return None, cid
        if cid not in self.links():
            raise store.NotFound(f"card {cid!r} is not linked on board {self.id!r}")
        return store.Board(bid), card

    def _view(self, src, c):
        if not (isinstance(c, dict) and "column" in c):
            return c  # a message or a file, not a card
        return dict(c, id=f"{src.id}:{c['id']}", source_board=src.id, source_id=c["id"],
                    source_title=src.meta.get("title", src.id), rank=None)

    def _missing(self, ref):
        bid, _, card = ref.partition(":")
        return {"id": ref, "title": ref, "status": "blocked", "column": "blocked", "progress": None,
                "blocked": MISSING, "source_board": bid, "source_id": card, "source_title": bid,
                "missing": True, "etag": "", "messages_open": 0, "requests_open": 0, "files_count": 0}

    def _live(self, ref):
        try:
            src, card = self._src(ref)
            src._read(card)
            return True
        except store.NotFound:
            return False

    # --- read: own cards first, then the links in their order ---
    def card_ids(self):
        return super().card_ids() + [r for r in self.links() if self._live(r)]

    def cards(self):
        out = [store.Board.card(self, c) for c in super().card_ids()]
        for ref in self.links():
            out.append(self.card(ref) if self._live(ref) else self._missing(ref))
        return out

    def card(self, cid):
        src, card = self._src(cid)
        return super().card(cid) if src is None else self._view(src, src.card(card))

    def detail(self, cid, events=5):
        src, card = self._src(cid)
        return super().detail(cid, events) if src is None else self._view(src, src.detail(card, events))

    def _read(self, cid):
        src, card = self._src(cid)
        return super()._read(cid) if src is None else src._read(card)

    def events(self, cid):
        src, card = self._src(cid)
        return super().events(cid) if src is None else src.events(card)

    def file_path(self, cid, name):
        src, card = self._src(cid)
        return super().file_path(cid, name) if src is None else src.file_path(card, name)

    def rev(self):
        parts = [super().rev()]
        for bid in dict.fromkeys(r.partition(":")[0] for r in self.links()):
            try:
                parts.append(store.Board(bid).rev())
            except store.NotFound:
                parts.append("-")
        return hashlib.sha1(";".join(parts).encode()).hexdigest()[:12]

    def validate(self):
        return super().validate() + [f"board.json: link {r} points to a missing card"
                                     for r in self.links() if not self._live(r)]

    def audit(self):
        return {k: v for k, v in super().audit().items() if ":" not in k}  # linked cards: audit their board

    # --- write: a linked card is written on its source board ---
    def move(self, cid, status, by="human", etag=None, src=None, rank=None):
        s, card = self._src(cid)
        if s is None:
            return super().move(cid, status, by=by, etag=etag, src=src, rank=rank)
        return self._view(s, s.move(card, status, by=by, etag=etag, src=src))  # no rank: the source keeps its order


def _delegate(name):
    own = getattr(store.Board, name)

    def method(self, cid, *args, **kwargs):
        src, card = self._src(cid)
        if src is None:
            return own(self, cid, *args, **kwargs)
        return self._view(src, getattr(src, name)(card, *args, **kwargs))
    method.__name__ = name
    return method


for _name in ("set", "note", "check", "claim", "release", "message", "ask", "reply", "attach",
              "attach_stream", "detach"):
    setattr(LinkedBoard, _name, _delegate(_name))
