"""SourceSync — the kernel's source-sync engine (s-sync-s1..s5), extracted from
the Kernel god-object (s-kernel-decompose-god-object).

Behavior-preserving extraction: ``digest_manifest`` / ``diff_manifests`` /
``push_scope`` are moved **verbatim** from ``Kernel`` into this collaborator,
which holds a back-reference to the owning kernel for the few accessors it needs
(``_source``, ``_readers``, ``_kinds``, ``storage_for_kind``). The kernel keeps
the three methods as thin public delegators so every call site is unchanged.

The digest is source-independent by construction: the SAME scope in two sources
(FS git ↔ Postgres runtime) yields IDENTICAL manifests when in sync, so a sync
is a set-diff of two manifests (no content transfer) + a minimal apply.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from dna.kernel.protocols import StoragePattern

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.collaborator_ports import SourceSyncHost


class SourceSync:
    """Source-sync engine. One instance per Kernel; holds a back-ref to it."""

    def __init__(self, kernel: "SourceSyncHost") -> None:
        self._k = kernel

    async def digest_manifest(
        self, scope: str, *, tenant: str | None = None,
        include: "Callable[[dict], bool] | None" = None,
        source: "Any | None" = None,
    ) -> "dict[tuple[str, str], str]":
        """s-sync-s2 — content map of a scope: ``{(kind, name): digest}``.

        Each digest is the Kind-aware ``canonical_digest`` (s-sync-s1) of the
        doc's authored identity, combined with a Merkle hash of its non-marker
        bundle entries (so binary assets — fonts, images — are covered too).
        ``include(raw) -> bool`` optionally filters docs. ``source`` overrides
        the source read from (default: the kernel's registered one).

        Layer semantics (i-006): no ``tenant`` → digest the BASE scope via
        ``load_all`` (the same path the normal reader/scan uses); explicit
        ``tenant`` → digest that tenant's OVERLAY via ``load_layer``. The old
        ``load_layer(scope, "tenant", "__base__")`` read was a bug — real
        adapters treat ``load_layer`` strictly as an overlay read, so the
        ``"__base__"`` sentinel always digested ``{}`` and diff/push were
        no-ops. A scope missing entirely in ``src`` digests to ``{}``.
        """
        import hashlib
        from types import SimpleNamespace
        from dna.kernel.kind_base import KindBase

        k = self._k
        src = source if source is not None else k._source
        if src is None:
            raise RuntimeError("digest_manifest needs a source")

        if tenant:
            raws = await src.load_layer(
                scope, "tenant", tenant, readers=k._readers,
            )
        else:
            try:
                raws = await src.load_all(scope, readers=k._readers)
            except FileNotFoundError:
                # Scope absent in this source (e.g. diffing against an empty
                # replica) — an empty manifest, so everything diffs as added.
                raws = []
        kp_by_kind = {kp.kind: kp for kp in k._kinds.values()}
        _fallback = KindBase()
        entry_loader = getattr(src, "_load_bundle_entries", None)
        manifest: dict[tuple[str, str], str] = {}

        for raw in raws:
            if not isinstance(raw, dict):
                continue
            kind = raw.get("kind")
            meta = raw.get("metadata") or {}
            name = meta.get("name") or raw.get("name")
            if not kind or not name:
                continue
            if include is not None and not include(raw):
                continue
            spec = raw.get("spec") or {}
            kp = kp_by_kind.get(kind, _fallback)
            doc = SimpleNamespace(kind=kind, name=name, spec=spec)
            spec_digest = kp.canonical_digest(doc)

            # Bundle Merkle: hash of sorted (entry_path, sha256(content)) over
            # the NON-marker entries (the marker's content is the doc spec,
            # already in spec_digest). Catches binary-asset divergence.
            bundle_digest = ""
            sd = k.storage_for_kind(kind)
            if (
                entry_loader is not None and sd is not None
                and getattr(sd, "pattern", None) == StoragePattern.BUNDLE
            ):
                # tenant is keyword-only on some adapters' bundle-entry
                # loaders — keyword keeps every impl happy (i-006).
                entries = await entry_loader(scope, kind, name, tenant=tenant or "")
                if not entries:
                    entries = await entry_loader(scope, kind, name, tenant="")
                parts: list[str] = []
                for ep, payload in sorted((entries or {}).items()):
                    if ep == sd.marker:
                        continue
                    data = (
                        payload if isinstance(payload, (bytes, bytearray))
                        else str(payload).encode("utf-8")
                    )
                    parts.append(f"{ep}:{hashlib.sha256(bytes(data)).hexdigest()}")
                if parts:
                    bundle_digest = hashlib.sha256(
                        "|".join(parts).encode("utf-8")
                    ).hexdigest()

            if bundle_digest:
                manifest[(kind, name)] = hashlib.sha256(
                    f"{spec_digest}:{bundle_digest}".encode("utf-8")
                ).hexdigest()
            else:
                manifest[(kind, name)] = spec_digest

        return manifest

    @staticmethod
    def diff_manifests(
        a: "dict[tuple[str, str], str]", b: "dict[tuple[str, str], str]",
    ) -> "dict[str, list[tuple[str, str]]]":
        """s-sync-s4 — set-diff two digest manifests (a = source-of-truth / FS,
        b = target / runtime). Pure + O(n): no content is read here.

        Returns ``{"added": [...], "changed": [...], "removed": [...]}`` of
        ``(kind, name)`` keys (added=in a not b; removed=in b not a;
        changed=in both, digest differs). Identical manifests → all empty.
        """
        keys_a, keys_b = set(a), set(b)
        added = sorted(keys_a - keys_b)
        removed = sorted(keys_b - keys_a)
        changed = sorted(k for k in (keys_a & keys_b) if a[k] != b[k])
        return {"added": added, "changed": changed, "removed": removed}

    async def push_scope(
        self, scope: str, to_source: "Any", *,
        tenant: str | None = None,
        include: "Callable[[dict], bool] | None" = None,
        dry_run: bool = False,
        prune: bool = False,
    ) -> "dict[str, list]":
        """s-sync-s5 — reconcile ``to_source`` to match the kernel's source
        (source-of-truth) for ``scope``. Computes the minimal diff and applies
        it (read resolved doc + bundle entries from the source, write to
        ``to_source`` so the s-sync-s3 atomic net persists doc + entries
        together). ``prune`` deletes target-only docs. ``dry_run`` returns the
        diff without writing. Idempotent.
        """
        k = self._k
        manifest_from = await self.digest_manifest(
            scope, tenant=tenant, include=include,
        )
        manifest_to = await self.digest_manifest(
            scope, tenant=tenant, include=include, source=to_source,
        )
        diff = self.diff_manifests(manifest_from, manifest_to)
        if dry_run:
            return {**diff, "applied": []}

        applied: list[tuple[str, str, str]] = []
        loader = getattr(k._source, "_load_bundle_entries", None)
        # Draft-staged adapters (SQLite; PG's save auto-publishes but keeps
        # the method) need an explicit publish or the pushed doc stays an
        # invisible draft and the target never converges (i-006 push leg).
        # Same pattern as sync/apply._save_and_publish + the conformance
        # kit's ctx.publish: forward tenant only if the signature takes it.
        publish = getattr(to_source, "publish", None)
        publish_takes_tenant = False
        if callable(publish):
            import inspect
            publish_takes_tenant = "tenant" in inspect.signature(publish).parameters
        for kind, name in diff["added"] + diff["changed"]:
            raw = await k._source.load_one(
                scope, kind, name, readers=k._readers, tenant=tenant,
            )
            if raw is None:
                continue
            # Carry non-marker bundle entries so the target's save_document net
            # re-persists them atomically (the s-sync-s3 fix).
            sd = k.storage_for_kind(kind)
            if (
                loader is not None and sd is not None
                and getattr(sd, "pattern", None) == StoragePattern.BUNDLE
            ):
                entries = await loader(scope, kind, name, tenant=tenant or "")
                if not entries:
                    entries = await loader(scope, kind, name, tenant="")
                src_files = {
                    ep: payload for ep, payload in (entries or {}).items()
                    if ep != sd.marker
                }
                if src_files:
                    raw.setdefault("spec", {})["source_files"] = src_files
            await to_source.save_document(scope, kind, name, raw, tenant=tenant)
            if callable(publish):
                if tenant is not None and publish_takes_tenant:
                    await publish(scope, kind, name, tenant=tenant)
                else:
                    await publish(scope, kind, name)
            applied.append(("write", kind, name))

        if prune:
            for kind, name in diff["removed"]:
                await to_source.delete_document(scope, kind, name, tenant=tenant)
                applied.append(("delete", kind, name))

        return {**diff, "applied": applied}
