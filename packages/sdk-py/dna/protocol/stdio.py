"""The stdio binding — newline-delimited JSON.

**Why stdio first, and why NDJSON.**

*stdio first* because it is the binding with no infrastructure between the two
ends: no port, no TLS, no auth story, no reverse proxy. A DNAP server that runs
over stdio can be exercised from a test, a shell pipe, or a host process on the
day it is written, which is when its framing rules are cheapest to get wrong
and cheapest to fix. It is also what MCP shipped first, for the same reason.

*NDJSON* — one JSON value per line, ``\\n`` terminated — rather than
LSP-style ``Content-Length`` headers, on three grounds:

1. **It is what MCP's stdio transport uses.** A host that already muxes MCP
   over stdio has a line framer; giving DNAP a second, different framer buys
   nothing and costs every such host a second code path.
2. **It is safe by construction.** RFC 8259 requires control characters inside
   strings to be escaped, so a serialised JSON value provably contains no raw
   ``\\n``. Line framing is therefore not a heuristic that usually works.
3. **It is debuggable.** ``tee``, ``grep`` and a human eye all work on it; a
   length-prefixed stream needs a tool.

The cost is a hard requirement that the writer never emit a bare newline inside
a message — enforced here by ``json.dumps`` with no ``indent``, in one place.

⚠️ **The framing is a seam, not a decision baked into the dispatcher.**
:class:`~dna.protocol.server.DnapServer` deals in decoded payloads
(``handle_payload``) and knows nothing about lines. A ``Content-Length``
reader, or an HTTP binding with a streaming lane for §6.5 notifications, is a
new module beside this one — not a change to anything under it.
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, TextIO

from dna.protocol.server import DnapServer

__all__ = ["read_lines", "serve_stdio", "serve_stream"]


def _encode(message: Any) -> str:
    """One message, one line. ``ensure_ascii`` off — the wire is UTF-8, and a
    Kind's ``description`` in Portuguese should not travel as escape codes."""
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"


async def read_lines(reader: asyncio.StreamReader):
    """Yield decoded-as-text lines, skipping blank ones.

    A blank line is not an empty message: a writer that flushes twice or a
    terminal that echoes a newline should not produce a ``-32700``. Anything
    non-blank is handed on exactly as received, so a *malformed* line still
    gets its parse error.
    """
    while True:
        raw = await reader.readline()
        if not raw:
            return
        text = raw.decode("utf-8", errors="replace").strip()
        if text:
            yield text


async def serve_stream(
    server: DnapServer,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter | TextIO,
) -> None:
    """Run one DNAP connection over an already-connected pair of streams."""
    is_asyncio_writer = isinstance(writer, asyncio.StreamWriter)
    async for line in read_lines(reader):
        answer = await server.handle_text(line)
        if answer is None:
            # A notification, or a batch of them. JSON-RPC 2.0 §4.1/§6 require
            # silence — and silence is not an empty line.
            continue
        payload = _encode(json.loads(answer))
        if is_asyncio_writer:
            writer.write(payload.encode("utf-8"))
            await writer.drain()
        else:
            writer.write(payload)
            writer.flush()


async def serve_stdio(server: DnapServer) -> None:
    """Serve one DNAP connection on this process's stdin/stdout.

    ⚠️ Only ``stdout`` carries protocol. Anything a server wants to say to a
    human goes to ``stderr`` — a log line on stdout is a corrupt frame, which
    is the classic way a stdio protocol server fails in a way that looks like a
    client bug.
    """
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), sys.stdin,
    )
    await serve_stream(server, reader, sys.stdout)
