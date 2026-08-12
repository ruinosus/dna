"""DNAP — the DNA Protocol (JSON-RPC 2.0), server side.

DNAP specifies **the definition of an agent as a typed, versioned, owned
instance, and the contract for resolving it into something a runtime can
execute** — the gap MCP, A2A and AHP each leave open. The draft lives at
``docs/spec/dnap-1.0-draft.md`` and is normative for everything in this
package; where the code diverges from it, the divergence is written down at
the point of divergence rather than smoothed over.

This package is **wave 1**: the dispatcher, ``initialize``, ``kinds/*``,
``instances/*``, channels, cursors and the error table. ``resolve/*`` and
``search/*`` (spec §6.3/§6.4) are not here, and adding them requires touching
nothing in this package — see :mod:`dna.protocol.registry`.

.. code-block:: python

    from dna.application.live import LiveDna
    from dna.protocol import DnapServer, serve_stdio

    server = DnapServer(LiveDna(base_scope="my-scope", kernel=kernel))
    await serve_stdio(server)

Module map, in the order a reader should meet them:

``errors``     the §7 table, and the rule that outranks it
``channels``   §3 addressing — and the refusal that never substitutes
``jsonrpc``    JSON-RPC 2.0 framing, and nothing else
``registry``   ⭐ the method table; the extension point for wave 2
``select``     §6.2 rule 1 — the projection contract
``cursor``     §6.2 rules 2 and 3 — opacity and the pinned snapshot
``revision``   what the store can and cannot say about a moment
``server``     the dispatcher
``kinddef``   §6.1's reflexive rule — how a Kind is created
``methods``    the built-in handlers — cola over ``dna.application.instances``
``stdio``      the NDJSON binding
"""
from __future__ import annotations

from dna.protocol.channels import ROOT, Channel, ChannelSet, parse_channel
from dna.protocol.errors import (
    CHANNEL_NOT_SERVED,
    CURSOR_EXPIRED,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    KIND_NOT_SERVED,
    METHOD_NOT_FOUND,
    NOT_FOUND,
    NOT_INITIALIZED,
    NOT_WRITABLE,
    PARSE_ERROR,
    REFUSED,
    RESOLUTION_INCOMPLETE,
    REVISION_CONFLICT,
    SEARCH_UNAVAILABLE,
    VALIDATION_FAILED,
    DnapError,
)
from dna.protocol.kinddef import (
    BOUNDED_SCHEMA_KEYWORDS,
    KIND_DEFINITION,
    validate_kind_definition,
)
from dna.protocol.methods import builtin_registry
from dna.protocol.registry import ChannelRequirement, MethodRegistry, MethodSpec
from dna.protocol.select import Selection, parse_select
from dna.protocol.server import PROTOCOL_VERSION, DnapServer, RequestContext, Session
from dna.protocol.stdio import serve_stdio, serve_stream

__all__ = [
    "CHANNEL_NOT_SERVED",
    "CURSOR_EXPIRED",
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "KIND_NOT_SERVED",
    "METHOD_NOT_FOUND",
    "NOT_FOUND",
    "NOT_INITIALIZED",
    "NOT_WRITABLE",
    "PARSE_ERROR",
    "PROTOCOL_VERSION",
    "REFUSED",
    "RESOLUTION_INCOMPLETE",
    "REVISION_CONFLICT",
    "ROOT",
    "SEARCH_UNAVAILABLE",
    "VALIDATION_FAILED",
    "BOUNDED_SCHEMA_KEYWORDS",
    "KIND_DEFINITION",
    "Channel",
    "ChannelRequirement",
    "ChannelSet",
    "DnapError",
    "DnapServer",
    "MethodRegistry",
    "MethodSpec",
    "RequestContext",
    "Selection",
    "Session",
    "builtin_registry",
    "parse_channel",
    "validate_kind_definition",
    "parse_select",
    "serve_stdio",
    "serve_stream",
]
