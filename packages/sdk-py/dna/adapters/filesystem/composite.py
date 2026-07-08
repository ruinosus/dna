"""CompositeFilesystemSource — multi-base-dir source.

Wraps N ``FilesystemWritableSource`` instances, one per discovered child
directory that has its own ``.dna/`` tree. Dispatches per-scope methods to
the correct child based on which child contains the scope.

Layout this enables (the convention in ``examples/``):

    <parent_dir>/                           <- the configured base
    ├── hr-screening/.dna/hr-screening/manifest.yaml
    ├── bv-upstream/.dna/bv-upstream/manifest.yaml
    ├── kyc-onboarding/.dna/kyc-onboarding/manifest.yaml
    └── ...

Each ``<child>/.dna`` becomes a backing ``FilesystemWritableSource``.
``list_scopes()`` returns the union of scopes from all children. Looking
up a scope routes to the child that owns it.

Scope-name collisions across children fail loud at construction time —
if two children expose a scope with the same name, the composite refuses
to boot rather than picking one silently.

Discovery happens once at construction; adding a new ``<child>/.dna``
after boot requires re-instantiating the source (or restarting the
harness, which already requires restart for new agents in PR5).
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.kernel.protocols import WritableSourcePort

if TYPE_CHECKING:
    from dna.kernel.capabilities import SourceCapabilities


class CompositeFilesystemSource(WritableSourcePort):
    """Multi-base ``WritableSourcePort`` over N ``FilesystemWritableSource``."""

    def __init__(
        self,
        parent_dir: str | Path,
        writers: list | None = None,
        kernel: Any | None = None,
    ) -> None:
        self._parent = Path(parent_dir)
        self._writers = writers or []
        self._kernel = kernel
        # scope_name → child source that owns it
        self._children: dict[str, FilesystemWritableSource] = {}
        # child_dna_path → source (so we can register each only once even
        # when it owns multiple scopes)
        seen_dna: dict[Path, FilesystemWritableSource] = {}

        if not self._parent.is_dir():
            raise FileNotFoundError(
                f"CompositeFilesystemSource: parent dir not found: {self._parent}"
            )

        for entry in sorted(self._parent.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            dna = entry / ".dna"
            if not dna.is_dir():
                continue

            child = seen_dna.get(dna)
            if child is None:
                child = FilesystemWritableSource(
                    str(dna), writers=writers, kernel=kernel,
                )
                seen_dna[dna] = child

            for sub in sorted(dna.iterdir()):
                if not sub.is_dir() or sub.name.startswith("."):
                    continue
                # Phase 16 — accept either Genome.yaml (canonical) or
                # legacy manifest.yaml as the scope marker.
                if not (sub / "Genome.yaml").exists() and not (sub / "manifest.yaml").exists():
                    continue
                if sub.name in self._children:
                    existing = self._children[sub.name]
                    raise ValueError(
                        f"CompositeFilesystemSource: scope {sub.name!r} "
                        f"is exposed by both {existing.base_dir} and {dna}. "
                        f"Multi-base-dir requires unique scope names — "
                        f"rename one of the manifests."
                    )
                self._children[sub.name] = child

        if not self._children:
            # Empty composite is allowed (matches FilesystemSource behavior
            # on an empty .dna dir). list_scopes returns []. No reason to
            # error — caller can populate later.
            pass

    # ── helpers ───────────────────────────────────────────────────────

    def _route(self, scope: str) -> FilesystemWritableSource:
        try:
            return self._children[scope]
        except KeyError:
            raise FileNotFoundError(
                f"CompositeFilesystemSource: scope {scope!r} not found. "
                f"Known scopes: {sorted(self._children)}"
            ) from None

    @property
    def supports_readers(self) -> bool:
        """Defer to children — every backing FilesystemWritableSource
        walks its own directory tree via ReaderPort, so the composite
        does too. Without this property runtime_checkable Protocol
        ``isinstance(self, WritableSourcePort)`` returns False (the
        check counts attributes, not just methods)."""
        return True

    @property
    def base_dir(self) -> Path:
        """Logical parent dir. Code paths that depend on a single base
        (notably the legacy EvidenceCaptureHook in pre-Phase-8 builds)
        get the parent — but those paths SHOULD route through the kernel
        instead. Kept as a degraded escape hatch."""
        return self._parent

    @property
    def active_writers(self) -> list:
        """Mirror of FilesystemWritableSource.active_writers when needed
        by code that introspects the source's writer list."""
        return list(self._writers)

    @property
    def children(self) -> dict[str, FilesystemWritableSource]:
        """Read-only view of the scope→child map (test helper)."""
        return dict(self._children)

    # ── SourcePort ────────────────────────────────────────────────────

    async def load_bootstrap_docs(
        self, scope: str, *, tenant: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._route(scope).load_bootstrap_docs(scope, tenant=tenant)

    async def load_all(
        self, scope: str, readers: list | None = None,
    ) -> list[dict[str, Any]]:
        return await self._route(scope).load_all(scope, readers=readers)

    async def resolve_ref(self, scope: str, ref: str) -> str:
        return await self._route(scope).resolve_ref(scope, ref)

    async def load_layer(
        self, scope: str, layer_id: str, layer_value: str,
        readers: list | None = None,
    ) -> list[dict[str, Any]]:
        return await self._route(scope).load_layer(
            scope, layer_id, layer_value, readers=readers,
        )

    async def query(
        self, scope: str, kind: str, *,
        filter=None, projection=None, limit=None, offset=None,
        order_by=None, tenant=None,
    ):
        """Marco A — query layer. Delegates to the per-scope child
        source. Each child is a ``FilesystemWritableSource`` that has
        its own ``query`` impl (which itself falls back to the Protocol
        default — load_all + Python filter)."""
        async for row in self._route(scope).query(
            scope, kind,
            filter=filter, projection=projection, limit=limit,
            offset=offset, order_by=order_by, tenant=tenant,
        ):
            yield row

    async def count(
        self, scope: str, kind: str, *,
        filter=None, group_by=None, tenant=None,
    ) -> dict[str, Any]:
        """F2 — aggregation count. Delegates to the per-scope child
        source (``FilesystemWritableSource``), whose ``count`` falls back
        to the Protocol default (load_all + Counter). Mirrors ``query``."""
        return await self._route(scope).count(
            scope, kind, filter=filter, group_by=group_by, tenant=tenant,
        )

    async def list_doc_refs(
        self, scope: str, *, kind: str | None = None,
        tenant: str | None = None,
    ) -> list[tuple[str, str]]:
        """Marco A — doc-ref listing. Delegates per-scope to the
        backing child source (each ``FilesystemWritableSource``
        already implements this against its own tree).

        s-sourceport-contract-cleanup: signature fixed to match the
        SourcePort contract — it was missing ``kind`` and was an async
        generator where the port promises a coroutine returning a list,
        so the kernel's ``await source.list_doc_refs(...)`` path crashed
        on composite sources (latent — caught by the unified conformance
        test)."""
        return await self._route(scope).list_doc_refs(
            scope, kind=kind, tenant=tenant,
        )

    async def load_one(
        self, scope: str, kind: str, name: str, *,
        readers: list | None = None,
        tenant: str | None = None,
    ) -> dict[str, Any] | None:
        """Marco A — single-doc load. Delegates to the per-scope
        child source."""
        return await self._route(scope).load_one(
            scope, kind, name, readers=readers, tenant=tenant,
        )

    async def close(self) -> None:
        for child in set(self._children.values()):
            await child.close()

    def fetch_bundle_entry(
        self,
        scope: str,
        container: str,
        name: str,
        entry: str,
        *,
        tenant: str | None = None,
        kind: str | None = None,
    ) -> bytes:
        """Phase 14w — delegate to the per-scope child source."""
        return self._route(scope).fetch_bundle_entry(
            scope, container, name, entry, tenant=tenant, kind=kind,
        )

    def write_bundle_entry(
        self,
        scope: str,
        container: str,
        name: str,
        entry: str,
        content: bytes,
        *,
        tenant: str | None = None,
        kind: str | None = None,
    ) -> None:
        """BundleEntryWritable impl — delegate to the per-scope child."""
        return self._route(scope).write_bundle_entry(
            scope, container, name, entry, content,
            tenant=tenant, kind=kind,
        )

    # ── WritableSourcePort ────────────────────────────────────────────

    async def save_document(
        self, scope: str, kind: str, name: str, raw: dict,
        author: str | None = None,
        *,
        tenant: str | None = None,
        layer: tuple[str, str] | None = None,
        write_class: str = "substantive",
        version_retention: int | None = None,
    ) -> str:
        # write_class + version_retention ride the WritableSourcePort
        # contract (F2 T7 conformance) — delegated to the child,
        # which (FS) accepts and ignores them (no version-history table).
        return await self._route(scope).save_document(
            scope, kind, name, raw,
            author=author, tenant=tenant, layer=layer,
            write_class=write_class, version_retention=version_retention,
        )

    async def delete_document(
        self, scope: str, kind: str, name: str,
        *,
        tenant: str | None = None,
        layer: tuple[str, str] | None = None,
    ) -> None:
        await self._route(scope).delete_document(
            scope, kind, name, tenant=tenant, layer=layer,
        )

    async def save_manifest(self, scope: str, manifest: dict[str, Any]) -> str:
        return await self._route(scope).save_manifest(scope, manifest)

    async def publish(self, scope: str, kind: str, name: str) -> str:
        return await self._route(scope).publish(scope, kind, name)

    async def load_drafts(self, scope: str) -> list[dict[str, Any]]:
        return await self._route(scope).load_drafts(scope)

    async def list_versions(
        self, scope: str, kind: str, name: str,
    ) -> list[dict[str, Any]]:
        return await self._route(scope).list_versions(scope, kind, name)

    async def get_version(
        self, scope: str, kind: str, name: str, version_id: str,
    ) -> dict[str, Any]:
        return await self._route(scope).get_version(scope, kind, name, version_id)

    async def list_scopes(self) -> list[str]:
        return sorted(self._children.keys())

    def capabilities(self) -> "SourceCapabilities":
        """Explicit contract declaration (s-sourceport-contract-cleanup) --
        kept honest by the adapter conformance test (declaration ==
        reflection-derived oracle)."""
        from dna.kernel.capabilities import (
            DELETE_OPTIONAL_KWARGS,
            SAVE_OPTIONAL_KWARGS,
            SourceCapabilities,
        )
        return SourceCapabilities(
            source="composite-filesystem",
            drafts=True,
            versions=True,
            layers=True,
            bundle_read=True,
            bundle_write=True,
            kernel_attachable=False,
            granular_list=True,
            granular_one=True,
            query_pushdown=True,
            tenant_layer_writes=True,
            write_kwargs=SAVE_OPTIONAL_KWARGS,
            delete_kwargs=DELETE_OPTIONAL_KWARGS,
        )

    async def list_layer_values(self, scope: str, layer_key: str) -> list[str]:
        return await self._route(scope).list_layer_values(scope, layer_key)

    # ── Phase 5+ delegations (tenant + module catalog) ─────────────────
    # These must be forwarded explicitly because the harness uses
    # ``getattr(src, 'method', None)`` to feature-detect; without
    # explicit forwarders it would skip the composite entirely and
    # tenant/catalog reads would silently return empty in multi-scope
    # mode.

    async def list_tenants(self, scope: str | None = None) -> list[str]:
        """Union of tenants observed across all child scopes.

        Each child source has its own ``tenants/`` dir; when
        ``scope=None`` we union all children, when set we delegate
        to the owning child only.
        """
        if scope is not None:
            try:
                return await self._route(scope).list_tenants(scope=scope)
            except FileNotFoundError:
                return []
        observed: set[str] = set()
        for child in set(self._children.values()):
            try:
                observed.update(await child.list_tenants(scope=None))
            except Exception:
                continue
        return sorted(observed)

    async def list_module_versions(
        self, scope: str, *, tenant: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._route(scope).list_module_versions(scope, tenant=tenant)

    async def get_module_version(
        self, scope: str, version: str, *, tenant: str | None = None,
    ) -> dict[str, Any] | None:
        try:
            return await self._route(scope).get_module_version(
                scope, version, tenant=tenant,
            )
        except FileNotFoundError:
            return None

    async def deprecate_module_version(
        self, scope: str, version: str, *,
        tenant: str | None = None, message: str | None = None,
    ) -> bool:
        try:
            return await self._route(scope).deprecate_module_version(
                scope, version, tenant=tenant, message=message,
            )
        except FileNotFoundError:
            return False


__all__ = ["CompositeFilesystemSource"]
