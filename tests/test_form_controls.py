"""Agents fill whole forms in a Browser tab behind the chat: dropdowns, date boxes and checkboxes
take their value, a click lands where the button is after a smooth scroll, and a banner over it
is named instead of clicked (harness races, Oct 31 2026)."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "browser_plugin_form_controls", Path(__file__).resolve().parents[1] / "backend" / "__init__.py"
)
plugin = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(plugin)


def _page(monkeypatch, kind: dict, *, point: dict | None = None, choose: dict | None = None,
          set_value: dict | None = None, checked_after: bool = True) -> dict:
    """One marked element of *kind*; records what the page was asked to run."""
    page: dict = {"calls": [], "scripts": [], "checked": bool(kind.get("checked"))}

    def evaluate(pid, js, timeout_s=0):
        page["scripts"].append(js)
        if js is plugin._POINT_JS % "e3" or "getBoundingClientRect" in js:
            return {"ok": True, "value": point or {"ok": True, "x": 10, "y": 10, "secret": False, "covered": ""}}
        if "HTMLSelectElement" in js:
            return {"ok": True, "value": choose or {}}
        if "HTMLInputElement" in js:
            return {"ok": True, "value": set_value or {}}
        if "disabled:" in js:
            return {"ok": True, "value": {"ok": True, "tag": "input", "type": "", "disabled": False,
                                          **kind, "checked": page["checked"]}}
        return {"ok": True, "value": {}}

    def devtools(pid, method, params, timeout_s=0):
        page["calls"].append(method)
        if method == "Input.dispatchMouseEvent" and params.get("type") == "mouseReleased":
            page["checked"] = checked_after
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


def test_a_dropdown_takes_its_option_instead_of_typed_text(monkeypatch) -> None:
    # The typed "E-bike" landed in the email box focused before the dropdown.
    page = _page(monkeypatch, {"tag": "select"}, choose={"ok": True, "found": True, "label": "E-bike", "value": "ebike"})
    assert plugin.type_page("e3", "e-bike", conv_id="c") == {"ok": True, "done": "chose 'E-bike' in e3"}
    assert "Input.insertText" not in page["calls"]
    assert any(json.dumps("e-bike") in s for s in page["scripts"])


def test_a_missing_option_lists_the_ones_there_are(monkeypatch) -> None:
    _page(monkeypatch, {"tag": "select"}, choose={"ok": True, "found": False, "options": ["Road", "E-bike"]})
    out = plugin.type_page("e3", "Unicycle", conv_id="c")
    assert out == {"ok": False, "error": "e3 has no option 'Unicycle'. Its options: Road, E-bike."}


def test_a_date_box_takes_its_value_and_says_the_format_it_wants(monkeypatch) -> None:
    page = _page(monkeypatch, {"type": "date"}, set_value={"ok": True, "took": True, "value": "2026-11-04"})
    assert plugin.type_page("e4", "2026-11-04", conv_id="c") == {"ok": True, "done": "set e4 to 2026-11-04"}
    assert "Input.insertText" not in page["calls"]
    _page(monkeypatch, {"type": "date"}, set_value={"ok": True, "took": False, "value": ""})
    out = plugin.type_page("e4", "11052026", conv_id="c")
    assert out["ok"] is False and "YYYY-MM-DD" in out["error"]


def test_a_checkbox_is_ticked_with_a_real_click_and_checked_after(monkeypatch) -> None:
    page = _page(monkeypatch, {"type": "checkbox", "checked": False})
    assert plugin.type_page("e5", "true", conv_id="c") == {"ok": True, "done": "ticked e5"}
    assert page["calls"].count("Input.dispatchMouseEvent") == 3
    assert plugin.type_page("e5", "yes", conv_id="c") == {"ok": True, "done": "e5 was already ticked"}
    _page(monkeypatch, {"type": "checkbox", "checked": False}, checked_after=False)
    assert "didn't tick" in plugin.type_page("e5", "true", conv_id="c")["error"]
    assert "true to tick" in plugin.type_page("e5", "maybe", conv_id="c")["error"]


def test_typing_into_a_button_says_to_click_it(monkeypatch) -> None:
    _page(monkeypatch, {"tag": "button"})
    assert plugin.type_page("e6", "hello", conv_id="c")["error"] == "e6 is a button or link, not a box: browser_click it."


def test_a_click_scrolls_at_once_and_waits_for_the_button_to_stop_moving() -> None:
    # On a page with `scroll-behavior: smooth` the centre was read before the scroll ran.
    assert "behavior: 'instant'" in plugin._POINT_JS and "getBoundingClientRect" in plugin._POINT_JS
    assert "await sleep" in plugin._POINT_JS


def test_a_banner_over_the_button_is_named_not_clicked(monkeypatch) -> None:
    page = _page(monkeypatch, {"tag": "button"},
                 point={"ok": True, "x": 10, "y": 10, "secret": False, "covered": "We use cookies"})
    out = plugin.click_page("e6", conv_id="c")
    assert out["ok"] is False and "'We use cookies'" in out["error"]
    assert "Input.dispatchMouseEvent" not in page["calls"]


def test_clicks_and_keys_run_with_the_page_acting_focused(monkeypatch) -> None:
    page = _page(monkeypatch, {"tag": "button"})
    assert plugin.click_page("e6", conv_id="c") == {"ok": True, "done": "clicked e6"}
    assert plugin.press_page("Enter", conv_id="c") == {"ok": True, "done": "pressed Enter"}
    focus = [i for i, m in enumerate(page["calls"]) if m == "Emulation.setFocusEmulationEnabled"]
    assert len(focus) == 4 and page["calls"][-1] == "Emulation.setFocusEmulationEnabled"
