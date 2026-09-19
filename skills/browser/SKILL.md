---
name: browser
description: "In-app Chromium browser in UEFN-Ducky — open the Browser tab, navigate via browser_* MCP tools, and drive full DOM automation with chrome-devtools-mcp (--autoConnect to the pane's EBWebView profile)"
license: MIT
metadata:
  label: Browser
  version: 2
  author: UEFN-Ducky
  copyright: Copyright 2026 Mindful Path Company, LLC
  allow_redistribute: true
  managed_by: uefn-ducky
  source_plugin_id: browser
---

# Browser — director (in-app Chromium + CDP)

You drive the **in-app browser** through the **browser** Store plugin (`browser_*` on shared `uefn-ducky` MCP). The visited page is a real WebView2 pane — not an iframe — so sites that block embedding still work.

**Never navigate the pane to the app's own panel URL** (`http://127.0.0.1:…/` or `localhost:5173`). That causes a self-embed / Droste loop; the host blocks it.

## Prerequisites

1. Plugin **browser** installed + enabled.
2. Tools opted in for this chat.
3. **Open a Browser tab first** (header globe → **+ New browser**, or pick an existing one) so a native pane exists. Settings (history / cache / homepage) are in that same dropdown.

## Navigation (MCP)

| Tool | Use |
|------|-----|
| `browser_status` | List open panes + CDP summary |
| `browser_navigate` | Go to a URL (`pane_id` optional) |
| `browser_command` | `back` / `forward` / `reload` / `stop` |
| `browser_cdp_info` | Full EBWebView path + `chrome_devtools_mcp_args` |

Typical flow: `browser_status` → `browser_navigate` with `https://…`.

## Cloudflare / “Verify you are human”

Remote debugging (CDP) is **off by default**. Always-on `--remote-debugging-port` made Turnstile loop forever. For normal browsing leave CDP off. Never call `browser_clear_data` while tabs are open in a way that force-deletes Cookies on disk — that freezes WinForms; clear via Settings (uses WebView2 API) or close all Browser tabs first.

## Full DOM automation (chrome-devtools-mcp)

`browser_*` tools handle navigation and history. For snapshot / click / fill / evaluate:

1. Enable CDP: Browser Settings → **Enable remote debugging**, Save — applies on next start (or set `UEFN_DUCKY_BROWSER_CDP=1`).
2. Call `browser_cdp_info` (requires `cdp_enabled: true`).
3. Add **chrome-devtools-mcp** to the IDE with the returned args, e.g.:

```json
{
  "chrome-devtools": {
    "command": "npx",
    "args": [
      "chrome-devtools-mcp@latest",
      "--autoConnect",
      "--user-data-dir=<ebwebview_dir from browser_cdp_info>"
    ]
  }
}
```

Use the **EBWebView** profile from `browser_cdp_info` — **not** the system Chrome profile.

4. Open the Browser tab and navigate to the target page before using CDP tools.

## Do not

- Navigate to `127.0.0.1` / `localhost` panel URLs or `/plugin-ui/` paths in the browser pane.
- Point chrome-devtools-mcp at your daily Chrome user-data-dir (wrong session; use EBWebView).
