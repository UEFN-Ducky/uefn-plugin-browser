"""browser_type types into a tab that is behind Ducky's page, and says so when the text never
arrived instead of reporting it typed."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "browser_plugin_type_check", Path(__file__).resolve().parents[1] / "backend" / "__init__.py"
)
plugin = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(plugin)


def _page(monkeypatch, *, emulation_works: bool) -> dict:
    """A page with one text box, in a tab without focus: text lands only while it acts focused."""
    page: dict = {"value": "", "focused": False, "calls": []}

    def evaluate(pid, js, timeout_s=0):
        if "getBoundingClientRect" in js:
            return {"ok": True, "value": {"ok": True, "x": 10, "y": 10, "secret": False}}
        if "activeElement" in js:
            return {"ok": True, "value": {"ok": True, "value": page["value"]}}
        return {"ok": True, "value": {}}

    def devtools(pid, method, params, timeout_s=0):
        page["calls"].append(method)
        if method == "Emulation.setFocusEmulationEnabled":
            if not emulation_works:
                return {"ok": False, "error": "not supported"}
            page["focused"] = bool(params["enabled"])
        elif method == "Input.insertText" and page["focused"]:
            page["value"] += params["text"]
        return {"ok": True}

    overlay = types.SimpleNamespace(evaluate=evaluate, devtools=devtools)
    ui_web = types.ModuleType("frontend.ui_web")
    ui_web.browser_overlay = overlay
    monkeypatch.setitem(sys.modules, "frontend", types.ModuleType("frontend"))
    monkeypatch.setitem(sys.modules, "frontend.ui_web", ui_web)
    monkeypatch.setitem(sys.modules, "frontend.ui_web.browser_overlay", overlay)
    monkeypatch.setattr(plugin, "_agent_page", lambda pane_id, conv_id: ("pane1", ""))
    monkeypatch.setattr(plugin.time, "sleep", lambda s: None)
    monkeypatch.setattr(plugin, "_after", lambda pid, conv_id, done, max_chars: {"ok": True, "done": done})
    return page


def test_text_reaches_a_box_in_a_tab_behind_the_chat(monkeypatch) -> None:
    # Oct 31 2026: browser_type said "typed into e5" twice while the box stayed empty.
    page = _page(monkeypatch, emulation_works=True)
    out = plugin.type_page("e5", "Mallard", conv_id="c")
    assert out == {"ok": True, "done": "typed into e5"}
    assert page["value"] == "Mallard"
    calls = page["calls"]
    assert calls.index("Emulation.setFocusEmulationEnabled") < calls.index("Input.insertText")
    assert calls[-1] == "Emulation.setFocusEmulationEnabled" and page["focused"] is False  # off again


def test_text_that_never_arrived_is_an_error_not_a_success(monkeypatch) -> None:
    page = _page(monkeypatch, emulation_works=False)
    out = plugin.type_page("e5", "Mallard", submit=True, conv_id="c")
    assert out["ok"] is False and "didn't reach e5" in out["error"]
    assert page["value"] == "" and "Input.dispatchKeyEvent" not in page["calls"]  # no Enter after a miss
