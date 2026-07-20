"""``dna_cli.act_on_behalf`` — the provider-agnostic act-on-behalf-of-the-user port.

Feature ``f-act-on-behalf-port`` (ADR-act-on-behalf-port), under epic
``e-dna-portability``. Generalizes the Microsoft On-Behalf-Of graph adapter
(``dna_cli.graph``) into a pluggable :class:`ActOnBehalfPort` so DNA acts on the
signed-in user's productivity data (calendar first, read-only) across providers —
Microsoft 365 today via OBO, Google Workspace next via OAuth — each behind one
contract. Purely additive: the Microsoft OBO becomes the reference *implementation*
of the port; nothing about its shipped behavior changes.

Layering (mirrors ``dna_cli.graph``: MCP-runtime, HTTP-only, Python-side
execution):

* :mod:`._port`      — the contract: ``ActContext`` / ``UserCredential`` /
                       ``ActOnBehalfPort`` / ``ActOnBehalfUnavailable``.
* :mod:`._microsoft` — ``MicrosoftOboProvider`` (the reference impl; wraps
                       ``graph._obo`` — behavior identical to ADR-mcp-obo).
* :mod:`._google`    — ``GoogleWorkspaceProvider`` skeleton (calendar only; OAuth
                       shape, network boundary stubbed — proves a 2nd provider fits).
* :mod:`._calendar`  — the provider-neutral ``calendar_list`` capability adapter (B).
* :mod:`._dispatch`  — identity→provider resolution + the live-request context glue.
"""
from __future__ import annotations

from ._port import (
    ActContext,
    ActOnBehalfPort,
    ActOnBehalfUnavailable,
    UserCredential,
)

__all__ = [
    "ActContext",
    "ActOnBehalfPort",
    "ActOnBehalfUnavailable",
    "UserCredential",
]
