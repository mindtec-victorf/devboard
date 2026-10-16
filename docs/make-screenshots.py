#!/usr/bin/env python3
"""Rebuild docs/screenshots/*.png from the demo boards in docs/demo/ (needs Playwright + Chromium).

Everything runs in a temporary DEVBOARD_HOME, so your own boards are never touched:
    python3 docs/make-screenshots.py
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "devboard" / "scripts" / "devboard.py"
OUT = ROOT / "docs" / "screenshots"


def cli(*args, env):
    subprocess.run([sys.executable, str(CLI), *args], check=True, env=env, stdout=subprocess.DEVNULL)


def main():
    from playwright.sync_api import sync_playwright
    tmp = Path(tempfile.mkdtemp())
    # a temporary HOME makes the page show ~/.devboard; keep Playwright's browsers where they are
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / ".cache" / "ms-playwright"))
    env = dict(os.environ, HOME=str(tmp), DEVBOARD_HOME=str(tmp / ".devboard"), DEVBOARD_LANG="en")
    for repo, board, title in (("acme-checkout", "checkout", "Acme Checkout · v2 launch"),
                               ("acme-docs", "docs-site", "Docs site refresh"), ("old-poc", "poc", "Old proof of concept")):
        (tmp / repo).mkdir()
        cli("init", board, "--title", title, "--repo", str(tmp / repo), env=env)
        seed = ROOT / "docs" / "demo" / f"{board}.json"
        if seed.exists():
            cli("apply", str(seed), env=env)
    cli("archive", "poc", env=env)
    with tempfile.TemporaryDirectory() as d:  # a small "screenshot" attachment
        os.environ.update(env)
        sys.path.insert(0, str(CLI.parent))
        from boardlib import store
        b = store.Board("checkout")
        b.message("3", "Can you check the hold rate on staging before we tune the threshold?")
        b.attach("3", ROOT / "docs" / "demo" / "fraud-checks-prd.md")
        b.move("5", "doing")
        from boardlib import server
        srv = server.make_server(0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_address[1]}/"
        with sync_playwright() as p:
            br = p.chromium.launch()
            pg = br.new_page(viewport={"width": 1500, "height": 860})
            shot = Path(d) / "wire.png"
            pg.set_content('<div style="font:600 22px sans-serif;padding:40px;background:#eef6f3;width:520px;height:300px">'
                           'Hold queue · 12 orders<br><br><div style="background:#fff;height:40px;margin:8px 0"></div>'
                           '<div style="background:#fff;height:40px;margin:8px 0"></div><div style="background:#fff;height:40px"></div></div>')
            pg.locator("div").first.screenshot(path=str(shot))
            b.attach("3", shot)
            OUT.mkdir(parents=True, exist_ok=True)
            pg.goto(url + "#/checkout"); pg.wait_for_selector(".card"); time.sleep(0.4)
            pg.screenshot(path=str(OUT / "board.png"))
            pg.goto(url + "#/checkout/card/3"); pg.wait_for_selector("#ask"); time.sleep(0.6)
            pg.screenshot(path=str(OUT / "card.png"), full_page=True)
            pg.goto(url); pg.wait_for_selector(".bcard"); pg.check("#show-archived"); time.sleep(0.3)
            pg.screenshot(path=str(OUT / "home.png"), full_page=True)
            br.close()
        srv.shutdown()
    print(json.dumps({"written": sorted(p.name for p in OUT.glob("*.png"))}))


if __name__ == "__main__":
    main()
