"""LocalResolver — ResolverPort for local: URIs."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from dna.kernel.protocols import ResolvedItem, ResolveError

logger = logging.getLogger(__name__)

# i-009 — pre-v3 dependency shorthand: category-list keys at the dep top
# level (`skills: [...]`). DEAD format — the Genome contract is
# `items: [{kind, names}]` and no resolver ever read the shorthand, so it
# silently fell through to _resolve_all with the wrong granularity
# (bundle SUBDIRECTORIES instead of bundles). Rejected loudly instead.
LEGACY_SHORTHAND_KEYS = ("skills", "souls", "agents", "actors", "guardrails")


def reject_legacy_shorthand(dep: dict[str, Any]) -> None:
    """Raise ResolveError if the dep uses the dead pre-v3 category shorthand.

    Shared by the local, github and http resolvers so the legacy format
    fails loud (an entry in ``mi.resolve_errors``) with a rewrite recipe
    instead of silently resolving at the wrong granularity.
    """
    legacy = [
        k for k in LEGACY_SHORTHAND_KEYS
        if isinstance(dep.get(k), list)
    ]
    if legacy:
        source = dep.get("source", "<unknown>")
        raise ResolveError(
            f"Dependency {source!r} uses the legacy '{legacy[0]}:' shorthand, "
            f"which is no longer read. Rewrite it in the v3 items format:\n"
            f"  items:\n"
            f"  - kind: {legacy[0].rstrip('s').capitalize()}\n"
            f"    names: [...]"
        )


class LocalResolver:
    """Resolves dependencies from local filesystem paths.

    Does NOT know about specific kinds (Skill, Soul, etc.).
    Returns directories as ResolvedItem with kind="" — the Kernel + Scanners
    determine the actual kind during load_all().
    """

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self._base = Path(base_dir).resolve() if base_dir else None

    def cache_key(self, uri: str) -> str:
        path = uri.removeprefix("local:")
        safe = re.sub(r"[^a-zA-Z0-9_-]", "-", path).strip("-")
        return f"local-{safe}"

    async def resolve(self, uri: str, dep: dict[str, Any]) -> list[ResolvedItem]:
        path_str = uri.removeprefix("local:")
        local_path = Path(path_str)
        if not local_path.is_absolute() and self._base:
            local_path = (self._base / local_path).resolve()

        if not local_path.exists():
            logger.warning("Local source not found: %s", local_path)
            return []

        # Normalize dep format: skills/souls shorthand → names by category
        requested = self._collect_requested(dep)
        if requested:
            return self._resolve_by_category(local_path, requested)
        else:
            return self._resolve_all(local_path)

    @staticmethod
    def _collect_requested(dep: dict[str, Any]) -> dict[str, list[str]] | None:
        """Collect requested items by category directory name.

        v3 format only:
            items: [{kind: "Skill", names: [...]}, {kind: "Soul"}]

        kind maps to directory name: Skill → skills/, Soul → souls/
        When names is omitted, imports all items of that kind.

        The legacy pre-v3 shorthand (`skills: [...]` at the dep top level)
        raises ResolveError (i-009) — see ``reject_legacy_shorthand``.
        """
        reject_legacy_shorthand(dep)
        result: dict[str, list[str]] = {}
        for item in dep.get("items") or []:
            kind = item.get("kind", "")
            if kind:
                category = kind.lower() + "s"  # Skill → skills
                result[category] = item.get("names") or []  # [] = all
        return result or None

    def _resolve_all(self, source: Path) -> list[ResolvedItem]:
        """Import all subdirectory bundles from source."""
        items: list[ResolvedItem] = []
        for subdir in sorted(source.iterdir()):
            if not subdir.is_dir() or subdir.name.startswith("."):
                continue
            # Recurse into category dirs (skills/, souls/, agents/)
            for item_dir in sorted(subdir.iterdir()):
                if item_dir.is_dir():
                    items.append(ResolvedItem(
                        name=item_dir.name,
                        kind="",  # Scanner determines kind
                        source_path=item_dir,
                    ))
        return items

    def _resolve_by_category(
        self, source: Path, requested: dict[str, list[str]],
    ) -> list[ResolvedItem]:
        """Import items from their category directories.

        names=[] means import all items from that category.
        names=["a","b"] means import only those.
        """
        items: list[ResolvedItem] = []
        for category, names in requested.items():
            category_dir = source / category
            if not category_dir.exists():
                continue
            if names:
                # Import specific names
                for name in names:
                    for candidate in [category_dir / name, source / name]:
                        if candidate.exists() and candidate.is_dir():
                            items.append(ResolvedItem(
                                name=name, kind="", source_path=candidate,
                            ))
                            break
            else:
                # Import all from category
                for subdir in sorted(category_dir.iterdir()):
                    if subdir.is_dir():
                        items.append(ResolvedItem(
                            name=subdir.name, kind="", source_path=subdir,
                        ))
        return items
