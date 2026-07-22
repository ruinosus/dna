"""The DNA MCP tools with the per-request auth hook — parity with memory_agent's
_mcp_client(headers). The bearer is short-lived: re-read from the hook each call,
never cached from the checkpoint.

Verified against langchain-mcp-adapters 0.3.0 (see task-6-report.md for the
full trace): `StreamableHttpConnection.headers` is a plain `dict[str, Any] |
None`, read ONCE when the connection's httpx.AsyncClient is constructed — a
snapshot, not a callable, so passing `build_headers_provider(auth)()` there
would freeze the bearer for the lifetime of that client/session. The
connection DOES carry a real per-request hook, though: `auth: httpx.Auth`,
threaded verbatim into `httpx.AsyncClient(auth=...)`. httpx invokes
`Auth.auth_flow()` for every outgoing HTTP request (not just once at
construction), so wrapping the hook in an `httpx.Auth` gives genuine
per-request freshness — the bearer is re-read even across multiple requests
on one long-lived session, not merely once per `load_mcp_tools()` call.
"""
from __future__ import annotations

from typing import Any, Callable

import httpx


def build_headers_provider(auth: Callable[[], dict]) -> Callable[[], dict]:
    """Wrap the host's auth hook so headers are re-read at CALL time."""

    def provider() -> dict:
        return dict(auth() or {})

    return provider


class _HeadersProviderAuth(httpx.Auth):
    """httpx.Auth adapter that calls `headers_provider()` on every outgoing
    HTTP request. httpx drives `auth_flow` per request (not once at client
    construction), so this is what makes the bearer genuinely per-request
    rather than a value snapshotted when the MCP session was opened."""

    def __init__(self, headers_provider: Callable[[], dict]) -> None:
        self._headers_provider = headers_provider

    def auth_flow(self, request: httpx.Request):
        for key, value in self._headers_provider().items():
            request.headers[key] = value
        yield request


async def load_mcp_tools(mcp_url: str, auth: Callable[[], dict]) -> list[Any]:
    """Build a MultiServerMCPClient over the DNA MCP endpoint (streamable_http)
    and return its tools. The bearer is threaded via `auth` (httpx.Auth), not
    a static `headers` dict, so it is re-read from the host's auth hook on
    every outgoing HTTP request rather than cached from the checkpoint."""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(
        {
            "dna": {
                "transport": "streamable_http",
                "url": mcp_url,
                "auth": _HeadersProviderAuth(build_headers_provider(auth)),
            }
        }
    )
    return await client.get_tools()
