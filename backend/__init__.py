"""Web Browser UEFN desktop plugin — native pane, MCP tools for AI navigation, workflow node."""

from __future__ import annotations

import json
import re
import time
from typing import Any

INTENT = r"\b(browser|chrome|devtools|cdp)\b"

# How long a Browser tab that was just asked for gets to create its page view.
_TAB_WAIT_S = 20.0
# A dev server typed without http:// ("localhost:5199/x") is still an address.
_LOCAL_HOST = re.compile(r"^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?([/?#]|$)", re.IGNORECASE)


def _dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)


def _address(url: str) -> str:
    u = (url or "").strip()
    return f"http://{u}" if _LOCAL_HOST.match(u) else u


def _bring_tab_forward() -> tuple[str, str]:
    """Open the Browser tab, or bring it to the front, and wait for its page view.

    Returns (pane_id, "") or ("", why not)."""
    from backend.panel.rpc import panel_rpc
    from frontend.ui_web import browser_overlay

    opened = panel_rpc(
        "open_plugin_panel", {"plugin_id": "browser", "panel_id": "browser", "title": "Browser"}, timeout=10.0
    )
    if opened.get("error") == "panel not open":
        return "", "Ducky's window isn't open, so there is no Browser tab to show the page in."
    # The tab Ducky opened; with other Browser tabs open, the page goes to this one.
    # An app that can't open plugin tabs answers with an error: then any Browser tab
    # the person opens while this waits will do.
    tab = "" if opened.get("error") else str(opened.get("tab") or "")
    deadline = time.monotonic() + _TAB_WAIT_S
    while True:
        pid = browser_overlay.pick_pane_id(tab, allow_fallback=False) if tab else browser_overlay.pick_pane_id()
        if pid:
            return pid, ""
        if time.monotonic() >= deadline:
            return "", (
                f"The Browser tab didn't open within {_TAB_WAIT_S:.0f} s. "
                "Open it with the Web Browser button at the top of Ducky and try again."
            )
        time.sleep(0.25)


def _check_address(url: str) -> str:
    """Why *url* can't be shown, or ''."""
    from frontend.ui_web import browser_overlay

    if not browser_overlay.normalize_url(url):
        return f"{url!r} isn't a page address. Use https://…, http://… or localhost:<port>."
    if browser_overlay.is_app_ui_url(url):
        return "That address is Ducky's own window, which can't open inside itself."
    return ""


def open_page(url: str) -> dict[str, Any]:
    """Show *url* in the Browser tab, opening the tab first and bringing it to the front."""
    from frontend.ui_web import browser_overlay

    address = _address(url)
    problem = _check_address(address)
    if problem:
        return {"ok": False, "error": problem}
    pid, why = _bring_tab_forward()
    if not pid:
        return {"ok": False, "error": why}
    shown = browser_overlay.navigate(pid, address)
    if shown.get("ok") is False:
        return {"ok": False, "error": str(shown.get("error") or "the page didn't open")}
    return {"ok": True, "url": browser_overlay.normalize_url(address), "pane_id": pid}


def _open_node(ctx: dict[str, Any]) -> dict[str, Any]:
    """Workflow node browser.open: its Page address pin (wired, or set in its details)."""
    inputs = ctx.get("inputs") if isinstance(ctx.get("inputs"), dict) else {}
    url = str(inputs.get("url") or "").strip()
    if not url:
        return {"ok": False, "error": "Set the page address to show (https://…, http://… or localhost:<port>)."}
    return open_page(url)


def register(api) -> None:
    from frontend.ui_web import browser_overlay

    api.log("Browser plugin ready (ui panel + native browser pane + MCP tools + workflow node)")
    api.register_pipeline_node("browser.open", _open_node)

    @api.tool(name="browser_status", intent=INTENT)
    def browser_status() -> str:
        """List open browser panes and Chrome DevTools connection summary."""
        panes = browser_overlay.list_panes()
        cdp = browser_overlay.cdp_info()
        return _dumps(
            {
                "panes": panes,
                "pane_count": len(panes),
                "default_pane_id": browser_overlay.pick_pane_id(),
                "cdp": {
                    "ebwebview_dir": cdp.get("ebwebview_dir"),
                    "devtools_port": cdp.get("devtools_port"),
                    "cdp_enabled": cdp.get("cdp_enabled"),
                    "chrome_devtools_mcp_args": cdp.get("chrome_devtools_mcp_args"),
                    "hint": cdp.get("hint"),
                },
            }
        )

    @api.tool(name="browser_open", intent=INTENT)
    def browser_open(url: str) -> str:
        """Show *url* to the user in the Browser tab: opens the tab when it isn't open and
        brings it to the front. https://…, http://… or localhost:<port> (a local dev server)."""
        return _dumps(open_page(url))

    @api.tool(name="browser_navigate", intent=INTENT)
    def browser_navigate(url: str, pane_id: str = "") -> str:
        """Navigate a browser pane to *url* (http/https or localhost:<port>; app UI blocked).
        With no Browser tab open, opens one first."""
        address = _address(url)
        pid = browser_overlay.pick_pane_id(pane_id)
        if not pid:
            problem = _check_address(address)
            if problem:
                return _dumps({"ok": False, "error": problem})
            pid, why = _bring_tab_forward()
            if not pid:
                return _dumps({"ok": False, "error": why})
        return _dumps(browser_overlay.navigate(pid, address))

    @api.tool(name="browser_command", intent=INTENT)
    def browser_command(command: str, pane_id: str = "") -> str:
        """Run back / forward / reload / stop on a browser pane."""
        pid = browser_overlay.pick_pane_id(pane_id)
        if not pid:
            return _dumps({"ok": False, "error": "no browser pane open — open the Browser tab first"})
        return _dumps(browser_overlay.command(pid, command))

    @api.tool(name="browser_cdp_info", intent=INTENT)
    def browser_cdp_info() -> str:
        """Full CDP profile info for chrome-devtools-mcp (--autoConnect wiring)."""
        return _dumps(browser_overlay.cdp_info())

    @api.tool(name="browser_clear_data", intent=INTENT)
    def browser_clear_data(kinds: str = "all") -> str:
        """Clear in-app browser profile data. kinds: all | cache | cookies | history."""
        return _dumps(browser_overlay.clear_browsing_data(kinds))

    @api.tool(name="browser_runtime_info", intent=INTENT)
    def browser_runtime_info() -> str:
        """Chrome/WebView2 version, profile path, and security isolation summary."""
        return _dumps(browser_overlay.runtime_info())

    @api.tool(name="browser_site_security", intent=INTENT)
    def browser_site_security(pane_id: str = "") -> str:
        """Chrome-like site security: connection, certificate, cookies, engine protections."""
        return _dumps(browser_overlay.site_security_info(pane_id))
