"""HttpResolver — ResolverPort for http:/https: URIs.

Fetches manifest documents from HTTP endpoints. Supports two modes:

1. **Index mode** (default): GET {uri}/index.json → list of {kind, name, path}.
   Each item is fetched individually: GET {uri}/{path} → raw dict.

2. **Bundle mode** (?bundle=true): GET {uri} → list of raw dicts directly.
   Server returns all documents in a single JSON array.

Example dependency:
    dependencies:
      - source: "https://skills.example.com/v1/shared"
        items:
          - kind: Skill
            names: [brainstorming, writing-plans]
"""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

if TYPE_CHECKING:
    from pathlib import Path

from dna.kernel.protocols import (
    ResolvedItem, ResolveError, ResolveAuthError, ResolveNetworkError, ResolveNotFoundError,
)

logger = logging.getLogger(__name__)

# Timeout for HTTP requests (seconds)
_TIMEOUT = 30


class HttpResolver:
    """Resolves dependencies from HTTP endpoints.

    Returns ResolvedItem with source_path pointing to a temporary directory
    where the fetched content is stored.
    """

    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self._headers = headers or {}

    def cache_key(self, uri: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9_-]", "-", uri).strip("-")
        return f"http-{safe}"[:120]

    async def resolve(self, uri: str, dep: dict[str, Any]) -> list[ResolvedItem]:
        """Fetch documents from an HTTP endpoint.

        Tries index mode first (GET {uri}/index.json), then bundle mode
        (GET {uri} expecting JSON array) as fallback.
        """
        import tempfile
        from pathlib import Path

        base_url = uri.rstrip("/")
        requested = self._collect_requested(dep)

        try:
            # Try index mode: GET /index.json → [{kind, name, path}, ...]
            index = self._fetch_json(f"{base_url}/index.json")
            if isinstance(index, list):
                return self._resolve_from_index(base_url, index, requested)
        except ResolveError:
            pass

        # Fallback: bundle mode — GET base_url → [raw_dicts]
        try:
            bundle = self._fetch_json(base_url)
            if isinstance(bundle, list):
                return self._resolve_from_bundle(bundle, requested)
        except ResolveError as e:
            raise ResolveError(f"HTTP resolve failed for {uri}: {e}") from e

        raise ResolveError(f"HTTP endpoint returned unexpected format: {uri}")

    def _fetch_json(self, url: str) -> Any:
        """Fetch JSON from a URL."""
        req = Request(url, headers={
            "Accept": "application/json",
            **self._headers,
        })
        try:
            with urlopen(req, timeout=_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            if e.code == 404:
                raise ResolveNotFoundError(f"Not found: {url}") from e
            if e.code in (401, 403):
                raise ResolveAuthError(f"Auth failed ({e.code}): {url}") from e
            raise ResolveError(f"HTTP {e.code}: {url}: {e}") from e
        except (URLError, TimeoutError) as e:
            raise ResolveNetworkError(f"Network error: {url}: {e}") from e
        except json.JSONDecodeError as e:
            raise ResolveError(f"Invalid JSON from {url}: {e}") from e

    @staticmethod
    def _stage(name: str, raw: dict) -> "Path":
        """Create a fresh staging dir named ``name`` and write ``manifest.yaml``.

        ``name`` COMES FROM REMOTE JSON — ``entry["name"]`` in index mode,
        ``raw["metadata"]["name"]`` in bundle mode — and it becomes a directory
        name on this machine, so it is a PATH COMPONENT and is validated as one
        (``validate_document_name``: no ``/``, ``\\`` or NUL, not ``.``/``..``,
        ≤200 bytes; no charset — dots and hyphens stay legal, because real
        document names carry them).

        A sweep once recorded this site as "escapes a directory that holds
        nothing", and that verdict was wrong. Reproduced: a remote ``name`` of
        ``'../HIJACKED'`` reached ``mkdir(parents=True, exist_ok=True)`` and
        then a ``manifest.yaml`` write, landing OUTSIDE the ``mkdtemp`` — the
        file ``HIJACKED/manifest.yaml`` was created in the parent directory;
        with an ABSOLUTE ``name`` the directory and its ``manifest.yaml`` were
        created at an arbitrary absolute path, because a ``pathlib`` join
        DISCARDS the left operand when the right one is absolute. Arbitrary
        directory creation plus an attacker-chosen file path, from remote
        content. The fresh ``mkdtemp`` bounds nothing, because ``..`` leaves it.

        Two layers, as everywhere else in this family: the shape rule names the
        fault, and the containment check below catches what no textual rule can
        — the staging root is created by ``mkdtemp`` and cannot be a symlink
        today, so this is the cheap guard against a future caller passing in a
        root that can be.

        A refusal PROPAGATES rather than skipping the item. The loops here skip
        an item on a FETCH failure (a network fact), but a traversing name is
        hostile content, and silently dropping it would leave an operator
        looking at a short result set with no cause.
        """
        import tempfile
        from pathlib import Path

        from dna.kernel.errors import PathEscapesStoreRoot, validate_document_name

        validate_document_name(name)
        root = Path(tempfile.mkdtemp()).resolve()
        tmp = root / name
        if tmp.resolve().parent != root:
            raise PathEscapesStoreRoot(
                f"remote item name {name!r} resolves to {str(tmp.resolve())!r}, "
                f"which is outside its staging root {str(root)!r}. The name "
                f"passed the shape rule, so the staging root itself is a link "
                f"or a mount. Fix the root; do not widen this check."
            )
        tmp.mkdir(parents=True, exist_ok=True)
        (tmp / "manifest.yaml").write_text(
            json.dumps(raw, indent=2, ensure_ascii=False)
        )
        return tmp

    def _resolve_from_index(
        self, base_url: str, index: list[dict], requested: dict[str, list[str]] | None,
    ) -> list[ResolvedItem]:
        """Resolve items from an index listing."""
        items: list[ResolvedItem] = []
        for entry in index:
            kind = entry.get("kind", "")
            name = entry.get("name", "")
            path = entry.get("path", "")

            if requested and not self._matches_request(kind, name, requested):
                continue

            # Fetch individual document
            try:
                raw = self._fetch_json(f"{base_url}/{path}")
            except ResolveError:
                logger.warning("Failed to fetch %s/%s from %s", kind, name, base_url)
                continue

            # Write to temp dir so cache can store it — ``name`` is remote JSON,
            # so it goes through the one staging door (see ``_stage``).
            items.append(ResolvedItem(
                name=name, kind=kind, source_path=self._stage(name, raw),
            ))

        return items

    def _resolve_from_bundle(
        self, bundle: list[dict], requested: dict[str, list[str]] | None,
    ) -> list[ResolvedItem]:
        """Resolve items from a pre-bundled JSON array."""
        items: list[ResolvedItem] = []
        for raw in bundle:
            kind = raw.get("kind", "")
            name = (raw.get("metadata") or {}).get("name", "")
            if not name:
                continue

            if requested and not self._matches_request(kind, name, requested):
                continue

            items.append(ResolvedItem(
                name=name, kind=kind, source_path=self._stage(name, raw),
            ))

        return items

    @staticmethod
    def _collect_requested(dep: dict[str, Any]) -> dict[str, list[str]] | None:
        """Collect requested items by kind name.

        Rejects the legacy pre-v3 category shorthand (i-009) — same
        contract as ``LocalResolver._collect_requested``.
        """
        from dna.adapters.resolvers.local import reject_legacy_shorthand
        reject_legacy_shorthand(dep)
        result: dict[str, list[str]] = {}
        for item in dep.get("items") or []:
            kind = item.get("kind", "")
            if kind:
                result[kind] = item.get("names") or []
        return result or None

    @staticmethod
    def _matches_request(kind: str, name: str, requested: dict[str, list[str]]) -> bool:
        """Check if a document matches the requested items filter."""
        if kind not in requested:
            return False
        names = requested[kind]
        if not names:
            return True  # Empty names = import all of this kind
        return name in names
