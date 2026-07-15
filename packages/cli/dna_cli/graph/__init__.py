"""``dna_cli.graph`` — the Microsoft On-Behalf-Of (OBO) graph adapter.

The ``graph`` tool-group of the DNA MCP server (feature ``f-mcp-obo``,
ADR-mcp-obo). It turns the *verified inbound Entra token* the auth bridge already
holds into a *downstream Microsoft Graph token* minted for the same user, so DNA
MCP tools can act on the signed-in user's Microsoft 365 — on their behalf, with no
new sign-in.

Layering (mirrors ``_mcp_auth``: MCP-runtime, HTTP-only, Python-side execution —
no TS twin; the parity-critical part is the governed Tool *surface* doc):

* :mod:`.errors`   — the honest capability errors (consent / interaction / scope / …).
* :mod:`._obo`     — the per-request OBO exchange (pure, injectable, token never leaks).
* :mod:`._config`  — the ``graph:`` ``dna.config.yaml`` block (OFF by default,
                     fail-closed scope allow-list, credential as env-var NAME).
                     Groups are generic: ``calendar``, ``files``, … each opt-in
                     independently with its own delegated scopes.
* :mod:`._tools`   — the built-in tools + their governed Tool docs:
                     ``ms_calendar_list`` (calendar group, ``Calendars.Read``) and
                     ``ms_files_search`` + ``ms_file_read`` (files group, ``Files.Read``).

Optional ``dna-cli[graph]`` extra (``msal`` + ``httpx``); imported lazily so the
base install never carries it.
"""
from __future__ import annotations

from . import _config, _obo, _tools, errors  # noqa: F401

__all__ = ["_config", "_obo", "_tools", "errors"]
