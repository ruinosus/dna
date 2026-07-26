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

import hashlib
import json
from typing import Any, Iterable

from dna.application.live import LiveDna
from dna.memory.verbs import MEMORY_KINDS

__all__ = [
    "AmbiguousKindError",
    "BootstrapKindWriteRefused",
    "ConcurrentWriteError",
    "DEFAULT_FAMILY",
    "UnknownKindError",
    "bootstrap_kinds",
    "family_for_kind",
    "get_document_impl",
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


class BootstrapKindWriteRefused(PermissionError):
    """A generic write targeted a BOOTSTRAP Kind and was refused (fail closed).

    Not a plan/quota denial and not a bug: writing a Genome / LayerPolicy /
    KindDefinition changes what the scope *is*, which no generic
    write-any-document tool should be able to do. The purpose-built paths
    (workspace provisioning for a Genome, the operator's own policy authoring
    for a LayerPolicy, the KindDefinition wizard) stay available."""


# ── the Kind registry, generically ──────────────────────────────────────────


def resolve_kind_port(kernel: Any, kind: str, api_version: str | None = None) -> Any:
    """The registered ``KindPort`` for ``kind`` — the ONE resolution every
    generic use-case goes through.

    Deliberately NOT ``kernel.kind_port_for``: that resolves an ambiguous bare
    name deterministically (extension-first, then registration order), which is
    the right ergonomic for a CLI and the wrong one here — see the module
    docstring's "Refusal 2".

    Raises :class:`UnknownKindError` when nothing matches and
    :class:`AmbiguousKindError` when a bare name matches several ports.
    """
    ports = list(kernel.kind_ports())
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


def bootstrap_kinds(kernel: Any) -> set[str]:
    """The bootstrap Kind names registered on ``kernel`` (see
    :func:`is_bootstrap_kind`). Exposed so a face can SHOW the refusal in its
    catalog instead of letting an agent discover it by being denied."""
    return {p.kind for p in kernel.kind_ports() if is_bootstrap_kind(p)}


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


def spec_etag(spec: Any) -> str:
    """A content fingerprint of a document ``spec`` — the optimistic-concurrency
    token ``get_document`` returns and ``write_document`` checks (``if_match``).

    Deliberately NOT the adapter's version id: ``kernel.write_document`` returns
    one, but nothing on the READ path exposes it (``get_document`` yields the raw
    document and nothing else), and version support is per-adapter — the
    filesystem source has none. A hash of the content the tool actually writes is
    available on every adapter, is derivable by the caller from the very read it
    already made, and answers the only question that matters here: *is the spec I
    based my update on still the stored spec?*

    Keyed on the ``spec`` alone because the ``spec`` is all a generic write can
    change — the envelope is rebuilt from the resolved Kind port every time. Sorted
    keys + ``default=str`` make it stable across processes and tolerant of
    non-JSON scalars a Kind may store."""
    payload = json.dumps(spec or {}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


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

    Each entry also carries ``writable`` + ``write_refusal``, so a generic write
    that would be refused is visible BEFORE it is attempted."""
    allowed = frozenset(families) if families is not None else None
    entries: list[dict[str, Any]] = []
    for port in live.kernel.kind_ports():
        family = family_for_kind(port)
        if allowed is not None and family not in allowed:
            continue
        refusal = bootstrap_write_refusal(port) if is_bootstrap_kind(port) else None
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
            "writable": refusal is None,
            "write_refusal": refusal,
        })
    entries.sort(key=lambda e: (e["kind"], e["api_version"]))
    return {
        "scope": scope or live.default_scope(tenant),
        "kinds": entries,
        "count": len(entries),
        "filtered_by_plan": allowed is not None,
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
    port = resolve_kind_port(live.kernel, kind, api_version)
    sc = scope or live.default_scope(tenant)
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
    port = resolve_kind_port(live.kernel, kind, api_version)
    sc = scope or live.default_scope(tenant)
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

    port = resolve_kind_port(live.kernel, kind, api_version)
    if is_bootstrap_kind(port):
        raise BootstrapKindWriteRefused(bootstrap_write_refusal(port))
    sc = scope or live.default_scope(tenant)
    existing = await live.kernel.get_document(
        sc, port.kind, name, tenant=tenant)
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
    write_tenant = _write_tenant(port, tenant)
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
