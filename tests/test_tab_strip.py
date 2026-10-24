"""The Browser page's tab strip, run in Edge against a fake Ducky host bridge."""

from __future__ import annotations

from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parents[1] / "ui" / "index.html"

# Stands in for Ducky: answers the page's bridge calls and records them.
FAKE_HOST = r"""
window.__calls = [];
window.parent = { postMessage(msg) {
  if (!msg || !msg.method) return;
  window.__calls.push({ method: msg.method, params: msg.params });
  const p = msg.params || {};
  let result = { ok: true };
  if (msg.method === "browser.tabs") result = { ok: true, panes: [] };
  if (msg.method === "browser.open") result = { ok: true, pane_id: "B::" + p.tab, url: p.url, ready: true, title: "" };
  if (msg.method === "prefs.get") result = { value: null };
  setTimeout(() => window.postMessage({ channel: msg.channel, id: msg.id, ok: true, result }, "*"), 0);
} };
"""


def _tabs(page) -> list[str]:
    return page.eval_on_selector_all(".ptab", "els => els.map(e => e.className.includes('is-active') ? '*' : '-')")


def test_page_tabs_open_switch_close_and_follow_agents() -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="msedge")
        except Exception as exc:  # no Edge / browser on this machine
            pytest.skip(f"no browser: {exc}")
        page = browser.new_page()
        page.add_init_script(FAKE_HOST)
        page.goto(PAGE.as_uri())
        page.wait_for_function("document.querySelectorAll('.ptab').length === 1")
        assert _tabs(page) == ["*"]

        page.click("#newtab")
        page.wait_for_function("document.querySelectorAll('.ptab').length === 2")
        assert _tabs(page) == ["-", "*"]
        opened = [c["params"]["tab"] for c in page.evaluate("window.__calls") if c["method"] == "browser.open"]
        assert len(set(opened)) == 2
        # The tab left behind is hidden on the host; the new one is pinned visible.
        bounds = [c["params"] for c in page.evaluate("window.__calls") if c["method"] == "browser.bounds"]
        assert any(b["tab"] == opened[0] and b["visible"] is False for b in bounds)
        page.wait_for_function(
            f"window.__calls.some(c => c.method === 'browser.bounds' && c.params.tab === '{opened[1]}'"
            " && c.params.visible)")

        page.click(".ptab >> nth=0")
        assert _tabs(page) == ["*", "-"]

        # An agent's browser_new_tab / browser_close_tab arrive as tab commands.
        page.evaluate("window.postMessage({channel: 'uefn-plugin-ui', event: {type: 'browser_tab_command',"
                      " action: 'new', tab: 'agent1', url: 'https://x.com'}}, '*')")
        page.wait_for_function("document.querySelectorAll('.ptab').length === 3")
        assert _tabs(page) == ["-", "-", "*"]
        page.evaluate("window.postMessage({channel: 'uefn-plugin-ui', event: {type: 'browser_tab_command',"
                      " action: 'close', tab: 'agent1'}}, '*')")
        page.wait_for_function("document.querySelectorAll('.ptab').length === 2")
        assert any(c["method"] == "browser.close" and c["params"]["tab"] == "agent1"
                   for c in page.evaluate("window.__calls"))

        # A popup from a page opens as a page tab here, not a new Ducky tab.
        page.evaluate("window.postMessage({channel: 'uefn-plugin-ui', event: {type: 'browser_pane_new_window',"
                      " pane_id: 'B::x', url: 'https://example.com'}}, '*')")
        page.wait_for_function("document.querySelectorAll('.ptab').length === 3")

        # The host's snapshot stands in for the page while Ducky UI covers it.
        page.evaluate("window.postMessage({channel: 'uefn-plugin-ui', event: {type: 'browser_pane_snapshot',"
                      " data: 'data:image/gif;base64,R0lGODlhAQABAAAAACw='}}, '*')")
        page.wait_for_function("document.getElementById('snap').classList.contains('is-on')")
        page.evaluate("window.postMessage({channel: 'uefn-plugin-ui', event: {type: 'browser_pane_snapshot',"
                      " data: ''}}, '*')")
        page.wait_for_function("!document.getElementById('snap').classList.contains('is-on')")

        # Closing the last tab leaves a fresh one, never an empty Browser.
        for _ in range(3):
            page.click(".ptab.is-active .ptab-close")
        page.wait_for_function("document.querySelectorAll('.ptab').length === 1")
        browser.close()
