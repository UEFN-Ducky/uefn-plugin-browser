"""Agents use the person's own Chrome only when Settings allow it, after they say yes in the chat."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("browser_plugin_chrome", _ROOT / "backend" / "__init__.py")
plugin = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(plugin)
_CSPEC = importlib.util.spec_from_file_location("browser_plugin_chrome_mod", _ROOT / "backend" / "chrome.py")
chrome = importlib.util.module_from_spec(_CSPEC)
_CSPEC.loader.exec_module(chrome)


def _setup(monkeypatch, prefs: dict, answer: str = "", chat: str = "c1") -> tuple[list, list]:
    asked: list[int] = []
    saved: list[dict] = []
    monkeypatch.setattr(plugin, "_chrome_chats", set())
    monkeypatch.setattr(plugin, "_chrome_prefs", lambda: dict(prefs))
    monkeypatch.setattr(plugin, "_calling_chat", lambda: chat)
    monkeypatch.setattr(plugin, "_ask_own_chrome", lambda: asked.append(1) or answer)
    host = types.ModuleType("frontend.ui_web.plugin_host_api")
    host.prefs_plugin_set = lambda pid, p: saved.append(p) or {"ok": True}
    monkeypatch.setitem(sys.modules, "frontend", types.ModuleType("frontend"))
    monkeypatch.setitem(sys.modules, "frontend.ui_web", types.ModuleType("frontend.ui_web"))
    monkeypatch.setitem(sys.modules, "frontend.ui_web.plugin_host_api", host)
    return asked, saved


def test_turned_off_in_settings_never_asks(monkeypatch) -> None:
    asked, _ = _setup(monkeypatch, {"ownChrome": False}, answer="chat")
    url, why = plugin._own_chrome_gate()
    assert "turned off" in why and not asked


def test_asks_once_per_chat_then_remembers(monkeypatch) -> None:
    asked, saved = _setup(monkeypatch, {"ownChromeUrl": " http://127.0.0.1:9222 "}, answer="chat")
    assert plugin._own_chrome_gate() == ("http://127.0.0.1:9222", "")
    assert plugin._own_chrome_gate() == ("http://127.0.0.1:9222", "")
    assert len(asked) == 1 and not saved


def test_no_means_no(monkeypatch) -> None:
    asked, _ = _setup(monkeypatch, {}, answer="")
    url, why = plugin._own_chrome_gate()
    assert "didn't let" in why and len(asked) == 1


def test_always_allow_turns_the_question_off(monkeypatch) -> None:
    asked, saved = _setup(monkeypatch, {}, answer="always")
    assert plugin._own_chrome_gate() == ("", "")
    assert saved == [{"ownChromeAsk": False}]


def test_question_off_in_settings(monkeypatch) -> None:
    asked, _ = _setup(monkeypatch, {"ownChromeAsk": "false"})
    assert plugin._own_chrome_gate() == ("", "") and not asked


def test_launch_attaches_to_their_chrome_without_statistics() -> None:
    assert chrome.launch_args()[1:] == ["--autoConnect", "--no-usage-statistics", "--no-performance-crux"]
    assert chrome.launch_args("http://127.0.0.1:9222")[1] == "--browser-url=http://127.0.0.1:9222"
    assert chrome.SERVER_JS.is_file()
    assert chrome.connect_hint("Could not connect to Chrome. Check if Chrome is running") == chrome.SETUP
    assert chrome.connect_hint("Input validation error") == ""
