# python/dna/sync/engine.py
"""SyncEngine — bi-directional sync between WritableSourcePort instances."""
from __future__ import annotations

from typing import TYPE_CHECKING

from dna.sync.hash import document_hash
from dna.sync.snapshot import SyncSnapshot
from dna.sync.diff import compute_diff, SyncResult
from dna.sync.apply import apply_changes, _extract_identity

if TYPE_CHECKING:
    from dna.kernel.protocols import WritableSourcePort


class SyncEngine:
    """Bi-directional sync between two WritableSourcePort instances."""

    def __init__(
        self,
        source_a: WritableSourcePort,
        source_b: WritableSourcePort,
    ):
        self.a = source_a
        self.b = source_b

    async def _load_hashes(
        self, source: WritableSourcePort, scope: str
    ) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], dict]]:
        """Load all documents from a source, return (hash_map, raw_map).

        For filesystem sources (supports_readers=True), uses a Kernel with
        registered readers to detect bundle kinds (Skill, Soul, etc.).
        For database sources, calls load_all directly (self-contained docs).
        """
        if source.supports_readers:
            from dna.kernel import Kernel
            k = Kernel.auto()
            raws = await source.load_all(scope)
            mi = k.build(raws, scope)  # sync — pure computation
            raws = [doc.raw for doc in mi.documents]
        else:
            raws = await source.load_all(scope)

        hash_map: dict[tuple[str, str], str] = {}
        raw_map: dict[tuple[str, str], dict] = {}
        for raw in raws:
            key = _extract_identity(raw)
            if not key[0] or not key[1]:
                continue
            hash_map[key] = document_hash(raw)
            raw_map[key] = raw
        return hash_map, raw_map

    async def sync(
        self,
        scope: str,
        snapshot_path: str | None = None,
        dry_run: bool = False,
    ) -> SyncResult:
        """Bi-directional sync. Detects conflicts."""
        snap_path = snapshot_path or ".dna.sync"
        snapshot = await SyncSnapshot.load(snap_path)

        hashes_a, docs_a = await self._load_hashes(self.a, scope)
        hashes_b, docs_b = await self._load_hashes(self.b, scope)

        result = compute_diff(snapshot.documents, hashes_a, hashes_b)

        errors = await apply_changes(
            result.pushed, result.pulled,
            self.a, self.b, scope, docs_a, docs_b, dry_run,
        )
        result.errors.extend(errors)

        if not dry_run and not result.errors:
            # Update snapshot with current hashes
            snapshot.scope = scope
            new_docs: dict[tuple[str, str], str] = {}
            # Merge: start with A hashes, override with B for pulled items
            new_docs.update(hashes_a)
            new_docs.update(hashes_b)
            # Remove keys that were deleted from both or synced as deletes
            for item in result.pushed:
                if item.action == "delete_b":
                    new_docs.pop((item.kind, item.name), None)
            for item in result.pulled:
                if item.action == "delete_a":
                    new_docs.pop((item.kind, item.name), None)
            for key in result.removed_from_snapshot:
                new_docs.pop(key, None)
            snapshot.documents = new_docs
            await snapshot.save(snap_path)

        return result

    async def push(
        self,
        scope: str,
        snapshot_path: str | None = None,
        dry_run: bool = False,
    ) -> SyncResult:
        """A → B only. Ignores B-side changes."""
        snap_path = snapshot_path or ".dna.sync"
        snapshot = await SyncSnapshot.load(snap_path)

        hashes_a, docs_a = await self._load_hashes(self.a, scope)
        hashes_b, _ = await self._load_hashes(self.b, scope)

        result = compute_diff(snapshot.documents, hashes_a, hashes_b)
        # Discard pulled items — only push
        result.pulled = []

        errors = await apply_changes(
            result.pushed, [], self.a, self.b, scope, docs_a, {}, dry_run,
        )
        result.errors.extend(errors)

        if not dry_run and not result.errors:
            snapshot.scope = scope
            # Store union: A's hashes + B's untouched hashes (for correct next sync)
            snapshot.documents = {**hashes_b, **hashes_a}
            for item in result.pushed:
                if item.action == "delete_b":
                    snapshot.documents.pop((item.kind, item.name), None)
            await snapshot.save(snap_path)

        return result

    async def pull(
        self,
        scope: str,
        snapshot_path: str | None = None,
        dry_run: bool = False,
    ) -> SyncResult:
        """B → A only. Ignores A-side changes."""
        snap_path = snapshot_path or ".dna.sync"
        snapshot = await SyncSnapshot.load(snap_path)

        hashes_a, _ = await self._load_hashes(self.a, scope)
        hashes_b, docs_b = await self._load_hashes(self.b, scope)

        result = compute_diff(snapshot.documents, hashes_a, hashes_b)
        # Discard pushed items — only pull
        result.pushed = []

        errors = await apply_changes(
            [], result.pulled, self.a, self.b, scope, {}, docs_b, dry_run,
        )
        result.errors.extend(errors)

        if not dry_run and not result.errors:
            snapshot.scope = scope
            # Store union: B's hashes + A's untouched hashes
            snapshot.documents = {**hashes_a, **hashes_b}
            for item in result.pulled:
                if item.action == "delete_a":
                    snapshot.documents.pop((item.kind, item.name), None)
            await snapshot.save(snap_path)

        return result
