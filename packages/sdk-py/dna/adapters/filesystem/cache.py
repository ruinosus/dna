"""FilesystemCache — CachePort backed by .dna-cache/ directories."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import aiofiles
import yaml

from dna.kernel.protocols import CacheItem
from dna.kernel.bundle_handle import FilesystemBundleHandle

logger = logging.getLogger(__name__)


class FilesystemCache:
    """Stores and loads cached dependencies from .dna-cache/<scope>/."""

    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir).resolve().parent / ".dna-cache"

    async def has(self, scope: str, key: str) -> bool:
        return (self._base / scope / key).exists()

    async def store(self, scope: str, key: str, items: list[CacheItem]) -> None:
        dest_base = self._base / scope / key
        dest_base.mkdir(parents=True, exist_ok=True)
        for item in items:
            # When kind is known, organize by kind (skills/, souls/)
            # When kind is "" (scanner determines later), store flat by name
            if item.kind:
                sub_dir = dest_base / (item.kind.lower() + "s")
            else:
                sub_dir = dest_base
            dest = sub_dir / item.name
            if dest.exists():
                shutil.rmtree(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(item.content_path, dest)

    async def load_key(
        self, scope: str, key: str, readers: list | None = None,
    ) -> list[dict[str, Any]]:
        key_dir = self._base / scope / key
        if not key_dir.exists():
            return []
        documents: list[dict[str, Any]] = []
        await self._read_tree(key_dir, readers or [], documents)
        return documents

    async def load_all(
        self, scope: str, readers: list | None = None,
    ) -> list[dict[str, Any]]:
        scope_dir = self._base / scope
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
                    content = yaml.safe_load(raw)
                    if isinstance(content, dict) and "kind" in content:
                        documents.append(content)
                        has_yaml = True
                except yaml.YAMLError:
                    pass
            # Recurse deeper if nothing found at this level
            if not has_yaml:
                await self._read_tree(subdir, readers, documents)
