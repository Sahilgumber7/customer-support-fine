"""Browser-level smoke test: the real page, the real API, a real Chromium render.

Skipped when Playwright or its Chromium build is unavailable, so the unit suite stays portable.
Run: ``python -m pytest tests/test_ui.py -q``
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    port = _free_port()
    db = tmp_path_factory.mktemp("ui") / "ui.db"
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(ROOT)]),
        "SUPPORT_AI_DB_URL": f"sqlite:///{db.as_posix()}",
        "PYTHONWARNINGS": "ignore::DeprecationWarning",
    }
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "support_ai.api:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        env=env,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(base + "/healthz", timeout=1)  # noqa: S310
                break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.1)
        else:
            raise RuntimeError("uvicorn did not become healthy")
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _browser():
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.launch()
    except Exception as exc:  # noqa: BLE001 - missing browser build
        playwright.stop()
        pytest.skip(f"chromium unavailable: {type(exc).__name__}")
    return playwright, browser


@pytest.mark.slow
def test_customer_chat_returns_a_grounded_reply(live_server):
    playwright, browser = _browser()
    try:
        page = browser.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        page.goto(live_server)
        page.wait_for_function("document.querySelectorAll('#customer option').length > 0")
        page.click("#signin")
        page.wait_for_function("!document.getElementById('input').disabled")

        page.fill("#input", "Where is my order ORD-1001?")
        page.click("#send")
        page.wait_for_selector(".msg.bot:has-text('ORD-1001')", timeout=20000)

        assert errors == []
        assert "Serving:" in page.locator("#model").inner_text()
        assert page.locator(".msg.bot").count() >= 2
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.slow
def test_ops_console_renders_live_stats(live_server):
    playwright, browser = _browser()
    try:
        page = browser.new_page()
        page.goto(live_server + "/ops")
        page.wait_for_selector("#stats .card")
        assert page.locator("#stats .card").count() == 4
        assert "Northwind" in page.title()
        assert page.locator("#audit").is_visible()
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.slow
def test_over_threshold_refund_reaches_ops_and_can_be_approved(live_server):
    playwright, browser = _browser()
    try:
        page = browser.new_page()
        page.goto(live_server)
        page.wait_for_function("document.querySelectorAll('#customer option').length > 0")
        page.click("#signin")
        page.wait_for_function("!document.getElementById('input').disabled")

        page.fill("#input", "The watch from ORD-1005 arrived damaged, I'd like a refund.")
        page.click("#send")
        page.wait_for_selector(".msg.bot:has-text('review')", timeout=20000)

        page.goto(live_server + "/ops")
        page.wait_for_selector("#approvals .pill.pending")
        page.locator("#approvals button:has-text('Approve')").first.click()
        page.wait_for_selector("#approvals .pill.approved", timeout=15000)
        assert page.locator("#approvals .pill.pending").count() == 0
    finally:
        browser.close()
        playwright.stop()
