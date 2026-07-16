"""``dna_client`` — the official Python client for the **DNA REST read-API**
(``dna api serve``).

The spec-parity twin of the TypeScript ``dna-client``: both cover the SAME read
surface, derived from the SAME OpenAPI document (``docs/openapi.json``, dumped
from the FastAPI app by ``scripts/dump_openapi.py``). The TS client generates its
types from that spec with ``openapi-typescript``; this Python client is a
hand-thin ``httpx`` wrapper whose method surface + query params are derived from
the same spec (a drift test keeps the spec honest against the live routes). The
two clients stay semantically in sync — spec-parity, not byte-parity.

Read-first: the named methods cover the ``/v1/*`` GET read surface (the shape
dna-cloud's hand-rolled ``lib/rest-client.ts`` consumes today). The full surface
— including the few writes — is reachable via :meth:`DnaClient.request`.

NOTE ON RETURN TYPES: every DNA REST handler returns an untyped JSON object
(``dict[str, Any]``), so the OpenAPI *response* schemas are opaque. Request
inputs (query/path params) ARE typed here; response bodies are ``dict[str, Any]``
(documented per method). Tighten the API's response models to tighten these.
"""
from __future__ import annotations

from .client import DnaApiError, DnaClient

__all__ = ["DnaClient", "DnaApiError"]
__version__ = "0.17.0"
