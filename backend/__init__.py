"""Web Browser UEFN desktop plugin — native pane + MCP tools for AI navigation."""

from __future__ import annotations

import json
from typing import Any

INTENT = r"\b(browser|chrome|devtools|cdp)\b"


def _dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)


def register(api) -> None:
    from frontend.ui_web import browser_overlay

    api.log("Browser plugin ready (ui panel + native browser pane + MCP tools)")

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

    @api.tool(name="browser_navigate", intent=INTENT)
    def browser_navigate(url: str, pane_id: str = "") -> str:
        """Navigate a browser pane to *url* (http/https only; app UI blocked)."""
        pid = browser_overlay.pick_pane_id(pane_id)
        if not pid:
            return _dumps({"ok": False, "error": "no browser pane open — open the Browser tab first"})
        return _dumps(browser_overlay.navigate(pid, url))

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
