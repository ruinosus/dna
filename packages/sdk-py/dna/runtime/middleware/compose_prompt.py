"""i-040 — the runtime-composed, tenant-aware system prompt as middleware.
Degrades to the derived instruction fallback, loudly, on any compose failure."""
from __future__ import annotations

import logging

from langchain.agents.middleware import AgentMiddleware


class DnaComposePromptMiddleware(AgentMiddleware):
    def __init__(self, compose, fallback: str) -> None:
        super().__init__()
        self._compose = compose
        self._fallback = fallback

    async def awrap_model_call(self, request, handler):
        headers = (request.state or {}).get("mcp_headers") or {}
        try:
            request.system_message = await self._compose(headers) or self._fallback
        except Exception as exc:  # noqa: BLE001 — degrade, never fail the run
            logging.getLogger("dna.runtime.compose").warning(
                "compose_prompt failed — degraded to the derived fallback: %s", exc
            )
            request.system_message = self._fallback
        return await handler(request)
