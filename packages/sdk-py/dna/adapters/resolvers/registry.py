"""RegistryResolver — ResolverPort for registry: URIs.

Fetches manifest documents from an DNA Registry server. The registry URL
is read from the DNA_REGISTRY_URL environment variable.

Example dependency:
    dependencies:
      - source: "registry:@anthropic/skills"
        items:
          - kind: Skill
            names: [brainstorming, writing-plans]

Registry API contract:
    GET {DNA_REGISTRY_URL}/packages/@anthropic/skills → JSON array of raw dicts
    (same as HttpResolver bundle mode)
"""
from __future__ import annotations

import os
import re
from typing import Any

from dna.kernel.protocols import ResolvedItem, ResolveError


class RegistryResolver:
    """Resolves dependencies from an DNA Registry.

    Delegates to HttpResolver after constructing the registry URL.
    Requires DNA_REGISTRY_URL environment variable.
    """

    def __init__(self, registry_url: str | None = None) -> None:
        self._registry_url = registry_url

    @property
    def _url(self) -> str:
        url = self._registry_url or os.environ.get("DNA_REGISTRY_URL", "")
        if not url:
            raise ResolveError(
                "DNA_REGISTRY_URL not set. Configure it to use registry: dependencies."
            )
        return url.rstrip("/")

    def cache_key(self, uri: str) -> str:
        path = uri.removeprefix("registry:")
        safe = re.sub(r"[^a-zA-Z0-9_-]", "-", path).strip("-")
        return f"registry-{safe}"

    async def resolve(self, uri: str, dep: dict[str, Any]) -> list[ResolvedItem]:
        path = uri.removeprefix("registry:")
        full_url = f"{self._url}/packages/{path.lstrip('/')}"

        from dna.adapters.resolvers.http import HttpResolver
        http = HttpResolver()
        # Override the URI to the full registry URL
        return await http.resolve(full_url, dep)
