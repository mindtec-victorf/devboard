from boardlib import store


def test_longest_repo_wins_and_siblings_do_not_match(tmp_path):
    outer, inner, sibling = tmp_path / "proj", tmp_path / "proj" / "sub", tmp_path / "project"
    for d in (outer, inner, sibling):
        d.mkdir(parents=True)
    store.Board.init("outer", "o", [str(outer)])
    store.Board.init("inner", "i", [str(inner)])
    assert store.resolve(outer) == "outer"
    assert store.resolve(outer / "x") == "outer"
    assert store.resolve(inner / "deep") == "inner"
    assert store.resolve(sibling) is None


def test_no_boards_returns_none(tmp_path):
    assert store.resolve(tmp_path) is None
