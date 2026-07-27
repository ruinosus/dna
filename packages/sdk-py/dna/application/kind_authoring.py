"""Authoring a Kind — a dedicated door, not a hole in the generic one.

The generic write refuses BOOTSTRAP Kinds by construction, and that refusal
stays. This is a SEPARATE entry point with its own authorization: it writes
exactly one Kind (``KindDefinition``), always WITHOUT an approval marker, always
into the caller's own namespace.

What it writes is a real document — auditable, listable, diffable — that the
registry refuses to take until someone approves it (see the approval gate in
``dna/kernel/kinds/registry.py``). Absence of registration IS absence of effect:
an unregistered Kind neither validates documents nor routes the storage of its
documents.

**The apiVersion is BUILT here, not passed through.**
:func:`~dna.application.namespace_assignment.assign_namespace` returns an
apiVersion PREFIX (``ws-1a2b3c.dna.local``), never an apiVersion — a
``KindNamespace`` claim never carries a version segment, and
``namespace_of()`` (what ``NamespaceOwnershipGate`` resolves a write with)
strips the version off an apiVersion before looking the claim up. Storing
``target_api_version: <prefix>`` would therefore declare the Kind under a
namespace of ``""`` — a claim on nothing — and the gate would refuse the
workspace's own first Kind. The caller builds ``f"{namespace}/v1"``; that
caller is this module.

**No tenant argument on the write, deliberately.** ``KindDefinition`` is
structurally non-overlayable, so it cannot be forked into a layer at all: a
workspace's Kind is authored at the BASE of a scope the workspace owns, and the
namespace gate attributes that write through the scope's own declared owner
(``Genome.spec.owner_tenant``). Passing ``tenant=`` would turn this into a layer
write and be vetoed before the gate ever ran.
"""
from __future__ import annotations

import re
from typing import Any

from dna.application.namespace_assignment import assign_namespace

__all__ = [
    "AuthoredKindNotFound",
    "approve_kind_impl",
    "author_kind_impl",
    "kind_document_name",
    "list_authored_kinds_impl",
]

_KIND = "KindDefinition"
_API_VERSION = "github.com/ruinosus/dna/core/v1"

#: The separator between a namespace and a Kind name in the document's NAME.
#: The name has to carry the namespace: two workspaces may both author
#: ``Contrato``, and the pair is what keeps their documents apart in a scope
#: (the registry key is ``(api_version, kind)`` for the same reason).
_NAME_SEP = "--"


class AuthoredKindNotFound(LookupError):
    """No authored ``KindDefinition`` in this scope answers to that Kind name.

    Its own exception because the face must map it to **404** and never to the
    400 every other refusal here carries: an approval door that quietly CREATED
    the document it was asked to approve would be an authoring door with an
    approval marker on it — precisely the thing that must not exist."""


#: What a Kind name is allowed to be — a CamelCase identifier, exactly as the
#: schema documents ``target_kind`` (``docs/schemas/kind-definition.schema.json``).
#: An ALLOW-list, not a deny-list of the characters we happened to think of.
#:
#: ``kind`` is the ONLY field of the request body that reaches a PATH. The
#: document name is ``<namespace>--<kind>``, and on a filesystem-backed source
#: that name becomes a DIRECTORY (``<scope>/kinds/<name>/KIND.yaml``). Left
#: unvalidated it is a create-directories-anywhere + write-a-``KIND.yaml``
#: primitive OUTSIDE the store root (measured: six ``../`` segments land two
#: levels above the ``.dna`` root), and a name aimed at another scope's existing
#: ``kinds/<x>/KIND.yaml`` replaces an APPROVED KindDefinition with an
#: unapproved one — which silently deregisters the victim's Kind on the next
#: load. (It cannot forge an approval: the spec below is built field by field.)
#:
#: The same check closes the other half of the ``--`` separator. An ASSIGNED
#: namespace (``ws-<hex>.dna.local``) structurally cannot contain ``--``, but the
#: Kind half is caller-controlled, so ``Contrato--Extra`` would yield a name no
#: reader can split unambiguously. Nothing splits it today —
#: :func:`kind_document_name` is exported precisely so the APPROVAL act, a
#: separate task by a different actor, can address these documents by name, and
#: an ambiguous name is a trap laid for that task.
#:
#: The leading class is ``[A-Z]``, not ``[A-Za-z]``: the error message says
#: CamelCase and the guard must mean what its message says. MEASURED
#: consequence of the looser form — ``Contrato`` and ``contrato`` produce the
#: IDENTICAL alias (``generate_alias`` kebab-cases the Kind name), and on a
#: case-insensitive filesystem (the macOS/Windows default) the second write
#: lands in the SAME ``kinds/<name>/`` directory as the first and silently
#: replaces it, with a 201 in reply. Requiring the initial capital removes the
#: pair.
_KIND_NAME_RE = re.compile(r"[A-Z][A-Za-z0-9]{0,63}")


def _alias_owner(namespace: str) -> str:
    """The ``<owner>`` half of the alias convention, derived from the namespace.

    The alias is declared GLOBALLY unique, so the owner half has to be the whole
    namespace and not a readable piece of it: ``acme.example`` and
    ``acme.other`` share a first label but are two different owners. Dots and
    slashes collapse to ``-`` so the result stays a single kebab token.

    KNOWN COLLISION, recorded rather than fixed. The collapse is not injective:
    ``acme.example`` and ``acme-example`` are two different namespaces that
    produce the SAME owner half, and therefore the same alias for the same Kind
    name — against the schema's "globally unique" declaration for ``alias``.
    Unreachable today, because every namespace this door sees is MINTED in the
    ``ws-<hex>.dna.local`` shape and no two of those collapse together. It
    becomes reachable the moment a workspace can prove ownership of a namespace
    it chose — which
    :mod:`dna.application.namespace_assignment` explicitly anticipates. There is
    also no alias-uniqueness check at authoring time, so a collision would not
    surface here at all: it would surface at APPROVAL, to a reviewer with no
    context for it. The task that adds the proof-of-ownership flow owns both
    halves — an injective owner encoding, and a uniqueness check at authoring."""
    return "-".join(
        part for part in namespace.replace("/", ".").split(".") if part
    )


def kind_document_name(namespace: str, kind: str) -> str:
    """The document name an authored Kind is stored under.

    Exposed because approval (a separate act by a different actor) has to be
    able to address the very document this door wrote, and deriving that name in
    two places is how the two halves drift apart."""
    return f"{namespace}{_NAME_SEP}{kind}"


def _checked_kind_name(kind: str, *, verb: str) -> str:
    """The validated Kind name, or ``ValueError`` (the face maps it to 400).

    Shared by BOTH doors deliberately. ``kind`` is the one caller-controlled
    value that reaches a PATH, and the approval door takes it from the URL — a
    guard on the authoring door alone would leave the second door open to the
    same traversal it was written for."""
    kind = (kind or "").strip()
    if not kind:
        raise ValueError(f"kind is required to {verb} a Kind")
    if not _KIND_NAME_RE.fullmatch(kind):
        # See _KIND_NAME_RE: this is the one body field that reaches a path.
        raise ValueError(
            f"kind must be a CamelCase identifier — a CAPITAL letter followed "
            f"by up to 63 letters or digits, no '/', '.', '-' or path segments "
            f"(got {kind!r})"
        )
    return kind


async def author_kind_impl(
    live: Any, *, kind: str, schema: dict, tenant: str, now: str,
    actor: str | None = None, traits: list[str] | None = None,
) -> dict[str, Any]:
    """Write a tenant Kind, unapproved. It has no effect until approved.

    ``actor`` is the PROPOSER — the verified identity of the caller, resolved by
    the face from the token and NEVER read from the request body. It is stamped
    here, at the moment of the proposal, because it cannot be back-filled later:
    a document that never recorded who proposed it has lost that fact for good.

    Raises ``ValueError`` for a missing tenant, or for a Kind name that is not a
    CamelCase identifier (the face maps it to 400) — see :data:`_KIND_NAME_RE`,
    which is a security boundary and not a tidiness check. Every policy refusal
    below this — the namespace gate, the schema validation — surfaces from the
    kernel unchanged.
    """
    kind = _checked_kind_name(kind, verb="author")
    if not (tenant or "").strip():
        raise ValueError("tenant is required to author a Kind")
    if not isinstance(schema, dict):
        raise ValueError("schema must be a JSON Schema object")
    proposed_by = (actor or "").strip() or None

    from dna.kernel.kinds.registry import generate_alias

    namespace = await assign_namespace(live.kernel, tenant, now=now)
    name = kind_document_name(namespace, kind)
    raw = {
        "apiVersion": _API_VERSION,
        "kind": _KIND,
        "metadata": {"name": name},
        "spec": {
            # A PREFIX plus the version segment — see the module docstring.
            "target_api_version": f"{namespace}/v1",
            "target_kind": kind,
            "alias": generate_alias(_alias_owner(namespace), kind),
            "origin": namespace,
            "schema": schema,
            "traits": list(traits or []),
            "storage": {"type": "yaml", "container": f"{kind.lower()}s"},
            # `created_at` is documented as "Runtime-stamped volatile field
            # (never authored)" and IS listed in KindPort.VOLATILE_SPEC_FIELDS
            # — so authoring it looks wrong. It is authored anyway, on a
            # MEASUREMENT: a KindDefinition written through this same kernel
            # path with `created_at` omitted comes back from a fresh read with
            # no `created_at` at all (the on-disk KIND.yaml has no such key —
            # nothing in the write path stamps it; VOLATILE only means "excluded
            # from canonical_digest", not "supplied by the runtime"). And this
            # value IS load-bearing: `list_authored_kinds_impl` projects it into
            # the audit view, which exists so a reviewer can see WHEN a Kind was
            # proposed. Unauthored, every row would read `created_at: null`.
            # If a write-time stamp ever lands, it wins and this line becomes a
            # no-op — which is the harmless direction.
            "created_at": now,
            # WHO proposed, and WHEN — the first half of the audit. The value is
            # the face's VERIFIED identity for this request, passed in as
            # `actor`; a `proposed_by` in the request body reaches nothing,
            # because this spec is built field by field and never merged.
            "proposed_by": proposed_by,
            "proposed_at": now if proposed_by else None,
            # Deliberately absent: approved_by / approved_at. This path CANNOT
            # set them — approval is a separate, privileged act with its own
            # verified actor. A caller-supplied value is dropped on the floor
            # here for the same reason `proposed_by` cannot be forged: the spec
            # is BUILT field by field, never merged from the request body, so
            # there is no key an author can smuggle through.
        },
    }
    version = await live.kernel.write_document(
        live.default_scope(tenant), _KIND, name, raw,
    )
    return {
        "namespace": namespace, "kind": kind, "name": name,
        "approved": False, "proposed_by": proposed_by, "version": version,
    }


async def _authored_document_name(
    live: Any, *, scope: str, kind: str, tenant: str | None,
) -> tuple[str, str]:
    """Find the authored document for ``kind`` in ``scope`` → ``(name, namespace)``.

    Addresses the document by SEARCH, not by re-deriving the namespace. Calling
    :func:`assign_namespace` here would read better and be wrong twice over: it
    MINTS on absence, so approving a Kind nobody authored would leave a namespace
    claim behind as a side effect of a refusal; and a workspace may own several
    namespaces, so the derived name would only ever find Kinds authored under the
    first-assigned one.

    Names are ``<namespace>--<kind>`` and :data:`_KIND_NAME_RE` forbids ``-`` in
    the Kind half, so ``rsplit`` on the LAST separator recovers both halves
    unambiguously — even for a hand-written namespace claim that contains ``--``
    itself. Left-splitting would mis-address exactly that case.

    Raises :class:`AuthoredKindNotFound` when nothing matches, and ``ValueError``
    when two namespaces in one scope both declare the Kind — an ambiguity a
    reviewer must resolve by name, never one this function may pick a winner for.
    """
    matches: list[tuple[str, str]] = []
    async for raw in live.kernel.query(scope, _KIND, tenant=tenant):
        if not isinstance(raw, dict):
            continue
        name = str((raw.get("metadata") or {}).get("name") or raw.get("name") or "")
        if _NAME_SEP not in name:
            continue
        namespace, kind_half = name.rsplit(_NAME_SEP, 1)
        if kind_half == kind and namespace:
            matches.append((name, namespace))
    if not matches:
        raise AuthoredKindNotFound(
            f"no authored Kind {kind!r} in scope {scope!r} — approval acts on a "
            f"document that already exists, and creates none"
        )
    if len(matches) > 1:
        raise ValueError(
            f"Kind {kind!r} is declared under {len(matches)} namespaces in scope "
            f"{scope!r} ({', '.join(sorted(n for _, n in matches))}) — approve it "
            f"by document name, not by Kind name"
        )
    return matches[0]


async def approve_kind_impl(
    live: Any, *, kind: str, tenant: str, actor: str, now: str,
) -> dict[str, Any]:
    """Approve an authored Kind — the act that CONFERS effect.

    Registration is what gives a Kind schema validation and storage routing, and
    the registry's gate withholds registration until ``approved_by`` names
    someone. So this write is not a flag flip with a promise attached: it is the
    only thing that lets the next load take the Kind at all.

    ``actor`` is the APPROVER — the face's verified identity for THIS request,
    never a body field, and never the value stored in ``proposed_by``. The two
    may legitimately coincide (a solo author approving their own proposal is two
    credentials, and refusing on identity equality would block the commonest user
    while stopping nothing: the authoring door cannot write ``approved_by`` at
    all, so approval already requires a second call to a different route). What
    this function must never do is let one act wear the other's name.

    Raises :class:`AuthoredKindNotFound` (→ 404) when no such document exists,
    and ``ValueError`` (→ 400) for a missing tenant/actor or a malformed Kind
    name. Idempotent in shape but not in fact: a second approval re-stamps the
    approver and the timestamp, which is the honest record of what happened.
    """
    kind = _checked_kind_name(kind, verb="approve")
    if not (tenant or "").strip():
        raise ValueError("tenant is required to approve a Kind")
    actor = (actor or "").strip()
    if not actor:
        raise ValueError(
            "approval records a verified identity and this request carries "
            "none — an approval nobody signed is not an approval"
        )

    scope = live.default_scope(tenant)
    name, namespace = await _authored_document_name(
        live, scope=scope, kind=kind, tenant=tenant,
    )
    raw = await live.kernel.get_document(scope, _KIND, name)
    if not isinstance(raw, dict) or not raw:
        # The query above found the name, so this is a store that lost the
        # document between two reads — not a caller error, but still a 404's
        # worth of "there is nothing here to approve".
        raise AuthoredKindNotFound(
            f"the authored Kind {kind!r} ({name!r}) is listed in scope {scope!r} "
            f"but its document could not be read"
        )

    spec = dict(raw.get("spec") or {})
    # MERGE, unlike the authoring door — and deliberately: this preserves the
    # proposal (proposed_by/proposed_at/created_at) that the other act recorded,
    # which is the half of the audit this act must not overwrite. The two fields
    # below are the ONLY ones it sets.
    spec["approved_by"] = actor
    spec["approved_at"] = now
    version = await live.kernel.write_document(
        scope, _KIND, name, {**raw, "spec": spec},
    )
    return {
        "approved": True,
        "kind": kind,
        "name": name,
        "namespace": namespace,
        "approved_by": actor,
        "approved_at": now,
        # Echoed so the caller sees BOTH actors in one response — the audit is
        # the point, and a reviewer who has to make a second call to learn who
        # proposed is a reviewer who will not make it.
        "proposed_by": spec.get("proposed_by"),
        "proposed_at": spec.get("proposed_at"),
        "version": version,
    }


async def list_authored_kinds_impl(
    live: Any, *, tenant: str | None = None, scope: str | None = None,
) -> dict[str, Any]:
    """Every ``KindDefinition`` document in the caller's scope, with its
    approval state — the audit surface the authoring door exists to produce.

    Reads DOCUMENTS, not the registry: an unapproved Kind is precisely the one
    the registry does not have, so a registry-backed listing would show every
    Kind except the ones a reviewer needs to see.
    """
    sc = scope or live.default_scope(tenant)
    kinds: list[dict[str, Any]] = []
    async for raw in live.kernel.query(sc, _KIND, tenant=tenant):
        if not isinstance(raw, dict):
            continue
        spec = raw.get("spec") or {}
        meta = raw.get("metadata") or {}
        approved_by = str(spec.get("approved_by") or "").strip()
        kinds.append({
            "name": meta.get("name") or raw.get("name"),
            "kind": spec.get("target_kind"),
            "api_version": spec.get("target_api_version"),
            "namespace": spec.get("origin"),
            "approved": bool(approved_by),
            # BOTH actors — a reviewer reading this list is deciding whether to
            # confer effect, and "who proposed this" is the first thing that
            # decision needs. `proposed_by` is null for every document authored
            # before the field existed, and for a door that could not identify
            # its caller; null is the honest answer in both cases and is not the
            # same fact as "the two actors coincide".
            "proposed_by": (str(spec.get("proposed_by") or "").strip() or None),
            "proposed_at": spec.get("proposed_at"),
            "approved_by": approved_by or None,
            "approved_at": spec.get("approved_at"),
            "created_at": spec.get("created_at"),
        })
    return {"scope": sc, "kinds": kinds}
