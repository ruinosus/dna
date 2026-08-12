"""JSON-RPC 2.0 framing — parse, validate, and shape the envelope.

This module knows **nothing** about DNAP. It turns bytes-shaped Python objects
into :class:`Request` values and back into response objects, enforcing the ten
rules of JSON-RPC 2.0 and no more. Everything DNAP adds — channels,
capabilities, the Kind vocabulary — lives above it, in
:mod:`dna.protocol.server`.

Keeping it separate is not tidiness: it is the seam that makes the "build vs.
adopt" decision reversible. The whole of JSON-RPC's framing is ~150 lines here;
swapping it for a third-party dispatcher later is a change to *this file only*,
because nothing else in :mod:`dna.protocol` constructs an envelope.

⚠️ **Why this is hand-written, and what was searched first** (house rule:
procure quem já construiu). JSON-RPC 2.0 is the one protocol in DNA's
neighbourhood with **no official implementation and no governing body** — the
1-page spec ships no reference server, unlike MCP (``fastmcp``), A2A
(``a2a-sdk``) and AG-UI (``@ag-ui/client``), where reimplementation is
forbidden here precisely because a divergent *reading* of a large spec only
surfaces against a third party. The candidates measured on 2026-08-12:

===================  =======  ==========  ==================================
package              stars    last rel.   why not
===================  =======  ==========  ==================================
``pjrpc``            41       2026-08-08  best maintained, zero required
                                          deps — but its value is the
                                          transport integrations (aiohttp /
                                          flask / fastapi / aio-pika) we do
                                          not use, its licence classifier is
                                          the unqualified
                                          ``License :: Public Domain``
                                          (no SPDX id) on a **required**
                                          dependency of an MIT SDK, and its
                                          dispatcher has no seam for the two
                                          rules DNAP's dispatch exists to
                                          impose (capability gating →
                                          ``-32601``, channel addressing →
                                          ``-32004``) — so it would be
                                          wrapped, not used.
``jsonrpcserver``    ~700     2022-09-15  unmaintained for 4 years
``json-rpc``         ~1.5k    2023-06-11  sync-only, unmaintained
===================  =======  ==========  ==================================

The decision to keep this in-tree is therefore **weight**, not preference, and
it is a decision worth confirming rather than assuming — see the report on the
story. The mitigation is this file's isolation.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Final

from dna.protocol.errors import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    PARSE_ERROR,
    DnapError,
)

__all__ = [
    "JSONRPC_VERSION",
    "Request",
    "decode_json",
    "error_response",
    "parse_message",
    "split_batch",
    "success_response",
]

JSONRPC_VERSION: Final = "2.0"

#: The sentinel for "this request had no ``id`` member". ``None`` cannot serve:
#: ``{"id": null}`` is a *request* with a null id (JSON-RPC 2.0 §4 allows it and
#: §5 requires the response to echo it), while an ABSENT ``id`` is a
#: Notification, which gets no response at all. Collapsing the two would either
#: swallow a real response or emit one for a notification — the two halves of
#: the same bug.
_ABSENT: Final = object()


@dataclass(frozen=True, slots=True)
class Request:
    """One parsed JSON-RPC request or notification."""

    method: str
    params: dict[str, Any] = field(default_factory=dict)
    id: Any = None
    is_notification: bool = False

    @property
    def response_id(self) -> Any:
        """The ``id`` a response must echo (meaningless for a notification)."""
        return self.id


def decode_json(text: str | bytes) -> Any:
    """``json.loads`` with the protocol's own failure.

    A malformed payload is ``-32700``, and per JSON-RPC 2.0 §5 its response
    carries ``id: null`` — the server could not read far enough to learn one.
    """
    try:
        return json.loads(text)
    except (ValueError, TypeError) as exc:
        raise DnapError(PARSE_ERROR, f"invalid JSON: {exc}") from exc


def split_batch(payload: Any) -> tuple[list[Any], bool]:
    """``(messages, was_batch)``.

    JSON-RPC 2.0 §6 requires servers to support batches. An **empty** array is
    explicitly Invalid Request (a batch of nothing is not a batch), and it is
    answered with a *single* error object rather than an empty array — that is
    the spec's own example, and it matters because an empty array response is
    indistinguishable from "every element was a notification".
    """
    if isinstance(payload, list):
        if not payload:
            raise DnapError(INVALID_REQUEST, "batch must not be empty")
        return list(payload), True
    return [payload], False


def parse_message(raw: Any) -> Request:
    """Validate one member of the JSON-RPC envelope.

    Raises :class:`DnapError` with :data:`~dna.protocol.errors.INVALID_REQUEST`
    for a malformed envelope and
    :data:`~dna.protocol.errors.INVALID_PARAMS` for a well-formed envelope
    whose ``params`` DNAP cannot accept.
    """
    if not isinstance(raw, dict):
        raise DnapError(
            INVALID_REQUEST,
            f"a request must be a JSON object, got {type(raw).__name__}",
        )
    if raw.get("jsonrpc") != JSONRPC_VERSION:
        raise DnapError(
            INVALID_REQUEST,
            f'"jsonrpc" must be exactly "2.0" (got {raw.get("jsonrpc")!r})',
        )
    method = raw.get("method")
    if not isinstance(method, str) or not method:
        raise DnapError(INVALID_REQUEST, '"method" must be a non-empty string')

    ident = raw.get("id", _ABSENT)
    is_notification = ident is _ABSENT
    if not is_notification and not isinstance(ident, str | int | float | type(None)):
        raise DnapError(
            INVALID_REQUEST,
            '"id" must be a string, a number, or null',
        )
    # bool is an int in Python and would sail through the check above.
    if isinstance(ident, bool):
        raise DnapError(INVALID_REQUEST, '"id" must not be a boolean')

    params = raw.get("params", None)
    if params is None:
        params = {}
    elif isinstance(params, list):
        # DNAP names every parameter (spec §6 shows only by-name calls).
        # Positional params are legal JSON-RPC and illegal DNAP, so this is
        # -32602 (the envelope is fine; the arguments are not) rather than
        # -32600.
        raise DnapError(
            INVALID_PARAMS,
            "DNAP takes parameters BY NAME; positional `params` arrays are "
            "not accepted",
        )
    elif not isinstance(params, dict):
        raise DnapError(
            INVALID_REQUEST, '"params" must be an object when present',
        )

    return Request(
        method=method,
        params=params,
        id=None if is_notification else ident,
        is_notification=is_notification,
    )


def success_response(ident: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": ident, "result": result}


def error_response(ident: Any, error: DnapError) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": ident, "error": error.to_wire()}
