import threading
import time

import pytest

pw = pytest.importorskip("playwright.sync_api")

from boardlib import server, store  # noqa: E402

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


@pytest.fixture
def base_url():
    b = store.Board.init("p", "Project")
    b.add("20", "Multi-tenant", md="﻿- [ ] a\n- [ ] b\n")
    b.add("21", "Another card")
    s = server.make_server(0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}/"
    s.shutdown()
    s.server_close()


@pytest.fixture
def browser_page():
    with pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except pw.Error as e:
            pytest.skip(f"chromium not installed: {e}")
        pg = browser.new_page(viewport={"width": 1400, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        yield pg
        browser.close()
        assert errors == []


def test_drag_card_changes_status(base_url, browser_page):
    page = browser_page
    page.goto(base_url + "#/p")
    page.locator('.card[data-id="21"]').wait_for()
    page.drag_and_drop('.card[data-id="21"]', '.col[data-col="doing"]')
    page.locator('.col[data-col="doing"] .card[data-id="21"]').wait_for()
    time.sleep(0.5)
    assert store.Board("p").card("21")["column"] == "doing"
    assert store.Board("p").events("21")[-1]["by"] == "human"


def test_detail_checklist_and_message(base_url, browser_page):
    page = browser_page
    page.goto(base_url + "#/p/card/20")
    page.locator('[data-check="1"]').click()
    page.locator(".kpi").get_by_text("50%").wait_for()
    assert store.Board("p").detail("20")["md"].startswith("﻿- [x] a")
    page.fill("#ask", "check the 7am import")
    page.click("#send")
    page.get_by_text("Waiting for the agent").wait_for()
    assert [m["text"] for m in store.Board("p").inbox()] == ["check the 7am import"]
    assert page.locator(".tab .n").inner_text() == "1"


def test_empty_message_shows_inline_error(base_url, browser_page):
    page = browser_page
    page.goto(base_url + "#/p/card/21")
    page.click("#send")
    page.get_by_text("Write the message before sending.").wait_for()
    assert store.Board("p").inbox() == []


def test_poll_keeps_typed_message(base_url, browser_page):
    page = browser_page
    page.goto(base_url + "#/p/card/20")
    page.fill("#ask", "draft")
    page.click("h1")
    store.Board("p").set("21", {"situation": "changed by the agent"})
    time.sleep(4)
    assert page.input_value("#ask") == "draft"


def test_upload_shows_image_tile(base_url, browser_page, tmp_path):
    f = tmp_path / "screen.png"
    f.write_bytes(PNG)
    page = browser_page
    page.goto(base_url + "#/p/card/21")
    page.set_input_files("#file", str(f))
    page.locator('.file img[alt="screen.png"]').wait_for()
    assert [x["name"] for x in store.Board("p").files("21")] == ["screen.png"]
    page.goto(base_url + "#/p")
    page.locator('.card[data-id="21"] .clip').wait_for()


def test_foreign_drop_does_not_move_last_dragged_card(base_url, browser_page):
    page = browser_page
    page.goto(base_url + "#/p")
    page.locator('.card[data-id="21"]').wait_for()
    page.drag_and_drop('.card[data-id="21"]', '.col[data-col="todo"]')  # same column: no-op
    page.evaluate("""() => { const dt = new DataTransfer(); dt.setData('text/plain', 'some text');
      document.querySelector('.col[data-col="done"]').dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true})); }""")
    time.sleep(1)
    assert store.Board("p").card("21")["column"] == "todo"


def test_whole_attachment_tile_opens_the_file(base_url, browser_page, tmp_path):
    f = tmp_path / "prd.md"
    f.write_text("# PRD\n", encoding="utf-8")
    store.Board("p").attach("21", f)
    page = browser_page
    page.goto(base_url + "#/p/card/21")
    preview = page.locator(".file .doc")
    preview.wait_for()
    with page.context.expect_page() as new:
        preview.click()
    assert new.value.url.endswith("/api/b/p/cards/21/files/prd.md")


def test_home_groups_by_repo_and_opens_board(base_url, browser_page, tmp_path):
    repo = tmp_path / "acme-certificates"
    repo.mkdir()
    store.Board.init("cert", "Certificates", [str(repo)]).add("1", "A")
    page = browser_page
    page.goto(base_url)
    page.locator(".group h2", has_text="acme-certificates").wait_for()
    page.locator(".group h2", has_text="No repository").wait_for()
    page.locator('.bcard[data-board="cert"] .open-board').click()
    page.locator('.card[data-id="1"]').wait_for()
    assert page.url.endswith("#/cert")
    page.click(".crumb")
    page.locator('.bcard[data-board="p"]').wait_for()


def test_archive_and_restore_from_home(base_url, browser_page):
    page = browser_page
    page.goto(base_url)
    page.locator('.bcard[data-board="p"] [data-archive]').click()
    page.locator('.bcard[data-board="p"]').wait_for(state="detached")
    assert store.archived() == {"p"}
    page.check("#show-archived")
    page.locator('.group h2', has_text="Archived").wait_for()
    page.locator('.bcard[data-board="p"] [data-archive]').click()
    page.locator('.group h2', has_text="Archived").wait_for(state="detached")
    assert store.archived() == set()


def test_page_in_portuguese_when_asked(base_url, browser_page, monkeypatch):
    monkeypatch.setenv("DEVBOARD_LANG", "pt-BR")
    page = browser_page
    page.goto(base_url + "#/p/card/21")
    page.get_by_text("Recado para a IA").wait_for()
    assert page.locator("html").get_attribute("lang") == "pt-BR"
    page.goto(base_url)
    page.get_by_text("Quadros de acompanhamento").wait_for()


def test_english_by_default(base_url, browser_page):
    page = browser_page
    page.goto(base_url + "#/p")
    page.get_by_text("Not started; scope open or closed.").wait_for()
    page.get_by_text("Priority queue only").wait_for()


def test_claim_is_shown_on_board_and_card(base_url, browser_page):
    store.Board("p").claim("21", "codex-1", note="writing tests")
    page = browser_page
    page.goto(base_url + "#/p")
    page.locator('.card[data-id="21"] .agent', has_text="codex-1").wait_for()
    page.goto(base_url + "#/p/card/21")
    page.get_by_text("codex-1 is working on this").wait_for()
    page.get_by_text("codex-1 claimed it").wait_for()


def test_tab_title_shows_board_and_waiting_messages(base_url, browser_page):
    store.Board("p").message("21", "please check")
    page = browser_page
    page.goto(base_url + "#/p")
    page.locator('.card[data-id="21"]').wait_for()
    page.wait_for_function("document.title.startsWith('(1) Project')")


def test_keyboard_shortcuts(base_url, browser_page):
    page = browser_page
    page.goto(base_url + "#/p")
    page.locator('.card[data-id="21"]').wait_for()
    page.keyboard.press("/")
    assert page.evaluate("document.activeElement.id") == "search"
    page.goto(base_url + "#/p/card/21")
    page.fill("#ask", "sent with the keyboard")
    page.keyboard.press("Control+Enter")
    page.get_by_text("Waiting for the agent").wait_for()
    page.locator(".panel h1").click()
    page.keyboard.press("Escape")
    page.wait_for_function("location.hash === '#/p'")


def test_drag_feedback_and_relative_time(base_url, browser_page):
    page = browser_page
    page.goto(base_url + "#/p")
    page.locator('.col[data-col="done"] .empty-col').wait_for()
    page.drag_and_drop('.card[data-id="21"]', '.col[data-col="done"]')
    page.locator('.col[data-col="done"] .card[data-id="21"].moved').wait_for()
    page.goto(base_url + "#/p/history")
    t = page.locator(".tl time").first
    t.wait_for()
    assert "ago" in t.inner_text() or "just now" in t.inner_text()
    assert t.get_attribute("title")


def test_default_column_names_follow_the_page_language(base_url, browser_page, monkeypatch):
    monkeypatch.setenv("DEVBOARD_LANG", "es")
    page = browser_page
    page.goto(base_url + "#/p")
    page.locator('.col[data-col="todo"] h2', has_text="Por hacer").wait_for()
    page.locator('.col[data-col="doing"] h2', has_text="En curso").wait_for()


def test_agent_icons_follow_the_agent_name(base_url, browser_page):
    b = store.Board("p")
    b.claim("21", "claude-main", note="refactor")
    b.claim("20", "codex-tests")
    page = browser_page
    page.goto(base_url + "#/p")
    page.locator('.card[data-id="21"] .agent svg[data-kind="claude"]').wait_for()
    page.locator('.card[data-id="20"] .agent svg[data-kind="openai"]').wait_for()
    page.goto(base_url + "#/p/card/21")
    page.locator('.claim svg[data-kind="claude"]').wait_for()
    page.locator('.tl svg[data-kind="claude"]').first.wait_for()


def test_unknown_agent_gets_the_generic_icon(base_url, browser_page):
    store.Board("p").claim("21", "bob")
    page = browser_page
    page.goto(base_url + "#/p")
    page.locator('.card[data-id="21"] .agent svg[data-kind="generic"]').wait_for()
