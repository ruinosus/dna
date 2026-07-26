"""Namespace ownership — who may declare a Kind under which ``apiVersion``
(i-080 item 1).

A Kind's identity is ``(api_version, kind)``: both halves are the registry key.
So a workspace that authors its own Kind needs its own ``api_version``
NAMESPACE, or two workspaces declaring ``Deal`` are the same Kind and one
silently validates against the other's schema. The founder's decision is that
the namespace is a **claimed, owned NAME** (``acme.example``) rather than the
workspace id embedded in the string — see ``KindNamespace``'s descriptor for
why (short version: the ``api_version`` participates in every document's
identity, so a database id baked into it makes renaming a workspace rewrite the
identity of everything it owns).

Namespacing buys one thing for free, and it is worth naming because it is the
reason a single decision closes two collisions: the alias convention is
``<owner>-<kebab(kind)>`` and the alias is declared globally unique, so an
``api_version`` that carries the owner carries it into the alias too — and the
alias is the wire key of ``dep_filters`` and ``LayerPolicy``. The convention is
carried by AUTHORS, though, not by the kernel: ``spec.alias`` on a
``KindDefinition`` is a required, author-supplied string. What makes the win
real is the duplicate-alias guard now running for store-loaded Kinds (i-080
item 2) — a second workspace typing the first one's alias is refused loudly
instead of registering beside it.

This module is pure: the string algebra plus the ownership verdict over a list
of claim rows. The enforcer that reaches the store lives in
:mod:`dna.kernel.write.namespace_gate`.
"""
from __future__ import annotations

from typing import Any, Iterable

from dna.kernel.protocols import LayerPolicyViolationError

__all__ = [
    "NamespaceOwnershipError",
    "OwnershipVerdict",
    "is_reserved",
    "namespace_chain",
    "namespace_of",
    "owner_of",
    "reserved_namespaces",
]


class NamespaceOwnershipError(LayerPolicyViolationError):
    """A write tried to declare a Kind in a namespace its author does not own.

    Deliberately a subclass of :class:`LayerPolicyViolationError` rather than a
    new top-level refusal. It is enforced at the SAME write-path boundary, it is
    the same kind of verdict ("the policy for this write says no"), and every
    face already maps that class to the honest client refusal (HTTP 403) — so
    the reason reaches the caller with no new wiring, while the distinct class
    keeps ``except NamespaceOwnershipError`` available to anything that wants to
    tell the two apart."""


def namespace_of(api_version: str | None) -> str:
    """The namespace an ``api_version`` belongs to: everything before the
    VERSION segment.

    ``acme.example/v1`` → ``acme.example``;
    ``github.com/ruinosus/dna/helix/v1`` → ``github.com/ruinosus/dna/helix``.

    An ``api_version`` with no ``/`` has no namespace and yields ``""`` — which
    every caller here treats as unownable, never as a wildcard."""
    parts = [p for p in (api_version or "").split("/") if p]
    return "/".join(parts[:-1]) if len(parts) >= 2 else ""


def namespace_chain(namespace: str) -> list[str]:
    """``namespace`` and its parents, MOST SPECIFIC FIRST.

    ``a/b/c`` → ``["a/b/c", "a/b", "a"]``. This is what makes a claim a PREFIX:
    claiming ``acme.example`` covers ``acme.example/crm/v1``, and a longer claim
    on ``acme.example/crm`` overrides it for that branch alone."""
    parts = [p for p in (namespace or "").split("/") if p]
    return ["/".join(parts[:i]) for i in range(len(parts), 0, -1)]


def reserved_namespaces(ports: Iterable[Any]) -> frozenset[str]:
    """The namespaces nobody may claim — DERIVED from the live registry.

    A namespace is reserved when a Kind registered FROM CODE lives in it: an
    extension class or a builtin ``*.kind.yaml`` descriptor. That is deliberate
    in both directions:

    * it is not a hardcoded list, so ``github.com/ruinosus/dna/**`` and every
      standard DNA consumes byte-faithful under its owner's name
      (``agents.md``, ``agentskills.io``, ``soulspec.org``, ``presidio``,
      ``mif-spec.dev``) are protected the day their Kind registers, and the list
      cannot drift from reality because there is no list;
    * PER-SCOPE declarative ports are excluded — otherwise the first Kind a
      workspace declared would reserve its own namespace against its own owner
      and the second Kind would be refused. It is the same discriminator
      ``port_for`` and the i-195 guard already use.
    """
    out = set()
    for port in ports:
        is_per_scope = bool(getattr(port, "__declarative__", False)) and not bool(
            getattr(port, "__builtin_descriptor__", False)
        )
        if is_per_scope:
            continue
        ns = namespace_of(getattr(port, "api_version", ""))
        if ns:
            out.add(ns)
    return frozenset(out)


def is_reserved(namespace: str, reserved: frozenset[str]) -> str | None:
    """The reserved namespace ``namespace`` falls under, or ``None``.

    A DESCENDANT of a reserved namespace is reserved too: if
    ``github.com/ruinosus/dna/helix`` is occupied, nobody gets to squat on
    ``github.com/ruinosus/dna/helix/extra`` and inherit the neighbourhood."""
    for level in namespace_chain(namespace):
        if level in reserved:
            return level
    return None


class OwnershipVerdict:
    """The result of resolving a namespace against the claim registry.

    ``owner`` is ``None`` when nothing claims it. ``claimed_namespace`` is the
    prefix that actually matched, which is what the refusal message needs to be
    honest about (``acme.example`` may be why ``acme.example/crm/v1`` resolved)."""

    __slots__ = ("owner", "claimed_namespace")

    def __init__(self, owner: str | None, claimed_namespace: str | None) -> None:
        self.owner = owner
        self.claimed_namespace = claimed_namespace

    def __repr__(self) -> str:  # pragma: no cover — debugging aid
        return (
            f"OwnershipVerdict(owner={self.owner!r}, "
            f"claimed_namespace={self.claimed_namespace!r})"
        )


def owner_of(namespace: str, claims: Iterable[dict[str, Any]]) -> OwnershipVerdict:
    """Resolve ``namespace`` against ``claims`` (raw ``KindNamespace`` rows).

    Walks :func:`namespace_chain` most-specific-first and stops at the first
    level anything claims, so a claim on a sub-namespace overrides the claim on
    its parent — the ordinary delegation shape.

    Two claims on the SAME level naming different owners raise
    :class:`NamespaceOwnershipError` rather than picking one. An ambiguous
    authorization record is not a tie to be broken: whichever way it were
    broken, one of the two workspaces would be silently writing into a namespace
    the registry also says belongs to somebody else."""
    rows = [r for r in claims if isinstance(r, dict)]
    for level in namespace_chain(namespace):
        owners = {
            str(owner)
            for owner in (
                (r.get("spec") or {}).get("owner")
                for r in rows
                if (r.get("spec") or {}).get("namespace") == level
            )
            if owner
        }
        if not owners:
            continue
        if len(owners) > 1:
            raise NamespaceOwnershipError(
                f"namespace {level!r} is claimed by {len(owners)} different "
                f"workspaces ({', '.join(sorted(owners))}). Refusing every "
                f"write under it until exactly one KindNamespace claim remains "
                f"— resolving an ambiguous ownership record by picking one "
                f"would let a workspace author Kinds in a namespace the "
                f"registry also says belongs to somebody else."
            )
        return OwnershipVerdict(owners.pop(), level)
    return OwnershipVerdict(None, None)
