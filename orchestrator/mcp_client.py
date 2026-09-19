"""The only door from P3 to the data layer.

Specified by docs/mcp-tools.md and docs/adr/0007.
Implements schema.contracts.interfaces.McpClient.

TRANSPORT (amendment 3)
  MODE=mock, tests  the MCP SDK's IN-MEMORY transport, server in-process
  MODE=live         stdio, server spawned as a subprocess

Both are real MCP. Mock mode deliberately does NOT shortcut to data.api: if it
did, the boundary would only ever be exercised in production, and the first time
anyone found out the wiring was wrong would be during a live run.

Argument validation happens here too, against the contract request models, so a
malformed tool call fails in P3 with a clear message rather than inside P1.
Responses are validated against the contract response models on the way back.

The MCP SDK is async; McpClient is a sync protocol. _SyncSession runs the SDK
session on its own event-loop thread and exposes blocking calls, so the agents
and the coordinator stay plain synchronous code.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from pydantic import ValidationError

from schema.contracts.tools import TOOL_REQUESTS, TOOL_RESPONSES

CALL_TIMEOUT_S = 60.0


def sdk_client_class():
    """mcp 2.x has a high-level `mcp.Client` that covers every transport; mcp 1.x does not.

    P3 supports BOTH majors so the team can pick one without P3 blocking it: 2.x results use
    snake_case fields and 1.x camelCase, and the in-memory / stdio plumbing differs. Everything
    version-specific is confined to this function, `_field()`, and the two open_session factories."""
    try:
        from mcp import Client
    except ImportError:
        return None
    return Client


def _field(obj: Any, snake: str, camel: str, default: Any = None) -> Any:
    """Read a result field by its 2.x (snake_case) or 1.x (camelCase) name."""
    for name in (snake, camel):
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return default


class McpToolError(RuntimeError):
    """The server reported an error for a tool call (out-of-scope ticker, unknown id...)."""

    def __init__(self, tool: str, message: str) -> None:
        super().__init__(f"{tool}: {message}")
        self.tool, self.detail = tool, message


class McpServerUnavailable(RuntimeError):
    """No MCP server could be reached or constructed."""


class ToolArgumentError(ValueError):
    """Arguments failed the contract request model; raised before any server call."""


class _SyncSession:
    """A ClientSession living on a private event loop, used through blocking calls."""

    def __init__(
        self, open_session: Callable[[], AbstractAsyncContextManager], startup_timeout: float = 30.0
    ):
        self._open = open_session
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._session: Any = None
        self._stop: asyncio.Event | None = None
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="mcp-session", daemon=True)
        self._thread.start()
        if not self._ready.wait(startup_timeout):
            raise McpServerUnavailable("timed out starting the MCP session")
        if self._error is not None:
            raise McpServerUnavailable(
                f"could not start the MCP session: {self._error!r}"
            ) from self._error

    def _run(self) -> None:
        self._loop.run_until_complete(self._main())

    async def _main(self) -> None:
        try:
            async with self._open() as session:  # entered and exited in the same task
                self._session, self._stop = session, asyncio.Event()
                self._ready.set()
                await self._stop.wait()
        except BaseException as e:  # noqa: BLE001 - surfaced to the constructor / callers
            self._error = e
            self._ready.set()

    def request(self, fn: Callable[[Any], Any], timeout: float = CALL_TIMEOUT_S) -> Any:
        if self._closed or self._session is None:
            raise McpServerUnavailable("MCP session is closed")
        return asyncio.run_coroutine_threadsafe(fn(self._session), self._loop).result(timeout)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._stop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
        self._thread.join(timeout=10)


class _BaseMcpClient:
    _sync: _SyncSession

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Validate against TOOL_REQUESTS[name], call, validate the response."""
        if name not in TOOL_REQUESTS:
            raise KeyError(f"unknown MCP tool {name!r}; the surface is {sorted(TOOL_REQUESTS)}")
        try:
            request = TOOL_REQUESTS[name].model_validate(arguments)
        except ValidationError as e:
            raise ToolArgumentError(f"{name}: invalid arguments: {e.errors()[:3]}") from e
        payload = request.model_dump(mode="json", exclude_none=True)
        result = self._sync.request(lambda s: s.call_tool(name, payload))
        text = "".join(getattr(c, "text", "") for c in result.content)
        if _field(result, "is_error", "isError", False):
            raise McpToolError(name, text or "tool reported an error")
        data = _field(result, "structured_content", "structuredContent")
        if data is None:
            data = json.loads(text)
        if set(data) == {"result"} and isinstance(data["result"], dict):
            data = data["result"]  # FastMCP wraps non-object returns
        return TOOL_RESPONSES[name].model_validate(data).model_dump(mode="json")

    def list_tools(self) -> list[str]:
        result = self._sync.request(lambda s: s.list_tools())
        return sorted(t.name for t in result.tools)

    def close(self) -> None:
        self._sync.close()


class InMemoryMcpClient(_BaseMcpClient):
    """MCP over the SDK's in-memory transport. Mock mode and every test.

    `server` is any MCP server object (FastMCP or low-level Server). It is
    INJECTED because P3 may not import mcp_server/ (ADR 0007): whoever composes
    the process supplies it.
    """

    def __init__(self, server: Any = None) -> None:
        if server is None:
            raise McpServerUnavailable(
                "InMemoryMcpClient needs a server object. P3 may not import mcp_server/, so the "
                "composition root must inject one (see docs/requests/2026-09-19-p3-to-p1-mock-mcp-server.md)."
            )
        self.server = server
        Client = sdk_client_class()
        if Client is not None:  # mcp 2.x
            self._sync = _SyncSession(lambda: Client(server))
        else:  # mcp 1.x
            from mcp.shared.memory import create_connected_server_and_client_session

            self._sync = _SyncSession(lambda: create_connected_server_and_client_session(server))


class StdioMcpClient(_BaseMcpClient):
    """MCP over stdio against a spawned mcp_server process. Live mode."""

    def __init__(self, command: list[str] | None = None, env: dict[str, str] | None = None) -> None:
        self.command = command or ["python", "-m", "mcp_server.server"]
        child_env = {**os.environ, **(env or {})}

        @asynccontextmanager
        async def open_session():
            from mcp import StdioServerParameters

            params = StdioServerParameters(
                command=self.command[0], args=self.command[1:], env=child_env
            )
            Client = sdk_client_class()
            if Client is not None:  # mcp 2.x
                async with Client(params) as session:
                    yield session
                return
            from mcp import ClientSession  # mcp 1.x
            from mcp.client.stdio import stdio_client

            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session

        self._sync = _SyncSession(open_session, startup_timeout=60.0)


def build_client(mode: str | None = None, server: Any = None) -> Any:
    """In-memory client in mock mode, stdio client in live mode."""
    mode = (mode or os.environ.get("MODE", os.environ.get("BM_MODE", "mock"))).lower()
    if mode == "live":
        return StdioMcpClient()
    return InMemoryMcpClient(server)


def response_model(name: str):
    """Contract model for one tool's response."""
    return TOOL_RESPONSES[name]
