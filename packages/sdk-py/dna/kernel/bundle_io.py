"""BundleIO — the kernel's bundle-entry + document serialization I/O, extracted
from the Kernel god-object (kernel-decompose-continue).

Behavior-preserving: ``fetch_bundle_entry`` / ``fetch_bundle_entry_async`` /
``write_bundle_entry_async`` / ``serialize_document`` move verbatim; the kernel
keeps all four as thin public delegators (70+ external callers — extensions,
adapters, tools, tests — are unchanged). Holds a back-ref to the kernel for the
accessors it needs (source, storage_for_kind, writers, generic-RW ensure).
"""
from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.collaborator_ports import BundleIOHost


class BundleIO:
    """Source-agnostic bundle-entry read/write + document→files serialization."""

    def __init__(self, kernel: "BundleIOHost") -> None:
        self._k = kernel

    def fetch_sync(
        self, scope: str, kind: str, name: str, entry: str, *, tenant: str | None = None,
    ) -> bytes:
        """Phase 14w — fetch a binary bundle entry through the source adapter
        (port-respecting). Resolves ``kind`` → container via the KindPort's
        StorageDescriptor; honors tenant overlay routing.

        Raises ValueError (unknown kind / no container), NotImplementedError
        (adapter lacks BundleEntryReadable), or FileNotFoundError (absent)."""
        k = self._k
        sd = k.storage_for_kind(kind)
        if sd is None or not sd.container:
            raise ValueError(
                f"Kind {kind!r} is not registered or has no bundle container."
            )
        from dna.kernel.capabilities import BundleEntryReadable
        if not isinstance(k._source, BundleEntryReadable):
            raise NotImplementedError(
                f"Source adapter {type(k._source).__name__} does not "
                f"implement BundleEntryReadable. Capability Protocol at "
                f"dna.kernel.capabilities.BundleEntryReadable — "
                f"add a `fetch_bundle_entry(scope, container, name, entry, "
                f"*, tenant)` method to your source adapter."
            )
        # Source impls may be sync (FilesystemSource) or async (PostgresSource).
        # loop=self._main_loop so worker threads dispatch back to the loop that
        # owns the asyncpg pool (no new-loop orphaning). ``kind`` lets SQL
        # adapters disambiguate same-named docs across kinds; FS impls ignore it.
        from dna.kernel import _run_sync_helper
        return _run_sync_helper(
            k._source.fetch_bundle_entry(  # type: ignore[attr-defined]
                scope, sd.container, name, entry, tenant=tenant, kind=kind,
            ),
            loop=k._main_loop,
        )

    async def fetch_async(
        self, scope: str, kind: str, name: str, entry: str, *, tenant: str | None = None,
    ) -> bytes:
        """Async variant of ``fetch_sync`` — use inside an event loop so a
        Postgres source uses the loop's pool directly (no thread round-trip)."""
        k = self._k
        sd = k.storage_for_kind(kind)
        if sd is None or not sd.container:
            raise ValueError(
                f"Kind {kind!r} is not registered or has no bundle container."
            )
        from dna.kernel.capabilities import BundleEntryReadable
        if not isinstance(k._source, BundleEntryReadable):
            raise NotImplementedError(
                f"Source adapter {type(k._source).__name__} does not implement "
                "fetch_bundle_entry."
            )
        result = k._source.fetch_bundle_entry(
            scope, sd.container, name, entry, tenant=tenant, kind=kind,
        )
        if inspect.isawaitable(result):
            return await result
        return result

    async def write_async(
        self, scope: str, kind: str, name: str, entry: str, content: "bytes | str",
        *, tenant: str | None = None,
    ) -> None:
        """Persist a single bundle entry via the active source (source-agnostic).
        Must run AFTER the parent doc exists; the same ``tenant`` keeps the
        bundle row aligned with the doc row so delete cleans both atomically.

        Raises ValueError (unknown kind / no container) or NotImplementedError
        (adapter lacks BundleEntryWritable)."""
        k = self._k
        sd = k.storage_for_kind(kind)
        if sd is None or not sd.container:
            raise ValueError(
                f"Kind {kind!r} is not registered or has no bundle container."
            )
        from dna.kernel.capabilities import BundleEntryWritable
        if not isinstance(k._source, BundleEntryWritable):
            raise NotImplementedError(
                f"Source adapter {type(k._source).__name__} does not "
                f"implement BundleEntryWritable. Capability Protocol at "
                f"dna.kernel.capabilities.BundleEntryWritable — "
                f"add a `write_bundle_entry(scope, container, name, "
                f"entry, content, *, tenant=None, kind=None)` method."
            )
        result = k._source.write_bundle_entry(  # type: ignore[attr-defined]
            scope, sd.container, name, entry, content, tenant=tenant, kind=kind,
        )
        if inspect.isawaitable(result):
            await result

    def serialize(self, scope: str, kind: str, name: str, raw: dict) -> dict:
        """Serialize a document to files without writing. Returns
        ``{"files": [{"relativePath": str, "content": str}]}``."""
        k = self._k
        k._ensure_generic_readers_writers()

        kp = None
        for kind_port in k._kinds.values():
            if kind_port.kind == kind:
                kp = kind_port
                break
        if not kp:
            raise ValueError(f"Unknown kind: {kind}")
        sd = getattr(kp, "storage", None)
        if not sd:
            raise ValueError(f"Kind {kind} has no StorageDescriptor")

        from dna.kernel.protocols import StoragePattern

        writer = None
        for w in k._writers:
            if w.can_write(raw) and hasattr(w, "serialize"):
                writer = w
                break

        if writer:
            raw_files = writer.serialize(raw)
        elif sd.pattern == StoragePattern.YAML:
            from dna.kernel.generic_rw import safe_yaml_dump
            content = safe_yaml_dump(raw)
            container = f"{sd.container}/" if sd.container else ""
            return {"files": [{"relativePath": f"{container}{name}.yaml", "content": content}]}
        elif sd.pattern == StoragePattern.ROOT:
            from dna.kernel.generic_rw import safe_yaml_dump
            return {"files": [{"relativePath": sd.marker, "content": safe_yaml_dump(raw)}]}
        elif sd.pattern == StoragePattern.STANDALONE:
            spec = raw.get("spec", {})
            content = str(spec.get(sd.body_field, "")) if sd.body_field else ""
            return {"files": [{"relativePath": sd.marker, "content": content}]}
        else:
            from dna.kernel.generic_rw import safe_yaml_dump
            raw_files = [{"relativePath": sd.marker or f"{name}.yaml", "content": safe_yaml_dump(raw)}]

        if sd.pattern == StoragePattern.BUNDLE:
            prefix = f"{sd.container}/{name}/" if sd.container else f"{name}/"
        else:
            prefix = ""

        return {
            "files": [
                {"relativePath": f"{prefix}{f['relativePath']}", "content": f["content"]}
                for f in raw_files
            ]
        }
