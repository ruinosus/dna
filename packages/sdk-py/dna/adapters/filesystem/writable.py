"""FilesystemWritableSource — write-through adapter (no drafts, no versioning)."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiofiles
import yaml

from dna.adapters.filesystem.source import FilesystemSource, fs_tenant_segment
from dna.kernel.bundle.handle import FilesystemBundleHandle
from dna.kernel.protocols import WritableSourcePort

if TYPE_CHECKING:
    from dna.kernel import Kernel
    from dna.kernel.capabilities import SourceCapabilities


_SAFE_SEGMENT = re.compile(r"^[a-zA-Z0-9_\-.]+$")


def _is_path_safe(s: str) -> bool:
    """Allow only ``[a-zA-Z0-9_\\-.]+`` and forbid the literal ``..``
    sequence (which would otherwise pass the char-class regex since
    `.` is in the allowlist for semver-shaped values like ``1.0.0``)."""
    return bool(_SAFE_SEGMENT.match(s)) and ".." not in s


def _validate_layer_segments(layer: tuple[str, str] | None) -> None:
    """Reject anything outside a safe allowlist — prevents path traversal."""
    if layer is None:
        return
    layer_id, layer_value = layer
    if not _is_path_safe(layer_id) or not _is_path_safe(layer_value):
        raise ValueError(
            f"Invalid layer segment: {layer_id!r}/{layer_value!r} — "
            f"must match [a-zA-Z0-9_\\-.]+ (no slashes, no '..')"
        )


def _validate_tenant_path(tenant: str | None) -> None:
    """Adapter-side path-traversal check for the tenant slug. Kernel's
    ``validate_tenant_slug`` is intentionally lenient on character
    rules (so legacy uppercase tenants like ``T1`` keep working) and
    delegates path-safety to the adapter — see protocols.py docstring.

    Without this check, the back-compat rewrite
    ``layer=("tenant", "../evil")`` → ``tenant="../evil"`` skips
    ``_validate_layer_segments`` and the adapter happily builds
    ``<base>/tenants/../evil/scopes/<scope>``.
    """
    if tenant is None:
        return
    # ADR-personal-memory: a reserved-scheme tenant (e.g. ``personal:<oid>``)
    # carries a ``:`` sigil that ``fs_tenant_segment`` percent-encodes to a
    # path-safe on-disk segment. The ``:`` is the ONLY non-allowlist char it
    # introduces, so validate the value with the ``:`` sigils stripped — every
    # other char must still be a safe segment, and ``..`` traversal stays blocked.
    probe = tenant.replace(":", "")
    if not probe or not _is_path_safe(probe):
        raise ValueError(
            f"Invalid layer segment: 'tenant'/{tenant!r} — "
            f"must match [a-zA-Z0-9_\\-.]+ (no slashes, no '..')"
        )


class FilesystemWritableSource(FilesystemSource, WritableSourcePort):
    """WritableSourcePort backed by local .dna/ directories.

    Write-through: every save goes directly to disk. No draft stage,
    no version history — the filesystem IS the single version.

    Accepts optional ``writers`` for bundle kinds (Skill, Soul).
    When a writer matches, it handles writing the directory structure.
    Otherwise, falls back to writing a YAML file.

    Requires a ``kernel`` — either passed at construction time or later
    via ``set_kernel()`` — to resolve each kind's on-disk container
    through ``Kernel.storage_for_kind``. Call sites that build the
    source before the kernel exists should use ``set_kernel(k)`` once
    the kernel is ready.
    """

    # s-sqlite-cross-process-invalidation — the filesystem has no write
    # notification channel either; a second process learns of changes only on
    # its next read of disk (no cache coherence). False is the honest signal.
    supports_cross_process_invalidation: bool = False

    def __init__(
        self,
        base_dir: str | Path,
        writers: list | None = None,
        kernel: "Kernel | None" = None,
    ) -> None:
        super().__init__(base_dir)
        self._writers = writers or []
        self._kernel = kernel

    def set_kernel(self, kernel: "Kernel") -> None:
        """Bind the kernel used to resolve kind containers.

        Use when construction precedes kernel wiring (e.g. factories
        that build the source first and assemble the kernel around it).

        Deprecated alias for ``attach_kernel`` (H2). Kept for callers
        that wired this in before the unified capability was added.
        """
        self.attach_kernel(kernel)

    def attach_kernel(self, kernel: object) -> None:
        """H2 — KernelAttachable Protocol implementation.

        Idempotent: copies the kernel's registered writers + readers
        into this source's lookup tables and stores a back-ref so the
        save path can resolve ``storage_for_kind``. Replaces the
        ``isinstance(source, FilesystemWritableSource)`` special case
        in ``Kernel.auto`` — every WritableSource implements this
        method now, so the kernel can call it uniformly.

        H4 contract requirement: ``_readers`` is also populated so
        adapter parity is uniform (SQLite/Postgres store both lists).
        FS scanner historically read readers from the kernel directly
        (load_manifest pulls from kernel._readers); having them on the
        source is back-compat-safe — nothing reads from there yet on
        FS, but the contract test asserts both are present.
        """
        from dna.kernel import Kernel as _KernelType
        if not isinstance(kernel, _KernelType):
            raise TypeError(
                f"attach_kernel requires a Kernel instance; got {type(kernel).__name__}"
            )
        self._kernel = kernel
        if not self._writers:
            self._writers = list(kernel._writers)
        if not getattr(self, "_readers", None):
            self._readers = list(kernel._readers)

    def _subdir_for(self, kind: str) -> str | None:
        """Resolve the on-disk subdirectory for a kind via the kernel's
        registered StorageDescriptor.

        Returns ``None`` when the kind resolves to an empty container
        (ROOT pattern, e.g. Module) or is not registered at all —
        meaning the caller writes at the scope root.

        Raises ``RuntimeError`` when no kernel has been bound yet: the
        adapter cannot route kinds without a StorageDescriptor registry.
        """
        if self._kernel is None:
            raise RuntimeError(
                "FilesystemWritableSource has no kernel bound — pass "
                "kernel= at construction or call set_kernel(k) before "
                "save_document/delete_document."
            )
        sd = self._kernel.storage_for_kind(kind)
        if sd is None:
            return None
        return sd.container or None

    # ── write methods ─────────────────────────────────────────────

    def _target_dir(
        self, scope: str,
        layer: tuple[str, str] | None,
        *,
        tenant: str | None = None,
    ) -> Path:
        """Resolve the directory where this write should land.

        Phase 2b layout (tenant first-class):
          - ``tenant=X``           → ``<base>/tenants/<X>/scopes/<scope>``
          - ``tenant=X, layer=L``  → ``<base>/tenants/<X>/scopes/<scope>/overlays/<L_id>/<L_val>``
          - ``layer=("tenant",Y)`` → same as ``tenant=Y`` (back-compat
            handled at the adapter so direct callers don't need to know
            the new shape)
          - no tenant + no layer (legacy callers / Phase-1 data) → falls
            back to old ``<base>/<scope>`` layout. Reads see both via the
            tenant-aware loader.

        SECURITY: callers MUST invoke ``_validate_layer_segments`` on the
        layer arg (path-traversal sanitization happens there, not here).
        Tenant slug is path-safe because the kernel rejects reserved + non
        slug-shaped strings via ``validate_tenant_slug`` before reaching
        the adapter.
        """
        # Back-compat: layer=("tenant", X) reroutes to new tenant layout
        effective_tenant = tenant
        residual_layer = layer
        if layer is not None and layer[0] == "tenant" and tenant is None:
            effective_tenant = layer[1]
            residual_layer = None

        if effective_tenant is not None:
            scope_dir = (
                self.base_dir / "tenants" / fs_tenant_segment(effective_tenant) / "scopes" / scope
            )
        elif residual_layer is None:
            # Legacy layout — preserved for reads of pre-migration data
            return self.base_dir / scope
        else:
            # Layer overlay without tenant (rare: branch/region/user with
            # no tenant binding) — keep legacy layers/<id>/<val> path so
            # adapter doesn't have a third unanchored layout.
            scope_dir = self.base_dir / scope

        if residual_layer is None:
            return scope_dir
        layer_id, layer_value = residual_layer
        return scope_dir / "overlays" / layer_id / layer_value

    async def save_document(
        self, scope: str, kind: str, name: str, raw: dict,
        author: str | None = None,
        *,
        tenant: str | None = None,
        layer: tuple[str, str] | None = None,
        write_class: str = "substantive",
        version_retention: int | None = None,
    ) -> str:
        # version_retention rides the WritableSourcePort contract for parity; the FS
        # adapter has no version-history table (each write replaces the file in
        # place), so there's no churn to cap — accepted and ignored.
        # write_class is part of the WritableSourcePort contract (it rides the
        # Postgres NOTIFY payload for ObserverBus classification). The FS adapter
        # emits no events, so it accepts and ignores it. (s-buswrite-class-substantive-cue)
        _validate_layer_segments(layer)
        _validate_tenant_path(tenant)
        subdir = self._subdir_for(kind)
        scope_dir = self._target_dir(scope, layer, tenant=tenant)

        # Phase 9c — root kinds (Module today) live at <scope_dir>/manifest.yaml
        # by SDK convention. Without this special-case, a Module published as
        # 'foo' would land at 'foo.yaml' and load_manifest's
        # ``tenants/<X>/scopes/<S>/manifest.yaml`` lookup would miss it.
        #
        # Phase 10b — when ``spec.version`` is set, ALSO archive the immutable
        # release at ``<scope_dir>/versions/<ver>/manifest.yaml``. The bare
        # manifest.yaml continues to mirror the latest stable (npm dist-tags
        # 'latest' convention). Republish of an existing version raises so
        # the harness can surface 409 version_already_published.
        is_root = self._kind_is_root(kind)
        if is_root:
            scope_dir.mkdir(parents=True, exist_ok=True)
            spec_version = (raw.get("spec") or {}).get("version")
            if spec_version:
                versions_dir = scope_dir / "versions" / str(spec_version)
                versioned_path = versions_dir / "manifest.yaml"
                if versioned_path.exists():
                    from dna.kernel.protocols import (
                        VersionAlreadyPublished,
                    )
                    raise VersionAlreadyPublished(
                        f"Module version {spec_version!r} already published "
                        f"at {versioned_path}. Bump and republish."
                    )
                versions_dir.mkdir(parents=True, exist_ok=True)
                content = yaml.dump(raw, default_flow_style=False, sort_keys=False)
                async with aiofiles.open(versioned_path, "w", encoding="utf-8") as f:
                    await f.write(content)
                # Update the latest-stable mirror too
                async with aiofiles.open(scope_dir / "manifest.yaml", "w", encoding="utf-8") as f:
                    await f.write(content)
                return spec_version
            # Unversioned (Phase 9 path): write only the bare manifest.yaml.
            path = scope_dir / "manifest.yaml"
            content = yaml.dump(raw, default_flow_style=False, sort_keys=False)
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(content)
            return "1"

        # Try registered writers (for bundle kinds like Skill, Soul)
        for w in self._writers:
            if w.can_write(raw):
                if subdir:
                    dest = scope_dir / subdir / name
                else:
                    dest = scope_dir / name
                w.write(FilesystemBundleHandle(dest), raw)
                return "1"

        # Fallback: write as YAML file
        if subdir:
            parent = scope_dir / subdir
        else:
            parent = scope_dir
        parent.mkdir(parents=True, exist_ok=True)
        path = parent / f"{name}.yaml"
        content = yaml.dump(raw, default_flow_style=False, sort_keys=False)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(content)
        return "1"

    def _kind_is_root(self, kind: str) -> bool:
        """True iff the registered KindPort for ``kind`` is a "root-shaped"
        single-file Kind (Module, Genome).

        Used by save_document to redirect root-kind writes to the
        canonical ``<storage.marker>`` filename (Phase 9c). Phase 16:
        treats both ``is_root=True`` AND ``StoragePattern.ROOT`` as
        triggers, so legacy Module writes (now ``is_root=False`` after
        the root-flag transfer to Genome) still land at manifest.yaml
        instead of Module.yaml. Defensive: missing kernel binding →
        False (caller falls back to default behavior).
        """
        from dna.kernel.protocols import StoragePattern

        if self._kernel is None:
            return False
        for kp in self._kernel._kinds.values():
            if kp.kind != kind:
                continue
            if getattr(kp, "is_root", False):
                return True
            storage = getattr(kp, "storage", None)
            if storage is not None and getattr(storage, "pattern", None) == StoragePattern.ROOT:
                return True
            return False
        return False

    async def delete_document(
        self, scope: str, kind: str, name: str,
        *,
        tenant: str | None = None,
        layer: tuple[str, str] | None = None,
    ) -> None:
        # Phase 2b: tenant routes to dedicated layout (see save_document).
        _validate_layer_segments(layer)
        _validate_tenant_path(tenant)
        subdir = self._subdir_for(kind)
        scope_dir = self._target_dir(scope, layer, tenant=tenant)

        if subdir:
            parent = scope_dir / subdir
        else:
            parent = scope_dir

        # Try directory first (bundle), then .yaml, then .md
        bundle_path = parent / name
        yaml_path = parent / f"{name}.yaml"
        md_path = parent / f"{name}.md"

        if bundle_path.is_dir():
            shutil.rmtree(bundle_path)
        elif yaml_path.is_file():
            yaml_path.unlink()
        elif md_path.is_file():
            md_path.unlink()
        else:
            raise ValueError("not_found")

    async def save_manifest(self, scope: str, manifest: dict[str, Any]) -> str:
        path = self.base_dir / scope / "manifest.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        content = yaml.dump(manifest, default_flow_style=False)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(content)
        return "1"

    # ── no-op / stub methods (filesystem has no drafts or versions) ──

    async def publish(self, scope: str, kind: str, name: str) -> str:
        return "1"

    async def load_drafts(self, scope: str) -> list[dict[str, Any]]:
        return []

    async def list_versions(self, scope: str, kind: str, name: str) -> list[dict[str, Any]]:
        return []

    async def get_version(
        self, scope: str, kind: str, name: str, version_id: str,
    ) -> dict[str, Any]:
        raise ValueError("version_not_found")

    # ── discovery ─────────────────────────────────────────────────

    async def list_scopes(self) -> list[str]:
        """Enumerate scope dirs under base.

        Phase 2b reserves two top-level names that are NOT scopes:
        ``tenants/`` (per-tenant overlay container) and ``_legacy/``
        (migration sink). Both must be excluded so the harness's
        per-scope holder loop doesn't try to load them as manifests.
        """
        if not self.base_dir.is_dir():
            return []
        reserved = {"tenants", "_legacy"}
        return sorted(
            d.name
            for d in self.base_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".") and d.name not in reserved
        )

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
            source="filesystem",
            drafts=True,
            versions=True,
            layers=True,
            bundle_read=True,
            bundle_write=True,
            kernel_attachable=True,
            granular_list=True,
            granular_one=True,
            query_pushdown=True,
            tenant_layer_writes=True,
            write_kwargs=SAVE_OPTIONAL_KWARGS,
            delete_kwargs=DELETE_OPTIONAL_KWARGS,
        )

    async def list_layer_values(self, scope: str, layer_key: str) -> list[str]:
        """Discover overlay values under <base_dir>/<scope>/layers/<layer_key>/."""
        layers_dir = self.base_dir / scope / "layers" / layer_key
        if not layers_dir.is_dir():
            return []
        return sorted(
            d.name for d in layers_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

    async def list_tenants(self, scope: str | None = None) -> list[str]:
        """Enumerate tenants observed under ``<base_dir>/tenants/<X>/``.

        Phase 5 — supports the ``dna tenant list`` CLI and the future
        ``GET /tenants`` HTTP endpoint. Optional ``scope`` filters to
        tenants that have at least one document in that scope.

        ``_legacy`` is excluded — it's the migration sink, not a real
        tenant. Returns an empty list when ``tenants/`` doesn't exist.
        """
        tenants_dir = self.base_dir / "tenants"
        if not tenants_dir.is_dir():
            return []
        out: list[str] = []
        for d in tenants_dir.iterdir():
            if not d.is_dir() or d.name.startswith(".") or d.name == "_legacy":
                continue
            if scope is not None:
                if not (d / "scopes" / scope).is_dir():
                    continue
            out.append(d.name)
        return sorted(out)

    # ── Phase 10g — Module catalog version surface ────────────────────

    def _module_dir(self, scope: str, tenant: str | None) -> Path:
        if tenant:
            return self.base_dir / "tenants" / fs_tenant_segment(tenant) / "scopes" / scope
        return self.base_dir / scope

    async def list_module_versions(
        self, scope: str, *, tenant: str | None = None,
    ) -> list[dict[str, Any]]:
        """Walk ``<scope_dir>/versions/<v>/manifest.yaml`` and return entries.

        Mirror of the harness-side enumeration that Phase 10b shipped
        inline — moved into the adapter so app.py can dispatch
        uniformly across filesystem / sqlite / postgres.
        """
        from datetime import datetime, timezone
        scope_dir = self._module_dir(scope, tenant)
        versions_dir = scope_dir / "versions"
        if not versions_dir.is_dir():
            return []
        out: list[dict[str, Any]] = []
        for v_dir in sorted(versions_dir.iterdir()):
            vm = v_dir / "manifest.yaml"
            if not vm.is_file():
                continue
            try:
                spec = (yaml.safe_load(vm.read_text()) or {}).get("spec") or {}
            except Exception:
                spec = {}
            out.append({
                "version": v_dir.name,
                "deprecated": bool(spec.get("deprecated", False)),
                "deprecated_message": spec.get("deprecated_message"),
                "published_at": datetime.fromtimestamp(
                    vm.stat().st_mtime, tz=timezone.utc,
                ).isoformat(),
            })
        return out

    async def get_module_version(
        self, scope: str, version: str, *, tenant: str | None = None,
    ) -> dict[str, Any] | None:
        scope_dir = self._module_dir(scope, tenant)
        vm = scope_dir / "versions" / version / "manifest.yaml"
        if not vm.is_file():
            return None
        try:
            return yaml.safe_load(vm.read_text())
        except Exception:
            return None

    async def deprecate_module_version(
        self, scope: str, version: str, *,
        tenant: str | None = None, message: str | None = None,
    ) -> bool:
        scope_dir = self._module_dir(scope, tenant)
        vm = scope_dir / "versions" / version / "manifest.yaml"
        if not vm.is_file():
            return False
        try:
            raw = yaml.safe_load(vm.read_text())
        except Exception:
            return False
        spec = (raw or {}).setdefault("spec", {})
        spec["deprecated"] = True
        if message:
            spec["deprecated_message"] = message
        new_text = yaml.dump(raw, default_flow_style=False, sort_keys=False)
        vm.write_text(new_text)
        # Mirror to latest pointer when applicable
        latest = scope_dir / "manifest.yaml"
        if latest.is_file():
            try:
                cur = yaml.safe_load(latest.read_text())
                if (cur or {}).get("spec", {}).get("version") == version:
                    latest.write_text(new_text)
            except Exception:
                pass
        return True
