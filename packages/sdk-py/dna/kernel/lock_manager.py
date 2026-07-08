"""LockManager — mi.lock.generate() namespace.

Extracts lockfile logic from ManifestInstance. Both
``mi.generate_lock()`` and ``mi.lock.generate()`` return identical results.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dna.kernel.instance import ManifestInstance
    from dna.kernel.lock import Lockfile


class LockManager:
    """Namespace for lockfile operations — accessed via ``mi.lock``."""

    def __init__(self, host: ManifestInstance) -> None:
        self._host = host

    def generate(self) -> Lockfile:
        """Generate lockfile with SHA256 per document.

        Equivalent to ``mi.generate_lock()``.
        """
        import hashlib
        import json
        from dna.kernel.lock import LockEntry, Lockfile

        entries = []
        for d in self._host.documents:
            raw_json = json.dumps(d.raw, sort_keys=True, ensure_ascii=False)
            sha = hashlib.sha256(raw_json.encode()).hexdigest()
            entries.append(LockEntry(
                name=d.name, kind=d.kind, api_version=d.api_version,
                origin=getattr(d, "origin", "local"),
                path="",
                sha256=sha,
            ))
        return Lockfile(scope=self._host.scope, documents=entries)
