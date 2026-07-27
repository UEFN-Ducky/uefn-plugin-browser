# Web Browser

Real Chromium browser tab inside UEFN Ducky — docs, dashboards, search, and AI-driven navigation via browser_* MCP tools. CDP/remote debugging is off by default so Cloudflare checks work; opt in only for chrome-devtools-mcp.

Desktop plugin for [UEFN-Ducky](https://github.com/UEFN-Ducky/UEFN-Ducky) (`browser`).
Install or update from **Settings → Store** in the app — do not install from a zip by hand.

## Build

```bash
py scripts/build_zip.py
```

Writes `deploy/browser-1.0.27.ducky-plugin.zip` (scripts/ and deploy/ are not packed).
