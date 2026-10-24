"""Agents use a signed-in site in the Browser tab only after the person allows it in the chat."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "browser_plugin_sites", Path(__file__).resolve().parents[1] / "backend" / "__init__.py"
)
plugin = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(plugin)


def _overlay(monkeypatch, url: str, sites: list[str]) -> types.SimpleNamespace:
    overlay = types.SimpleNamespace(
        pick_pane_id=lambda pane_id="": "pane1",
        get_state=lambda pid: {"url": url},
        agent_sites=lambda: list(sites),
        site_of=lambda u: "x.com",
        sensitive_site=lambda u: "accounts.google.com" in u,
    )
    ui_web = types.ModuleType("frontend.ui_web")
    ui_web.browser_overlay = overlay
    monkeypatch.setitem(sys.modules, "frontend", types.ModuleType("frontend"))
    monkeypatch.setitem(sys.modules, "frontend.ui_web", ui_web)
    monkeypatch.setitem(sys.modules, "frontend.ui_web.browser_overlay", overlay)
    return overlay


def test_a_site_needs_the_persons_ok(monkeypatch) -> None:
    _overlay(monkeypatch, "https://x.com/home", [])
    with pytest.raises(plugin._NeedSite) as need:
        plugin._agent_page("", "c")
    assert need.value.host == "x.com"
    assert plugin._site_checked(plugin.look_page)(conv_id="c")["need_site"] == "x.com"

    _overlay(monkeypatch, "https://mobile.x.com/home", ["x.com"])
    assert plugin._agent_page("", "c") == ("pane1", "")
    _overlay(monkeypatch, "https://evilx.com/", ["x.com"])
    with pytest.raises(plugin._NeedSite):
        plugin._agent_page("", "c")
    _overlay(monkeypatch, "https://www.linkedin.com/feed/", ["*"])
    assert plugin._agent_page("", "c") == ("pane1", "")
    _overlay(monkeypatch, "https://accounts.google.com/signin", ["*"])
    pid, why = plugin._agent_page("", "c")
    assert pid == "" and "only the person" in why


def test_localhost_only_for_this_chats_sandbox(monkeypatch) -> None:
    _overlay(monkeypatch, "http://127.0.0.1:9999/", ["127.0.0.1"])
    service = types.ModuleType("backend.sandbox.service")
    service.owned_ports = lambda conv_id: {5199}
    monkeypatch.setitem(sys.modules, "backend", types.ModuleType("backend"))
    monkeypatch.setitem(sys.modules, "backend.sandbox", types.ModuleType("backend.sandbox"))
    monkeypatch.setitem(sys.modules, "backend.sandbox.service", service)
    pid, why = plugin._agent_page("", "c")
    assert pid == "" and "sandbox" in why


@pytest.mark.parametrize("answer", ["x.com", "*", ""])
def test_site_work_asks_once_then_runs_again(monkeypatch, answer: str) -> None:
    _overlay(monkeypatch, "https://x.com/home", [])
    runs: list[dict] = []
    saved: list[list[str]] = []

    def pane_work(name, **params):
        runs.append(params)
        return {"ok": False, "need_site": "x.com"} if len(runs) == 1 else {"ok": True, "text": "home"}

    monkeypatch.setattr(plugin, "_pane_work", pane_work)
    monkeypatch.setattr(plugin, "_calling_chat", lambda: "c")
    monkeypatch.setattr(plugin, "_ask_site", lambda host: answer)
    monkeypatch.setattr(plugin, "_set_sites", lambda sites: saved.append(sites) or "")
    out = plugin._site_work("look_page", pane_id="")
    if answer:
        assert out == {"ok": True, "text": "home"} and saved == [[answer]] and len(runs) == 2
    else:
        assert out["ok"] is False and saved == [] and len(runs) == 1


def test_agents_open_switch_and_close_page_tabs(monkeypatch) -> None:
    app = "plugin:browser:browser"
    overlay = _overlay(monkeypatch, "https://x.com/", [])
    panes = [{"pane_id": f"{app}::t1", "url": "https://x.com/", "title": "X"}]
    sent: list[tuple] = []

    def push(app_tab, action, **data):
        sent.append((app_tab, action, data))
        if action == "new":
            panes.append({"pane_id": f"{app_tab}::{data['tab']}", "url": data["url"], "title": ""})
        return {"ok": True}

    overlay.list_panes = lambda: panes
    overlay.push_tab_command = push
    overlay.pick_pane_id = lambda pid="", allow_fallback=True: (
        pid if any(p["pane_id"] == pid for p in panes) else ("" if pid else panes[0]["pane_id"]))
    overlay.normalize_url = lambda u: u
    overlay.is_app_ui_url = lambda u: False
    monkeypatch.setattr(plugin, "_bring_tab_forward", lambda: (f"{app}::t1", ""))

    out = plugin.new_tab("https://linkedin.com/feed")
    assert out["ok"] and out["pane_id"].startswith(f"{app}::a") and sent[-1][1] == "new"
    listed = plugin.tabs_info()["tabs"]
    assert [t["active"] for t in listed] == [True, False]
    assert plugin.switch_tab(out["pane_id"]) == {"ok": True} and sent[-1][1] == "switch"
    assert plugin.close_tab(out["pane_id"]) == {"ok": True} and sent[-1][:2] == (app, "close")
    assert plugin.close_tab(f"{app}::nope")["ok"] is False


def test_bad_refs_and_keys_are_refused_before_the_page() -> None:
    assert "isn't a ref" in plugin._click_ref("pane1", "e1'); alert(1); ('")
    assert "isn't a key" in plugin._press("pane1", "F13")


def test_look_marks_what_can_be_clicked_and_point_finds_it() -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="msedge")
        except Exception as exc:  # no Edge / browser on this machine
            pytest.skip(f"no browser: {exc}")
        page = browser.new_page()
        page.set_content('<p>Hello</p><button aria-label="Post">x</button><div contenteditable="true" style="height:20px">'
                         '</div><button style="display:none">hidden</button><a href="/n">Next</a>')
        out = page.evaluate(plugin._LOOK_JS % 1000)
        names = [(e["ref"], e["name"]) for e in out["elements"]]
        assert names == [("e1", "Post"), ("e2", ""), ("e3", "Next")]
        assert "Hello" in out["text"]
        point = page.evaluate(plugin._POINT_JS % "e1")
        assert point["ok"] and point["x"] > 0 and point["y"] > 0
        assert page.evaluate(plugin._POINT_JS % "e9") == {"ok": False}

        page.set_content('<input type="password" value="hunter2"><input autocomplete="one-time-code" value="123456">'
                         '<input value="draft">')
        out = page.evaluate(plugin._LOOK_JS % 1000)
        assert "hunter2" not in str(out) and "123456" not in str(out) and "draft" in str(out)
        assert [e.get("secret", False) for e in out["elements"]] == [True, True, False]
        assert page.evaluate(plugin._POINT_JS % "e1")["secret"] is True
        browser.close()


def test_type_refuses_a_password_box(monkeypatch) -> None:
    overlay = _overlay(monkeypatch, "https://x.com/login", ["x.com"])
    sent: list[str] = []
    overlay.evaluate = lambda pid, js, timeout_s: {"ok": True, "value": {"ok": True, "x": 1, "y": 1, "secret": True}}
    overlay.devtools = lambda pid, method, params, timeout_s: sent.append(method) or {"ok": True}
    out = plugin.type_page("e1", "hunter2", conv_id="c")
    assert out["ok"] is False and "types that themselves" in out["error"] and sent == []
