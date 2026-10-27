"""The person's own Google Chrome, driven through Chrome DevTools MCP (bundled).

``vendor/chrome-devtools-mcp`` is Google's chrome-devtools-mcp npm package, pinned
(VERSION); it has no runtime dependencies, so nothing is fetched from npm. Node is
Ducky's own pinned runtime (``backend.sandbox.runtimes``), else one on PATH.

``--autoConnect`` attaches to the Chrome the person already has open (Chrome 144+):
they turn on chrome://inspect/#remote-debugging once, and Chrome asks them to Allow
each new connection. ``browser_url`` (http://127.0.0.1:9222) is for a Chrome started
with --remote-debugging-port instead.

One background asyncio loop owns the stdio session; tool calls come from many threads
(FastMCP) and go to it with run_coroutine_threadsafe.
"""

from __future__ import annotations

import asyncio
import base64
import os
import shutil
import threading
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

VERSION = "1.12.0"
SERVER_JS = Path(__file__).resolve().parents[1] / "vendor" / "chrome-devtools-mcp" / "build" / "src" / "bin" / "chrome-devtools-mcp.js"
CONNECT_TIMEOUT_S = 30.0
CALL_TIMEOUT_S = 120.0

SETUP = (
    "Use the person's own Chrome: 1) Chrome open (version 144 or newer). 2) In Chrome, go to "
    "chrome://inspect/#remote-debugging and turn remote debugging on (once). 3) On the first "
    "chrome_call Chrome asks them to Allow the connection; they press Allow."
)

_lock = threading.Lock()
_state: dict[str, Any] = {"phase": "idle", "error": "", "browser_url": ""}
_loop: asyncio.AbstractEventLoop | None = None
_stack: AsyncExitStack | None = None
_session: Any = None


def node_exe() -> str:
    """Ducky's pinned Node (set up on first use), else node on PATH; "" when neither."""
    try:
        from backend.sandbox.runtimes import setup

        got = setup("node")
        if got.get("ok"):
            exe = Path(str(got["path"])) / "node.exe"
            if exe.is_file():
                return str(exe)
    except Exception:  # noqa: BLE001 — not inside Ducky, or offline on first use
        pass
    return shutil.which("node") or ""


def launch_args(browser_url: str = "") -> list[str]:
    """The server's arguments: attach to the person's Chrome, no usage statistics sent."""
    target = f"--browser-url={browser_url}" if browser_url else "--autoConnect"
    return [str(SERVER_JS), target, "--no-usage-statistics", "--no-performance-crux"]


def status() -> dict[str, Any]:
    with _lock:
        out = dict(_state)
    out.update({"server": f"chrome-devtools-mcp {VERSION}", "bundled": SERVER_JS.is_file()})
    return out


def close() -> None:
    global _loop, _stack, _session
    with _lock:
        loop, stack = _loop, _stack
        _loop = _stack = _session = None
        _state.update({"phase": "idle", "error": ""})
    if loop is None:
        return
    if stack is not None:
        try:
            asyncio.run_coroutine_threadsafe(stack.aclose(), loop).result(timeout=5)
        except Exception:  # noqa: BLE001 — the server may already be gone
            pass
    loop.call_soon_threadsafe(loop.stop)


def connect(browser_url: str = "") -> dict[str, Any]:
    """Start the bundled server (again when browser_url changes). Safe from any thread."""
    global _loop, _stack, _session
    with _lock:
        if _session is not None and _state["browser_url"] == browser_url:
            return dict(_state)
    close()
    if not SERVER_JS.is_file():
        return _fail("The bundled Chrome DevTools MCP is missing; reinstall the Web Browser plugin.")
    node = node_exe()
    if not node:
        return _fail("Node.js isn't available and Ducky couldn't set it up (offline?). Try again online.")

    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True, name="chrome-devtools-mcp").start()

    async def start() -> tuple[AsyncExitStack, Any]:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        env = dict(os.environ, CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS="1", CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS="1")
        stack = AsyncExitStack()
        read, write = (await stack.enter_async_context(
            stdio_client(StdioServerParameters(command=node, args=launch_args(browser_url), env=env))
        ))[:2]
        session = await stack.enter_async_context(ClientSession(read, write))
        await asyncio.wait_for(session.initialize(), timeout=CONNECT_TIMEOUT_S)
        return stack, session

    try:
        stack, session = asyncio.run_coroutine_threadsafe(start(), loop).result(timeout=CONNECT_TIMEOUT_S + 5)
    except Exception as exc:  # noqa: BLE001
        loop.call_soon_threadsafe(loop.stop)
        return _fail(f"Chrome DevTools MCP didn't start: {describe(exc)}", browser_url)
    with _lock:
        _loop, _stack, _session = loop, stack, session
        _state.update({"phase": "ready", "error": "", "browser_url": browser_url})
        return dict(_state)


def _fail(error: str, browser_url: str = "") -> dict[str, Any]:
    with _lock:
        _state.update({"phase": "error", "error": error, "browser_url": browser_url})
        return dict(_state)


def describe(exc: BaseException) -> str:
    """Readable text for an error (anyio task groups nest the real one)."""
    nested = getattr(exc, "exceptions", None)
    if nested:
        return "; ".join(describe(sub) for sub in nested)
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def _run(work: Any, browser_url: str) -> Any:
    state = connect(browser_url)
    if state.get("phase") != "ready":
        raise RuntimeError(state.get("error") or "Chrome DevTools MCP isn't running")
    with _lock:
        loop, session = _loop, _session
    if loop is None or session is None:
        raise RuntimeError("Chrome DevTools MCP stopped; call chrome_reconnect")
    return asyncio.run_coroutine_threadsafe(work(session), loop).result(timeout=CALL_TIMEOUT_S + 5)


def list_tools(browser_url: str = "") -> list[dict[str, Any]]:
    async def work(session: Any) -> list[dict[str, Any]]:
        got = await asyncio.wait_for(session.list_tools(), timeout=CALL_TIMEOUT_S)
        return [{"name": t.name, "description": t.description or "", "input_schema": t.inputSchema or {}}
                for t in got.tools or []]

    return _run(work, browser_url)


def connect_hint(text: str) -> str:
    """The setup steps when an error says Chrome couldn't be reached, else ""."""
    low = text.lower()
    if any(k in low for k in ("could not connect", "devtoolsactiveport", "econnrefused", "remote debugging",
                              "failed to fetch browser", "no browser", "not allowed")):
        return SETUP
    return ""


def call(tool: str, arguments: dict[str, Any], browser_url: str = "") -> dict[str, Any]:
    """One chrome-devtools-mcp tool: {ok, text, images: [{mime, data(bytes)}]}."""
    async def work(session: Any) -> Any:
        return await asyncio.wait_for(session.call_tool(tool, arguments), timeout=CALL_TIMEOUT_S)

    result = _run(work, browser_url)
    texts: list[str] = []
    images: list[dict[str, Any]] = []
    for block in getattr(result, "content", None) or []:
        if isinstance(getattr(block, "text", None), str):
            texts.append(block.text)
        elif isinstance(getattr(block, "data", None), str):
            images.append({"mime": str(getattr(block, "mimeType", "") or "image/png"),
                           "data": base64.b64decode(block.data)})
    text = "\n".join(texts)
    ok = not bool(getattr(result, "isError", False))
    out: dict[str, Any] = {"ok": ok, "tool": tool, "text": text, "images": images}
    if not ok and connect_hint(text):
        out["hint"] = SETUP
    return out
