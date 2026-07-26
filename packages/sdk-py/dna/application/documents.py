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
from dna.memory.verbs import MEMORY_KINDS

__all__ = [
    "AmbiguousKindError",
    "BootstrapKindWriteRefused",
    "DEFAULT_FAMILY",
    "UnknownKindError",
    "bootstrap_kinds",
    "family_for_kind",
    "get_document_impl",
    "is_bootstrap_kind",
    "list_documents_impl",
    "list_kinds_impl",
    "resolve_kind_port",
    "write_document_impl",
]


# ── errors (each face maps these to its transport) ──────────────────────────


class UnknownKindError(LookupError):
    """The named Kind is not registered on this kernel."""


class AmbiguousKindError(ValueError):
    """The bare Kind name resolves to more than one registered port — the caller
    must disambiguate with ``api_version`` (see the module docstring)."""


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
) -> dict[str, Any]:
    """List the documents of one Kind in a scope (tenant-resolved).

    Pages through the kernel's own push-down query — one extra row is fetched to
    answer ``has_more`` honestly instead of guessing from a full page."""
    port = resolve_kind_port(live.kernel, kind, api_version)
    sc = scope or live.default_scope(tenant)
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    rows: list[dict[str, Any]] = []
    async for row in live.kernel.query(
        sc, port.kind, tenant=tenant, limit=limit + 1, offset=offset,
    ):
        rows.append(row)
    has_more = len(rows) > limit
    names = [n for n in (_row_name(r) for r in rows[:limit]) if n]
    return {
        "scope": sc,
        "kind": port.kind,
        "api_version": port.api_version,
        "documents": [{"name": n} for n in names],
        "count": len(names),
        "offset": offset,
        "has_more": has_more,
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
    }


async def write_document_impl(
    live: LiveDna, *, kind: str, name: str, spec: dict[str, Any],
    scope: str | None = None, tenant: str | None = None,
    api_version: str | None = None,
) -> dict[str, Any]:
    """Create or update one document — through ``kernel.write_document``.

    Nothing about the write path is re-implemented here: schema validation, the
    LayerPolicy gate (Kind-level and the ``OVERLAYABLE_FIELDS`` per-field
    allowlist), reference validation, the ``pre_save`` veto hook and the
    invalidation fan-out are the kernel's, exactly as for the hand-written
    tools. This use-case adds one thing the kernel cannot know — that the caller
    is a GENERIC write-any-document tool — and refuses the bootstrap Kinds
    accordingly (:class:`BootstrapKindWriteRefused`).

    The ``apiVersion`` is taken from the resolved port, never from the caller:
    an agent cannot smuggle a document into a different Kind's namespace."""
    port = resolve_kind_port(live.kernel, kind, api_version)
    if is_bootstrap_kind(port):
        raise BootstrapKindWriteRefused(bootstrap_write_refusal(port))
    sc = scope or live.default_scope(tenant)
    raw = {
        "apiVersion": port.api_version,
        "kind": port.kind,
        "metadata": {"name": name},
        "spec": dict(spec or {}),
    }
    write_tenant = _write_tenant(port, tenant)
    version = await live.kernel.write_document(
        sc, port.kind, name, raw, tenant=write_tenant,
    )
    return {
        "scope": sc, "kind": port.kind, "api_version": port.api_version,
        "name": name, "version": version, "tenant": write_tenant,
    }
