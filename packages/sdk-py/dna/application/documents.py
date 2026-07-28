"""``dna.application.documents`` — GENERIC, registry-driven document use-cases.

The gap this closes: every serving face DNA ships enumerated its capabilities by
hand. The MCP face has 21 hand-written tools and no loop over the Kind registry,
so 85% of its lines name one specific Kind — and a Kind that exists (including
the ones declared purely by a ``*.kind.yaml`` descriptor) is invisible to an
agent unless somebody writes tools for it. The generic path is not missing: the
CLI's ``dna doc`` has served every Kind in-process for a long time
(``dna_cli._ctx._LocalDocs``). It was simply never *served*.

These four use-cases are that generic path, transport-agnostic, resolved from
the kernel's :class:`~dna.kernel.kinds.registry.KindRegistry` **at call time**:

    list_kinds_impl      — the Kind catalog (what can I act on here?)
    list_documents_impl  — the documents of one Kind in a scope
    get_document_impl    — one document, verbatim
    write_document_impl  — create/update one document

They live in the CORE (``adr-faces-reorg`` move #1) so a face is a thin adapter
and every face inherits the same rules — most importantly the two refusals
below, which would be a hole the moment a second face re-implemented them.

**Refusal 1 — bootstrap Kinds are never written generically.** A ``Genome``, a
``LayerPolicy`` or a ``KindDefinition`` is not content *inside* a scope, it is
the declaration of what that scope *is*: the Genome carries the scope's identity
and its ``parent_scope`` inheritance, a LayerPolicy is the operator's own
override policy (the very gate ``write_document`` consults), and a
KindDefinition registers a brand-new Kind with its own schema, storage marker
and dep_filters. The set is **derived**, not hand-typed: it is exactly the ports
that declare ``is_overlayable = False`` — the kernel's own marker for "a layer
may not fork this". A new bootstrap Kind is therefore refused the day it is
declared, with no list to keep in sync. Reads are untouched.

**Refusal 2 — an ambiguous bare Kind name.** Two api_versions may share a Kind
name (i-195; live today whenever a per-scope ``KindDefinition`` shadows a
builtin). Bare-name lookup resolves one deterministically, which is fine for a
human at a CLI and wrong here: the
resolved port decides both the document's ``apiVersion`` **and** its metering
family, so silently picking one would let the registry pick a caller's quota
family for them. The generic surface refuses and asks for ``api_version``.

**The metering family** (:func:`family_for_kind`) is derived from the target
Kind's own port, so a face can meter a generic call exactly as it meters the
hand-written tool for the same Kind — and a caller cannot choose the family by
choosing a tool. Enforcement itself is the face's job (it owns the plan); this
module only classifies.
"""
from __future__ import annotations

from typing import Any, Iterable

from dna.application.live import LiveDna
from dna.kernel.etag import spec_etag
from dna.kernel.kinds.registry import ports_in_scope
from dna.memory.verbs import MEMORY_KINDS

__all__ = [
    "AmbiguousKindError",
    "BootstrapKindWriteRefused",
    "ConcurrentWriteError",
    "DEFAULT_FAMILY",
    "DeleteRefused",
    "TRAIT_APPEND_ONLY",
    "UnknownDocumentError",
    "UnknownKindError",
    "bootstrap_kinds",
    "delete_document_impl",
    "delete_refusal",
    "family_for_kind",
    "get_document_impl",
    "is_append_only_kind",
    "is_bootstrap_kind",
    "list_documents_impl",
    "list_kinds_impl",
    "resolve_kind_port",
    "spec_etag",
    "write_document_impl",
]


# ── errors (each face maps these to its transport) ──────────────────────────


class UnknownKindError(LookupError):
    """The named Kind is not registered on this kernel."""


class AmbiguousKindError(ValueError):
    """The bare Kind name resolves to more than one registered port — the caller
    must disambiguate with ``api_version`` (see the module docstring)."""


class ConcurrentWriteError(ValueError):
    """An ``if_match`` guard on a generic write did not hold — the stored
    document changed (or vanished) since the caller read it, so the write would
    have silently overwritten somebody else's update.

    Subclasses ``ValueError`` so every face that already maps write-path vetoes
    to an honest client refusal surfaces it with no new wiring."""


class UnknownDocumentError(LookupError):
    """A generic delete named a document that is not there.

    Distinct from :class:`UnknownKindError`: the Kind resolved fine, the
    document did not. Returning quietly would report success for a delete that
    did nothing — which is exactly how a caller convinces itself something is
    gone."""


class BootstrapKindWriteRefused(PermissionError):
    """A generic write targeted a BOOTSTRAP Kind and was refused (fail closed).

    Not a plan/quota denial and not a bug: writing a Genome / LayerPolicy /
    KindDefinition changes what the scope *is*, which no generic
    write-any-document tool should be able to do. The purpose-built paths
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


def is_bootstrap_kind(port: Any) -> bool:
    """Whether ``port`` is a BOOTSTRAP Kind — one whose documents declare what a
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
        f"{port.kind!r} is a BOOTSTRAP Kind: its documents declare what this "
        f"scope IS (identity + inheritance, the operator's own layer policy, or "
        f"the definition of a Kind itself), not content within it. The generic "
        f"write refuses it — fail closed — because a tool that can write any "
        f"document must not be the tool that rewrites the frame every other "
        f"document is validated and composed against. Use the purpose-built "
        f"path for this Kind (it is still READABLE here)."
    )


#: A Kind carrying this trait is an audit / evidence record: writable and
#: readable, never deletable through a generic tool.
TRAIT_APPEND_ONLY = "record.append-only"


class DeleteRefused(PermissionError):
    """A generic delete targeted a Kind that must not be deleted this way.

    A ``PermissionError`` for the same reason :class:`BootstrapKindWriteRefused`
    is: it is a policy refusal, not a bug and not a quota denial, and every face
    already maps it to an honest client-facing denial."""


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

    Two categories, and both refusals are DERIVED (from ``is_overlayable`` and
    from a declared trait) rather than from a list of Kind names, so a Kind that
    arrives later — including one a tenant declares in a ``.kind.yaml`` — is
    covered on arrival rather than the next time somebody remembers.

    **1. Bootstrap Kinds** — Genome, LayerPolicy, KindDefinition. The generic
    write already refuses these because they declare what the scope IS. Delete
    is strictly worse than write here, and the asymmetry is the point: a bad
    Genome is recoverable by writing a better one, but deleting a KindDefinition
    leaves every document of that Kind on disk with nothing left that can
    validate, compose or even name them — and the thing that would have told you
    what the orphans were is what you just deleted.

    **2. Append-only records** — AuditLog, Evidence, WorkflowEvent. The record is
    what proves what happened. Deleting it is the first move of anyone with
    something to hide, and there is no "write a better one" for a fact.

    Everything else is deletable, and deliberately so: a memory, a Story, a
    Skill, a tenant's own document are all things whose owner may legitimately
    want gone, and a delete they cannot perform is a delete they will perform by
    hand against the database."""
    if port is None:
        return None
    if is_bootstrap_kind(port):
        return (
            f"{port.kind!r} is a BOOTSTRAP Kind: its documents declare what this "
            f"scope IS (identity + inheritance, the operator's layer policy, or "
            f"the definition of a Kind itself). The generic delete refuses it. "
            f"Deleting one is worse than writing a bad one: a bad Genome is "
            f"fixed by writing a better Genome, but deleting a KindDefinition "
            f"leaves every document of that Kind in place with nothing left to "
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
    return None


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
    supplies the document's ``apiVersion`` supplies the family, so the meter and
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
# token now guards ``kernel.write_document`` itself, and that guard is evaluated
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
    registry the digest reads a document's date THROUGH and the named write paths
    are guarded against (i-078). Deriving from it rather than keeping a second list
    is the whole point: a Kind a reader learns to date is dated by this path on the
    day it is added there, and a Kind outside it gets nothing — many of those close
    their schema (``Kaizen`` is ``additionalProperties: false``), so inventing
    timestamps would be a write-time veto, not a cosmetic difference.

    Three rules, in order of who is most likely to be right:

    * a field the CALLER sent is left alone — importing a document with its real
      dates has to stay possible; the stamp is a floor, not an override;
    * ``updated_at`` is always ``now`` — this write IS the update, so the claim is
      true by construction;
    * ``created_at`` is stamped ``now`` only on a CREATE. On an update it is
      recovered from the document's own timeline (``backfill_created_at``) and
      otherwise left ABSENT. Falling back to ``now`` there would date a months-old
      document as filed today, put it in the current digest window and hide it from
      the one it belongs to — a louder version of the bug this repairs. That is the
      identical rule ``plan_date_repair`` and ``set_status`` already hold.

    No timeline event is appended. The generic write has no verb — it cannot know
    whether this was a groom, a decision or a status flip, the ``type`` vocabulary
    is verb-shaped, and a Kind may declare no ``timeline`` at all. Narrating a board
    item is what ``comment`` / ``set_status`` are for; what this path owes the
    readers is the dated fields above, and what it owes the document is to not
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
    """The tenant to thread into ``kernel.write_document``.

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


async def list_documents_impl(
    live: LiveDna, *, kind: str, scope: str | None = None,
    tenant: str | None = None, api_version: str | None = None,
    limit: int = 50, offset: int = 0,
    fields: Iterable[str] | None = None,
    filter: dict[str, Any] | None = None,  # noqa: A002 — the kernel's own kwarg
    order_by: Iterable[str] | None = None,
) -> dict[str, Any]:
    """List the documents of one Kind in a scope (tenant-resolved), optionally
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
    port = resolve_kind_port(live.kernel, kind, api_version, scope=sc)
    limit = max(1, min(int(limit), 500))
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
        documents: list[dict[str, Any]] = [
            {"name": n} for n in (_row_name(r) for r in page) if n
        ]
    else:
        documents = [r for r in page if isinstance(r, dict)]
    return {
        "scope": sc,
        "kind": port.kind,
        "api_version": port.api_version,
        "documents": documents,
        "count": len(documents),
        "offset": offset,
        "has_more": has_more,
        "projected": projection,
    }


async def get_document_impl(
    live: LiveDna, *, kind: str, name: str, scope: str | None = None,
    tenant: str | None = None, api_version: str | None = None,
) -> dict[str, Any]:
    """Read one document verbatim, as the caller's layer sees it."""
    sc = scope or live.default_scope(tenant)
    port = resolve_kind_port(live.kernel, kind, api_version, scope=sc)
    raw = await live.kernel.get_document(sc, port.kind, name, tenant=tenant)
    if raw is None:
        raise LookupError(f"no {port.kind} named {name!r} in scope {sc!r}")
    return {
        "scope": sc, "kind": port.kind, "api_version": port.api_version,
        "name": name, "document": raw,
        # The optimistic-concurrency token for a follow-up write (see
        # :func:`spec_etag`): pass it back as ``write_document``'s ``if_match``
        # and a lost update becomes a refusal instead of a silent overwrite.
        "etag": spec_etag(raw.get("spec") if isinstance(raw, dict) else None),
    }


async def write_document_impl(
    live: LiveDna, *, kind: str, name: str, spec: dict[str, Any],
    scope: str | None = None, tenant: str | None = None,
    api_version: str | None = None, merge: bool = True,
    if_match: str | None = None, now: str | None = None,
) -> dict[str, Any]:
    """Create or UPDATE one document — read-modify-merge, through
    ``kernel.write_document``.

    Nothing about the write path is re-implemented here: schema validation, the
    LayerPolicy gate (Kind-level and the ``OVERLAYABLE_FIELDS`` per-field
    allowlist), reference validation, the ``pre_save`` veto hook and the
    invalidation fan-out are the kernel's, exactly as for the hand-written
    tools. This use-case adds the three things the kernel cannot know:

    **1. the caller is a GENERIC write-any-document tool**, so the bootstrap
    Kinds are refused (:class:`BootstrapKindWriteRefused`).

    **2. an update is an update.** This path used to build the document from
    scratch and hand it over, which made every write a REPLACE: updating one
    field of a Story erased its ``timeline`` (append-only history), its status and
    its parent Feature unless the caller re-sent all of them. It now reads the
    stored document first and merges the caller's ``spec`` over it at the TOP
    LEVEL (:func:`_merged_spec` — which also documents why not deep, and how an
    explicit ``None`` clears a field). ``merge=False`` is the old behavior, kept
    reachable but only by name: it REPLACES the spec and drops anything the caller
    did not send.

    **3. the read surfaces need the document dated.** :func:`_stamp_dates` stamps
    exactly what :data:`~dna.application.sdlc.DATED_SPEC_FIELDS` declares for the
    target Kind — the same registry ``sdlc_digest`` reads a document's date
    through — so an ADR / Kaizen / Spike filed here is visible to the digest
    instead of permanently missing from every window (i-078, one write path
    later). It never forges a ``created_at`` onto an older document.

    ``if_match`` (OPTIONAL) is the ``etag`` from :func:`get_document_impl`: when
    given, the write proceeds only if the stored spec still hashes to it, else
    :class:`ConcurrentWriteError`. Opt-in rather than mandatory, deliberately —
    a CREATE has nothing to match, MCP tool calls are stateless (an agent that
    never read the document has no token to send), and making it mandatory would
    turn every first write into a two-call dance. What makes the default safe is
    (2): without a token, concurrent writers no longer clobber each other's whole
    document, only the individual fields both of them sent. A caller that cannot
    tolerate even that reads first and passes the etag — and gets the next one
    back from this call, so a chain of updates costs no extra reads.

    The ``apiVersion`` is taken from the resolved port, never from the caller:
    an agent cannot smuggle a document into a different Kind's namespace."""
    from dna.application.sdlc import now_iso

    sc = scope or live.default_scope(tenant)
    port = resolve_kind_port(live.kernel, kind, api_version, scope=sc)
    if is_bootstrap_kind(port):
        raise BootstrapKindWriteRefused(bootstrap_write_refusal(port))
    # Read at the coordinates the write will act on — ``write_tenant``, not the
    # caller's ``tenant`` (i-088, the same family as the delete path below).
    # The two differ only for a GLOBAL Kind, where ``_write_tenant`` returns
    # None; this never broke, and the measurement of WHY is in
    # ``test_delete_document_tenant_coordinates.py``: a GLOBAL Kind can have no
    # tenant row at all (the write pipeline raises ``TenantNotAllowed`` for any
    # effective tenant), and ``get_document(tenant=X)`` falls back to the base
    # layer, so both readings returned byte-identical documents on every store.
    # It is aligned anyway because the equality is a property of TODAY's
    # declarations, not of this code: a Kind whose declared scope changes from
    # tenanted to GLOBAL leaves real overlay rows behind, and the old reading
    # would have merged one into the shared base that every tenant inherits.
    write_tenant = _write_tenant(port, tenant)
    existing = await live.kernel.get_document(
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
                f"updating a document you read; the document was deleted, or the "
                f"name is wrong. Re-read it, or drop if_match to create."
            )
        current = spec_etag(stored)
        if current != if_match:
            raise ConcurrentWriteError(
                f"{port.kind} {name!r} in scope {sc!r} changed since you read it "
                f"(if_match={if_match!r}, now {current!r}) — refusing so your "
                f"update does not overwrite somebody else's. Re-read the document "
                f"with get_document and re-apply your change to the fresh etag."
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
    version = await live.kernel.write_document(
        sc, port.kind, name, raw, tenant=write_tenant,
    )
    return {
        "scope": sc, "kind": port.kind, "api_version": port.api_version,
        "name": name, "version": version, "tenant": write_tenant,
        "created": existing is None,
        "merged": bool(merge) and existing is not None,
        # Chain this into the next write's ``if_match`` — no re-read needed.
        "etag": spec_etag(new_spec),
    }


async def delete_document_impl(
    live: LiveDna, *, kind: str, name: str, api_version: str,
    scope: str | None = None, tenant: str | None = None,
    if_match: str | None = None,
) -> dict[str, Any]:
    """Delete one document — the generic delete the faces were missing.

    ``kernel.delete_document`` has always existed; REST reaches it through four
    narrow routes and ``dna doc delete`` uses it, but the MCP face had NO delete
    at all. An agent that could create and update every Kind could remove
    nothing, so the only way to undo a mistaken write was a human with database
    access. This is the same operation, through the same guards.

    Refuses per :func:`delete_refusal` — bootstrap Kinds and append-only records
    — and the refusal is REPORTED in ``list_kinds`` (``deletable`` /
    ``delete_refusal``) so it is visible before it is attempted rather than
    discovered by being denied.

    ``if_match`` is the same optimistic-concurrency guard the generic write
    takes, and it matters more here: a write that races loses one edit, a delete
    that races destroys a document its author never saw. It is OPTIONAL rather
    than required because a caller that has just read the document to decide it
    should go can pass the etag, while one deleting by name (a cleanup script)
    genuinely has nothing to match on — requiring it would only push that caller
    into an extra read whose result it ignores.

    ``api_version`` is REQUIRED, unlike the write path where it can be inferred
    from the document. A delete carries no document, and a bare Kind name can
    resolve to two ports once two workspaces each declare a `Deal` in their own
    namespace — so the caller states which Kind it means, and the pin travels
    all the way down to the adapter (:meth:`WritableSourcePort.delete_document`).
    """
    sc = scope or live.default_scope(tenant)
    port = resolve_kind_port(live.kernel, kind, api_version, scope=sc)
    refusal = delete_refusal(port)
    if refusal is not None:
        raise DeleteRefused(refusal)
    write_tenant = _write_tenant(port, tenant)
    # THE SAME COORDINATES THE DELETE WILL ACT ON (i-088). This check used to
    # read with no tenant while the delete below targeted ``write_tenant``, and
    # the write that created the row had used ``write_tenant`` too. ``tenant``
    # participates in the lookup key of every store — it is in the WHERE clause
    # of both SQL dialects (and in the Postgres primary key), and it selects the
    # overlay directory on the filesystem — so a tenant's document was reported
    # as "not found" by the one operation that could remove it, while write,
    # list and get all resolved it perfectly. An existence check asked at other
    # coordinates is a check of a different question; its answer says nothing
    # about the operation that follows it.
    existing = await live.kernel.get_document(
        sc, port.kind, name, tenant=write_tenant)
    if existing is None:
        raise UnknownDocumentError(
            f"{port.kind} {name!r} not found in scope {sc!r} — nothing to delete"
        )
    if if_match is not None:
        current = spec_etag((existing.get("spec") or {}) if isinstance(existing, dict) else {})
        if current != if_match:
            raise ConcurrentWriteError(
                f"if_match {if_match!r} does not match the stored document "
                f"(etag {current!r}): {port.kind} {name!r} changed since you read "
                f"it. Re-read it and decide again — a delete that races destroys "
                f"an edit its author never saw."
            )
    await live.kernel.delete_document(
        sc, port.kind, name, tenant=write_tenant,
        api_version=port.api_version, invalidate_mode="doc",
    )
    return {
        "scope": sc, "kind": port.kind, "api_version": port.api_version,
        "name": name, "tenant": write_tenant, "deleted": True,
    }
