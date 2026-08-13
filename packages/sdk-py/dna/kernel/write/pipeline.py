"""WritePipeline — the kernel's instance write/delete execution, extracted from
the Kernel god-object (kernel decomposition, Fase 2 —
``s-kernel-decomp-f2-writepipeline``).

This is the FAT write-path logic: tenant resolution, capability-gated adapter
kwargs (author / write_class / version_retention / tenant / layer), the
layer-policy check, the ``pre_save`` veto gate, ``save_instance`` /
``delete_instance`` persistence, and the three-tier cache-invalidation fan-out
(granular → catalog → base-drop → invalidate → observers → post_save). The
Kernel RETAINS the public ``write_instance`` / ``delete_instance`` methods as
THIN facades (invalidate-mode validation, ``_REMOVED_KINDS`` block, record-plane
demotion, OTel span) that delegate their body here.

The load-bearing sequence this pipeline MUST reproduce byte-for-byte (spec Risk
#1, pinned by ``test_kernel_writepath_characterization``):

    write:  pre_save veto → save_instance → granular-invalidate →
            catalog-invalidate (only is_catalog_identity) → base-drop
            (scope-mode + base layer) → invalidate (scope-mode) →
            fire-observers (ALWAYS) → post_save (unless skip_hooks)
    delete: delete_instance → granular-invalidate → base-drop → invalidate →
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

from dna.kernel.invalidation_cost import emit_write, invalidation_logging_enabled
from dna.kernel.validity import strip_derived_status

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.protocols import (
        KindPort,
        TenantScope,
        WritableSourcePort,
    )

logger = logging.getLogger("dna.kernel")




class WritePipeline:
    """Executes instance writes/deletes against the host's writable source with
    the full invalidation fan-out. One per kernel; stateless (all state lives on
    the host, reached via the narrow ``WriteHost`` ref)."""

    def __init__(self, host: WriteHost) -> None:
        self._host = host

    # -- the REVOKED Kind refusal (i-085) ------------------------------------

    @staticmethod
    def _refuse_revoked_kind(
        scope: str, kind: str, name: str, port: Any,
    ) -> None:
        """Refuse the write outright when ``port`` is a REVOKED Kind.

        This is the "new instances" column of i-085's table, and it is checked
        HERE — one call site, on the port the write already resolved — rather
        than by any caller remembering to ask. The state travels on the port
        precisely so that it cannot be forgotten.

        Note what it refuses: EVERY instance of that Kind, conforming or not. A
        revoked Kind is not a stricter schema, it is a withdrawn Kind, so there
        is no shape that would pass and nothing for the author to fix. And note
        what it does NOT touch — deletes. Refusing those would trap the very
        instances the workspace may now want to clear out, and revocation
        already refuses to destroy anything on its own.

        No ``DNA_WRITE_VALIDATION`` escape hatch, unlike its schema-validating
        neighbour: that knob exists so an operator can bulk-load legacy data
        past a shape check, and this is not a shape check — it is a workspace's
        decision about its own Kind, which an environment variable must not be
        able to overrule.
        """
        from dna.kernel.kinds.registry import port_revoked

        if not port_revoked(port):
            return
        from dna.kernel.errors import RevokedKindWrite

        raise RevokedKindWrite(
            f"write refused for {scope}/{kind}/{name}: the Kind {kind!r} has "
            f"been revoked, so no new instances of it are accepted — this is "
            f"not about the instance's shape, and editing it will not help. "
            f"Existing instances are untouched and still readable (marked "
            f"invalid). Approve the Kind again to accept writes."
        )

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

        # Applied through the linear-time engine when `dna-sdk[re2]` is present
        # (decision C): the author-time guard accepts a `pattern` because RE2
        # proves it cannot backtrack, so the engine that RUNS it at write time
        # must be the same one. Falls back to plain jsonschema otherwise.
        from dna.kernel.kinds.regex_engine import validate_instance
        try:
            validate_instance(spec, schema)
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

    # -- declared relation validation (i-040, f-modelagem-das-relacoes) -------

    @staticmethod
    def _ref_validation_mode() -> str:
        """Read the relation-validation knob — ``warn`` (default), ``enforce``
        or ``off``.

        Deliberately a SEPARATE knob from ``DNA_WRITE_VALIDATION``, with a
        different default, because the two checks have different costs and
        different blast radii. Schema validation is pure CPU on data already in
        hand, so it defaults to ``enforce``. Relation validation costs one
        instance READ per declared relation (~5ms PG / ~3ms SQLite / ~20ms FS,
        LRU-cached), and it can fail on an instance that is perfectly
        well-formed — a forward reference to a target written later in the same
        bootstrap is a legitimate, common pattern (a seed writing a Plan before
        its Story; a scope installed in dependency-free order).

        Defaulting to ``enforce`` would therefore turn working setups into hard
        failures on upgrade, for a public contract third parties author against.
        Defaulting to ``warn`` still ends the SILENCE that i-040 is actually
        about — a dangling reference becomes a logged, observable event instead
        of nothing at all — while leaving the hard gate one environment
        variable away for CI and for operators who want it.
        """
        mode = os.environ.get("DNA_REF_VALIDATION", "warn").strip().lower()
        return mode if mode in ("enforce", "warn", "off") else "warn"

    async def _ensure_instance_id(
        self, scope: str, kind: str, name: str, raw: Any,
        *, tenant: str | None, api_version: Any = None,
        if_absent: bool = False,
    ) -> Any:
        """Guarantee ``raw["metadata"]["id"]`` — minting one only for an
        instance that does not already have one (i-114).

        Three cases, and the ORDER of them is the whole contract:

        1. The envelope already carries a well-formed id → keep it, untouched.
           This is the ordinary round-trip: a ``.dna/`` file was read, edited
           and written back, and its identity rode along in the frontmatter.
        2. The envelope carries none, but an instance is ALREADY STORED at
           these coordinates → **adopt the stored id**. This clause is the one
           that matters, and it is not defensive coding. The application-level
           write path (``dna.application.instances.write_instance_impl``)
           rebuilds the envelope from scratch as
           ``{"metadata": {"name": name}, "spec": …}`` — it does not carry
           metadata forward at all. Every write through the REST and MCP doors
           therefore arrives here with NO id. Minting a fresh one on that path
           would re-identify the instance on every save, and every
           ``dna_edges.to_id`` pointing at it would silently go stale: the
           feature would look implemented and be worthless. So an id is minted
           only where none exists to inherit.
        3. An instance IS stored and it has no id either → it PREDATES this
           feature, and it gets the DERIVED id
           (:func:`dna.kernel.identity.derived_instance_id`), not a random one.
           This is the same rule the Postgres backfill (revision 0008) applies,
           and it is here so that every OTHER store converges on the same
           values without needing a migration of its own. The case is real:
           this repo's own board lives BOTH as ``.dna/`` YAML in git and as
           rows in a database, and if the files were minted at random while the
           rows were derived, the same logical instance would carry two
           identities and ``to_id`` would be right in one store and wrong in
           the other from day one.
        4. Nothing stored at all → a genuinely NEW instance, so mint at random
           (see :func:`dna.kernel.identity.mint_instance_id`). The split
           between 3 and 4 is what lets both rules be true at once: "an
           instance that already existed converges" and "a new instance is
           unguessable, so delete-and-recreate under the same name is visibly a
           different object".

        ``get_instance_local`` and not ``get_instance``: the read must NOT fall
        back to a parent scope, because inheriting a parent instance's id would
        give two different instances the same identity — the exact confusion
        ``to_scope`` exists elsewhere in this file to avoid.

        ``if_absent`` skips the read entirely: the caller has asserted the
        instance does not exist, and the adapter is about to refuse the write
        if it does, so there is no id to inherit and no reason to pay for the
        lookup.

        A read that RAISES mints nothing and stamps nothing — it leaves the
        envelope exactly as it came. Inventing an identity because the store
        was briefly unreachable is how a transient failure becomes a permanent
        wrong answer; a write that reaches the adapter without an id keeps the
        id column it already has (see the adapter's COALESCE), so the honest
        move is to say nothing.
        """
        from dna.kernel.identity import (  # noqa: PLC0415
            derived_instance_id, instance_id_of, mint_instance_id,
            stamp_instance_id,
        )
        if not isinstance(raw, dict):
            return raw
        if instance_id_of(raw) is not None:
            return raw
        stored: Any = None
        if not if_absent:
            getter = getattr(self._host, "get_instance_local", None)
            if callable(getter):
                try:
                    stored = await getter(scope, kind, name, tenant=tenant)
                except Exception:  # noqa: BLE001 — see the docstring: an
                    # unreachable store must not mint a second identity.
                    return raw
        if stored is None:
            return stamp_instance_id(raw, mint_instance_id())
        return stamp_instance_id(raw, instance_id_of(stored) or derived_instance_id(
            tenant=tenant, scope=scope,
            api_version=(api_version if isinstance(api_version, str) else "") or "",
            kind=kind, name=name,
        ))

    async def _resolve_references(
        self, scope: str, kind: str, name: str, raw: Any, port: Any,
        *, tenant: str | None,
    ) -> tuple[list, bool]:
        """Resolve declared relations ONCE, validate, and hand back the edges.

        The validation contract is unchanged from i-040 (each clause is a
        deliberate refusal to break something):

        - A Kind declaring NO resolvable relation returns before doing any work
          — no reads, no cost. This is what keeps every Kind that points at
          nothing exactly as cheap as it was.
        - An absent / null / empty relation field is NOT a violation. Optional
          relations stay optional.
        - Existence is checked in the SAME scope and tenant as the write.
        - A polymorphic relation passes if the target exists as ANY declared
          Kind.
        - If the host cannot read instances, the check is SKIPPED rather than
          guessed at.
        - ``enforce`` vetoes; ``warn`` logs and persists; ``off`` skips.

        The lookups this method performs also identify, per relation value,
        WHICH declared Kind matched — the fact the edge table is made of.
        Returning it makes the edge a by-product of the check rather than a
        second derivation that could disagree with it.

        **Reciprocity is REPORTED here, and only reported.** When a relation
        declares ``inverse_of`` and the target instance does not name this one
        back, that is logged in EVERY mode and vetoes in NONE — including
        ``enforce``. The reason is in ``dna.kernel.kinds.relations``: imposing
        the inverse deadlocks (neither half of a pair can be written first) and
        deriving it means the kernel writing an instance the author did not
        touch. It costs nothing to report, because the target instance was
        already materialized by the existence check above. A dangling relation
        and a one-sided pair are different failures, and only the first is the
        author's to fix in the write they are making right now.

        Returns ``(edges, complete)``. ``complete=False`` means a read failed
        part-way: the validator says nothing (as it always has) and the
        producer must not replace anything, because a partial edge set stored
        as whole is a graph that lies while looking finished.
        """
        mode = self._ref_validation_mode()
        if mode == "off" or port is None or not isinstance(raw, dict):
            # ``off`` skips the reads, so there is no resolution and there are
            # no edges. NOT an empty graph — the face reports the producer as
            # off (``graph_producer``) so nobody reads silence as "no
            # relations". Fail-open in SILENCE is this house's signature defect.
            return [], False

        from dna.kernel.query.references import resolve_relations  # noqa: PLC0415

        host = self._host
        # The WritePipeline's WriteHost slice is intentionally narrow and does
        # not promise an instance read. The Kernel that satisfies it structurally
        # does provide ``get_instance``; a host that does not (a test double,
        # a reduced embedding) makes this check unavailable, and an unavailable
        # check must be a no-op rather than a false accusation.
        getter = getattr(host, "get_instance", None)
        if not callable(getter):
            return [], False

        edges, problems, discords, complete = await resolve_relations(
            port, raw,
            scope=scope, name=name, tenant=tenant,
            getter=getter,
            port_for=host.kind_port_for,
            # Same duck-type as ``get_instance`` above: the local-only read
            # that attributes a hit to THIS scope rather than to an inherited
            # parent. A cache hit in practice (``get_instance`` just loaded the
            # very same key), and simply absent on a reduced host.
            local_getter=getattr(host, "get_instance_local", None),
            # The by-KEY read (fatia 5). Same duck-type, same consequence when
            # absent: no `by: <key>` relation resolves and every one records
            # the reason ``unsupported`` — never ``missing``, which would
            # accuse the data of a gap that belongs to the host.
            key_getter=getattr(host, "find_instance_by_key", None),
        )

        if discords:
            # Reported BEFORE the veto branch on purpose: a write about to be
            # refused for a dangling by-NAME relation may ALSO have a one-sided
            # pair or an unresolved `by: <key>`, and the author should hear
            # every one rather than discover the next only after fixing the
            # first. Each note carries its OWN reason for not being a veto —
            # they are different reasons, and one summary line covering both
            # would have to be vague enough to explain neither.
            logger.warning(
                "%s/%s/%s: relation(s) reported and not enforced: %s",
                scope, kind, name, "; ".join(discords),
            )

        if not problems:
            return edges, complete

        detail = "; ".join(problems)
        msg = (
            f"write vetoed for {scope}/{kind}/{name}: unresolved relation(s): "
            f"{detail} — create the target first, or see "
            f"`dna kind show {kind}` for the declared relations"
        )
        if mode == "warn":
            logger.warning(
                "%s (DNA_REF_VALIDATION=warn — persisted anyway)", msg,
            )
            return edges, complete
        from dna.kernel.protocols import SpecValidationError  # noqa: PLC0415
        raise SpecValidationError(msg)

    async def _validate_references(
        self, scope: str, kind: str, name: str, raw: Any, port: Any,
        *, tenant: str | None,
    ) -> None:
        """Validation-only facade over :meth:`_resolve_references` (i-040).

        Kept because the check is meaningful on its own and is called that way
        by tests and by any caller that wants the gate without the graph.
        """
        await self._resolve_references(
            scope, kind, name, raw, port, tenant=tenant,
        )

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
        Called from ``write_instance`` only when ``spec.writes_kind`` OR
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
        from dna.kernel.boot.events import derive_event_type
        # Parity with typescript/src/kernel/index.ts::_emitPostSave:
        # scope is a HookContext top-level field (subscribers like
        # EvidenceCaptureHook read ctx.scope directly — stuffing it into
        # data.scope leaves ctx.scope as "" and the evidence policy
        # lookup fails silently).
        await host.hooks.emit_async("post_save", HookContext(
            scope=scope, kind=kind, name=name,
            layer=layer,
            data={
                "event_type": derive_event_type(kind, is_update=False, kernel=host),
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
        *, api_version: str | None = None, scope: str | None = None,
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
                "write_instance/delete_instance instead",
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
        scope_decl = host._kind_scope(
            kind, api_version=api_version, scope=scope,
        )
        if scope_decl == TenantScope.TENANTED and effective is None:
            raise TenantRequired(
                f"Kind {kind!r} is TENANTED — pass tenant=<slug> to "
                "write_instance() or bind one via Kernel(tenant=...) / "
                "kernel.with_tenant(...)"
            )
        if scope_decl == TenantScope.GLOBAL and effective is not None:
            raise TenantNotAllowed(
                f"Kind {kind!r} is GLOBAL — must NOT pass a tenant. "
                "Use the unbound kernel (Kernel() with tenant=None) or "
                "kernel.with_tenant(None) for global writes."
            )
        return effective, residual_layer

    # -- write (moved verbatim from Kernel._write_instance_inner) ---------------

    async def write(
        self, scope: str, kind: str, name: str, raw: dict,
        author: str | None,
        skip_hooks: bool,
        *,
        tenant: str | None,
        layer: tuple[str, str] | None,
        invalidate_mode: str,
        write_class: str = "substantive",
        if_absent: bool = False,
        if_match: str | None = None,
    ) -> str | None:
        """Real write_instance body — the facade (``Kernel.write_instance``) owns
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
          the mi rebuild + holder.reload. Sidecar writes (Engram, …).
        - ``"none"``: skip ALL invalidation. Test-only / out-of-band writes.

        A catalog-identity Kind (``KindPort.is_catalog_identity``) additionally
        drops the whole catalog cache. ``_fire_write_observers`` (the SSE /
        cross-process listeners) fires ALWAYS regardless of mode — the channel
        contract guarantees delivery for every write."""
        from dna.kernel.capabilities import write_kwarg_support
        from dna.kernel import (
            LEGACY_VERSION_CHURN_KINDS, VERSION_CHURN_RETENTION,
        )
        host = self._host
        src = host._require_writable_source()
        # i-195: colliding kind names resolve their port by the doc's own
        # apiVersion wherever we consult Kind metadata below.
        _api_version = raw.get("apiVersion") if isinstance(raw, dict) else None
        # i-081: resolve the Kind AS THIS SCOPE SEES IT. A store-loaded Kind
        # governs only the scope whose store declared it, and this port is what
        # decides schema enforcement, tenancy and storage routing for the write
        # — resolving it unscoped is how another scope's schema came to veto
        # this one's instances.
        _kind_port = host.kind_port_for(
            kind, api_version=_api_version, scope=scope,
        )
        # i-085 — the REVOKED-Kind refusal, and the ``status`` strip that keeps
        # validity DERIVED. Both run first, before hooks, tenancy and schema
        # validation, because both are about whether this write may exist at all
        # rather than about the shape it has.
        self._refuse_revoked_kind(scope, kind, name, _kind_port)
        raw = strip_derived_status(raw)
        # Resolve tenant + validate against KindPort.scope
        effective_tenant, residual_layer = self._resolve_tenant_arg(
            kind, tenant, layer, api_version=_api_version, scope=scope,
        )
        # i-114 — the instance's IDENTITY, stamped before anything downstream
        # can see the envelope: hooks, schema validation, relation resolution
        # and persistence all operate on the shape that will actually be
        # stored, id included.
        raw = await self._ensure_instance_id(
            scope, kind, name, raw, tenant=effective_tenant,
            api_version=_api_version, if_absent=if_absent,
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
        # the machine-churn Kinds so autopilot rewrites don't drown the
        # authored-content history. Authored Kinds keep full history.
        #
        # DERIVED from the Kind's own ``version_retention`` declaration (class
        # attribute or ``spec.version_retention`` in a descriptor), never from a
        # list of names here — that list is gone (i-107). The declaration was
        # ALREADY read first, on the line below; the set was its fallback, which
        # is to say a second copy of a per-Kind fact. ``LEGACY_VERSION_CHURN_KINDS``
        # holds only retired doc-kinds with no class to declare on.
        if ws.version_retention:
            _kp = _kind_port
            _retention = getattr(_kp, "version_retention", None) if _kp else None
            if _retention is None and kind in LEGACY_VERSION_CHURN_KINDS:
                _retention = VERSION_CHURN_RETENTION
            if _retention is not None:
                kwargs["version_retention"] = _retention
        if if_absent:
            # An ATOMIC create. Refuse rather than degrade: a caller that asked
            # for "create or fail" and silently got an upsert would believe it
            # holds a guarantee it does not, which is worse than not offering
            # the guarantee at all.
            if not ws.if_absent:
                raise NotImplementedError(
                    f"{type(src).__name__} does not support if_absent writes "
                    f"(it declares write_kwargs without 'if_absent'), so this "
                    f"kernel cannot promise an atomic create against it. Use "
                    f"read-then-write and accept the race, or run against an "
                    f"adapter that declares the kwarg."
                )
            kwargs["if_absent"] = True
        if if_match is not None:
            # A GUARDED update (i-083) — the mirror of the block above, and
            # refused for the same reason with one extra edge to it. ``if_match``
            # is not asked for defensively: a caller passes it because it is
            # about to REPLACE an instance it read a moment ago, and the value of
            # the token is that the replacement is refused if the instance moved
            # underneath. Degrading to an unguarded upsert would perform exactly
            # the lost update the caller paid a round trip to prevent, and report
            # success.
            if not ws.if_match:
                raise NotImplementedError(
                    f"{type(src).__name__} does not support if_match writes "
                    f"(it declares write_kwargs without 'if_match'), so this "
                    f"kernel cannot promise your update will be refused if the "
                    f"instance changed since you read it. Re-read immediately "
                    f"before writing and accept the race, or run against an "
                    f"adapter that declares the kwarg."
                )
            if if_absent:
                # Mutually exclusive by meaning, not by policy: one asserts the
                # instance is ABSENT, the other that it is PRESENT and unchanged.
                # Together they can never both hold, so an adapter handed both
                # would have to invent a precedence — and whichever it picked,
                # one of the two guarantees the caller believes it holds would be
                # silently untrue.
                raise ValueError(
                    "if_absent and if_match cannot be combined: if_absent "
                    "asserts the instance does not exist, if_match asserts it "
                    "exists and still hashes to a token you read. Pick the one "
                    "you mean."
                )
            kwargs["if_match"] = if_match
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
        # --- namespace ownership (i-080 item 1) ---
        # ONE boundary governs both write policies, which is why this sits here
        # and not in a face. Two details are deliberate:
        #
        # * it runs AFTER the layer check, continuing that gate's own
        #   coarse-to-fine rule: "this Kind may never be forked into a layer" is
        #   broader than "you do not own this namespace", so a layer write keeps
        #   the broader message;
        # * but UNCONDITIONALLY, not only for layer writes. The layer check is
        #   skipped entirely for a BASE write, and a workspace-authored Kind is
        #   authored exactly there — KindDefinition is structurally
        #   non-overlayable, so a workspace's Kind lives at the base of a scope
        #   the workspace owns. Gating only layer writes would gate every path
        #   except the one a tenant Kind actually takes.
        #
        # A no-op for every Kind but KindDefinition, and for an unattributed
        # write — see dna.kernel.write.namespace_gate for the full contract.
        await host._check_namespace_ownership_async(
            scope, kind, name, raw, tenant=effective_tenant,
        )
        # --- pre_save veto hooks (s-write-path-despecialize) ---
        # Kind-specific write rules (platform-agent fork guard, prompt-budget
        # enforcement, Kind-Writer contract, bitemporal Engram guard,
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
        # --- declared relation validation (i-040) ---
        # Immediately after the shape check and before persistence, for the
        # same reason: the author hears about a dangling relation here, not
        # when something far away later tries to follow it. No-op (and no
        # reads) for any Kind whose ``spec.relations`` declares nothing the
        # kernel resolves.
        edges, edges_complete = await self._resolve_references(
            scope, kind, name, raw, _kind_port, tenant=effective_tenant,
        )
        # --- the derived edges ride along with the save (spec-grafo-1) --------
        # The SAME lookups the check above just made also say which Kind each
        # reference resolved to. Handing that to the adapter as a kwarg lets it
        # write the edges INSIDE the transaction that writes the instance —
        # the form ``_events.emit(conn, …)`` → ``dna_outbox`` established — so
        # the instance and its edges enter together or neither does.
        #
        # Three refusals are encoded in this one condition:
        #  * an adapter that has not adopted the kwarg is never handed it (the
        #    capability probe, exactly like ``tenant`` and ``if_match``), so the
        #    ``WriteHost`` Protocol stays untouched — widening it to pass a
        #    connection is marked in its own file as a code-review event;
        #  * ``complete=False`` (a read failed mid-resolution, or the producer
        #    is off) does NOT replace what is stored: an old-but-known edge set
        #    beats a new-but-partial one, and the backfill can repair it later;
        #  * an instance with no declared references still passes ``edges=[]``,
        #    which is how removing the last reference from an instance removes
        #    its rows instead of leaving stale ones behind.
        if ws.edges and edges_complete:
            kwargs["edges"] = edges
        version = await src.save_instance(scope, kind, name, raw, **kwargs)
        # R2-fix (2026-05-14): three invalidation tiers.
        #
        # mode=none — write only, no cache invalidation. Caller owns hygiene.
        # mode=doc  — only the granular per-doc L2 cache is dropped. The
        #             instance cache + holder.reload chain is SKIPPED. Use
        #             for sidecar writes (Engram, WorkflowEvent, ...)
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
        # i-123 — o CONTADOR do gatilho 2. Desligado, a única linha a mais no
        # caminho quente é uma comparação de nível; nada é formatado.
        if invalidation_logging_enabled():
            emit_write(
                kind=kind, port=_kind_port,
                plane=getattr(_kind_port, "plane", "composition"),
                mode=invalidate_mode, op="write", tenant=effective_tenant,
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

    # -- delete (moved from the persistence body of Kernel.delete_instance) -----

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
        """Real delete_instance body — the facade owns mode validation +
        record-plane demotion; the policy gate, the persistence and the fan-out
        live here.

        ⚠️ **THE chokepoint for ``on_target_delete``.** Deletes have no
        ``pre_save`` veto (only writes do), and that absence is exactly what the
        spec's slice 2 named as the gap: *"deleting a Feature that 47 Stories
        point at is accepted in silence"*. The gate is here rather than in a
        face because five of the six delete call sites in this repo funnel into
        this one method — see :mod:`dna.kernel.write.target_delete` for the
        count, and for why the sixth (source-to-source ``sync``) is deliberately
        below it.

        ⚠️ **And the chokepoint for ``record.invalidate-only``** (i-130), for
        the same reason one question earlier: whether an instance of this KIND
        may be removed at all. See :mod:`dna.kernel.write.hard_delete` — it runs
        first because it is a registry lookup that touches no store, and because
        a Kind that may not be deleted must not have its referrers walked to
        find that out.
        """
        host = self._host
        src = host._require_writable_source()
        # ── the KIND gate ─────────────────────────────────────────────────
        # An Engram promises in its own descriptor that it is never
        # hard-deleted. Enforced here so the promise holds at every door rather
        # than at whichever one somebody guarded.
        from dna.kernel.errors import DeleteRefused
        from dna.kernel.write.hard_delete import hard_delete_refusal

        kind_refusal = hard_delete_refusal(
            host.kind_port_for(kind, api_version=api_version, scope=scope)
        )
        if kind_refusal is not None:
            raise DeleteRefused(kind_refusal)
        # Resolve tenant + validate against KindPort.scope (back-compat for
        # layer=("tenant", X) → tenant=X with DeprecationWarning)
        effective_tenant, residual_layer = self._resolve_tenant_arg(
            kind, tenant, layer, api_version=api_version, scope=scope,
        )
        # ── the GRAPH gate ────────────────────────────────────────────────
        # Raises TargetDeleteRestricted before ANYTHING is removed. Returns []
        # — touching no store at all — whenever no registered relation declares
        # a policy naming this Kind, which is every delete in this registry
        # today. See the module docstring for why that has to be free.
        from dna.kernel.write.target_delete import (
            plan_target_delete,
            registry_relations,
        )

        cascade = await plan_target_delete(
            src, registry_relations(host.kind_ports()),
            scope, kind, name, tenant=effective_tenant,
        )
        # The KIND gate again, over the PLAN — a ``delete_source`` cascade is a
        # hard delete too, and it reaches ``_persist_delete`` directly. Asked
        # before the first removal, so a plan that touches an invalidate-only
        # record is refused whole rather than half-executed. Free today (no
        # relation declares ``delete_source`` at all, so the plan is empty), and
        # the point is that it stays free when one does.
        for cascade_kind, cascade_name in cascade:
            cascade_refusal = hard_delete_refusal(
                host.kind_port_for(cascade_kind, scope=scope))
            if cascade_refusal is not None:
                raise DeleteRefused(
                    f"deleting {kind}/{name} would cascade into "
                    f"{cascade_kind}/{cascade_name}, and {cascade_refusal}"
                )
        for cascade_kind, cascade_name in cascade:
            # api_version is NOT passed: the edge carries a bare Kind name, and
            # i-195 makes a Kind name globally unique by an ENFORCED registry
            # invariant, so the bare name resolves unambiguously. Inventing an
            # api_version here would be guessing at something the graph did not
            # say.
            await self._persist_delete(
                scope, cascade_kind, cascade_name,
                skip_hooks=skip_hooks, tenant=effective_tenant,
                residual_layer=residual_layer, layer=layer,
                invalidate_mode=invalidate_mode, api_version=None,
            )
        await self._persist_delete(
            scope, kind, name,
            skip_hooks=skip_hooks, tenant=effective_tenant,
            residual_layer=residual_layer, layer=layer,
            invalidate_mode=invalidate_mode, api_version=api_version,
        )

    async def _persist_delete(
        self, scope: str, kind: str, name: str, *,
        skip_hooks: bool,
        tenant: str | None,
        residual_layer: tuple[str, str] | None,
        layer: tuple[str, str] | None,
        invalidate_mode: str,
        api_version: str | None,
    ) -> None:
        """One instance gone, plus the ordered invalidation fan-out.

        Split out of :meth:`delete` so a ``delete_source`` cascade removes its
        instances through the SAME persistence and fan-out as a direct delete —
        the alternative was recursing into ``delete`` and re-planning the whole
        closure per node, which is quadratic and, worse, would re-ask a question
        the plan already answered for the whole set.
        """
        from dna.kernel.capabilities import write_kwarg_support
        host = self._host
        src = host._require_writable_source()
        effective_tenant = tenant
        # s-kernel-capability-protocols — memoized kwarg probe (see write_instance).
        ws = write_kwarg_support(src)
        kwargs: dict = {}
        if ws.api_version_delete and api_version:
            # i-081: route the delete by the EXACT Kind. Without it the adapter
            # resolves a bare Kind NAME, and two workspaces may each declare a
            # `Deal` under their own namespace — the delete then looks in the
            # other Kind's container, finds nothing, and the caller is told it
            # succeeded. Passed only when the adapter DECLARES the kwarg
            # (``delete_kwargs``), so an adapter that has not adopted it is
            # unaffected.
            kwargs["api_version"] = api_version
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
        await src.delete_instance(scope, kind, name, **kwargs)
        # R2-fix (2026-05-14): mirror write_instance's three-tier invalidate.
        if invalidate_mode != "none":
            host._invalidate_granular_cache(scope, kind=kind, name=name)
        if invalidate_mode == "scope":
            if effective_tenant is None and residual_layer is None:
                host._kcache.base_drop(scope)
            host.invalidate(
                scope=scope, tenant=effective_tenant or "",
                kind=kind, name=name, op="delete",
            )
        # i-123 — o mesmo contador da escrita. O delete resolve o port SÓ aqui,
        # e só com o funil ligado: ele é o único consumidor dele neste corpo, e
        # uma resolução a mais por delete no caminho desligado seria custo por
        # nada. Desligado, a única linha a mais é a comparação de nível.
        if invalidation_logging_enabled():
            _deleted_port = host.kind_port_for(
                kind, api_version=api_version, scope=scope,
            )
            emit_write(
                kind=kind, port=_deleted_port,
                plane=getattr(_deleted_port, "plane", "composition"),
                mode=invalidate_mode, op="delete", tenant=effective_tenant,
            )
        host._fire_write_observers(
            scope, kind, name, "delete", tenant=effective_tenant or "",
        )
        if not skip_hooks:
            await self.emit_post_delete(scope, kind, name, layer=layer)
