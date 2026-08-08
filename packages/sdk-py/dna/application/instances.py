"""``dna.application.instances`` — GENERIC, registry-driven instance use-cases.

The gap this closes: every serving face DNA ships enumerated its capabilities by
hand. The MCP face has 21 hand-written tools and no loop over the Kind registry,
so 85% of its lines name one specific Kind — and a Kind that exists (including
the ones declared purely by a ``*.kind.yaml`` descriptor) is invisible to an
agent unless somebody writes tools for it. The generic path is not missing: the
CLI's ``dna instance`` has served every Kind in-process for a long time
(``dna_cli._ctx._LocalDocs``). It was simply never *served*.

These use-cases are that generic path, transport-agnostic, resolved from the
kernel's :class:`~dna.kernel.kinds.registry.KindRegistry` **at call time** (the
list is spelled out rather than counted: it said "these four" while shipping
seven, and a count that drifts is the one thing a reader trusts without checking):

    list_kinds_impl        — the Kind catalog (what can I act on here?)
    list_instances_impl    — the instances of one Kind in a scope
    search_instances_impl  — the instances of one Kind that RESEMBLE a query
    get_instance_impl      — one instance, verbatim
    resolve_instance_impl  — one instance, by id
    graph_refs_impl        — what points at one instance
    write_instance_impl    — create/update one instance
    delete_instance_impl   — remove one instance

They live in the CORE (``adr-faces-reorg`` move #1) so a face is a thin adapter
and every face inherits the same rules — most importantly the two refusals
below, which would be a hole the moment a second face re-implemented them.

**Refusal 1 — bootstrap Kinds are never written generically.** A ``Genome``, a
``LayerPolicy`` or a ``KindDefinition`` is not content *inside* a scope, it is
the declaration of what that scope *is*: the Genome carries the scope's identity
and its ``parent_scope`` inheritance, a LayerPolicy is the operator's own
override policy (the very gate ``write_instance`` consults), and a
KindDefinition registers a brand-new Kind with its own schema, storage marker
and dep_filters. The set is **derived**, not hand-typed: it is exactly the ports
that declare ``is_overlayable = False`` — the kernel's own marker for "a layer
may not fork this". A new bootstrap Kind is therefore refused the day it is
declared, with no list to keep in sync. Reads are untouched.

**Refusal 2 — an ambiguous bare Kind name.** Two api_versions may share a Kind
name (i-195; live today whenever a per-scope ``KindDefinition`` shadows a
builtin). Bare-name lookup resolves one deterministically, which is fine for a
human at a CLI and wrong here: the
resolved port decides both the instance's ``apiVersion`` **and** its metering
family, so silently picking one would let the registry pick a caller's quota
family for them. The generic surface refuses and asks for ``api_version``.

**The metering family** (:func:`family_for_kind`) is derived from the target
Kind's own port, so a face can meter a generic call exactly as it meters the
hand-written tool for the same Kind — and a caller cannot choose the family by
choosing a tool. Enforcement itself is the face's job (it owns the plan); this
module only classifies.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from dna.application.live import LiveDna
from dna.kernel.errors import DeleteRefused
from dna.kernel.etag import spec_etag
from dna.kernel.kinds.registry import ports_in_scope
from dna.memory.verbs import MEMORY_KINDS

logger = logging.getLogger(__name__)

__all__ = [
    "AmbiguousKindError",
    "BootstrapKindWriteRefused",
    "ConcurrentWriteError",
    "DEFAULT_FAMILY",
    "DeleteRefused",
    "TRAIT_APPEND_ONLY",
    "UnknownInstanceError",
    "UnknownKindError",
    "bootstrap_kinds",
    "delete_instance_impl",
    "delete_refusal",
    "family_for_kind",
    "get_instance_impl",
    "is_append_only_kind",
    "is_bootstrap_kind",
    "list_instances_impl",
    "list_kinds_impl",
    "resolve_kind_port",
    "resolve_kind_port_live",
    "search_instances_impl",
    "spec_etag",
    "write_instance_impl",
]


# ── errors (each face maps these to its transport) ──────────────────────────


class UnknownKindError(LookupError):
    """The named Kind is not registered on this kernel."""


class AmbiguousKindError(ValueError):
    """The bare Kind name resolves to more than one registered port — the caller
    must disambiguate with ``api_version`` (see the module docstring)."""


class ConcurrentWriteError(ValueError):
    """An ``if_match`` guard on a generic write did not hold — the stored
    instance changed (or vanished) since the caller read it, so the write would
    have silently overwritten somebody else's update.

    Subclasses ``ValueError`` so every face that already maps write-path vetoes
    to an honest client refusal surfaces it with no new wiring."""


class UnknownInstanceError(LookupError):
    """A generic delete named an instance that is not there.

    Distinct from :class:`UnknownKindError`: the Kind resolved fine, the
    instance did not. Returning quietly would report success for a delete that
    did nothing — which is exactly how a caller convinces itself something is
    gone."""


class BootstrapKindWriteRefused(PermissionError):
    """A generic write targeted a BOOTSTRAP Kind and was refused (fail closed).

    Not a plan/quota denial and not a bug: writing a Genome / LayerPolicy /
    KindDefinition changes what the scope *is*, which no generic
    write-any-instance tool should be able to do. The purpose-built paths
    (workspace provisioning for a Genome, the operator's own policy authoring
    for a LayerPolicy, the KindDefinition wizard) stay available."""


# ── the Kind registry, generically ──────────────────────────────────────────


def resolve_kind_port(
    kernel: Any, kind: str, api_version: str | None = None, *,
    scope: str | None = None,
) -> Any:
    """The registered ``KindPort`` for ``kind`` — the ONE resolution every
    generic use-case goes through.

    Deliberately NOT ``kernel.kind_port_for``: that resolves an ambiguous bare
    name deterministically (extension-first, then registration order), which is
    the right ergonomic for a CLI and the wrong one here — see the module
    docstring's "Refusal 2".

    ``scope`` restricts resolution to the Kinds that GOVERN that scope (i-081).
    Passing it is what keeps two workspaces apart on this surface: without it a
    Kind another workspace declared is resolvable here, and two workspaces
    declaring the same Kind NAME made this function raise
    :class:`AmbiguousKindError` at both of them for a name neither shares.

    Raises :class:`UnknownKindError` when nothing matches and
    :class:`AmbiguousKindError` when a bare name matches several ports.
    """
    ports = ports_in_scope(kernel, scope)
    if api_version is not None:
        exact = [
            p for p in ports
            if p.kind == kind and p.api_version == api_version
        ]
        if not exact:
            raise UnknownKindError(
                f"no Kind {kind!r} registered under apiVersion {api_version!r} — "
                f"call list_kinds to see what this source serves."
            )
        return exact[0]
    matches = [p for p in ports if p.kind == kind]
    if not matches:
        raise UnknownKindError(
            f"Kind {kind!r} is not registered on this source — call list_kinds "
            f"to see what it serves."
        )
    if len(matches) > 1:
        versions = sorted(p.api_version for p in matches)
        raise AmbiguousKindError(
            f"Kind name {kind!r} is registered under {len(matches)} apiVersions "
            f"({', '.join(versions)}) — pass api_version to say which one you "
            f"mean. Refusing to guess: the resolved Kind decides both what is "
            f"written and how the call is metered."
        )
    return matches[0]


async def resolve_kind_port_live(
    live: LiveDna, kind: str, api_version: str | None = None, *,
    scope: str | None = None,
) -> Any:
    """:func:`resolve_kind_port`, preceded by the instance routes' REBUILD
    TRIGGER — the seam that lets an approval take effect on THIS replica (i-090).

    The instance routes resolve their Kind straight off the registry, and the
    registry is only ever (re)populated inside a Manifest Instance build. No
    instance route builds one, so on a replica that did not itself serve the
    approval a freshly approved Kind stayed unregistered until somebody happened
    to call a ``definitions``-family route for that scope — indeterminate, per
    replica, and for a REVOCATION a door that is slow to close.

    :meth:`~dna.application.live.LiveDna.ensure_kinds` is the answer, and it is
    TTL'd (:data:`~dna.application.live.KIND_REFRESH_TTL_DEFAULT`), so the cost
    is one bootstrap-slice read per scope per window per replica — not one per
    request — and what it buys is a number an operator can publish rather than a
    hope.

    Every generic use-case below resolves through HERE rather than through the
    bare :func:`resolve_kind_port`, precisely so a new route cannot forget the
    trigger: it is attached to the resolution, the one thing an instance route
    cannot skip. The bare function stays exported for callers that hold a kernel
    and no live handle.
    """
    await live.ensure_kinds(scope)
    return resolve_kind_port(live.kernel, kind, api_version, scope=scope)


def is_bootstrap_kind(port: Any) -> bool:
    """Whether ``port`` is a BOOTSTRAP Kind — one whose instances declare what a
    scope *is* rather than holding content within it.

    Derived from the kernel's own ``KindPort.is_overlayable`` marker (False =
    "no layer may fork this Kind"), which today selects exactly ``Genome`` /
    ``LayerPolicy`` / ``KindDefinition``. Deriving rather than naming means a
    future bootstrap Kind — including one declared by a ``.kind.yaml``
    descriptor's ``is_overlayable: false`` — is covered on arrival."""
    return port is not None and not bool(getattr(port, "is_overlayable", True))


def bootstrap_kinds(kernel: Any, *, scope: str | None = None) -> set[str]:
    """The bootstrap Kind names registered on ``kernel`` (see
    :func:`is_bootstrap_kind`). Exposed so a face can SHOW the refusal in its
    catalog instead of letting an agent discover it by being denied."""
    return {
        p.kind for p in ports_in_scope(kernel, scope) if is_bootstrap_kind(p)
    }


def bootstrap_write_refusal(port: Any) -> str:
    """The refusal message for a generic write on ``port`` — one text, so the
    catalog's ``write_refusal`` and the raised error can never drift."""
    return (
        f"{port.kind!r} is a BOOTSTRAP Kind: its instances declare what this "
        f"scope IS (identity + inheritance, the operator's own layer policy, or "
        f"the definition of a Kind itself), not content within it. The generic "
        f"write refuses it — fail closed — because a tool that can write any "
        f"instance must not be the tool that rewrites the frame every other "
        f"instance is validated and composed against. Use the purpose-built "
        f"path for this Kind (it is still READABLE here)."
    )


#: A Kind carrying this trait is an audit / evidence record: writable and
#: readable, never deletable through a generic tool.
TRAIT_APPEND_ONLY = "record.append-only"


# ``DeleteRefused`` — a delete targeted a Kind that must not be deleted this
# way — used to be DECLARED right here and is now imported from
# ``dna.kernel.errors`` (i-130) and re-exported through ``__all__``, so
# ``D.DeleteRefused`` and ``from dna.application import DeleteRefused`` keep
# resolving to the same class.
#
# It moved because the refusal stopped being a rule about this TOOL.
# ``record.invalidate-only`` is enforced at the kernel chokepoint every door
# crosses, and one verdict must not reach the caller as two exception types
# depending on which door asked. The class kept its ``PermissionError`` base
# (additive, never a re-parenting) and gained ``KernelRefusal`` — the family
# for a verdict about the REQUEST, which is exactly what this is: the store
# could have removed the row, and policy said no.


def _port_traits(port: Any) -> frozenset[str]:
    from dna.kernel.kinds.traits import port_traits

    return port_traits(port)


def is_append_only_kind(port: Any) -> bool:
    """Whether ``port`` declares :data:`TRAIT_APPEND_ONLY`."""
    if port is None:
        return False
    from dna.kernel.kinds.traits import port_has_trait

    return port_has_trait(port, TRAIT_APPEND_ONLY)


def delete_refusal(port: Any) -> str | None:
    """Why a generic DELETE of ``port``'s Kind is refused, or ``None``.

    Three categories, and every one of them is DERIVED (from ``is_overlayable``
    and from a declared trait) rather than from a list of Kind names, so a Kind
    that arrives later — including one a tenant declares in a ``.kind.yaml`` —
    is covered on arrival rather than the next time somebody remembers.

    **1. Bootstrap Kinds** — Genome, LayerPolicy, KindDefinition. The generic
    write already refuses these because they declare what the scope IS. Delete
    is strictly worse than write here, and the asymmetry is the point: a bad
    Genome is recoverable by writing a better one, but deleting a KindDefinition
    leaves every instance of that Kind on disk with nothing left that can
    validate, compose or even name them — and the thing that would have told you
    what the orphans were is what you just deleted.

    **2. Append-only records** — AuditLog, Evidence, WorkflowEvent. The record is
    what proves what happened. Deleting it is the first move of anyone with
    something to hide, and there is no "write a better one" for a fact.

    **3. Invalidate-only records** — the Engram (i-130). Reported here so
    ``list_kinds`` says ``deletable: false`` with the reason BEFORE anybody
    tries, and refused here so the generic tool never reaches the store. Unlike
    the first two it is not enforced ONLY here: it is a promise about the row
    rather than a rule about this tool, so the kernel refuses it at the
    chokepoint every door crosses (:mod:`dna.kernel.write.hard_delete`). This
    call is the early, catalogued half of the same verdict — same trait, same
    message, same exception type.

    ⚠️ This line said "everything else is deletable" and then measured itself
    wrong: the sentence was true of a memory too, and a memory promises the
    opposite in its own descriptor. Everything else really is deletable, and
    deliberately so — a Story, a Skill, a tenant's own instance are all things
    whose owner may legitimately want gone, and a delete they cannot perform is
    a delete they will perform by hand against the database."""
    if port is None:
        return None
    if is_bootstrap_kind(port):
        return (
            f"{port.kind!r} is a BOOTSTRAP Kind: its instances declare what this "
            f"scope IS (identity + inheritance, the operator's layer policy, or "
            f"the definition of a Kind itself). The generic delete refuses it. "
            f"Deleting one is worse than writing a bad one: a bad Genome is "
            f"fixed by writing a better Genome, but deleting a KindDefinition "
            f"leaves every instance of that Kind in place with nothing left to "
            f"validate, compose or name them — and what would have told you what "
            f"they were is what you deleted. Use the purpose-built path."
        )
    if is_append_only_kind(port):
        return (
            f"{port.kind!r} is an APPEND-ONLY record: it is the evidence of what "
            f"happened. It can be written and read here, never deleted — "
            f"deleting the audit trail is the first move of anyone with "
            f"something to hide, and unlike a bad write there is no better "
            f"version to replace it with. Supersede it with a new record."
        )
    from dna.kernel.write.hard_delete import hard_delete_refusal

    return hard_delete_refusal(port)


# ── the metering family, derived from the Kind ──────────────────────────────
#
# The family vocabulary (definitions / sdlc / memory / emit) is a PRODUCT
# vocabulary — a tier's `feature_families` — not kernel truth, so it cannot be
# read off a KindPort attribute. It is derived instead from the two things the
# registry does know: the Kind's api_version NAMESPACE and the SDK's own
# declared memory vocabulary. That keeps it registry-grained rather than
# per-Kind: all 25 Kinds of the sdlc namespace (and any added later) classify
# with no edit here.

#: The family for anything that is neither the board nor memory — i.e. every
#: definition DNA composes from. Also the family an UNKNOWN Kind meters as, so
#: a face charges the probe before refusing it.
DEFAULT_FAMILY = "definitions"

#: api_version namespaces that belong to the `sdlc` feature family. ``testkit``
#: is here because TestGuide/TestRun are board artifacts authored by
#: ``dna sdlc test-guide`` / ``test-run``, not definitions.
#:
#: Namespace-grained, so it classifies every Kind of a namespace (all 25 of
#: ``…/sdlc/v1`` today, and any added later) with no edit here. One consequence
#: is deliberate: ``PromptTemplate`` lives in the sdlc namespace, so a generic
#: call on it meters as ``sdlc`` while the hand-written ``get_template`` meters
#: as ``definitions``. That is STRICTER, never looser — the generic surface
#: never grants what a named tool would refuse, which is the invariant that
#: matters; re-homing the Kind is a separate decision.
_SDLC_NAMESPACES = frozenset({"sdlc", "testkit"})


def _namespace(api_version: str) -> str:
    """The owning namespace segment of an apiVersion (``…/dna/sdlc/v1`` →
    ``sdlc``; ``agents.md/v1`` → ``agents.md``)."""
    parts = [p for p in (api_version or "").split("/") if p]
    return parts[-2] if len(parts) >= 2 else ""


def family_for_kind(port: Any) -> str:
    """The quota FEATURE FAMILY a call touching ``port``'s Kind belongs to.

    Derived from the target Kind, never from the caller: the same port that
    supplies the instance's ``apiVersion`` supplies the family, so the meter and
    the write can never disagree. ``None`` (an unregistered Kind) →
    :data:`DEFAULT_FAMILY`."""
    if port is None:
        return DEFAULT_FAMILY
    if getattr(port, "kind", None) in MEMORY_KINDS:
        return "memory"
    if _namespace(getattr(port, "api_version", "")) in _SDLC_NAMESPACES:
        return "sdlc"
    return DEFAULT_FAMILY


# ── shared shaping helpers ──────────────────────────────────────────────────


def _row_name(row: dict[str, Any]) -> str | None:
    meta = row.get("metadata") if isinstance(row, dict) else None
    if isinstance(meta, dict) and meta.get("name"):
        return str(meta["name"])
    return str(row["name"]) if isinstance(row, dict) and row.get("name") else None


def _enum_value(value: Any) -> str | None:
    """A ``TenantScope``/``StoragePattern`` enum (or a plain string) as a
    JSON-safe string; ``None`` stays ``None``."""
    if value is None:
        return None
    return str(getattr(value, "value", value))


# ``spec_etag`` MOVED to :mod:`dna.kernel.etag` (i-083) and is re-exported here
# unchanged, so every existing importer keeps working. It moved because the SAME
# token now guards ``kernel.write_instance`` itself, and that guard is evaluated
# by the ADAPTER — which may import ``dna.kernel.*`` and nothing above it. The
# alternative was a second copy of the hash one layer down, and two hashes that
# disagreed by a sort order or a separator would refuse every honest write while
# admitting the stale one, failing as flakiness rather than as a bug. See
# ``dna.kernel.etag`` for why the token is a content digest and not the
# adapter's version id.


def _merged_spec(
    stored: dict[str, Any], incoming: dict[str, Any], *, merge: bool,
) -> dict[str, Any]:
    """The spec to persist, given the stored one and the caller's.

    **TOP-LEVEL merge, not deep.** A DNA spec's top level is scalars plus
    self-contained collections (``timeline``, ``acceptance_criteria``, ``labels``,
    ``produces``), and there is no correct generic answer for a nested list: append,
    replace, or match by index? Deep-merging mappings has the mirror problem — a
    caller could never replace a mapping wholesale, only accrete into it. Top level
    is also the granularity the frame around this write already uses: a
    ``RESTRICTED`` LayerPolicy is defined on "new TOP-LEVEL spec keys", and the
    kernel's ``field_level`` composition merge overlays per top-level field. Matching
    it means the generic write cannot express a shape the policy gate cannot reason
    about.

    ``None`` DELETES the key. Merge semantics cost the caller the ability to remove
    a field by omitting it, so removal needs a word; JSON ``null`` is unambiguous
    over every wire a face speaks, and no Kind's schema asks for a literal null
    value. It applies to ``merge=False`` too, so the two modes never disagree about
    what ``null`` means."""
    out = dict(stored) if merge else {}
    for key, value in (incoming or {}).items():
        if value is None:
            out.pop(key, None)
        else:
            out[key] = value
    return out


def _stamp_dates(
    spec: dict[str, Any], kind: str, *, now: str, existed: bool,
    caller_sent: frozenset[str],
) -> None:
    """Stamp the dated fields ``kind``'s read surfaces need — in place.

    The field list is :data:`~dna.application.sdlc.DATED_SPEC_FIELDS`, the SAME
    registry the digest reads an instance's date THROUGH and the named write paths
    are guarded against (i-078). Deriving from it rather than keeping a second list
    is the whole point: a Kind a reader learns to date is dated by this path on the
    day it is added there, and a Kind outside it gets nothing — many of those close
    their schema (``Kaizen`` is ``additionalProperties: false``), so inventing
    timestamps would be a write-time veto, not a cosmetic difference.

    Three rules, in order of who is most likely to be right:

    * a field the CALLER sent is left alone — importing an instance with its real
      dates has to stay possible; the stamp is a floor, not an override;
    * ``updated_at`` is always ``now`` — this write IS the update, so the claim is
      true by construction;
    * ``created_at`` is stamped ``now`` only on a CREATE. On an update it is
      recovered from the instance's own timeline (``backfill_created_at``) and
      otherwise left ABSENT. Falling back to ``now`` there would date a months-old
      instance as filed today, put it in the current digest window and hide it from
      the one it belongs to — a louder version of the bug this repairs. That is the
      identical rule ``plan_date_repair`` and ``set_status`` already hold.

    No timeline event is appended. The generic write has no verb — it cannot know
    whether this was a groom, a decision or a status flip, the ``type`` vocabulary
    is verb-shaped, and a Kind may declare no ``timeline`` at all. Narrating a board
    item is what ``comment`` / ``set_status`` are for; what this path owes the
    readers is the dated fields above, and what it owes the instance is to not
    destroy the timeline somebody else wrote."""
    from dna.application.sdlc import DATED_SPEC_FIELDS, backfill_created_at

    declared = DATED_SPEC_FIELDS.get(kind, ())
    if "updated_at" in declared and "updated_at" not in caller_sent:
        spec["updated_at"] = now
    if "created_at" in declared and "created_at" not in caller_sent:
        if not spec.get("created_at"):
            if existed:
                backfill_created_at(spec)  # from its own timeline, or not at all
            else:
                spec["created_at"] = now


def _write_tenant(port: Any, tenant: str | None) -> str | None:
    """The tenant to thread into ``kernel.write_instance``.

    A ``TenantScope.GLOBAL`` Kind must NOT carry one (the kernel raises
    ``TenantNotAllowed``) — for those the resolved workspace has already done
    its job by SELECTING the scope, exactly as the SDLC write core treats the
    board. Every other Kind writes into the caller's layer, so the workspace's
    change lands in its own overlay rather than the shared base."""
    if _enum_value(getattr(port, "scope", None)) == "global":
        return None
    return tenant


# ── the use-cases ───────────────────────────────────────────────────────────


async def list_kinds_impl(
    live: LiveDna, *, scope: str | None = None, tenant: str | None = None,
    families: Iterable[str] | None = None,
) -> dict[str, Any]:
    """The Kind catalog — what an agent can actually act on in this scope.

    ``families`` is the caller's unlocked feature families (a tier's
    ``feature_families``); when given, the catalog reports ONLY the Kinds whose
    family is unlocked, and says so via ``filtered_by_plan``. That is the
    deliberate answer to "every registered Kind, or only the actionable ones?":
    an inflated catalog is not generosity, it is 60 Kinds that answer 403 on the
    next call — each costing the agent a round trip and the operator a metered
    unit — so the honest, shorter list wins. ``None`` (the unmetered stdio /
    self-host path, where nothing is gated) reports everything.

    Each entry carries ``writable`` + ``write_refusal`` AND ``deletable`` +
    ``delete_refusal``, so an operation that would be refused is visible BEFORE
    it is attempted. Delete needed its own pair rather than riding on
    ``writable``: the two refusals do not coincide (an AuditLog is writable and
    never deletable) and a face that inferred one from the other would be
    guessing about the more destructive of the two.

    ``filtered_by_plan`` reports whether the catalog was actually SHORTENED, not
    whether a filter was configured. It used to be ``allowed is not None`` — true
    on every metered call, including the two shipped plans where it filters
    nothing (``family_for_kind`` only ever answers definitions / sdlc / memory,
    and Free and Pro both grant all three). A flag that is true when nothing
    happened teaches its reader to ignore it, and this one is the caller's only
    signal that the catalog it is looking at is partial. ``filtered_out`` names
    the count, so "the plan filtered nothing" and "the plan hid 40 Kinds" are
    finally different answers."""
    allowed = frozenset(families) if families is not None else None
    entries: list[dict[str, Any]] = []
    filtered_out = 0
    # i-081: the catalog answers "what can I act on HERE", so it lists the Kinds
    # that govern this scope — the globals plus this scope's own. Another
    # workspace's Kind is not actionable here and must not be advertised.
    catalog_scope = scope or live.default_scope(tenant)
    # i-090 — the catalog is an instance route too: it reads the registry
    # directly and never built a Manifest Instance, so without this it kept
    # answering "no such Kind" for a Kind that had just been approved (and kept
    # advertising one that had just been revoked). Same TTL'd seam as
    # :func:`resolve_kind_port_live`.
    await live.ensure_kinds(catalog_scope)
    for port in ports_in_scope(live.kernel, catalog_scope):
        family = family_for_kind(port)
        if allowed is not None and family not in allowed:
            filtered_out += 1
            continue
        refusal = bootstrap_write_refusal(port) if is_bootstrap_kind(port) else None
        del_refusal = delete_refusal(port)
        storage = getattr(port, "storage", None)
        entries.append({
            "kind": port.kind,
            "alias": getattr(port, "alias", None),
            "api_version": port.api_version,
            "family": family,
            "plane": getattr(port, "plane", "composition"),
            "display_label": getattr(port, "display_label", None),
            "tenant_scope": _enum_value(getattr(port, "scope", None)),
            "storage_pattern": _enum_value(getattr(storage, "pattern", None)),
            "traits": sorted(_port_traits(port)),
            "writable": refusal is None,
            "write_refusal": refusal,
            "deletable": del_refusal is None,
            "delete_refusal": del_refusal,
        })
    entries.sort(key=lambda e: (e["kind"], e["api_version"]))
    return {
        "scope": scope or live.default_scope(tenant),
        "kinds": entries,
        "count": len(entries),
        # TRUE only when the plan actually removed something (item 4).
        "filtered_by_plan": filtered_out > 0,
        "filtered_out": filtered_out,
    }


async def list_instances_impl(
    live: LiveDna, *, kind: str, scope: str | None = None,
    tenant: str | None = None, api_version: str | None = None,
    limit: int | None = None, offset: int = 0,
    fields: Iterable[str] | None = None,
    filter: dict[str, Any] | None = None,  # noqa: A002 — the kernel's own kwarg
    order_by: Iterable[str] | None = None,
) -> dict[str, Any]:
    """List the instances of one Kind in a scope (tenant-resolved), optionally
    PROJECTED, FILTERED and ORDERED.

    Names-only used to be the whole result, which made every question about a
    board cost 1 + N calls: list the 51 Issues, then read each one to find the
    open ones and discard most of what came back. ``fields`` / ``filter`` /
    ``order_by`` are handed straight to ``kernel.query`` — the SAME push-down the
    REST list surfaces use, so on Postgres the filter is a WHERE clause and the
    projection trims each row before it travels, instead of being re-implemented
    here over a full scan.

    * ``fields`` — dotted paths (``spec.title``; unprefixed resolves under
      ``spec.``, ``name`` is always included). A projected row travels as the
      kernel shaped it: ``{"name": …, "spec": {…}}``.
    * ``filter`` — field → value, ANDed; a single-key dict is an operator
      (``{"status": {"in": [...]}}``). An unknown operator raises ``QueryError``
      (a ``ValueError``) naming the valid set, rather than silently matching.
    * ``order_by`` — dotted paths, ``-`` prefix for descending.

    With no ``fields`` the result is byte-identical to before (``[{"name": …}]``),
    so every existing caller is untouched; ``projected`` echoes what was asked
    for, so a reader can tell a names-only page from a projected one.

    Pages through the kernel's own query — one extra row is fetched to answer
    ``has_more`` honestly instead of guessing from a full page. That extra row is
    only fully meaningful WITH an ``order_by``: without one, ``kernel.query``'s
    page is stable per adapter but not globally defined."""
    sc = scope or live.default_scope(tenant)
    port = await resolve_kind_port_live(live, kind, api_version, scope=sc)
    # E3: default e teto vêm da CognitivePolicy do workspace (o leitor que o
    # schema citava e nunca existiu). Sem doc, os números de sempre (50/500) —
    # paridade byte-igual. `limit=None` = "o chamador não pediu" = default da
    # política; explícito é clampado ao teto DELA.
    from dna.memory.policy import resolve_pagination
    from dna.memory.verbs import cognitive_policy_spec

    paginacao = resolve_pagination(await cognitive_policy_spec(live.kernel, sc, tenant))
    limit = (
        paginacao.default_limit
        if limit is None
        else max(1, min(int(limit), paginacao.max_limit))
    )
    offset = max(0, int(offset))
    projection = [str(f) for f in fields] if fields else None
    rows: list[dict[str, Any]] = []
    async for row in live.kernel.query(
        sc, port.kind, tenant=tenant, limit=limit + 1, offset=offset,
        projection=projection, filter=filter or None,
        order_by=[str(o) for o in order_by] if order_by else None,
    ):
        rows.append(row)
    has_more = len(rows) > limit
    page = rows[:limit]
    if projection is None:
        instances: list[dict[str, Any]] = [
            {"name": n} for n in (_row_name(r) for r in page) if n
        ]
    else:
        instances = [r for r in page if isinstance(r, dict)]
    return {
        "scope": sc,
        "kind": port.kind,
        "api_version": port.api_version,
        "instances": instances,
        "count": len(instances),
        "offset": offset,
        "has_more": has_more,
        "projected": projection,
    }


#: The standing caveat for a HEALTHY hybrid answer (i-103) — imported rather
#: than restated so the words a caller reads and the measurement that justifies
#: them cannot drift apart.
from dna.kernel.query.relevance import RANKED_NOT_FILTERED  # noqa: E402

#: The three shapes a search result can take, as ONE machine-readable word.
#: ``degraded`` alone cannot carry them: the kernel sets that single flag both
#: when there is no semantic plane at all and when there is one that just
#: failed, and the two have different remedies (install/configure a provider vs
#: look at the logs). ``None`` = nothing was lost.
SEARCH_NO_PROVIDER = "no_search_provider"
SEARCH_PROVIDER_ERROR = "search_provider_error"
SEARCH_INDEX_STALE = "index_refresh_failed"

#: What each degradation COSTS the caller, in words the caller will act on.
#: The sentence exists because ``degraded: true`` beside an empty ``hits`` is
#: read by both humans and models as *"I searched and there is nothing"* — the
#: exact fabrication `indisponível ≠ zero` names. Every one of them therefore
#: ends by saying what the empty list may NOT be taken to mean; the caller sees
#: the caveat in the same breath as the result, not in a doc it did not open.
_SEARCH_NOTICE: dict[str, str] = {
    SEARCH_NO_PROVIDER: (
        "No embedding/search provider is registered on this deployment, so "
        "similarity search did not run. What ran instead is an honest LEXICAL "
        "token-match scan: it finds instances that repeat the words of the "
        "query and CANNOT find one that says the same thing in other words. "
        "A short or empty result here is NOT evidence that nothing similar "
        "exists — it is evidence that this deployment cannot tell."
    ),
    SEARCH_PROVIDER_ERROR: (
        "The search provider is registered but FAILED on this call, so "
        "similarity search did not run and an honest lexical token-match scan "
        "answered in its place. A short or empty result here is NOT evidence "
        "that nothing similar exists — the semantic plane never answered."
    ),
    SEARCH_INDEX_STALE: (
        "The search index could not be refreshed before this query, so any "
        "instance written since the last successful refresh is invisible to "
        "it. These results are NOT read-your-writes, and an absent instance "
        "may simply be an unindexed one."
    ),
}


async def search_instances_impl(
    live: LiveDna, *, kind: str, query: str, scope: str | None = None,
    tenant: str | None = None, api_version: str | None = None, k: int = 10,
    min_similarity: float | None = None, name_prefix: str | None = None,
) -> dict[str, Any]:
    """Find the instances of one Kind that RESEMBLE ``query`` — similarity, not
    enumeration.

    The capacity was already built and already wired: ``kernel.search()`` routes
    to the registered ``RecordSearchProvider`` (``adapters/search/pgvector.py``
    or ``sqlite_vec.py`` — dense pgvector/vec0 + a lexical plane, fused by the
    shared ``rrf.reciprocal_rank_fusion``) and degrades to an in-memory lexical
    scan when there is none. Nothing about ranking, fusion or embedding is
    implemented here and nothing may be: this is the DOOR onto that engine for
    an arbitrary Kind, which is the only piece that was missing (`s-porta-de-busca`).
    ``list_instances`` answers *"what is there"* and is the only thing a creator
    asking *"does something like this already exist?"* had — enumeration works at
    six Kinds and does not at six hundred, which is exactly what tenant Kind
    authoring produces.

    ONE Kind per call, deliberately. The Kind is what decides the metering family
    (:func:`family_for_kind`), so a multi-Kind search would be the cheap door into
    a family the caller's plan gates — the same reason ``list_instances`` takes one.

    **The index is refreshed first**, for the target Kind, through the same
    :func:`dna.memory.backfill_index` ``recall`` uses (idempotent by text hash —
    unchanged instances are not re-embedded). Without it the provider-backed
    plane would answer confidently out of an index nothing but the memory verbs
    ever wrote to, and a Kind nobody had recalled would come back empty while its
    instances sat in the store. A refresh FAILURE is not swallowed: it degrades
    the answer and says so.

    Returns ``{scope, kind, api_version, query, hits, count, mode, degraded,
    degraded_reason, notice, relevance_notice, min_similarity, floored_out,
    index_refreshed, index_error?}``.

    ``mode`` is ``hybrid`` (dense + lexical + RRF) or ``lexical``, and it is the
    field that makes the two EMPTIES different results rather than the same one:

    * ``mode: "hybrid"``, ``degraded: false``, ``hits: []`` — the semantic plane
      ran and found nothing. *This* one may be read as "nothing similar exists".
    * ``degraded: true`` with a ``degraded_reason`` and a ``notice`` — something
      did not run. The empty list is a BLIND SPOT, and the notice says so in
      words, because an empty list beside a bare boolean is read as an answer by
      every caller that does not already know better.

    ⭐ **i-103 — the other half of that honesty, which was missing.** The three
    fields above all describe FAILURE; when everything worked the envelope said
    nothing at all, and a NON-EMPTY result on the healthy path was therefore
    read as "yes, something like this exists". It is not: RRF orders by RANK,
    rank exists over noise, and the top hit is the least dissimilar instance in
    the Kind rather than a similar one. Measured against the real corpus, a
    query about *"a report service in ruby"* returned an MCP door with
    ``degraded: false``, and one about the tax-filing deadline outscored ten of
    twelve genuine matches. Two additions close it, and neither touches the
    three fields above (a live consumer branches on those, and widening them to
    also mean "this ran fine, read carefully" would make the honest signal
    ambiguous):

    * ``relevance_notice`` — the standing caveat on a HEALTHY hybrid answer,
      in prose, in the same breath as the hits. ``None`` when there is nothing
      to caveat (no hits, or a degraded answer whose ``notice`` already speaks).
    * ``min_similarity`` / ``floored_out`` — the caller's own floor over the raw
      cosine, echoed, plus how many hits it removed. A filter that silently
      shortens a list teaches its reader the corpus is smaller than it is.

    ⚠️ No DEFAULT floor is shipped, here or anywhere, and that is a measurement
    and not an omission: relevant and irrelevant queries OVERLAP on raw cosine
    (0.35–0.63 vs 0.16–0.53), on corpus z-score and on top-1 margin — the last
    two overlap completely. :mod:`dna.kernel.query.relevance` carries the
    numbers and names the cross-encoder reranker as the real remedy.

    Hits carry the port's guaranteed ``{scope, kind, name, score}``; a
    provider-backed hit may also carry ``title`` / ``snippet`` / ``rank_dense`` /
    ``rank_lexical`` and — since i-103 — ``similarity`` (cosine against the
    query, dense plane) and ``lexical_score`` (token-overlap strength, higher is
    better on both stores). All optional by contract; never depend on them.
    ``score`` remains the FUSED RRF value, which is a function of rank alone.
    """
    sc = scope or live.default_scope(tenant)
    port = await resolve_kind_port_live(live, kind, api_version, scope=sc)
    k = max(1, min(int(k), 100))

    # Refresh THIS Kind's slice of the index — same seam, same idempotence, as
    # the one `recall_impl` runs before every recall. Reused rather than
    # re-derived: `backfill_index` already takes the Kinds to walk, and its
    # default (the memory Kinds) is the only thing that made it look memory-only.
    index_refreshed = False
    index_error: str | None = None
    provider = getattr(live.kernel, "search_provider", None)
    if provider is not None:
        from dna.memory import backfill_index

        try:
            await backfill_index(
                live.kernel, sc, kinds=[port.kind], tenant=tenant,
            )
            index_refreshed = True
        except Exception as exc:  # noqa: BLE001 — a read never breaks on this
            index_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "search_instances: index refresh failed for %s/%s (tenant=%s): %s",
                sc, port.kind, tenant, index_error,
            )

    # The tenant travels EXPLICITLY. `kernel.search` would otherwise fall back to
    # the kernel's own binding, and a door that let a caller's scope decide whose
    # overlay it reads is the one leak this surface must not have: the provider
    # filters `row_tenant in ("", tenant)`, so the value passed here IS the
    # isolation boundary.
    res = await live.kernel.search(
        sc, query, kind=port.kind, k=k, tenant=tenant,
        min_similarity=min_similarity, name_prefix=name_prefix,
    )
    hits = list(res.get("hits") or [])
    degraded = bool(res.get("degraded"))

    reason: str | None = None
    if degraded:
        # The kernel collapses both into one flag; separate them here, where the
        # provider is still in hand. Order matters: no provider at all is the
        # deployment's shape, a failure is an incident.
        reason = SEARCH_NO_PROVIDER if provider is None else SEARCH_PROVIDER_ERROR
    elif index_error is not None:
        # The semantic plane answered, but out of an index that may be missing
        # the caller's own last write. Degraded, because that is what it is.
        degraded = True
        reason = SEARCH_INDEX_STALE

    out: dict[str, Any] = {
        "scope": sc,
        "kind": port.kind,
        "api_version": port.api_version,
        "query": query,
        "hits": hits,
        "count": len(hits),
        "mode": "lexical" if res.get("degraded") else "hybrid",
        "degraded": degraded,
        "degraded_reason": reason,
        "notice": _SEARCH_NOTICE.get(reason) if reason else None,
        # i-103 — the caveat for the case that used to be silent: hits came
        # back and nothing failed. Only on the HEALTHY hybrid path with actual
        # hits: an empty result needs no warning against over-reading it, and a
        # degraded one already carries a louder `notice` that must stay the
        # thing the reader acts on.
        "relevance_notice": (
            RANKED_NOT_FILTERED
            if (hits and not degraded and not res.get("degraded"))
            else None
        ),
        # Echoed so a reader of the RESULT can tell a filtered answer from an
        # unfiltered one without re-reading its own request, and can tell "the
        # floor removed nothing" from "no floor ran".
        "min_similarity": min_similarity,
        "floored_out": int(res.get("floored_out") or 0),
        "index_refreshed": index_refreshed,
    }
    if index_error is not None:
        out["index_error"] = index_error
    return out


async def resolve_instance_impl(
    live: LiveDna, *, id: str, scope: str | None = None,
    tenant: str | None = None,
) -> dict[str, Any]:
    """Expand a short ``metadata.id`` prefix and return the instance it names
    (i-114) — the ONE door where an id, rather than a name, is the address.

    Kept as a SEPARATE surface instead of teaching ``get_instance`` to accept
    "a name, or maybe an id". That overload is where this design would rot: a
    short name and a short id are both strings, so a lookup that tried both
    would eventually answer a name query with an id match, and nobody would see
    it happen. Two lanes, each with one meaning — the same separation the whole
    feature rests on.

    ``scope`` narrows the search and is normally unnecessary: ids are unique
    across the store, and not having to know the scope is most of what an id
    buys. It exists for a caller who wants the refusal scoped too.
    """
    ref = await live.kernel.resolve_instance_id(id, scope=scope, tenant=tenant)
    raw = await live.kernel.get_instance(
        ref.scope, ref.kind, ref.name, tenant=ref.tenant or tenant,
    )
    if raw is None:
        # The id index and the instance disagree — a torn write, or a delete
        # that left the row behind. Say exactly that; answering "unknown id"
        # would send the caller hunting for a typo that is not there.
        raise LookupError(
            f"instance id {ref.id!r} resolves to {ref.kind} {ref.name!r} in "
            f"scope {ref.scope!r}, but that instance could not be read"
        )
    return {
        "id": ref.id, "scope": ref.scope, "kind": ref.kind,
        "api_version": ref.api_version, "name": ref.name,
        "instance": raw,
        "etag": spec_etag(raw.get("spec") if isinstance(raw, dict) else None),
    }


async def get_instance_impl(
    live: LiveDna, *, kind: str, name: str, scope: str | None = None,
    tenant: str | None = None, api_version: str | None = None,
    as_of: str | None = None,
    valid_at: str | None = None,
) -> dict[str, Any]:
    """Read one instance verbatim, as the caller's layer sees it.

    **``as_of`` (ISO-8601) reads the BELIEF STATE** — the instance as this store
    RECORDED it at or before that instant (transaction time,
    ``dna_versions.created_at``), not as it stands now. The same second time axis
    ``recall`` and ``list_memories`` already carry, generalised to every Kind:
    :func:`~dna.memory.as_of.resolve_as_of` was always keyed on
    ``(scope, kind, name)`` and the adapter's ``load_one_as_of`` never knew
    ``Engram`` from anything else — only memory had a door to it.

    i-106 is why this is a parameter and not a wish: the REST route ACCEPTED
    ``?as_of=`` and ignored it, because FastAPI drops an undeclared query param
    in silence. A caller asking what an instance looked like yesterday got today's
    instance under a 200, with nothing in the response to say otherwise — the
    failure mode the whole ``as_of`` module exists to refuse. The three refusals
    below are the point; the read is the easy half.

    * a store with no version history → :class:`~dna.memory.as_of.AsOfUnsupported`
    * history pruned past ``as_of`` → :class:`~dna.memory.as_of.AsOfTruncated`
    * the instance did not exist yet → ``LookupError``, which is an ANSWER and
      deliberately the SAME exception "no such instance" already raises: at
      ``as_of`` those two ARE the same statement (nothing was there), while
      "pruned" is not, and only the pruned case gets its own type.

    **``valid_at`` (ISO-8601) reads the OTHER axis** — WORLD time: *was the fact
    this instance states TRUE at that instant?*, from ``dna_instances.valid_at``
    (a ``tstzrange``, revision 0010). It is a different question from ``as_of``
    and the two are separate parameters for that reason alone: a note written
    today about last year is **valid** last year and **believed** today, so
    ``valid_at=<last year>`` finds it and ``as_of=<last year>`` must not.
    Confusing the two is the classic bitemporal mistake, and a single parameter
    serving both would make it unavoidable.

    Three outcomes, and the middle one is the whole reason this is a parameter:

    * inside the window → the instance, plus ``valid_at`` echoed so a world-time
      read is never mistaken for a live one;
    * outside it → ``LookupError``, an ANSWER — the instance exists and was not
      true then;
    * a store with no world-time column →
      :class:`~dna.kernel.valid_time.ValidTimeUnsupported` (501). Never the
      instance unfiltered, which would assert *"yes, it was true then"* on no
      evidence at all.

    ⚠️ ``as_of`` and ``valid_at`` together are REFUSED as a ``ValueError``, and
    that is a named gap rather than an oversight. The genuine bitemporal read —
    *what did this store believe at T1 about what was true at T2* — needs the
    validity window on the VERSION rows, and ``dna_versions`` does not carry
    one. Serving whichever axis happened to be checked first would answer a
    question nobody asked, in the shape of one they did.

    ``etag`` is computed over whatever spec is returned, so a follow-up write
    carrying a historical etag as ``if_match`` refuses as stale instead of
    quietly rewinding the instance.
    """
    from dna.memory.as_of import (
        AsOfTruncated, AsOfUnsupported, normalize_as_of, resolve_as_of,
        store_supports_as_of,
    )

    sc = scope or live.default_scope(tenant)
    port = await resolve_kind_port_live(live, kind, api_version, scope=sc)
    if valid_at is not None:
        return await _get_instance_valid_at(
            live, scope=sc, port=port, name=name, tenant=tenant,
            valid_at=valid_at, as_of=as_of,
        )
    if as_of is None:
        raw = await live.kernel.get_instance(sc, port.kind, name, tenant=tenant)
        if raw is None:
            raise LookupError(f"no {port.kind} named {name!r} in scope {sc!r}")
        return {
            "scope": sc, "kind": port.kind, "api_version": port.api_version,
            "name": name, "instance": raw,
            # The optimistic-concurrency token for a follow-up write (see
            # :func:`spec_etag`): pass it back as ``write_instance``'s ``if_match``
            # and a lost update becomes a refusal instead of a silent overwrite.
            "etag": spec_etag(raw.get("spec") if isinstance(raw, dict) else None),
        }

    as_of_iso = normalize_as_of(as_of)  # ValueError on a non-ISO-8601 instant
    if not store_supports_as_of(live.kernel):
        raise AsOfUnsupported(
            f"get_instance(as_of=...) needs a store that retains version history "
            f"with a transaction timestamp; this deployment's source does not. "
            f"Refusing rather than returning the CURRENT state of {port.kind} "
            f"{name!r} under a past timestamp."
        )
    res = await resolve_as_of(
        live.kernel, sc, port.kind, name,
        as_of=as_of_iso, tenant=tenant, api_version=port.api_version,
    )
    if res.truncated:
        raise AsOfTruncated(
            f"{port.kind} {name!r} in scope {sc!r} HAS history, but none of it "
            f"reaches back to {as_of_iso} — the versions that old were pruned. "
            f"What this store believed then is not knowable; it is not 'the "
            f"instance did not exist'."
        )
    if not res.found:
        raise LookupError(
            f"no {port.kind} named {name!r} in scope {sc!r} at {as_of_iso} — "
            f"nothing was recorded under that name at or before that instant."
        )
    return {
        "scope": sc, "kind": port.kind, "api_version": port.api_version,
        "name": name, "instance": res.raw,
        "etag": spec_etag(
            res.raw.get("spec") if isinstance(res.raw, dict) else None
        ),
        # The three fields that keep an as-of read from being mistaken for a
        # live one by a caller that only looks at ``instance``.
        "as_of": as_of_iso,
        "as_of_version": res.version,
        "as_of_recorded_at": res.recorded_at,
    }


async def _get_instance_valid_at(
    live: LiveDna, *, scope: str, port: Any, name: str,
    tenant: str | None, valid_at: str, as_of: str | None,
) -> dict[str, Any]:
    """The WORLD-time branch of :func:`get_instance_impl`.

    Its own function rather than another arm inside the caller, because the two
    axes share nothing but the address they resolve: different column, different
    adapter method, different refusal, different echoed fields. Interleaving
    them is how a later edit ends up applying one filter and reporting the
    other.
    """
    from dna.kernel.valid_time import (
        ValidTimeUnsupported, normalize_valid_at, store_supports_valid_time,
    )

    if as_of is not None:
        # BEFORE the capability check, and before the store is touched: this is
        # a statement about what this face implements, not about the deployment,
        # so it must not arrive dressed as a 501 the caller could fix by
        # switching adapters.
        raise ValueError(
            "as_of and valid_at ask about DIFFERENT time axes and cannot be "
            "combined on this read: as_of is transaction time (what this store "
            "believed at T, from dna_versions), valid_at is world time (when the "
            "fact was true, from dna_instances.valid_at). The bitemporal "
            "intersection would need the validity window on the version rows, "
            "which dna_versions does not carry. Ask one axis at a time."
        )
    # ValueError on a typo, BEFORE the capability is consulted — a bad instant
    # is the caller's mistake and has a different remedy from a store that
    # cannot answer at all.
    instant = normalize_valid_at(valid_at)
    if not store_supports_valid_time(live.kernel):
        raise ValidTimeUnsupported(
            f"get_instance(valid_at=...) needs a store that keeps the validity "
            f"window as a column (dna_instances.valid_at); this deployment's "
            f"source does not. Refusing rather than returning {port.kind} "
            f"{name!r} unfiltered, which would assert it was true at "
            f"{instant.isoformat()} on no evidence."
        )
    raw = await live.kernel._source.load_one_valid_at(
        scope, port.kind, name,
        valid_at=instant, tenant=tenant, api_version=port.api_version,
    )
    if raw is None:
        # An ANSWER, not a refusal, and worded so the two cannot be confused:
        # the store HAS the column, looked, and the window does not contain the
        # instant. ``ValidTimeUnsupported`` above is the other statement.
        raise LookupError(
            f"no {port.kind} named {name!r} in scope {scope!r} was valid at "
            f"{instant.isoformat()} — either it does not exist, or its declared "
            f"validity window does not contain that instant."
        )
    return {
        "scope": scope, "kind": port.kind, "api_version": port.api_version,
        "name": name, "instance": raw,
        "etag": spec_etag(raw.get("spec") if isinstance(raw, dict) else None),
        # Echoed for the same reason ``as_of`` is: a caller that only looks at
        # ``instance`` must still be able to tell this from a live read.
        "valid_at": instant.isoformat(),
    }


async def graph_refs_impl(
    live: LiveDna, *, kind: str, name: str, scope: str | None = None,
    tenant: str | None = None, api_version: str | None = None,
    direction: str = "in", depth: int | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """"What points at this instance?" — the DERIVED reference graph.

    The read the product question needed and that nothing could answer: the
    Kind screen has always been able to say ``Story.feature → Feature`` exists
    as a RULE, and never that THESE forty-seven Stories point at THIS Feature.

    Three things travel with the answer, none of them decoration:

    * ``resolved`` per edge — ``false`` is a reference that points at nothing.
      Listed, never filtered: with ``DNA_REF_VALIDATION=warn`` (the default)
      such instances persist, and a graph that hid the broken half would read
      as healthier than the data is. It answers about NOW, not about the write
      (i-131): an edge whose target has since been deleted says ``false``, and
      ``to_deleted_at`` says WHEN — the difference between "this was never
      written" and "a delete took this out from under a live reference", which
      are different repairs.
    * ``stop`` — ``complete`` / ``depth_reached`` / ``truncated``. A caller
      that cannot tell "this is everything" from "this is where I stopped"
      renders the second as the first.
    * ``graph_producer`` — ``warn`` / ``enforce`` / ``off``. With the producer
      ``off`` no edges are made at all; that is a defensible operational
      choice, and a screen rendering the resulting emptiness as "no relations"
      is not.

    Raises :class:`~dna.kernel.query.graph.GraphUnsupported` on a store that
    keeps no edges — deliberately, rather than an empty list that would read as
    "nothing points at this instance".

    **``as_of`` (ISO-8601) walks the graph AS IT WAS at that transaction
    instant** — the fourth coordinate of the same question, and the same axis
    :func:`get_instance_impl` already carries for one instance
    (``dna_versions.created_at``: *what did this store BELIEVE at T*). It is
    re-derived from the versions' specs rather than filtered out of
    ``dna_edges``, because that table is replaced on every write and holds no
    history — see ``dna.kernel.query.graph`` for the measurement.

    Two fields travel with a historical answer, and neither is decoration:

    * ``as_of`` echoed — a caller that only reads ``edges`` must still be able
      to tell a past answer from a present one. Exactly why
      :func:`get_instance_impl` echoes its own.
    * ``as_of_truncated`` — ``Kind/name`` for every node the walk REACHED and
      could not read that far back (history pruned). Reported, never dropped:
      omitting them would let a reader conclude "nothing pointed at this" out
      of "we cannot know what these said". The ANCHOR being unreadable is a
      refusal instead (:class:`~dna.memory.as_of.AsOfTruncated`, 410), because
      a single-anchor read either answers or says it cannot.

    ⚠️ ``as_of`` and ``valid_at`` are DIFFERENT axes and this surface carries
    only the first, for the same named reason ``get_instance(as_of=,
    valid_at=)`` together is refused: the bitemporal intersection needs the
    validity window on the VERSION rows, and ``dna_versions`` has none.
    """
    sc = scope or live.default_scope(tenant)
    port = await resolve_kind_port_live(live, kind, api_version, scope=sc)
    as_of_iso = None
    if as_of is not None:
        from dna.memory.as_of import normalize_as_of  # noqa: PLC0415

        # ValueError on a non-ISO-8601 instant, BEFORE the store is touched —
        # the same normalization ``get_instance_impl`` applies, so the two
        # surfaces cannot disagree about what "2026-08-06" means.
        as_of_iso = normalize_as_of(as_of)
    result = await live.kernel.graph_refs(
        sc, port.kind, name,
        tenant=tenant, direction=direction, depth=depth, as_of=as_of_iso,
    )
    return {
        "scope": sc, "kind": port.kind, "api_version": port.api_version,
        "name": name,
        "direction": result.direction, "depth": result.depth,
        "stop": result.stop, "graph_producer": result.graph_producer,
        "as_of": result.as_of,
        "as_of_truncated": list(result.as_of_truncated),
        "edges": [
            {
                "depth": e["depth"], "direction": e["direction"],
                # i-110.3 — the apiVersion of BOTH ends. Without them a reader
                # holding two rows that say ``to_kind: "Reference"`` cannot
                # tell whether they mean the same Kind, and the answer used to
                # be "trust the registry's collision guard, in another module,
                # which has an exception list".
                "from_api_version": e.get("from_api_version"),
                "from_kind": e["from_kind"], "from_name": e["from_name"],
                "field": e["source_field"], "ordinal": e["ordinal"],
                "to_api_version": e.get("to_api_version"),
                "to_kind": e["to_kind"], "to_name": e["to_name"],
                "to_scope": e["to_scope"],
                # i-114 — name AND id on the derived edge. The face reports
                # both because they answer different questions: the name is
                # what the author wrote, the id is which instance it hit.
                "to_id": e.get("to_id"),
                "declared_to": list(e["declared_to"]),
                "resolved": e["resolved"],
                # i-131 — WHY it is unresolved, when it is. ``resolved: false``
                # alone conflates two states with different repairs: a
                # reference that NEVER found a target (a typo, or a target
                # nobody wrote) and one that found it and was then orphaned by
                # a delete. NULL here with ``resolved: false`` is the first; a
                # timestamp is the second, and it says when.
                "to_deleted_at": e.get("to_deleted_at"),
                "closes_cycle": e["closes_cycle"],
                "from_version": e["from_version"],
            }
            for e in result.edges
        ],
    }


async def write_instance_impl(
    live: LiveDna, *, kind: str, name: str, spec: dict[str, Any],
    scope: str | None = None, tenant: str | None = None,
    api_version: str | None = None, merge: bool = True,
    if_match: str | None = None, now: str | None = None,
    source_sha256: str | None = None,
) -> dict[str, Any]:
    """Create or UPDATE one instance — read-modify-merge, through
    ``kernel.write_instance``.

    Nothing about the write path is re-implemented here: schema validation, the
    LayerPolicy gate (Kind-level and the ``OVERLAYABLE_FIELDS`` per-field
    allowlist), reference validation, the ``pre_save`` veto hook and the
    invalidation fan-out are the kernel's, exactly as for the hand-written
    tools. This use-case adds the three things the kernel cannot know:

    **1. the caller is a GENERIC write-any-instance tool**, so the bootstrap
    Kinds are refused (:class:`BootstrapKindWriteRefused`).

    **2. an update is an update.** This path used to build the instance from
    scratch and hand it over, which made every write a REPLACE: updating one
    field of a Story erased its ``timeline`` (append-only history), its status and
    its parent Feature unless the caller re-sent all of them. It now reads the
    stored instance first and merges the caller's ``spec`` over it at the TOP
    LEVEL (:func:`_merged_spec` — which also instances why not deep, and how an
    explicit ``None`` clears a field). ``merge=False`` is the old behavior, kept
    reachable but only by name: it REPLACES the spec and drops anything the caller
    did not send.

    **3. the read surfaces need the instance dated.** :func:`_stamp_dates` stamps
    exactly what :data:`~dna.application.sdlc.DATED_SPEC_FIELDS` declares for the
    target Kind — the same registry ``sdlc_digest`` reads an instance's date
    through — so an ADR / Kaizen / Spike filed here is visible to the digest
    instead of permanently missing from every window (i-078, one write path
    later). It never forges a ``created_at`` onto an older instance.

    ``if_match`` (OPTIONAL) is the ``etag`` from :func:`get_instance_impl`: when
    given, the write proceeds only if the stored spec still hashes to it, else
    :class:`ConcurrentWriteError`. Opt-in rather than mandatory, deliberately —
    a CREATE has nothing to match, MCP tool calls are stateless (an agent that
    never read the instance has no token to send), and making it mandatory would
    turn every first write into a two-call dance. What makes the default safe is
    (2): without a token, concurrent writers no longer clobber each other's whole
    instance, only the individual fields both of them sent. A caller that cannot
    tolerate even that reads first and passes the etag — and gets the next one
    back from this call, so a chain of updates costs no extra reads.

    The ``apiVersion`` is taken from the resolved port, never from the caller:
    an agent cannot smuggle an instance into a different Kind's namespace.

    ``source_sha256`` (OPTIONAL) closes the PROVENANCE edge from the write
    side: when given, it must name an already-registered ``SourceArtifact``
    (``POST /v1/artifacts`` — content-addressed as ``sha256-<hex>``) under
    ``tenant``, and this instance is appended to that artifact's
    ``derived_refs`` — the SAME field :func:`~dna.application.runtime.
    register_artifact_impl` initializes and preserves on the artifact's own
    side. Idempotent per ``(kind, name)``: re-writing the SAME instance
    updates its own entry (a fresh ``extracted_at``) instead of appending a
    duplicate, and every OTHER instance's entry is left untouched — the
    write-side twin of the "a re-registration preserves ``derived_refs``"
    property the artifact route already holds. Raises :class:`ValueError` when
    the cited artifact does not exist under ``tenant`` (a caller cannot cite
    what it has not registered), or when ``tenant`` is absent (there is no
    workspace to resolve the artifact under)."""
    from dna.application.sdlc import now_iso

    sc = scope or live.default_scope(tenant)
    port = await resolve_kind_port_live(live, kind, api_version, scope=sc)
    if is_bootstrap_kind(port):
        raise BootstrapKindWriteRefused(bootstrap_write_refusal(port))
    # Read at the coordinates the write will act on — ``write_tenant``, not the
    # caller's ``tenant`` (i-088, the same family as the delete path below).
    # The two differ only for a GLOBAL Kind, where ``_write_tenant`` returns
    # None; this never broke, and the measurement of WHY is in
    # ``test_delete_document_tenant_coordinates.py``: a GLOBAL Kind can have no
    # tenant row at all (the write pipeline raises ``TenantNotAllowed`` for any
    # effective tenant), and ``get_instance(tenant=X)`` falls back to the base
    # layer, so both readings returned byte-identical instances on every store.
    # It is aligned anyway because the equality is a property of TODAY's
    # declarations, not of this code: a Kind whose declared scope changes from
    # tenanted to GLOBAL leaves real overlay rows behind, and the old reading
    # would have merged one into the shared base that every tenant inherits.
    write_tenant = _write_tenant(port, tenant)
    existing = await live.kernel.get_instance(
        sc, port.kind, name, tenant=write_tenant)
    stored = (
        dict(existing.get("spec") or {})
        if isinstance(existing, dict) and isinstance(existing.get("spec"), dict)
        else {}
    )
    if if_match is not None:
        if existing is None:
            raise ConcurrentWriteError(
                f"if_match={if_match!r} was given but no {port.kind} named "
                f"{name!r} exists in scope {sc!r} — if_match asserts you are "
                f"updating an instance you read; the instance was deleted, or the "
                f"name is wrong. Re-read it, or drop if_match to create."
            )
        current = spec_etag(stored)
        if current != if_match:
            raise ConcurrentWriteError(
                f"{port.kind} {name!r} in scope {sc!r} changed since you read it "
                f"(if_match={if_match!r}, now {current!r}) — refusing so your "
                f"update does not overwrite somebody else's. Re-read the instance "
                f"with get_instance and re-apply your change to the fresh etag."
            )

    new_spec = _merged_spec(stored, dict(spec or {}), merge=merge)
    _stamp_dates(
        new_spec, port.kind, now=now or now_iso(), existed=existing is not None,
        caller_sent=frozenset(spec or {}),
    )
    raw = {
        "apiVersion": port.api_version,
        "kind": port.kind,
        "metadata": {"name": name},
        "spec": new_spec,
    }
    version = await live.kernel.write_instance(
        sc, port.kind, name, raw, tenant=write_tenant,
    )
    if source_sha256:
        await _link_source_artifact(
            live, scope=sc, tenant=tenant, sha256=source_sha256,
            derived_kind=port.kind, derived_name=name,
            now=now or now_iso(),
        )
    return {
        "scope": sc, "kind": port.kind, "api_version": port.api_version,
        "name": name, "version": version, "tenant": write_tenant,
        "created": existing is None,
        "merged": bool(merge) and existing is not None,
        # Chain this into the next write's ``if_match`` — no re-read needed.
        "etag": spec_etag(new_spec),
        "source_sha256": source_sha256,
    }


async def _link_source_artifact(
    live: LiveDna, *, scope: str, tenant: str | None, sha256: str,
    derived_kind: str, derived_name: str, now: str,
) -> None:
    """Append ``{kind, name, scope, extracted_at}`` to the cited
    ``SourceArtifact``'s ``derived_refs`` — the write side of the provenance
    edge :func:`~dna.application.runtime.register_artifact_impl` already reads
    and preserves on the artifact's own side (see :func:`write_instance_impl`).

    ``tenant`` is the WORKSPACE the artifact was registered under (the same
    coordinate :func:`~dna.application.runtime.register_artifact_impl` binds
    to) — never the derived instance's own ``write_tenant``, which can differ
    for a GLOBAL Kind. A ``SourceArtifact`` is always tenanted, so a caller
    with no workspace has nothing to cite here.
    """
    from dna.application.runtime import artifact_name

    if not tenant:
        raise ValueError(
            "source_sha256 was given but there is no tenant/workspace to "
            "resolve a SourceArtifact under — register the artifact under a "
            "workspace first (POST /v1/artifacts), then cite it from one."
        )
    digest = (sha256 or "").strip().lower()
    art_name = artifact_name(digest)
    existing = await live.kernel.get_instance(
        scope, "SourceArtifact", art_name, tenant=tenant)
    if not isinstance(existing, dict):
        raise ValueError(
            f"source_sha256 {digest!r} cites no SourceArtifact registered "
            f"under workspace {tenant!r} in scope {scope!r} — register it "
            f"first via POST /v1/artifacts, then cite it from this write."
        )
    art_spec = dict(existing.get("spec") or {})
    refs = [
        r for r in (art_spec.get("derived_refs") or []) if isinstance(r, dict)
    ]
    # Idempotent per (kind, name): drop any PRIOR entry for this SAME derived
    # instance before appending the fresh one, so a re-write updates in place
    # rather than accreting a duplicate. Every OTHER instance's entry is left
    # exactly as it was — the "preserve, don't erase" property.
    refs = [
        r for r in refs
        if not (r.get("kind") == derived_kind and r.get("name") == derived_name)
    ]
    refs.append({
        "kind": derived_kind, "name": derived_name, "scope": scope,
        "extracted_at": now,
    })
    art_spec["derived_refs"] = refs
    write_kernel = live.kernel.with_tenant(tenant)
    await write_kernel.write_instance(
        scope, "SourceArtifact", art_name,
        {
            "apiVersion": existing.get("apiVersion"),
            "kind": "SourceArtifact",
            "metadata": {"name": art_name},
            "spec": art_spec,
        },
        invalidate_mode="doc",
    )


async def delete_instance_impl(
    live: LiveDna, *, kind: str, name: str, api_version: str,
    scope: str | None = None, tenant: str | None = None,
    if_match: str | None = None,
) -> dict[str, Any]:
    """Delete one instance — the generic delete the faces were missing.

    ``kernel.delete_instance`` has always existed; REST reaches it through four
    narrow routes and ``dna instance delete`` uses it, but the MCP face had NO delete
    at all. An agent that could create and update every Kind could remove
    nothing, so the only way to undo a mistaken write was a human with database
    access. This is the same operation, through the same guards.

    Refuses per :func:`delete_refusal` — bootstrap Kinds and append-only records
    — and the refusal is REPORTED in ``list_kinds`` (``deletable`` /
    ``delete_refusal``) so it is visible before it is attempted rather than
    discovered by being denied.

    ``if_match`` is the same optimistic-concurrency guard the generic write
    takes, and it matters more here: a write that races loses one edit, a delete
    that races destroys an instance its author never saw. It is OPTIONAL rather
    than required because a caller that has just read the instance to decide it
    should go can pass the etag, while one deleting by name (a cleanup script)
    genuinely has nothing to match on — requiring it would only push that caller
    into an extra read whose result it ignores.

    ``api_version`` is REQUIRED, unlike the write path where it can be inferred
    from the instance. A delete carries no instance, and a bare Kind name can
    resolve to two ports once two workspaces each declare a `Deal` in their own
    namespace — so the caller states which Kind it means, and the pin travels
    all the way down to the adapter (:meth:`WritableSourcePort.delete_instance`).
    """
    sc = scope or live.default_scope(tenant)
    port = await resolve_kind_port_live(live, kind, api_version, scope=sc)
    refusal = delete_refusal(port)
    if refusal is not None:
        raise DeleteRefused(refusal)
    write_tenant = _write_tenant(port, tenant)
    # THE SAME COORDINATES THE DELETE WILL ACT ON (i-088). This check used to
    # read with no tenant while the delete below targeted ``write_tenant``, and
    # the write that created the row had used ``write_tenant`` too. ``tenant``
    # participates in the lookup key of every store — it is in the WHERE clause
    # of both SQL dialects (and in the Postgres primary key), and it selects the
    # overlay directory on the filesystem — so a tenant's instance was reported
    # as "not found" by the one operation that could remove it, while write,
    # list and get all resolved it perfectly. An existence check asked at other
    # coordinates is a check of a different question; its answer says nothing
    # about the operation that follows it.
    existing = await live.kernel.get_instance(
        sc, port.kind, name, tenant=write_tenant)
    if existing is None:
        raise UnknownInstanceError(
            f"{port.kind} {name!r} not found in scope {sc!r} — nothing to delete"
        )
    if if_match is not None:
        current = spec_etag((existing.get("spec") or {}) if isinstance(existing, dict) else {})
        if current != if_match:
            raise ConcurrentWriteError(
                f"if_match {if_match!r} does not match the stored instance "
                f"(etag {current!r}): {port.kind} {name!r} changed since you read "
                f"it. Re-read it and decide again — a delete that races destroys "
                f"an edit its author never saw."
            )
    await live.kernel.delete_instance(
        sc, port.kind, name, tenant=write_tenant,
        api_version=port.api_version, invalidate_mode="doc",
    )
    return {
        "scope": sc, "kind": port.kind, "api_version": port.api_version,
        "name": name, "tenant": write_tenant, "deleted": True,
    }
