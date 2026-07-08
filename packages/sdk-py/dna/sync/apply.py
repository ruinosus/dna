# python/dna/sync/apply.py
"""Apply sync changes to WritableSourcePort instances."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dna.kernel.protocols import WritableSourcePort
    from dna.sync.diff import SyncItem


def _extract_identity(raw: dict) -> tuple[str, str]:
    """Extract (kind, name) from a raw document dict."""
    kind = raw.get("kind", "")
    name = raw.get("name") or raw.get("metadata", {}).get("name", "")
    return (kind, name)


def _is_database_source(source: WritableSourcePort) -> bool:
    """Check if a source requires publish() after save_document()."""
    return not source.supports_readers


async def _save_and_publish(
    source: WritableSourcePort,
    scope: str,
    kind: str,
    name: str,
    raw: dict,
) -> None:
    """Save document and publish if source requires it (database backends)."""
    is_db = _is_database_source(source)

    if kind == "Genome" and not is_db:
        # Filesystem: use save_manifest (writes Genome.yaml directly)
        await source.save_manifest(scope, raw)
    else:
        # Database or non-Genome: use save_document (controlled name)
        # Note: FilesystemWritableSource.save_document does NOT accept author
        kwargs: dict = {"author": "sync-engine"} if is_db else {}
        await source.save_document(scope, kind, name, raw, **kwargs)
        if is_db:
            await source.publish(scope, kind, name)


async def apply_changes(
    pushed: list[SyncItem],
    pulled: list[SyncItem],
    source_a: WritableSourcePort,
    source_b: WritableSourcePort,
    scope: str,
    docs_a: dict[tuple[str, str], dict],
    docs_b: dict[tuple[str, str], dict],
    dry_run: bool = False,
) -> list[str]:
    """Apply sync actions to both sources. Returns list of errors."""
    errors: list[str] = []

    for item in pushed:
        if dry_run:
            continue
        try:
            if item.action == "delete_b":
                await source_b.delete_document(scope, item.kind, item.name)
            else:
                raw = docs_a.get((item.kind, item.name))
                if not raw:
                    errors.append(f"Missing raw data for push: {item.kind}/{item.name}")
                    continue
                await _save_and_publish(source_b, scope, item.kind, item.name, raw)
        except Exception as e:
            errors.append(f"Push {item.kind}/{item.name}: {e}")

    for item in pulled:
        if dry_run:
            continue
        try:
            if item.action == "delete_a":
                await source_a.delete_document(scope, item.kind, item.name)
            else:
                raw = docs_b.get((item.kind, item.name))
                if not raw:
                    errors.append(f"Missing raw data for pull: {item.kind}/{item.name}")
                    continue
                await _save_and_publish(source_a, scope, item.kind, item.name, raw)
        except Exception as e:
            errors.append(f"Pull {item.kind}/{item.name}: {e}")

    return errors
