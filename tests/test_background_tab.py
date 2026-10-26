"""Agents' pages open behind the person's tab and show on the chat card; a workflow brings the
Browser tab up."""

from __future__ import annotations

import base64
import importlib.util
import sys
import types
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "browser_plugin_background", Path(__file__).resolve().parents[1] / "backend" / "__init__.py"
)
plugin = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(plugin)


def _host(monkeypatch, sites: list[str]) -> dict:
    seen: dict = {"rpc": [], "behind": [], "state": {"url": "https://old.example/", "title": "Old", "loading": False}}

    def navigate(pid, url):
        seen["state"] = {"url": url, "title": "Home / X", "loading": False}
        return {"ok": True}

    overlay = types.SimpleNamespace(
        pick_pane_id=lambda pane_id="", allow_fallback=True: "plugin:browser:browser::a1",
        get_state=lambda pid: {"ok": True, **seen["state"]},
        navigate=navigate,
        normalize_url=lambda u: u,
        is_app_ui_url=lambda u: False,
        render_behind=lambda pid, seconds: seen["behind"].append(pid) or {"ok": True},
        agent_sites=lambda: list(sites),
        site_of=lambda u: "x.com",
        sensitive_site=lambda u: False,
        evaluate=lambda pid, js, timeout_s=0: {"ok": True, "value": {}},
        devtools=lambda pid, method, params, timeout_s=0: {"ok": True, "reply": {"data": base64.b64encode(b"png").decode()}},
    )
    captures = types.ModuleType("frontend.ui_web.tool_captures")
    captures.save_capture_for_agents = lambda data, prefix, conv_id: {"ok": True, "path": "C:\\caps\\browser_page_1.png"}
    ui_web = types.ModuleType("frontend.ui_web")
    ui_web.browser_overlay = overlay
    rpc = types.ModuleType("backend.panel.rpc")
    rpc.panel_rpc = lambda method, params, timeout=0: seen["rpc"].append((method, dict(params))) or {
        "ok": True, "tab": "plugin:browser:browser"}
    for name, module in {
        "frontend": types.ModuleType("frontend"), "frontend.ui_web": ui_web,
        "frontend.ui_web.browser_overlay": overlay, "frontend.ui_web.tool_captures": captures,
        "backend": types.ModuleType("backend"), "backend.panel": types.ModuleType("backend.panel"),
        "backend.panel.rpc": rpc,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    return seen


def test_an_agents_page_opens_behind_and_shows_on_the_card(monkeypatch) -> None:
    seen = _host(monkeypatch, ["x.com"])
    out = plugin.open_page("https://x.com/home", conv_id="c1", preview=True)
    assert seen["rpc"] == [("open_plugin_panel", {"plugin_id": "browser", "panel_id": "browser",
                                                  "title": "Browser", "background": True})]
    assert seen["behind"]  # the page keeps drawing while its tab is off screen
    view = out["chat_view"]
    assert view["title"] == "Home / X · x.com"
    assert view["media"] == ["C:\\caps\\browser_page_1.png"]
    assert view["open"] == {"panel": "browser", "label": "Open in Browser"}


def test_no_picture_of_a_site_agents_may_not_use(monkeypatch) -> None:
    _host(monkeypatch, [])
    out = plugin.open_page("https://x.com/home", conv_id="c1", preview=True)
    assert out["ok"] and "media" not in out["chat_view"]


def test_a_workflow_brings_the_browser_tab_up(monkeypatch) -> None:
    seen = _host(monkeypatch, [])
    out = plugin._open_node({"inputs": {"url": "https://x.com/"}})
    assert out["ok"] and "chat_view" not in out
    assert seen["rpc"][0][1].get("background") is None
    assert seen["behind"] == []
