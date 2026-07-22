"""i-038 — fail-closed federation tool allowlist as a create_agent middleware."""
from __future__ import annotations

import logging

from langchain.agents.middleware import AgentMiddleware


class DnaAllowlistMiddleware(AgentMiddleware):
    """Keep only the allowlisted tools; drop anything else BEFORE the model sees
    a schema (the hosted DNA MCP exposes its whole surface). Fail-closed."""

    def __init__(self, allowed: frozenset[str]) -> None:
        super().__init__()
        self._allowed = allowed

    def wrap_model_call(self, request, handler):
        kept = [t for t in (request.tools or []) if getattr(t, "name", None) in self._allowed]
        dropped = sorted({getattr(t, "name", "?") for t in (request.tools or [])} - self._allowed)
        if dropped:
            logging.getLogger("dna.runtime.allowlist").warning(
                "allowlist dropped %d non-allowlisted tool(s): %s", len(dropped), ", ".join(dropped)
            )
        request.tools = kept
        return handler(request)

    async def awrap_model_call(self, request, handler):
        kept = [t for t in (request.tools or []) if getattr(t, "name", None) in self._allowed]
        request.tools = kept
        return await handler(request)
