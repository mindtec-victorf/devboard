"""Read-only board "user": every open card, across all active local boards, that is assigned to the person
(`--for user`) or carries an agent's open request (`ask`). Nothing is stored here: it is built on each read
from the real boards, so it never drifts from them. Card ids are "<board>:<card>"; the page opens the
original card, where the person answers or works.
"""
import hashlib

from . import store

TITLE = "For you"
COLUMNS = {"todo": "To do", "blocked": "Blocked / waiting", "doing": "In progress", "final": "Final touches"}


def wanted(card):
    return card["column"] != "done" and (card.get("assignee") == "user" or card.get("requests_open"))


def _sources():
    hidden = store.archived()
    for bid, kind in store.list_boards():
        if kind == "board" and bid not in hidden and bid != store.USER_BOARD:
            try:
                yield store.Board(bid)
            except (store.BoardError, ValueError):
                continue


def _split(cid):
    bid, sep, card = str(cid).partition(":")
    if not sep:
        raise store.NotFound(f"card {cid!r} not found in {store.USER_BOARD!r} (ids look like <board>:<card>)")
    return store.Board(bid), card


class UserBoard:
    readonly = True
    kind = "user"

    def __init__(self):
        self.id = store.USER_BOARD
        self.meta = {"id": self.id, "title": TITLE, "repos": [], "columns": dict(COLUMNS)}

    def _view(self, b, c):
        return dict(c, id=f"{b.id}:{c['id']}", source_board=b.id, source_title=b.meta.get("title", b.id),
                    source_id=c["id"], etag="")

    def cards(self):
        out = [self._view(b, c) for b in _sources() for c in b.cards() if wanted(c)]
        return sorted(out, key=lambda c: (c.get("priority") or 99, c["source_board"], c["source_id"]))

    def card_ids(self):
        return [c["id"] for c in self.cards()]

    def card(self, cid):
        b, card = _split(cid)
        return self._view(b, b.card(card))

    def detail(self, cid, events=5):
        b, card = _split(cid)
        return self._view(b, b.detail(card, events))

    def events(self, cid):
        b, card = _split(cid)
        return b.events(card)

    def history(self, limit=50):
        evs = []
        for c in self.cards():
            b = store.Board(c["source_board"])
            evs += [dict(ev, card=c["id"], seq=i) for i, ev in enumerate(b.events(c["source_id"]))]
        evs.sort(key=lambda e: (store._ts(e.get("ts")), e["card"], e["seq"]), reverse=True)
        return evs[:limit] if limit else evs

    def pending(self):
        return [c for c in self.cards() if c.get("blocked") or c.get("waiting") or c["column"] == "blocked"]

    def requests(self):
        out = []
        for b in _sources():
            out += [dict(m, card=f"{b.id}:{m['card']}") for m in b.requests()]
        return sorted(out, key=lambda m: (store._ts(m["ts"]), m["card"], m["n"]))

    def rev(self):
        h = hashlib.sha1()
        for b in _sources():
            h.update(f"{b.id}:{b.rev()};".encode())
        return h.hexdigest()[:12]

    def validate(self):
        return []

    def audit(self):
        return {}

    def _read_only(self, *args, **kwargs):
        raise store.ReadOnly(f"the {store.USER_BOARD!r} board is built from the other boards; write on the original card")

    add = set = note = check = move = message = ask = reply = attach = attach_stream = detach = claim = release = _read_only

    def claims(self):
        return []

    def messages(self, cid):
        b, card = _split(cid)
        return b.messages(card)

    def inbox(self, to="agent"):
        return self.requests() if to == "user" else []

    def files(self, cid):
        b, card = _split(cid)
        return b.files(card)

    def file_path(self, cid, name):
        b, card = _split(cid)
        return b.file_path(card, name)
