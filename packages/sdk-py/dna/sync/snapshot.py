# python/dna/sync/snapshot.py
"""Read/write .dna.sync snapshot file (YAML)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

import aiofiles
import aiofiles.os
import yaml


@dataclass
class SyncSnapshot:
    """Tracks document hashes at the time of last sync."""

    scope: str | None = None
    documents: dict[tuple[str, str], str] = field(default_factory=dict)
    last_sync: str | None = None

    @classmethod
    async def load(cls, path: str) -> SyncSnapshot:
        """Load snapshot from file. Returns empty snapshot if file missing."""
        if not os.path.exists(path):
            return cls()
        async with aiofiles.open(path) as f:
            content = await f.read()
        data = yaml.safe_load(content)
        if not data or not isinstance(data, dict):
            return cls()
        docs = {}
        for entry in data.get("documents", []):
            key = (entry["kind"], entry["name"])
            docs[key] = entry["hash"]
        return cls(
            scope=data.get("scope"),
            documents=docs,
            last_sync=data.get("last_sync"),
        )

    async def save(self, path: str) -> None:
        """Save snapshot to file."""
        entries = [
            {"kind": k, "name": n, "hash": h}
            for (k, n), h in sorted(self.documents.items())
        ]
        data = {
            "version": 1,
            "last_sync": datetime.now(timezone.utc).isoformat(),
            "scope": self.scope,
            "documents": entries,
        }
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        async with aiofiles.open(path, "w") as f:
            await f.write(yaml.dump(data, default_flow_style=False, sort_keys=False))
