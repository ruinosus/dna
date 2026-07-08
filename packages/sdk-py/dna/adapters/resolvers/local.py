"""LocalResolver — ResolverPort for local: URIs."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from dna.kernel.protocols import ResolvedItem

logger = logging.getLogger(__name__)


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
        """
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
