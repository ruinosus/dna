"""HelixResolver — ResolverPort for helix: URIs.

Fetches manifest documents from the Helix platform APIs.

Example dependency:
    dependencies:
      - source: "helix:shared-module/skills"
        items:
          - kind: Skill
            names: [compliance, onboarding]

Requires environment variables:
    HELIX_API_URL     — Helix API base URL
    HELIX_API_KEY     — API key for authentication
    HELIX_LICENSE_ID  — License identifier
    HELIX_NAMESPACE_ID — Namespace identifier
"""
from __future__ import annotations

import os
import re
from typing import Any

from dna.kernel.protocols import ResolvedItem, ResolveError


class HelixResolver:
    """Resolves dependencies from the Helix platform.

    Delegates to HttpResolver with Helix-specific headers and URL construction.
    """

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        license_id: str | None = None,
        namespace_id: str | None = None,
    ) -> None:
        self._api_url = api_url
        self._api_key = api_key
        self._license_id = license_id
        self._namespace_id = namespace_id

    def _get_config(self) -> dict[str, str]:
        url = self._api_url or os.environ.get("HELIX_API_URL", "")
        key = self._api_key or os.environ.get("HELIX_API_KEY", "")
        lid = self._license_id or os.environ.get("HELIX_LICENSE_ID", "")
        nid = self._namespace_id or os.environ.get("HELIX_NAMESPACE_ID", "")

        if not url:
            raise ResolveError(
                "HELIX_API_URL not set. Configure it to use helix: dependencies."
            )
        return {"url": url.rstrip("/"), "key": key, "license_id": lid, "namespace_id": nid}

    def cache_key(self, uri: str) -> str:
        path = uri.removeprefix("helix:")
        safe = re.sub(r"[^a-zA-Z0-9_-]", "-", path).strip("-")
        return f"helix-{safe}"

    async def resolve(self, uri: str, dep: dict[str, Any]) -> list[ResolvedItem]:
        config = self._get_config()
        path = uri.removeprefix("helix:")
        full_url = f"{config['url']}/manifests/{path.lstrip('/')}"

        headers = {
            "x-api-key": config["key"],
            "x-helix-api-key": config["key"],
            "x-helix-license-id": config["license_id"],
            "x-helix-namespace-id": config["namespace_id"],
        }

        from dna.adapters.resolvers.http import HttpResolver
        http = HttpResolver(headers=headers)
        return http.resolve(full_url, dep)
