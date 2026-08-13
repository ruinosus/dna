"""DNAP — the DNA spoken as a protocol (``docs/spec/dnap-1.0-draft.md``).

This package holds the **client** side: a program that speaks DNAP to whatever
server is on the other end, without knowing what that server stores.

    from dna.dnap import DnapClient

    async with DnapClient(endpoint) as client:
        for kind in client.kinds:              # the vocabulary came from the wire
            page = await client.list_instances(
                channel=client.channels[0], kind=kind)

⭐ The client names no type of its own. Not as a style preference — as the
obligation §8 places on it, and as the property that separates "Kind-agnostic"
as a claim from "Kind-agnostic" as something a test can fail on. The guard is
``tests/test_dnap_client.py::test_the_client_names_no_kind``, which scans this
package's own AST against the live registry.

The conformance suite for the other side of the wire lives in
``dna.testing.dnap_conformance``.
"""
from dna.dnap.client import (
    ChannelNotServed,
    CursorExpired,
    DERIVED_METADATA_MEMBERS,
    DnapClient,
    DnapError,
    DnapProtocolError,
    KindNotServed,
    NotFound,
    NotWritable,
    Page,
    ResolutionIncomplete,
    RevisionConflict,
    SearchUnavailable,
    ServerHello,
    UnknownCapability,
    UnknownKind,
    ValidationFailed,
)

__all__ = [
    "ChannelNotServed",
    "CursorExpired",
    "DERIVED_METADATA_MEMBERS",
    "DnapClient",
    "DnapError",
    "DnapProtocolError",
    "KindNotServed",
    "NotFound",
    "NotWritable",
    "Page",
    "ResolutionIncomplete",
    "RevisionConflict",
    "SearchUnavailable",
    "ServerHello",
    "UnknownCapability",
    "UnknownKind",
    "ValidationFailed",
]
