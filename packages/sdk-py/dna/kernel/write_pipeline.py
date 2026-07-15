"""WritePipeline — the kernel's document write/delete execution, extracted from
the Kernel god-object (kernel decomposition, Fase 2 —
``s-kernel-decomp-f2-writepipeline``).

This is the FAT write-path logic: tenant resolution, capability-gated adapter
kwargs (author / write_class / version_retention / tenant / layer), the
layer-policy check, the ``pre_save`` veto gate, ``save_document`` /
``delete_document`` persistence, and the three-tier cache-invalidation fan-out
(granular → catalog → base-drop → invalidate → observers → post_save). The
Kernel RETAINS the public ``write_document`` / ``delete_document`` methods as
THIN facades (invalidate-mode validation, ``_REMOVED_KINDS`` block, record-plane
demotion, OTel span) that delegate their body here.

The load-bearing sequence this pipeline MUST reproduce byte-for-byte (spec Risk
#1, pinned by ``test_kernel_writepath_characterization``):

    write:  pre_save veto → save_document → granular-invalidate →
            catalog-invalidate (only is_catalog_identity) → base-drop
            (scope-mode + base layer) → invalidate (scope-mode) →
            fire-observers (ALWAYS) → post_save (unless skip_hooks)
    delete: delete_document → granular-invalidate → base-drop → invalidate →
            fire-observers → post_delete  (NO pre_save veto — deletes never veto)

The ``pre_save`` veto (an integrity gate) fires even with ``skip_hooks=True``;
``skip_hooks`` silences ONLY ``post_save`` / ``post_delete``.

Narrow-interface contract (kernel-decomposition anti-cosmetic rule): the pipeline
receives a ``WriteHost`` Protocol — ~13 members — NOT the 117-member Kernel
back-ref. The Kernel satisfies it structurally. All side-effect calls go THROUGH
the host so a monkeypatched ``kernel.invalidate`` / ``_fire_write_observers`` /
… (the characterization spy) is observed. STATELESS by design: the pipeline
holds only the host ref, so ``with_tenant`` re-instantiates it pointing at the
copy exactly like the other back-ref collaborators.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path  # noqa: F401 — kept for parity with prior inline imports
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.protocols import (
        KindPort,
        TenantScope,
        WritableSourcePort,
    )

logger = logging.getLogger("dna.kernel")




class WritePipeline:
    """Executes document writes/deletes against the host's writable source with
    the full invalidation fan-out. One per kernel; stateless (all state lives on
    the host, reached via the narrow ``WriteHost`` ref)."""

    def __init__(self, host: WriteHost) -> None:
        self._host = host

    # -- generic write-time spec↔schema validation (s-write-path-validation,
    #    i-008) ----------------------------------------------------------------

    @staticmethod
    def _validation_mode() -> str:
        """Read the write-validation mode knob. ``enforce`` (default) vetoes
        an invalid write; ``warn`` logs and persists; ``off`` skips the step.
        Read per-write (not memoized) so tests / operators can flip it live."""
        mode = os.environ.get("DNA_WRITE_VALIDATION", "enforce").strip().lower()
        return mode if mode in ("enforce", "warn", "off") else "enforce"

    def _validate_spec_schema(
        self, scope: str, kind: str, name: str, raw: Any, port: Any,
    ) -> None:
        """Validate ``raw['spec']`` against the Kind's declared JSON Schema
        at WRITE time (i-008 — the systemic gap found on the Automation work:
        the kernel only schema-validated at scan/read, via the fail-soft
        ``parse_error`` channel, so a shape-broken doc persisted and exploded
        later, far from the author).

        Contract:
        - Kinds without a schema (``schema()`` None/empty, or raising) stay
          PERMISSIVE — validation is opt-in by data, as always.
        - ``spec_defaults`` (descriptor D5) are shallow-merged into the spec
          BEFORE validating, mirroring ``DeclarativeKindPort.parse`` — a doc
          that parses clean must also write clean.
        - Runs AFTER the ``pre_save`` veto hooks so Kind-owned cures (e.g.
          the Automation YAML-1.1 ``on:``→True heal) apply first; what gets
          validated is the exact shape that would persist.
        - Didactic failure (install #26 pattern): names the field, the
          violation, and points at ``dna kind show <Kind>``.
        - ``DNA_WRITE_VALIDATION=warn`` downgrades the veto to a log line;
          ``off`` skips entirely (escape hatch for bulk/legacy loads).
        """
        mode = self._validation_mode()
        if mode == "off" or port is None or not isinstance(raw, dict):
            return
        try:
            schema = port.schema()
        except Exception:  # noqa: BLE001 — a Kind whose schema errors stays permissive
            return
        if not isinstance(schema, dict) or not schema:
            return
        spec = raw.get("spec")
        spec = spec if isinstance(spec, dict) else {}
        # Descriptor D5: defaults fill, spec overrides — exactly what the
        # validating parse sees (autolab-run style Kinds must not be vetoed
        # for fields their own defaults provide).
        defaults = getattr(port, "_spec_defaults", None)
        if isinstance(defaults, dict) and defaults:
            spec = {**defaults, **spec}
        import jsonschema  # local import — core dep (pyproject: jsonschema>=4.0)
        try:
            jsonschema.validate(spec, schema)
        except jsonschema.ValidationError as e:
            path = ".".join(str(p) for p in e.absolute_path)
            loc = f"spec.{path}" if path else "spec"
            msg = (
                f"write vetoed for {scope}/{kind}/{name}: schema validation "
                f"failed at {loc}: {e.message} — see `dna kind show {kind}` "
                f"for the expected shape"
            )
            if mode == "warn":
                logger.warning("%s (DNA_WRITE_VALIDATION=warn — persisted anyway)", msg)
                return
            from dna.kernel.protocols import SpecValidationError  # noqa: PLC0415
            raise SpecValidationError(msg) from e

    # -- Kind-Writer slot↔schema validation (write-time; fired by the helix
    #    ``pre_save`` veto hook via ``kernel._validate_kind_writer`` shim) ------

    def validate_one_kind_writer_entry(
        self,
        target: str,
        creative_slots: list[str],
        system_slots: dict[str, str],
    ) -> None:
        """Validate a SINGLE Kind-Writer target's slot↔schema contract.

        - ``target`` must resolve to a registered KindPort whose ``.schema()``
          is a dict (schema-bearing). Unknown / schema-less → ``ValueError``
          (message mentions "schema").
        - every creative slot must be a property in the schema.
        - every ``required`` schema field must be covered by
          ``creative_slots ∪ system_slots.keys()``; uncovered → ``ValueError``.

        Shared by the single-Kind (``writes_kind``) and multi-Kind
        (``writes_kinds``) paths so both enforce the same contract per Kind.
        """
        port = self._host.kind_port_for(target)
        schema = port.schema() if port is not None else None
        if not isinstance(schema, dict):
            raise ValueError(
                f"Kind-Writer Agent writes_kind={target!r} has no "
                f"schema (Kind is unknown or schema-less); a Kind-Writer "
                f"must target a schema-bearing Kind."
            )
        properties = schema.get("properties") or {}
        for slot in creative_slots:
            if slot not in properties:
                raise ValueError(
                    f"Kind-Writer Agent creative_slot {slot!r} is not a "
                    f"property of Kind {target!r}'s schema."
                )
        covered = set(creative_slots) | set((system_slots or {}).keys())
        for req in schema.get("required", []):
            if req not in covered:
                raise ValueError(
                    f"Kind-Writer Agent: required field {req!r} of Kind "
                    f"{target!r} is unmapped — cover it via creative_slots or "
                    f"system_slots."
                )

    def validate_kind_writer(self, spec: "Any") -> None:
        """Validate a Kind-Writer Agent's slot↔schema contract
        (feat/kind-writer-pilot, Task 2; multi-Kind: feat/kind-writer-multikind).
        Called from ``write_document`` only when ``spec.writes_kind`` OR
        ``spec.writes_kinds`` is set — fail early at write time so a malformed
        Kind-Writer is rejected before runtime emission.

        Single-Kind (``writes_kind``): validate the one target's
        creative/system slots against its schema (unchanged).

        Multi-Kind (``writes_kinds``): validate EACH ``{kind: {creative_slots,
        system_slots}}`` entry the same way — each Kind must be schema-bearing,
        its creative slots ⊆ schema properties, its required ⊆ creative ∪ system.
        """
        writes_kinds = getattr(spec, "writes_kinds", None)
        if isinstance(writes_kinds, dict) and writes_kinds:
            for target, entry in writes_kinds.items():
                entry = entry or {}
                self.validate_one_kind_writer_entry(
                    target,
                    list(entry.get("creative_slots") or []),
                    entry.get("system_slots") or {},
                )
            return
        self.validate_one_kind_writer_entry(
            spec.writes_kind, spec.creative_slots, spec.system_slots,
        )

    # -- post-hook emission (write-time; kept callable on the kernel via shim
    #    for the write-facade unit tests) --------------------------------------

    async def emit_post_save(
        self, scope: str, kind: str, name: str, raw: dict,
        *,
        layer: tuple[str, str] | None = None,
    ) -> None:
        host = self._host
        if not host.hooks.has("post_save"):
            return
        from dna.kernel.hooks import HookContext
        from dna.kernel.events import derive_event_type
        # Parity with typescript/src/kernel/index.ts::_emitPostSave:
        # scope is a HookContext top-level field (subscribers like
        # EvidenceCaptureHook read ctx.scope directly — stuffing it into
        # data.scope leaves ctx.scope as "" and the evidence policy
        # lookup fails silently).
        await host.hooks.emit_async("post_save", HookContext(
            scope=scope, kind=kind, name=name,
            layer=layer,
            data={
                "event_type": derive_event_type(kind, is_update=False),
                "author": "sdk",
                "is_update": False,
                "spec": raw,
            },
        ))

    async def emit_post_delete(
        self, scope: str, kind: str, name: str,
        *,
        layer: tuple[str, str] | None = None,
    ) -> None:
        host = self._host
        if not host.hooks.has("post_delete"):
            return
        from dna.kernel.hooks import HookContext
        await host.hooks.emit_async("post_delete", HookContext(
            scope=scope, kind=kind, name=name, data={}, layer=layer,
        ))

    # -- tenant reconciliation (moved verbatim from Kernel._resolve_tenant_arg) --

    def _resolve_tenant_arg(
        self, kind: str, tenant: str | None, layer: tuple[str, str] | None,
        *, api_version: str | None = None,
    ) -> tuple[str | None, tuple[str, str] | None]:
        """Reconcile tenant + layer args + Kernel.tenant + KindPort.scope.

        Returns ``(effective_tenant, residual_layer)``. The residual
        layer is what to pass to the adapter for non-tenant overlays
        (e.g. ``("branch", "feature-x")``).

        Back-compat: ``layer=("tenant", X)`` is rewritten to ``tenant=X``
        with a DeprecationWarning. Other layer ids pass through unchanged.

        Validation: TENANTED kind requires a tenant; GLOBAL kind forbids it.
        """
        from dna.kernel.protocols import (
            TenantScope, TenantRequired, TenantNotAllowed,
            validate_tenant_slug,
        )
        import warnings as _w

        host = self._host
        residual_layer = layer
        explicit_tenant = tenant

        # Back-compat: layer=("tenant", X) → tenant=X
        if layer is not None and layer[0] == "tenant":
            _w.warn(
                "layer=('tenant', X) is deprecated — pass tenant=X to "
                "write_document/delete_document instead",
                DeprecationWarning, stacklevel=3,
            )
            if explicit_tenant is None:
                explicit_tenant = layer[1]
            residual_layer = None  # consumed by tenant promotion

        # Effective tenant: explicit per-call > Kernel.tenant binding
        effective = explicit_tenant if explicit_tenant is not None else host.tenant
        # ADR-personal-memory: a reserved ``personal:<oid>`` partition is a valid
        # PHYSICAL slug but rejected as user input; the authorized personal write
        # path carries ``host._allow_personal`` so the slug validation permits it.
        validate_tenant_slug(
            effective, allow_personal=getattr(host, "_allow_personal", False)
        )

        # Validate against KindPort.scope when EXPLICITLY declared.
        # Phase 1 keeps undeclared kinds permissive (back-compat).
        scope_decl = host._kind_scope(kind, api_version=api_version)
        if scope_decl == TenantScope.TENANTED and effective is None:
            raise TenantRequired(
                f"Kind {kind!r} is TENANTED — pass tenant=<slug> to "
                "write_document() or bind one via Kernel(tenant=...) / "
                "kernel.with_tenant(...)"
            )
        if scope_decl == TenantScope.GLOBAL and effective is not None:
            raise TenantNotAllowed(
                f"Kind {kind!r} is GLOBAL — must NOT pass a tenant. "
                "Use the unbound kernel (Kernel() with tenant=None) or "
                "kernel.with_tenant(None) for global writes."
            )
        return effective, residual_layer

    # -- write (moved verbatim from Kernel._write_document_inner) ---------------

    async def write(
        self, scope: str, kind: str, name: str, raw: dict,
        author: str | None,
        skip_hooks: bool,
        *,
        tenant: str | None,
        layer: tuple[str, str] | None,
        invalidate_mode: str,
        write_class: str = "substantive",
    ) -> str | None:
        """Real write_document body — the facade (``Kernel.write_document``) owns
        the OTel span + mode validation + record-plane demotion; the fat logic
        stays here.

        Tenant resolution (Phase 1 — kernel-level multi-tenancy):
        - ``tenant`` arg overrides ``Kernel.tenant`` binding for this call
          (Stripe Connect pattern).
        - ``KindPort.scope`` declares whether this kind is TENANTED (default —
          tenant required) or GLOBAL (tenant forbidden).
        - Back-compat: ``layer=("tenant", X)`` is rewritten to ``tenant=X`` with
          a DeprecationWarning. Other ``layer`` values (``("branch", "x")``, …)
          are overlays and pass through unchanged.

        ``invalidate_mode`` — the three cache-invalidation tiers (the facade has
        already demoted record-plane "scope" → "doc"):
        - ``"scope"``: drop ``_base_instance_cache[scope]`` (base writes only)
          + ``Kernel.invalidate`` (holder.reload + observers). For schema /
          Genome / KindDefinition writes that affect sibling docs.
        - ``"doc"``: only the L2 granular cache for (scope, kind, name); skips
          the mi rebuild + holder.reload. Sidecar writes (LessonLearned, …).
        - ``"none"``: skip ALL invalidation. Test-only / out-of-band writes.

        A catalog-identity Kind (``KindPort.is_catalog_identity``) additionally
        drops the whole catalog cache. ``_fire_write_observers`` (the SSE /
        cross-process listeners) fires ALWAYS regardless of mode — the channel
        contract guarantees delivery for every write."""
        from dna.kernel.capabilities import write_kwarg_support
        from dna.kernel import (
            VERSION_CHURN_KINDS, VERSION_CHURN_RETENTION,
        )
        host = self._host
        src = host._require_writable_source()
        # i-195: colliding kind names resolve their port by the doc's own
        # apiVersion wherever we consult Kind metadata below.
        _api_version = raw.get("apiVersion") if isinstance(raw, dict) else None
        _kind_port = host.kind_port_for(kind, api_version=_api_version)
        # Resolve tenant + validate against KindPort.scope
        effective_tenant, residual_layer = self._resolve_tenant_arg(
            kind, tenant, layer, api_version=_api_version,
        )
        # Phase 2a: pass tenant as a first-class kwarg to the adapter
        # if supported. Adapters that don't support tenant yet fall back
        # to the legacy layer=("tenant", X) translation. Phase 2b moves
        # the FS adapter to use tenant natively (with new layout).
        #
        # s-kernel-capability-protocols — kwarg support is detected via the
        # memoized write_kwarg_support() (inspect.signature runs once per source,
        # not on every write) instead of an inline per-call signature probe.
        ws = write_kwarg_support(src)
        kwargs: dict = {}
        if ws.author:
            kwargs["author"] = author
        if ws.write_class:
            kwargs["write_class"] = write_class
        # s-version-prune-record-plane-churn — cap retained version history for
        # the machine-churn Kinds (curated set + per-Kind opt-in) so autopilot
        # rewrites don't drown the authored-content history. Authored Kinds keep
        # full history.
        if ws.version_retention:
            _kp = _kind_port
            _retention = getattr(_kp, "version_retention", None) if _kp else None
            if _retention is None and kind in VERSION_CHURN_KINDS:
                _retention = VERSION_CHURN_RETENTION
            if _retention is not None:
                kwargs["version_retention"] = _retention
        # Compute effective layer for cache + hook tracking
        # (adapter receives tenant + residual_layer separately when supported)
        adapter_layer = residual_layer
        if ws.tenant:
            kwargs["tenant"] = effective_tenant
            if ws.layer_save:
                kwargs["layer"] = residual_layer
        else:
            # Legacy adapter — fold tenant into layer for back-compat
            if effective_tenant is not None:
                adapter_layer = ("tenant", effective_tenant)
            if ws.layer_save:
                kwargs["layer"] = adapter_layer
        # Policy check BEFORE touching the adapter (use the effective
        # layer that the adapter will see)
        policy_check_layer = (
            ("tenant", effective_tenant) if effective_tenant is not None
            else residual_layer
        )
        if policy_check_layer is not None:
            await host._check_layer_policy_async(
                scope, kind, name, raw, policy_check_layer,
            )
        # --- pre_save veto hooks (s-write-path-despecialize) ---
        # Kind-specific write rules (platform-agent fork guard, prompt-budget
        # enforcement, Kind-Writer contract, bitemporal LessonLearned guard,
        # ...) live in the extension that OWNS the Kind and register here via
        # ``kernel.on_veto("pre_save", fn, priority=N)``. A raise vetoes the
        # write; listeners may mutate ``ctx.raw`` in place. Fires regardless
        # of ``skip_hooks`` — these are integrity gates, not notifications
        # (``skip_hooks`` only silences post_save).
        if host.hooks.has_veto("pre_save"):
            from dna.kernel.hooks import PreSaveContext  # noqa: PLC0415
            await host.hooks.emit_veto("pre_save", PreSaveContext(
                scope=scope, kind=kind, name=name, raw=raw,
                tenant=effective_tenant, layer=policy_check_layer,
                kernel=host,
            ))
        # --- generic spec↔schema validation (s-write-path-validation, i-008) ---
        # AFTER the veto hooks (Kind-owned cures — e.g. the Automation
        # YAML-1.1 `on:` heal — mutate ctx.raw first), BEFORE persistence:
        # what gets validated is the exact shape that would be saved.
        self._validate_spec_schema(scope, kind, name, raw, _kind_port)
        version = await src.save_document(scope, kind, name, raw, **kwargs)
        # R2-fix (2026-05-14): three invalidation tiers.
        #
        # mode=none — write only, no cache invalidation. Caller owns hygiene.
        # mode=doc  — only the granular per-doc L2 cache is dropped. The
        #             instance cache + holder.reload chain is SKIPPED. Use
        #             for sidecar writes (LessonLearned, WorkflowEvent, ...)
        #             that don't alter the schema graph and thus don't
        #             require a full mi rebuild.
        # mode=scope (default) — full Phase-15.1 invalidate: drop
        #             _base_instance_cache + holder.reload + observers.
        #
        # Cross-process write observers fire regardless of mode — the SSE
        # / EventBus contract guarantees notification of every write.
        if invalidate_mode != "none":
            # L2 granular cache invalidation — cheap, always safe.
            host._invalidate_granular_cache(scope, kind=kind, name=name)
            # Phase 3b ch1 (i-112) — writing the scope's catalog-identity
            # Kind changes the Catalog tier's mandatory set for EVERY tenant
            # → drop the whole catalog cache. Keyed by the KindPort's
            # ``is_catalog_identity`` attribute (s-write-path-despecialize),
            # NOT a hardcoded Kind name — the cache is kernel-internal, but
            # WHICH Kind carries catalog identity is Kind metadata.
            if getattr(_kind_port, "is_catalog_identity", False):
                host._invalidate_catalog_cache()

        if invalidate_mode == "scope":
            # Drop base instance cache (only for base writes — tenant /
            # layer writes have their own resolution path).
            if effective_tenant is None and residual_layer is None:
                host._kcache.base_drop(scope)
            # Holder reload + observer fan-out via invalidate.
            host.invalidate(
                scope=scope, tenant=effective_tenant or "",
                kind=kind, name=name, op="write",
            )
        host._fire_write_observers(
            scope, kind, name, "write", tenant=effective_tenant or "",
        )
        if not skip_hooks:
            # post_save still receives the legacy layer tuple for back-compat
            # with subscribers (evidence_capture etc.) — Phase 4 cleanup.
            hook_layer = (
                ("tenant", effective_tenant) if effective_tenant is not None
                else residual_layer
            )
            await self.emit_post_save(scope, kind, name, raw, layer=hook_layer)
        return version

    # -- delete (moved from the persistence body of Kernel.delete_document) -----

    async def delete(
        self, scope: str, kind: str, name: str,
        author: str | None,
        skip_hooks: bool,
        *,
        tenant: str | None,
        layer: tuple[str, str] | None,
        invalidate_mode: str,
        api_version: str | None = None,
    ) -> None:
        """Real delete_document body — the facade owns mode validation +
        record-plane demotion; the persistence + fan-out live here. NOTE:
        deletes have NO pre_save veto gate (only writes do)."""
        from dna.kernel.capabilities import write_kwarg_support
        host = self._host
        src = host._require_writable_source()
        # Resolve tenant + validate against KindPort.scope (back-compat for
        # layer=("tenant", X) → tenant=X with DeprecationWarning)
        effective_tenant, residual_layer = self._resolve_tenant_arg(
            kind, tenant, layer, api_version=api_version,
        )
        # s-kernel-capability-protocols — memoized kwarg probe (see write_document).
        ws = write_kwarg_support(src)
        kwargs: dict = {}
        if ws.tenant_delete:
            kwargs["tenant"] = effective_tenant
            if ws.layer_delete:
                kwargs["layer"] = residual_layer
        else:
            # Legacy adapter — fold tenant into layer for back-compat
            adapter_layer = residual_layer
            if effective_tenant is not None:
                adapter_layer = ("tenant", effective_tenant)
            if ws.layer_delete:
                kwargs["layer"] = adapter_layer
        await src.delete_document(scope, kind, name, **kwargs)
        # R2-fix (2026-05-14): mirror write_document's three-tier invalidate.
        if invalidate_mode != "none":
            host._invalidate_granular_cache(scope, kind=kind, name=name)
        if invalidate_mode == "scope":
            if effective_tenant is None and residual_layer is None:
                host._kcache.base_drop(scope)
            host.invalidate(
                scope=scope, tenant=effective_tenant or "",
                kind=kind, name=name, op="delete",
            )
        host._fire_write_observers(
            scope, kind, name, "delete", tenant=effective_tenant or "",
        )
        if not skip_hooks:
            await self.emit_post_delete(scope, kind, name, layer=layer)
