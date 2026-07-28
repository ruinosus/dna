"""FilesystemCache — CachePort backed by .dna-cache/ directories."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import aiofiles
import yaml

from dna._yaml import safe_load
from dna.kernel.protocols import CacheItem
from dna.kernel.bundle.handle import FilesystemBundleHandle

logger = logging.getLogger(__name__)


class FilesystemCache:
    """Stores and loads cached dependencies from .dna-cache/<scope>/."""

    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir).resolve().parent / ".dna-cache"

    def _contained(self, path: Path) -> Path:
        """Resolve ``path`` and refuse it unless it stays under ``.dna-cache``.

        The same second layer ``FilesystemSource._contained`` is, applied here
        because the segments this adapter joins reach it from FURTHER AWAY than
        anything the source adapter sees. ``scope`` and ``key`` are tame —
        every ``ResolverPort.cache_key`` sanitises its uri through
        ``re.sub(r"[^a-zA-Z0-9_-]", "-", …)``, so a key cannot carry a ``/`` or
        a dot at all. ``item.kind`` and ``item.name`` are not: ``HttpResolver``
        reads both straight out of REMOTE JSON (``raw["kind"]``,
        ``raw["metadata"]["name"]``), and they land in a ``shutil.copytree``
        destination — and in an ``rmtree`` of that destination first, which is
        the worse half.

        Nothing is known to abuse it today; this is the layer that means a
        hostile or merely careless registry cannot, rather than an incident
        being cleaned up. Refuses with ``PathEscapesStoreRoot``, the same
        refusal the source adapter raises, so a face relays it identically.
        """
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(self._base.resolve())
        except ValueError as exc:
            from dna.kernel.errors import PathEscapesStoreRoot

            raise PathEscapesStoreRoot(
                f"FilesystemCache refused a path that leaves its cache root: "
                f"{str(resolved)!r} is not under {str(self._base)!r}. The "
                f"scope, the resolver cache key and the resolved item's kind + "
                f"name are all PATH COMPONENTS here, and the last two come "
                f"from the remote payload. Fix the resolver's output; do not "
                f"widen this check."
            ) from exc
        return resolved

    async def has(self, scope: str, key: str) -> bool:
        return self._contained(self._base / scope / key).exists()

    async def store(self, scope: str, key: str, items: list[CacheItem]) -> None:
        dest_base = self._contained(self._base / scope / key)
        dest_base.mkdir(parents=True, exist_ok=True)
        for item in items:
            # When kind is known, organize by kind (skills/, souls/)
            # When kind is "" (scanner determines later), store flat by name
            if item.kind:
                sub_dir = self._contained(dest_base / (item.kind.lower() + "s"))
            else:
                sub_dir = dest_base
            # ``item.name`` is remote-derived on the HTTP resolver — contained
            # BEFORE the rmtree, not only before the copy.
            dest = self._contained(sub_dir / item.name)
            if dest.exists():
                shutil.rmtree(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(item.content_path, dest)

    async def load_key(
        self, scope: str, key: str, readers: list | None = None,
    ) -> list[dict[str, Any]]:
        key_dir = self._contained(self._base / scope / key)
        if not key_dir.exists():
            return []
        documents: list[dict[str, Any]] = []
        await self._read_tree(key_dir, readers or [], documents)
        return documents

    async def load_all(
        self, scope: str, readers: list | None = None,
    ) -> list[dict[str, Any]]:
        scope_dir = self._contained(self._base / scope)
        if not scope_dir.exists():
            return []

        documents: list[dict[str, Any]] = []
        readers = readers or []
        await self._read_tree(scope_dir, readers, documents)
        return documents

    async def _read_tree(
        self, directory: Path, readers: list,
        documents: list[dict[str, Any]],
    ) -> None:
        """Recursively read directories for bundles and YAMLs."""
        for subdir in sorted(directory.iterdir()):
            if not subdir.is_dir():
                continue
            # Try readers first
            matched = False
            bundle = FilesystemBundleHandle(subdir)
            for reader in readers:
                try:
                    if reader.detect(bundle):
                        doc = reader.read(bundle)
                        if isinstance(doc, dict) and "kind" in doc:
                            documents.append(doc)
                        matched = True
                        break
                except Exception as e:
                    logger.warning("Reader error on %s: %s", subdir, e)
            if matched:
                continue
            # Check for YAML files with kind:
            has_yaml = False
            for yf in sorted(subdir.glob("*.yaml")):
                try:
                    async with aiofiles.open(yf, "r") as f:
                        raw = await f.read()
                    content = safe_load(raw)
                    if isinstance(content, dict) and "kind" in content:
                        documents.append(content)
                        has_yaml = True
                except yaml.YAMLError:
                    pass
            # Recurse deeper if nothing found at this level
            if not has_yaml:
                await self._read_tree(subdir, readers, documents)
