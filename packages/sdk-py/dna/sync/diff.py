# python/dna/sync/diff.py
"""Compute diff between snapshot and two source sides."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SyncItem:
    kind: str
    name: str
    action: str  # "push", "pull", "delete_a", "delete_b", "conflict", "skip"
    hash_a: str | None = None
    hash_b: str | None = None


@dataclass
class SyncResult:
    pushed: list[SyncItem] = field(default_factory=list)
    pulled: list[SyncItem] = field(default_factory=list)
    conflicts: list[SyncItem] = field(default_factory=list)
    skipped: list[SyncItem] = field(default_factory=list)
    removed_from_snapshot: list[tuple[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def compute_diff(
    snapshot: dict[tuple[str, str], str],
    side_a: dict[tuple[str, str], str],
    side_b: dict[tuple[str, str], str],
) -> SyncResult:
    """Compare two sides against a snapshot to determine sync actions."""
    result = SyncResult()
    all_keys = set(snapshot) | set(side_a) | set(side_b)

    for key in sorted(all_keys):
        kind, name = key
        s_hash = snapshot.get(key)
        a_hash = side_a.get(key)
        b_hash = side_b.get(key)

        if s_hash is None:
            # Not in snapshot — new document
            if a_hash and not b_hash:
                result.pushed.append(SyncItem(kind, name, "push", a_hash, None))
            elif not a_hash and b_hash:
                result.pulled.append(SyncItem(kind, name, "pull", None, b_hash))
            elif a_hash and b_hash:
                if a_hash == b_hash:
                    result.skipped.append(SyncItem(kind, name, "skip", a_hash, b_hash))
                else:
                    result.conflicts.append(SyncItem(kind, name, "conflict", a_hash, b_hash))
        elif a_hash is None and b_hash is None:
            # Both deleted
            result.removed_from_snapshot.append(key)
        elif a_hash is None:
            # Deleted from A
            if b_hash == s_hash:
                result.pushed.append(SyncItem(kind, name, "delete_b", None, b_hash))
            else:
                result.conflicts.append(SyncItem(kind, name, "conflict", None, b_hash))
        elif b_hash is None:
            # Deleted from B
            if a_hash == s_hash:
                result.pulled.append(SyncItem(kind, name, "delete_a", a_hash, None))
            else:
                result.conflicts.append(SyncItem(kind, name, "conflict", a_hash, None))
        elif a_hash == b_hash:
            # Both same (possibly both changed to same value)
            result.skipped.append(SyncItem(kind, name, "skip", a_hash, b_hash))
        elif a_hash == s_hash:
            # Only B changed
            result.pulled.append(SyncItem(kind, name, "pull", a_hash, b_hash))
        elif b_hash == s_hash:
            # Only A changed
            result.pushed.append(SyncItem(kind, name, "push", a_hash, b_hash))
        else:
            # Both changed differently
            result.conflicts.append(SyncItem(kind, name, "conflict", a_hash, b_hash))

    return result
