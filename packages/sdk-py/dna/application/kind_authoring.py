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
from dna.kernel.etag import spec_etag
from dna.kernel.kinds.approval import approval_state

__all__ = [
    "AuthoredKindNotFound",
    "NamespaceRegistryUnreadable",
    "approve_kind_impl",
    "author_kind_impl",
    "get_authored_kind_impl",
    "list_authored_kinds_impl",
    "revoke_kind_impl",
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


class NamespaceRegistryUnreadable(RuntimeError):
    """The ``KindNamespace`` claim registry could not be read, so who owns a
    namespace cannot be decided — mapped to **503**, never to 400/403/500.

    Its own exception because it is a deployment PRECONDITION and not the
    caller's fault, and because the alternative — letting the underlying store
    error out of the use-case raw — is what made the two doors disagree. The
    write path's :class:`~dna.kernel.write.namespace_gate.NamespaceOwnershipGate`
    catches a BROAD ``Exception`` on the same read and converts it to an honest
    refusal; the read doors caught only ``FileNotFoundError``. On a filesystem
    store the two coincide (a missing ``_lib`` directory), so the gap was
    invisible — on Postgres a transient registry read error would 500 on
    approval while the identical failure refused honestly one path over.

    Fail-CLOSED is the whole content of it: without the registry we cannot tell
    an owner from a stranger, and "no rows" is not the same fact as "the read
    failed"."""


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
#: reader can split unambiguously. Something DOES split it:
#: :func:`_authored_kind_visibility` decides who may see a row by taking the
#: namespace half of its name (``rsplit(_NAME_SEP, 1)``) and asking whether the
#: caller owns it — so an ambiguous name is not a trap laid for a future task,
#: it is an ambiguity in a live authorization decision.
#:
#: The leading class is ``[A-Z]``, not ``[A-Za-z]``: the error message says
#: CamelCase and the guard must mean what its message says. MEASURED
#: consequence of the looser form — ``Contrato`` and ``contrato`` produce the
#: IDENTICAL alias (``generate_alias`` kebab-cases the Kind name), and on a
#: case-insensitive filesystem (the macOS/Windows default) the second write
#: lands in the SAME ``kinds/<name>/`` directory as the first and silently
#: replaces it, with a 201 in reply. Requiring the initial capital removes the
#: pair.
#:
#: It gates the APPROVAL url too (both doors share :func:`_checked_kind_name`),
#: so a Kind authored under the looser form would be permanently unapprovable
#: with no migration path. VERIFIED to affect nothing: this door first appeared
#: in ``71f8aa8`` and the tightening landed in ``7299a26`` the same day on the
#: same unmerged branch — ``git tag --contains`` names no release for either —
#: and a tree-wide scan of stored ``target_kind`` values found no non-CamelCase
#: declaration. No migration is owed.
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

    Module-private in practice, and deliberately NOT in ``__all__``. It was
    exported on the rationale that approval — a separate act by a different
    actor — would address the document by name; that rationale was never true.
    :func:`approve_kind_impl` reaches the document through
    :func:`_authored_document_name`, a SEARCH over the caller's own namespaces,
    because the approval URL carries only the Kind half and the namespace half
    is what the caller must be shown to own. One caller (:func:`author_kind_impl`,
    which mints the name) is not an API."""
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

    **This is also the EDIT path**, and the spec below is rebuilt from scratch
    and PERSISTED (``write_document`` does not merge), so what an edit does to
    each audit field is decided by what this function carries forward:

    * ``created_at`` — the BIRTH of the document, carried forward. Only a
      document that does not exist yet gets ``now``. The schema calls it "when
      the document was created" and an unconditional re-stamp made that false
      from the first edit onward.
    * ``proposed_by``/``proposed_at`` — the CURRENT proposal, re-stamped every
      time. They answer "who proposed the shape that is pending or approved
      right now", and after an edit that is the editor, not whoever went first.
      The original proposer stays recoverable through the kernel's version
      history; the live document answers the live question.
    * ``approved_by``/``approved_at`` — dropped, by never being written. An edit
      changes the shape a human approved, so the approval no longer applies to
      it and the Kind loses its effect until the new shape is approved.

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
    scope = live.default_scope(tenant)
    # The ONE thing read back off an existing document. Not a merge — a merge
    # would carry `approved_by` forward too, and an edit must withdraw the
    # approval it invalidated. A missing document reads as None here (the
    # ordinary first-author case), so `created_at` falls back to `now`.
    #
    # NOT a plain local existence check, and the difference is accepted here
    # EXPLICITLY rather than left for the next reader to discover. `get_document`
    # answers through a bounded cache (2000 entries / 60s TTL) and through the
    # parent-scope inheritance fallback, so "there is no document" is really
    # "no document is VISIBLE from here right now". Two consequences, both
    # measured and both narrow:
    #
    #   * a stale birth date needs an out-of-band deletion INSIDE the TTL. It
    #     cannot be reached through any API path: the generic delete refuses
    #     BOOTSTRAP Kinds and `KindDefinition` is one of them, so nothing a
    #     caller can invoke removes the document that seeds `born_at`.
    #   * a same-named document in the PARENT scope would be read instead — and
    #     writing one there requires owning the same namespace in that scope,
    #     i.e. being the same workspace. It carries forward its own birth date,
    #     which is the honest answer for a Kind the workspace is re-authoring
    #     locally, not a foreign value.
    #
    # A fresh read (cache bypass, local-only) would be the exact measurement,
    # but it costs a store round-trip on every author call to close a window
    # only an operator with shell access can open on their own documents.
    existing = await live.kernel.get_document(scope, _KIND, name)
    prior = existing.get("spec") if isinstance(existing, dict) else None
    born_at = prior.get("created_at") if isinstance(prior, dict) else None
    # i-085 — the REVOCATION is carried forward, unlike the approval. The
    # symmetry is tempting and it is the loosening trap in a second door: this
    # function rebuilds the spec from scratch and PERSISTS it, so a dropped
    # ``revoked_by`` would land the Kind in *never approved*, where documents
    # are accepted with NO validation at all. An edit withdraws the approval it
    # invalidated; it cannot grant itself the effect of an un-revocation, and
    # only the approval door can undo one.
    # Carried as KEYS-IF-PRESENT (never as explicit nulls): the KindDefinition
    # port's schema derives ``str | None`` to ``{"type": "string"}``, so a null
    # here would veto every edit of a Kind that was never revoked.
    was_revoked = {
        k: prior[k]
        for k in ("revoked_by", "revoked_at")
        if isinstance(prior, dict) and prior.get(k)
    }
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
            #
            # CARRIED FORWARD on an edit (`born_at`), never re-stamped: this is
            # the document's birth, and the schema says so in those words.
            "created_at": born_at or now,
            # WHO proposed, and WHEN — the first half of the audit. The value is
            # the face's VERIFIED identity for this request, passed in as
            # `actor`; a `proposed_by` in the request body reaches nothing,
            # because this spec is built field by field and never merged.
            #
            # RE-STAMPED on an edit, unlike `created_at` above, and the asymmetry
            # is the point: these two answer "who proposed the shape that is
            # pending or approved RIGHT NOW", which after an edit is the editor.
            # The first proposer is not lost — the kernel keeps the version
            # history — but the live document answers the live question.
            "proposed_by": proposed_by,
            "proposed_at": now if proposed_by else None,
            # Deliberately absent: approved_by / approved_at. This path CANNOT
            # set them — approval is a separate, privileged act with its own
            # verified actor. A caller-supplied value is dropped on the floor
            # here for the same reason `proposed_by` cannot be forged: the spec
            # is BUILT field by field, never merged from the request body, so
            # there is no key an author can smuggle through.
            #
            # `revoked_by`/`revoked_at` are NOT in that group — see `was_revoked`
            # above. They are carried forward from the stored document (and, by
            # being spread LAST, cannot be supplied by the caller either).
            **was_revoked,
        },
    }
    version = await live.kernel.write_document(scope, _KIND, name, raw)
    return {
        "namespace": namespace, "kind": kind, "name": name,
        "approved": False, "proposed_by": proposed_by, "version": version,
    }


async def _owns(live: Any, tenant: str) -> Any:
    """A predicate ``(namespace) -> bool``: does ``tenant`` own that namespace?

    Answered from the ``KindNamespace`` claim registry — the SAME rows and the
    SAME resolver (:func:`~dna.kernel.kinds.namespaces.owner_of`) the write-path
    gate decides with. PARITY WITH THE GATE is the entire reason, and it is not
    a coverage argument: ``owner_of``'s prefix walk is inert on this path,
    because a document name cannot contain ``/`` and so a sub-namespace claim
    can never appear as the namespace half of one. What using it buys is that
    ownership cannot mean one thing to the gate that decides the WRITE and
    another to the doors that decide who may approve and who may see — including
    its refusal to resolve a doubly-claimed namespace, which is a verdict this
    door must inherit rather than re-derive.

    Read once per call and closed over: the registry is a single ``_lib`` read
    and a per-candidate read would turn one query into N.

    An unreadable registry REFUSES, as :class:`NamespaceRegistryUnreadable`, on
    the same broad ``except Exception`` the gate uses — see that class for why
    the narrower ``FileNotFoundError``-only shape was a real gap and not a
    tidiness point."""
    from dna.kernel.kinds.namespaces import owner_of

    try:
        claims = await live.kernel.kind_namespaces()
    except Exception as exc:  # noqa: BLE001 — mirror NamespaceOwnershipGate.
        raise NamespaceRegistryUnreadable(
            f"cannot verify which namespaces workspace {tenant!r} owns: the "
            f"KindNamespace registry is unreadable. Refusing rather than "
            f"assuming — a namespace claim is an authorization record, and an "
            f"unreadable one is not a granted one. Underlying: {exc}"
        ) from exc

    def owns(namespace: str) -> bool:
        return owner_of(namespace, claims).owner == tenant

    return owns


#: The verb-specific tail of the "no such Kind here" refusal. The refusal is
#: the SAME sentence for a Kind that does not exist and for a neighbour's — see
#: the ownership paragraph below — so the only thing that may vary is which act
#: was refused, never which of the two facts caused it.
_NOT_FOUND_TAIL = {
    "approve": (
        "— approval acts on a document that already exists, and creates none"
    ),
    "revoke": (
        "— revocation acts on a document that already exists, and creates none"
    ),
    "read": (
        "— an authored Kind is readable by the workspace that authored it, and "
        "the reader is not told which of the two it is"
    ),
}


async def _authored_document_name(
    live: Any, *, scope: str, kind: str, tenant: str | None,
    allow_unattributed: bool,
    verb: str = "approve",
) -> tuple[str, str]:
    """Find the CALLER's authored document for ``kind`` in ``scope`` →
    ``(name, namespace)``.

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

    **The ownership filter is a security boundary, not a nicety.** A scope holds
    the authored Kinds of every workspace that shares it — and with
    multi-workspace off, ``LiveDna.default_scope`` hands EVERY workspace the same
    ``base_scope``, so sharing is the default configuration and not an exotic
    one. The Kind half of the name is all the approval URL carries, so an
    unfiltered search lets workspace A approve the ``…--Contrato`` that belongs
    to B: one match, no refusal, and effect conferred on a document A never
    wrote. Nothing downstream catches it — the approval write passes no
    ``tenant=`` (``KindDefinition`` is non-overlayable), so the namespace gate
    attributes it to the SCOPE's owner rather than to the caller. Filtering here,
    against the claim registry, is where the caller is still known.

    A match the caller does not own is dropped, not refused: to this caller the
    Kind is simply not there, and a distinct "it exists but is not yours" would
    hand a stranger a probe for what its neighbours are authoring.

    **No resolved tenant ⇒ no filter — but only for a caller that ASKED for
    that.** ``allow_unattributed`` is a required keyword with no default, and it
    is the whole precondition made structural. The two doors that call this
    function have OPPOSITE tenancy preconditions: the read passes ``None``
    through on purpose (``allow_unattributed=True``), because ``--auth none``
    self-host and an explicit operator ``scope=`` call resolve no workspace, and
    a filter that demanded ownership would answer every self-hoster "not found"
    for a document sitting in their own store — the same hinge
    :class:`~dna.kernel.write.namespace_gate.NamespaceOwnershipGate` uses for an
    unattributed write and :func:`_authored_kind_visibility` uses for the
    listing, resting on the same standing invariant that a hosted face never
    issues an unattributed request on a user's behalf. Approval passes
    ``allow_unattributed=False``, because an approval nobody can attribute is
    not an approval.

    That difference used to be a paragraph of prose and an ordering promise —
    ``approve_kind_impl`` refuses a missing tenant BEFORE it calls here — which
    held for the two callers that existed and would have failed silently for a
    third: forget the check and you get an unfiltered search across every
    workspace sharing the scope, with no error anywhere. Now the parameter has
    no default, so a third caller cannot forget to answer the question; and
    answering ``False`` with an empty ``tenant`` raises rather than searching.

    ``verb`` selects only the tail of the not-found message
    (:data:`_NOT_FOUND_TAIL`) — which ACT was refused. It must never encode
    which FACT caused the refusal, or the message becomes the probe the drop
    above exists to close.

    Raises :class:`AuthoredKindNotFound` when nothing the caller owns matches,
    and ``ValueError`` when the CALLER owns two namespaces that both declare the
    Kind — an ambiguity a reviewer must resolve by name, never one this function
    may pick a winner for — or when ``allow_unattributed`` is ``False`` and the
    request resolves no workspace.
    """
    attributed = bool((tenant or "").strip())
    if not attributed and not allow_unattributed:
        # The precondition, ENFORCED. The caller said this act needs an owner;
        # searching the shared scope unfiltered would answer it with whichever
        # workspace's document happens to carry the Kind name.
        raise ValueError(
            f"a workspace is required to address the authored Kind {kind!r}: "
            f"this act is filtered to the namespaces the CALLER owns, and an "
            f"unattributed request has no owner to filter by"
        )
    owns = await _owns(live, tenant) if attributed else None
    matches: list[tuple[str, str]] = []
    async for raw in live.kernel.query(scope, _KIND, tenant=tenant):
        if not isinstance(raw, dict):
            continue
        name = str((raw.get("metadata") or {}).get("name") or raw.get("name") or "")
        if _NAME_SEP not in name:
            continue
        namespace, kind_half = name.rsplit(_NAME_SEP, 1)
        if kind_half == kind and namespace and (owns is None or owns(namespace)):
            matches.append((name, namespace))
    under = (
        f" under a namespace workspace {tenant!r} owns" if attributed else ""
    )
    if not matches:
        raise AuthoredKindNotFound(
            f"no authored Kind {kind!r} in scope {scope!r}{under} "
            f"{_NOT_FOUND_TAIL.get(verb, _NOT_FOUND_TAIL['approve'])}"
        )
    if len(matches) > 1:
        owned = (
            f"namespaces that workspace {tenant!r} owns in scope {scope!r}"
            if attributed else f"namespaces in scope {scope!r}"
        )
        raise ValueError(
            f"Kind {kind!r} is declared under {len(matches)} {owned} "
            f"({', '.join(sorted(n for _, n in matches))}) — address it "
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

    ``tenant`` is not decoration on the lookup: it is what scopes the search to
    the caller's OWN namespaces (see :func:`_authored_document_name`). A scope is
    shared by default, and the approval URL carries only the Kind half of the
    document name.

    Raises :class:`AuthoredKindNotFound` (→ 404) when no document the CALLER
    owns exists under that Kind name — including when a neighbour's does — and
    ``ValueError`` (→ 400) for a missing tenant/actor or a malformed Kind name.
    Idempotent in shape but not in fact: a second approval re-stamps the
    approver and the timestamp, which is the honest record of what happened —
    and it is the ordinary path, because an EDIT drops the approval marker (see
    :func:`author_kind_impl`) and re-approving is what lets the NEW shape be
    taken at the next load. Note what that does and does not say: the edit never
    unregistered the previous shape, so this is the act that replaces it, not
    one that restores an effect the edit removed.

    **The write is GUARDED** (i-083). This is a read-modify-write — it reads the
    document, merges two keys and persists ``{**raw, "spec": spec}`` — so
    everything it did not read, it overwrites. Unguarded, that lost an edit for
    real: the reviewer opens the Kind on replica B (warming B's 60-second
    document cache with v1), the author edits to v2 on replica A (invalidating
    only A), and the approval on B reads v1 from cache, stamps the approver onto
    it and writes it back. The edit is gone AND v1 is now marked approved — the
    shape a human signed is not the shape in effect, which is the one thing this
    act exists to make true.

    So the read's ``etag`` rides along as ``if_match`` and the kernel refuses the
    write if the stored document moved
    (:class:`~dna.kernel.errors.StaleDocumentWrite` → 409). Note where the guard
    is evaluated: at the ADAPTER, against the store. Re-reading and comparing
    HERE would go through the same stale cache and match v1 against v1.

    The refusal is the correct outcome, not a degradation — an approval that
    cannot see the shape it is approving is not an approval — and it is
    recoverable in one step: re-read the Kind and approve again.

    **The effect is conferred synchronously (i-090).** Registration happens only
    inside a Manifest Instance build, and NOTHING used to schedule one: the write
    below correctly invalidated the scope so the next build would be fresh, and
    then no build was ever asked for. The measured consequence was the sequence a
    human actually performs — approve, then immediately use the Kind — answering
    ``UnknownKindError: Kind 'Deal' is not registered on this source``, with the
    Kind becoming real at whatever later moment somebody happened to call a
    ``definitions``-family route on that replica. So this function now ends by
    calling :meth:`~dna.application.live.LiveDna.refresh_kinds`, roughly 60 ms,
    once per approval.

    Be precise about what that buys: it closes the case on **the replica that
    served the approval**, and only that one. Sibling replicas hold their own
    registries and are closed by the second mechanism —
    :meth:`~dna.application.live.LiveDna.ensure_kinds`, the TTL'd refresh the
    document routes go through — which bounds their lag at
    :data:`~dna.application.live.KIND_REFRESH_TTL_DEFAULT` seconds rather than
    leaving it indeterminate.
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
        live, scope=scope, kind=kind, tenant=tenant, allow_unattributed=False,
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
    # The token for the write below, taken from the spec AS READ — before the
    # merges, because what it has to identify is the document this approval
    # is based on, not the one it is about to produce.
    read_etag = spec_etag(spec)
    # MERGE, unlike the authoring door — and deliberately: this preserves the
    # proposal (proposed_by/proposed_at/created_at) that the other act recorded,
    # which is the half of the audit this act must not overwrite. The fields
    # below are the ONLY ones it touches.
    spec["approved_by"] = actor
    spec["approved_at"] = now
    # i-085 — approving CLEARS the revocation, and this is the only act that
    # does. It is what makes "reversible" a mechanism rather than a claim, and
    # it is why ``approval_state`` never has to arbitrate between two
    # caller-supplied timestamps: the two acts keep each other exclusive.
    #
    # REMOVED, not set to None. Measured: the KindDefinition port's schema is
    # derived from the typed spec dataclass, and ``str | None`` derives to
    # ``{"type": "string"}`` — so writing an explicit null vetoes the approval
    # at the write path (``spec.revoked_by: None is not of type 'string'``).
    # Absence is also the honester encoding: "this Kind is not revoked" and
    # "this Kind was never revoked" are the same fact, and ``approval_state``
    # reads both the same way.
    spec.pop("revoked_by", None)
    spec.pop("revoked_at", None)
    version = await live.kernel.write_document(
        scope, _KIND, name, {**raw, "spec": spec},
        # i-083 — see the docstring. Everything this write does not carry it
        # overwrites, so it must not land on a document that moved since the
        # read above. Refused (StaleDocumentWrite) rather than clobbering.
        if_match=read_etag,
    )
    # i-090 — CONFER THE EFFECT, in the act. See the docstring's closing
    # paragraph: without this the approval landed in the store and changed
    # nothing until some unrelated call happened to rebuild this scope.
    await live.refresh_kinds(scope)
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


async def revoke_kind_impl(
    live: Any, *, kind: str, tenant: str, actor: str, now: str,
) -> dict[str, Any]:
    """Revoke an authored Kind — the act that WITHDRAWS effect (i-085).

    The counterpart of :func:`approve_kind_impl`, and deliberately not its
    inverse. Un-approving would return the Kind to *never approved*, and a Kind
    that never registered is the PERMISSIVE state: its documents are accepted
    with no validation at all. So revoking by clearing the approval would switch
    the gate off rather than close it. Revoked is a THIRD state, recorded as its
    own fact:

        state            existing documents      new documents
        ---------------- ---------------------- ---------------------------
        never approved   —                       accepted WITHOUT validation
        approved         valid, routed           validated against the schema
        revoked          INVALID                 REFUSED

    What it does to documents that already exist: nothing. They are not deleted
    and not made unreadable — a read returns THE DOCUMENT, marked invalid
    (``status.valid == false``). Erasing them or refusing the read would destroy
    the ability to audit what existed, and the data did nothing wrong; the
    workspace changed its mind. In a LISTING they appear, marked, and never
    vanish, so revocation cannot be used to hide data without deleting it.

    **Reversible in one act.** Validity follows the Kind's CURRENT state, never
    a stamp on the document, so :func:`approve_kind_impl` clears the markers this
    sets and every existing document is valid again with nothing to migrate.

    ``approved_by`` is deliberately LEFT STANDING. Revoking is a third act, not
    an erasure of the second, and a record saying only "revoked by X" has lost
    the fact that somebody approved this Kind and it governed real documents for
    a while.

    ``actor`` is the REVOKER — the face's verified identity for THIS request,
    never a body field. ``tenant`` scopes the search to the caller's OWN
    namespaces exactly as approval does, so a neighbour's Kind answers 404 and
    "it exists but is not yours" cannot become a probe.

    **The write is GUARDED** (i-083), for the same reason approval is: this is a
    read-modify-write that persists ``{**raw, "spec": spec}``, so everything it
    did not read it overwrites. Unguarded, a revocation issued from a replica
    holding a stale cache would resurrect the shape that replica last saw AND
    mark it revoked. The read's ``etag`` rides along as ``if_match`` and the
    kernel refuses the write if the stored document moved
    (:class:`~dna.kernel.errors.StaleDocumentWrite` → 409); the remedy is one
    step — re-read and revoke again.

    Idempotent in shape but not in fact: a second revocation re-stamps the
    revoker and the timestamp, which is the honest record of what happened.

    **The door closes synchronously (i-090), and this is the dangerous half.**
    The revoked mark reaches the port only through a Manifest Instance build,
    and nothing used to schedule one — so a revocation landed in the store and
    the Kind went on accepting documents until some unrelated call rebuilt that
    scope, on each replica independently. Slow to TIGHTEN is the failure mode
    i-085 exists to prevent, so this function ends by calling
    :meth:`~dna.application.live.LiveDna.refresh_kinds`. As with approval that
    closes the serving replica only; the siblings are bounded by
    :meth:`~dna.application.live.LiveDna.ensure_kinds`' window.

    Raises :class:`AuthoredKindNotFound` (→ 404) when no document the CALLER
    owns exists under that Kind name, and ``ValueError`` (→ 400) for a missing
    tenant/actor or a malformed Kind name.
    """
    kind = _checked_kind_name(kind, verb="revoke")
    if not (tenant or "").strip():
        raise ValueError("tenant is required to revoke a Kind")
    actor = (actor or "").strip()
    if not actor:
        raise ValueError(
            "revocation records a verified identity and this request carries "
            "none — withdrawing a Kind marks every existing document of it "
            "invalid, and an act nobody signed cannot be audited"
        )

    scope = live.default_scope(tenant)
    name, namespace = await _authored_document_name(
        live, scope=scope, kind=kind, tenant=tenant, allow_unattributed=False,
        verb="revoke",
    )
    raw = await live.kernel.get_document(scope, _KIND, name)
    if not isinstance(raw, dict) or not raw:
        raise AuthoredKindNotFound(
            f"the authored Kind {kind!r} ({name!r}) is listed in scope {scope!r} "
            f"but its document could not be read"
        )

    spec = dict(raw.get("spec") or {})
    read_etag = spec_etag(spec)
    # MERGE, like the approval door and for the same reason — the proposal and
    # the approval are the other acts' halves of the audit, and this act must
    # not overwrite either.
    spec["revoked_by"] = actor
    spec["revoked_at"] = now
    version = await live.kernel.write_document(
        scope, _KIND, name, {**raw, "spec": spec},
        if_match=read_etag,
    )
    # i-090 — CLOSE THE DOOR, in the act, and this is the half that matters
    # most: a revocation that takes effect "eventually" keeps accepting
    # documents of a Kind the workspace has just withdrawn.
    await live.refresh_kinds(scope)
    return {
        "revoked": True,
        "kind": kind,
        "name": name,
        "namespace": namespace,
        "revoked_by": actor,
        "revoked_at": now,
        # Echoed so the caller sees the whole chain of acts in one response —
        # who proposed the shape, who conferred effect on it, and who has just
        # withdrawn it.
        "proposed_by": spec.get("proposed_by"),
        "approved_by": spec.get("approved_by"),
        "approved_at": spec.get("approved_at"),
        "version": version,
    }


async def _authored_kind_visibility(live: Any, *, tenant: str | None) -> Any:
    """A predicate ``(document_name) -> bool``: may this caller see that row?

    **No resolved tenant ⇒ no filter.** The same hinge
    :class:`~dna.kernel.write.namespace_gate.NamespaceOwnershipGate` uses for an
    unattributed write, and for the same reason: ``--auth none`` self-host and an
    explicit operator ``scope=`` call resolve no workspace, so there is nobody to
    own anything and a filter that demanded ownership would answer every
    self-hoster with an empty list. It rests on the same standing invariant — a
    hosted face never issues an unattributed request on a user's behalf.

    Otherwise a row is visible when the caller **owns the namespace half of its
    name** — except that a name with no ``--`` has no namespace half to test at
    all (every ``KindDefinition`` predating the authoring door, and every
    hand-written one, looks like this), so it is kept rather than split blindly.

    This used to carry a second, ``origin="local"`` pass whose only job was to
    spare INHERITED rows the ownership test — a curated base Kind consumed
    through ``parent_scope`` is nobody in this scope's to own. It was DEAD, and
    measured so twice (i-087): ``KindDefinition`` is a BOOTSTRAP Kind and
    ``Kernel._NON_INHERITABLE_KINDS`` unions ``_BOOTSTRAP_KINDS``, so
    :meth:`Kernel.query` skips both its catalog and its parent pass — over a
    child scope that really declares ``parent_scope`` and a parent that really
    holds an approved ``KindDefinition``, the parent's row appears in NONE of
    the three passes, so ``default - local`` is always empty and the exemption
    never fired. ONE condition would make it load-bearing again, and it is the
    one to restore it under: ``KindDefinition`` becoming ``scope_inheritable``.

    NEVER degrades to unfiltered: an unreadable registry raises
    :class:`NamespaceRegistryUnreadable` out of :func:`_owns` and an ambiguous
    one raises out of ``owns()`` — both refuse the whole listing, because a
    visibility decision made without the authorization record is not a
    decision."""
    if not (tenant or "").strip():
        return lambda name: True

    owns = await _owns(live, tenant)

    def visible(name: str) -> bool:
        if _NAME_SEP not in name:
            return True  # no namespace half to test.
        namespace, _kind_half = name.rsplit(_NAME_SEP, 1)
        return bool(namespace) and owns(namespace)

    return visible


def _authored_kind_summary(name: Any, spec: dict[str, Any]) -> dict[str, Any]:
    """The audit projection of one ``KindDefinition`` — ONE function, because
    the listing and the single-Kind read describe the same document.

    Two projections would be two vocabularies for one thing, and the drift
    lands on the reviewer: a field renamed in the roster but not in the detail
    (or given a different null convention) reads as two different documents.
    The detail route adds ``schema``/``traits`` ON TOP of this — it does not
    re-derive any field this returns."""
    approved_by = str(spec.get("approved_by") or "").strip()
    revoked_by = str(spec.get("revoked_by") or "").strip()
    return {
        "name": name,
        "kind": spec.get("target_kind"),
        "api_version": spec.get("target_api_version"),
        "namespace": spec.get("origin"),
        # i-085 — the STATE, because the boolean below cannot carry three
        # values and the two it collapses behave in OPPOSITE ways: a Kind that
        # was never approved accepts documents unvalidated, a revoked one
        # refuses them and marks the existing ones invalid. A reviewer reading
        # ``approved: false`` on both rows would be reading the same word for
        # the loosest and the tightest states in the system.
        "state": approval_state(spec),
        # Kept, and kept meaning exactly what it always meant: "is this Kind
        # currently conferring effect". A revoked Kind is not, so it is false
        # here too — the field did not change, the vocabulary grew beside it.
        "approved": bool(approved_by) and not revoked_by,
        # BOTH actors — a reviewer reading this is deciding whether to confer
        # effect, and "who proposed this" is the first thing that decision
        # needs. `proposed_by` is null for every document authored before the
        # field existed, and for a door that could not identify its caller; null
        # is the honest answer in both cases and is not the same fact as "the
        # two actors coincide".
        "proposed_by": (str(spec.get("proposed_by") or "").strip() or None),
        "proposed_at": spec.get("proposed_at"),
        "approved_by": approved_by or None,
        "approved_at": spec.get("approved_at"),
        # The third act, projected beside the other two. Null on every document
        # that was never revoked — the honest answer, and not the same fact as
        # "revoked by nobody".
        "revoked_by": revoked_by or None,
        "revoked_at": spec.get("revoked_at"),
        "created_at": spec.get("created_at"),
    }


async def list_authored_kinds_impl(
    live: Any, *, tenant: str | None = None, scope: str | None = None,
) -> dict[str, Any]:
    """The ``KindDefinition`` documents in the caller's scope that the CALLER
    may see, with their approval state — the audit surface the authoring door
    exists to produce.

    Reads DOCUMENTS, not the registry: an unapproved Kind is precisely the one
    the registry does not have, so a registry-backed listing would show every
    Kind except the ones a reviewer needs to see.

    **Filtered to the caller** (:func:`_authored_kind_visibility`). A scope is
    SHARED by default — with multi-workspace off ``LiveDna.default_scope`` hands
    every workspace the same ``base_scope`` — and unfiltered this route handed a
    caller its neighbours' Kind names, their namespaces and their
    ``proposed_by``/``approved_by``, which are identity strings. That
    contradicted its own sibling: the approval door answers 404 for a
    neighbour's Kind precisely so that "it exists but is not yours" cannot
    become a probe for what the neighbours are authoring, and the listing gave
    away more than that 404 withheld.

    The "but this is also the operator's audit view" objection is the
    conflation, not the counter-argument: an operator view needs different
    authorization, a different result set (every workspace) and probably a
    different shape. Serving it by leaving the TENANT route unfiltered makes the
    tenant's default the operator's power.

    Raises :class:`NamespaceRegistryUnreadable` (→ 503) when ownership cannot be
    resolved, and ``NamespaceOwnershipError`` (→ 403) for a doubly-claimed
    namespace. Neither degrades to an unfiltered list.
    """
    sc = scope or live.default_scope(tenant)
    visible = await _authored_kind_visibility(live, tenant=tenant)
    kinds: list[dict[str, Any]] = []
    async for raw in live.kernel.query(sc, _KIND, tenant=tenant):
        if not isinstance(raw, dict):
            continue
        spec = raw.get("spec") or {}
        meta = raw.get("metadata") or {}
        name = meta.get("name") or raw.get("name")
        if not visible(str(name or "")):
            continue
        kinds.append(_authored_kind_summary(name, spec))
    return {"scope": sc, "kinds": kinds}


async def get_authored_kind_impl(
    live: Any, *, kind: str, tenant: str | None = None, scope: str | None = None,
) -> dict[str, Any]:
    """ONE authored Kind, in full — the summary the listing publishes PLUS the
    ``schema`` and the ``traits``.

    The listing deliberately projects ten summary fields and NOT ``spec.schema``
    (it is a roster, and a roster that inlined every JSON Schema would be
    unreadable), which left a reviewer deciding whether to confer effect unable
    to see what they would be conferring it on. Registration is what gives a
    Kind schema validation and storage routing, so "should this take effect?" is
    a question about the schema; this is the route that answers it.

    The shape is the listing's own (:func:`_authored_kind_summary`), literally
    the same projection function, plus the two stored fields it omits. Nothing
    is synthesized: ``schema`` and ``traits`` are read off the document exactly
    as :func:`author_kind_impl` wrote them, and a document authored before
    ``traits`` existed reads back ``[]`` rather than a guess.

    **Strictly more data than the listing, so at least as tight a filter.**
    Ownership is resolved by :func:`_authored_document_name` — the same
    ``owner_of`` walk over the same ``KindNamespace`` claims that
    :class:`~dna.kernel.write.namespace_gate.NamespaceOwnershipGate` decides
    WRITES with — and a Kind the caller does not own is dropped, so a stranger's
    Kind is a :class:`AuthoredKindNotFound` indistinguishable from a Kind nobody
    ever authored. That is the approval door's decision, inherited rather than
    re-argued: "it exists but is not yours" is a probe for what the neighbours
    are authoring, and this door would answer that probe with their data model.

    An unattributed request (no resolved tenant) is NOT filtered, for the same
    reason the listing's is not — see :func:`_authored_document_name`.

    Raises ``ValueError`` (→ 400) for a Kind name that is not a CamelCase
    identifier — ``kind`` arrives from the URL PATH and the guard is the shared
    :func:`_checked_kind_name`, not a copy — or for a Kind the caller declared
    under two of its own namespaces; :class:`AuthoredKindNotFound` (→ 404);
    :class:`NamespaceRegistryUnreadable` (→ 503) and ``NamespaceOwnershipError``
    (→ 403) when ownership cannot be decided. None of them degrades to answering
    with the document.
    """
    kind = _checked_kind_name(kind, verb="read")
    sc = scope or live.default_scope(tenant)
    name, _namespace = await _authored_document_name(
        live, scope=sc, kind=kind, tenant=tenant, verb="read",
        # The read is the door that WANTS the unfiltered lane when nothing
        # resolves: an operator ``scope=`` call and a self-host have no
        # workspace, and answering them "not found" for their own document
        # would be a filter with nobody to filter for. Stated here rather than
        # inherited from a default — the sibling door's answer is the opposite.
        allow_unattributed=True,
    )
    raw = await live.kernel.get_document(sc, _KIND, name)
    if not isinstance(raw, dict) or not raw:
        # The query above found the name, so this is a store that lost the
        # document between two reads. Same verdict the approval door gives for
        # the same race: there is nothing here to read.
        raise AuthoredKindNotFound(
            f"the authored Kind {kind!r} ({name!r}) is listed in scope {sc!r} "
            f"but its document could not be read"
        )
    spec = raw.get("spec") or {}
    schema = spec.get("schema")
    return {
        **_authored_kind_summary(name, spec),
        # The point of the route. ``None`` rather than ``{}`` for a document
        # that stored no schema (or stored a non-object where one belongs):
        # "there is no schema here" and "the schema is the empty object" are
        # different facts, and a reviewer must not be shown the second when the
        # first is true.
        "schema": schema if isinstance(schema, dict) else None,
        # Stored as a list by the authoring door and read back as one. Absent on
        # a document that predates the field — ``[]`` is what the authoring door
        # itself writes for "no traits", so it is the document's own vocabulary
        # for the fact, not an invention of this projection.
        "traits": [str(t) for t in (spec.get("traits") or [])],
    }
