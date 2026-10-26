"""browser_capture waits for a late-rendering page, and starts at the top after browser_open."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "browser_plugin", Path(__file__).resolve().parents[1] / "backend" / "__init__.py"
)
plugin = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(plugin)

# Renders nothing for 1 s, then a tall page scrolled away from the top.
LATE_PAGE = """<!doctype html><body style="margin:0"><script>
setTimeout(() => {
  document.body.innerHTML = '<h1 id="chart">Charts ready</h1><div style="height:4000px"></div>';
  window.scrollTo(0, 2000);
}, 1000);
</script></body>"""


def test_settle_script_waits_for_a_page_that_renders_after_1s() -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="msedge")
        except Exception as exc:  # no Edge / browser on this machine
            pytest.skip(f"no browser: {exc}")
        page = browser.new_page()
        page.set_content(LATE_PAGE)
        assert page.evaluate("document.body.innerText.trim()") == ""
        out = page.evaluate(plugin._SETTLE_JS % 1)  # the capture's first call
        assert out == {"settled": True, "drawn": True}
        assert "Charts ready" in page.evaluate("document.body.innerText")
        assert page.evaluate("window.scrollY") == 0
        browser.close()


def test_capture_settles_first_and_resets_scroll_once_after_open(monkeypatch) -> None:
    calls: list[tuple] = []
    overlay = types.SimpleNamespace(
        normalize_url=lambda u: u,
        is_app_ui_url=lambda u: False,
        navigate=lambda pid, url: {"ok": True},
        evaluate=lambda pid, js, timeout_s: calls.append(("evaluate", pid, js)) or {"ok": True},
        devtools=lambda pid, method, params, timeout_s: calls.append(("shot", pid)) or {"ok": True, "reply": {"data": "aGk="}},
        get_state=lambda pid: {"url": "http://localhost:5199/"},
    )
    captures = types.SimpleNamespace(save_capture_for_agents=lambda data, prefix, conv_id: {"ok": True, "path": "p.png"})
    ui_web = types.ModuleType("frontend.ui_web")
    ui_web.browser_overlay = overlay
    ui_web.tool_captures = captures
    monkeypatch.setitem(sys.modules, "frontend", types.ModuleType("frontend"))
    monkeypatch.setitem(sys.modules, "frontend.ui_web", ui_web)
    monkeypatch.setitem(sys.modules, "frontend.ui_web.browser_overlay", overlay)
    monkeypatch.setitem(sys.modules, "frontend.ui_web.tool_captures", captures)
    monkeypatch.setattr(plugin, "_browser_tab", lambda front=False: ("pane1", ""))
    monkeypatch.setattr(plugin, "_agent_page", lambda pane_id, conv_id: ("pane1", ""))
    plugin._FRESH_PANES.clear()

    assert plugin.open_page("localhost:5199")["ok"] is True
    assert plugin.capture_page(conv_id="c")["ok"] is True
    assert plugin.capture_page(conv_id="c")["ok"] is True
    kinds = [c[0] for c in calls]
    assert kinds == ["evaluate", "shot", "evaluate", "shot"]  # settle before every picture
    assert "TOP = 1," in calls[0][2] and "TOP = 0," in calls[2][2]  # top only after a new open
