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


def _workspace_scoped_path(path: str, workspace: str) -> str:
    """Splice the DNA per-workspace selector into the MCP URL path:
    ``/mcp`` → ``/w/<workspace>/mcp``. The DNA MCP server mounts the SAME app
    at both ``/mcp`` (falls back to the identity's sole/default membership) and
    ``/w/{workspace_id}/mcp``; a MULTI-workspace identity that hits the bare
    ``/mcp`` naming no workspace is rejected (CrossWorkspaceError), so the
    caller must name one — and the server resolves it from the PATH, never a
    header. Idempotent: a path already carrying ``/w/`` is left untouched."""
    if not workspace or "/w/" in path:
        return path
    suffix = "/mcp"
    if path.endswith(suffix):
        return f"{path[: -len(suffix)]}/w/{workspace}{suffix}"
    return f"{path.rstrip('/')}/w/{workspace}"


class _HeadersProviderAuth(httpx.Auth):
    """httpx.Auth adapter that calls `headers_provider()` on every outgoing
    HTTP request. httpx drives `auth_flow` per request (not once at client
    construction), so this is what makes the bearer genuinely per-request
    rather than a value snapshotted when the MCP session was opened.

    It ALSO names the per-request workspace: when the provider carries an
    ``X-DNA-Workspace`` value it rewrites the URL to ``/w/<id>/mcp`` (the DNA
    server resolves the workspace from the path, never that header), so a
    multi-workspace identity is not rejected for naming none. Tool DISCOVERY
    (build time, no request context → no workspace header) keeps the bare
    ``/mcp`` — schemas are workspace-independent — and only per-request tool
    CALLS get the scoped path."""

    def __init__(self, headers_provider: Callable[[], dict]) -> None:
        self._headers_provider = headers_provider

    def auth_flow(self, request: httpx.Request):
        headers = self._headers_provider()
        for key, value in headers.items():
            request.headers[key] = value
        workspace = (headers.get("X-DNA-Workspace") or "").strip()
        if workspace:
            scoped = _workspace_scoped_path(request.url.path, workspace)
            if scoped != request.url.path:
                request.url = request.url.copy_with(path=scoped)
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
