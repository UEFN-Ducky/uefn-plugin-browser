"""browser_batch runs a list of steps in one call, finding elements by name, and stops at the
first step that fails."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "browser_plugin_batch", Path(__file__).resolve().parents[1] / "backend" / "__init__.py"
)
plugin = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(plugin)


def _page(monkeypatch, names: list[str]) -> dict:
    """A page whose elements are called *names*; each text box keeps what is typed into it."""
    page: dict = {"marked": "", "values": {}, "clicked": [], "focused": False}

    def evaluate(pid, js, timeout_s=0):
        if "tiers" in js:  # _FIND_JS
            want = js.rsplit("})(", 1)[1].split(",")[0].strip().strip('"')
            if want in names:
                page["marked"] = want
                return {"ok": True, "value": {"ok": True, "found": True, "count": 1}}
            return {"ok": True, "value": {"ok": True, "found": False, "count": 0, "names": names}}
        if "getBoundingClientRect" in js:
            return {"ok": True, "value": {"ok": True, "x": 10, "y": 10, "secret": False}}
        if "disabled:" in js:
            return {"ok": True, "value": {"ok": True, "tag": "input", "type": "text", "checked": False, "disabled": False}}
        if "activeElement" in js:
            return {"ok": True, "value": {"ok": True, "value": page["values"].get(page["marked"], "")}}
        return {"ok": True, "value": {}}

    def devtools(pid, method, params, timeout_s=0):
        if method == "Emulation.setFocusEmulationEnabled":
            page["focused"] = bool(params["enabled"])
        elif method == "Input.insertText" and page["focused"]:
            page["values"][page["marked"]] = page["values"].get(page["marked"], "") + params["text"]
        elif method == "Input.dispatchMouseEvent" and params["type"] == "mousePressed":
            page["clicked"].append(page["marked"])
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
    monkeypatch.setattr(plugin, "_look", lambda pid, max_chars: {"ok": True, "text": "page"})
    return page


def test_fills_a_form_in_one_call(monkeypatch) -> None:
    page = _page(monkeypatch, ["First Name", "Last Name", "Save"])
    out = plugin.batch_page([
        {"type": "First Name", "text": "Ada"},
        {"type": "Last Name", "text": "Lovelace"},
        {"click": "Save"},
    ], conv_id="c")
    assert out["ok"] is True and out["done"] == "ran 3 steps"
    assert page["values"] == {"First Name": "Ada", "Last Name": "Lovelace"}
    assert page["clicked"][-1] == "Save"
    assert out["steps_done"][0] == "typed into 'First Name'"


def test_stops_at_the_first_missing_element(monkeypatch) -> None:
    page = _page(monkeypatch, ["First Name", "Save"])
    out = plugin.batch_page([
        {"type": "First Name", "text": "Ada"},
        {"type": "Nickname", "text": "A"},
        {"click": "Save"},
    ], conv_id="c")
    assert out["ok"] is False and out["failed_step"] == 2
    assert "Nickname" in out["error"] and out["steps_done"] == ["typed into 'First Name'"]
    assert "Save" not in page["clicked"]  # nothing after the failure ran


def test_rejects_an_empty_or_huge_batch(monkeypatch) -> None:
    _page(monkeypatch, [])
    assert plugin.batch_page([], conv_id="c")["ok"] is False
    assert plugin.batch_page([{"wait": 0}] * (plugin._BATCH_MAX + 1), conv_id="c")["ok"] is False
