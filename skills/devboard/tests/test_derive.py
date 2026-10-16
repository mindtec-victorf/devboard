import pytest

from boardlib import derive

MD = "## Checklist\n- [x] a\n- [ ] b\n```\n- [ ] not an item\n```\n* [X] c\n"


def test_checklist_ignores_fenced_code():
    assert [(d, t) for _, d, t in derive.checklist(MD)] == [(True, "a"), (False, "b"), (True, "c")]


def test_progress_from_checklist_rounds():
    assert derive.progress({"progress": 10}, MD) == 67
    assert derive.progress_source(MD) == "checklist"


def test_progress_manual_without_checklist():
    assert derive.progress({"progress": 40}, "texto") == 40
    assert derive.progress({}, "") is None
    assert derive.progress_source("texto") == "manual"


@pytest.mark.parametrize("card,prog,col", [
    ({"blocked": "ETL"}, 100, "blocked"),
    ({"waiting": "vendor"}, 0, "blocked"),
    ({}, 100, "done"),
    ({}, 90, "final"),
    ({}, 99, "final"),
    ({"started": True}, None, "doing"),
    ({}, 1, "doing"),
    ({}, 0, "todo"),
    ({}, None, "todo"),
])
def test_column_rules(card, prog, col):
    assert derive.column(card, prog) == col


def test_toggle_sets_item_and_keeps_line_endings():
    md = "- [ ] a\r\n- [ ] b\r\n"
    new, text = derive.toggle(md, 2, True)
    assert new == "- [ ] a\r\n- [x] b\r\n" and text == "b"
    assert derive.toggle(new, 2, False)[0] == md


def test_toggle_skips_fenced_items():
    md = "```\n- [ ] fake\n```\n- [ ] real\n"
    assert derive.toggle(md, 1, True)[0] == "```\n- [ ] fake\n```\n- [x] real\n"


def test_toggle_out_of_range():
    with pytest.raises(IndexError, match="has 1 item"):
        derive.toggle("- [ ] a\n", 2, True)


def test_checklist_bom_and_odd_line_breaks_match_the_page():
    # the page (app.js) splits on \n only, strips a leading BOM and a trailing \r
    assert [t for _, _, t in derive.checklist("﻿- [ ] a\n- [ ] b")] == ["a", "b"]
    assert [t for _, _, t in derive.checklist("- [ ] a\x85- [ ] b\n- [ ] c\r\n")] == ["a\x85- [ ] b", "c"]


def test_toggle_keeps_bom():
    new, text = derive.toggle("﻿- [ ] a\n- [ ] b", 1, True)
    assert new == "﻿- [x] a\n- [ ] b" and text == "a"
