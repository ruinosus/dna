"""NamespaceOwnershipGate — the write-time half of namespace ownership
(i-080 item 1).

The pure algebra (what a namespace is, which are reserved, who owns one) lives
in :mod:`dna.kernel.kinds.namespaces`. This is the part that reaches the store
and produces the verdict, wired into ``WritePipeline.write`` **immediately
before the LayerPolicy check** so one boundary governs both — which is where the
founder asked for it, and the only place where the writer's identity, the target
namespace and the registry are all in hand at once.

**What it gates.** A write of a ``KindDefinition`` instance, and nothing else.
Declaring a Kind is what CLAIMS a namespace; USING one is not. A workspace
writing a ``Story`` under ``…/sdlc/v1`` is ordinary traffic and stays
ungated — gating it would mean no workspace could write any instance of any
Kind DNA ships.

**Who the writer is.** The workspace the write is attributed to, resolved from
two existing kernel concepts and nothing new:

1. the write's EFFECTIVE TENANT — the explicit ``tenant=`` argument, else the
   ``kernel.tenant`` binding a hosted face sets per request (``with_tenant``);
2. failing that, the scope's OWN declared owner — ``Genome.spec.owner_tenant``,
   the field a tenant-published scope already carries. This is what makes a
   tenant-authored Kind attributable at all: ``KindDefinition`` is structurally
   non-overlayable, so a workspace's Kind is authored at the BASE layer of a
   scope the workspace owns, which carries no ``tenant`` argument.

**An unattributed write is not gated.** No effective tenant and no declared
scope owner means the platform operator's own write — the self-host shape (one
tenant, a laptop, `dna` on the CLI), where there is no second party to protect a
namespace from and where the operator can register any Kind in Python anyway.
This is the back-compat hinge: every existing write path in this repo is
unattributed, so nothing that works today stops working. It rests on one
standing invariant, which predates this gate and is load-bearing for the whole
tenancy model: **a hosted face never issues an unattributed write on behalf of a
user** — ``tenant=None`` means "write the shared base", not "write as nobody".

**An unclaimed namespace is REFUSED for an attributed writer.** Letting the
first writer squat would be a land-grab race with no audit trail, on a decision
(who owns a name) whose whole point is that it is recorded. Claiming is one
instance.

**A read failure is a refusal, not a shrug.** If the claim registry cannot be
read we cannot tell an owner from a stranger, and the only safe answer to "may
this workspace declare a Kind here?" without evidence is no.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from dna.kernel.kinds.namespaces import (
    NamespaceOwnershipError,
    is_reserved,
    namespace_of,
    owner_of,
    reserved_namespaces,
)

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.collaborator_ports import NamespaceGateHost

logger = logging.getLogger(__name__)


class NamespaceOwnershipGate:
    """Refuses a ``KindDefinition`` write whose target namespace the writer does
    not own. One per kernel; stateless apart from the narrow host back-ref, so
    ``with_tenant`` re-instantiates it against the copy like every other
    collaborator."""

    def __init__(self, kernel: "NamespaceGateHost") -> None:
        self._k = kernel

    async def check(
        self, scope: str, kind: str, name: str, raw: dict, *,
        tenant: str | None,
    ) -> None:
        """Raise :class:`NamespaceOwnershipError` if this write would declare a
        Kind in a namespace the writer does not own. Silent otherwise."""
        from dna.kernel.models import TypedKindDefinition

        if kind != TypedKindDefinition.KIND or not isinstance(raw, dict):
            return
        target = (raw.get("spec") or {}).get("target_api_version")
        if not isinstance(target, str) or not target:
            return  # malformed; the KindDefinition parse refuses it with a
            # better message than this gate could give.

        writer = tenant or await self._scope_owner(scope)
        if not writer:
            return  # unattributed — the operator's own write. See the module
            # docstring for why this is the right default and what it rests on.

        namespace = namespace_of(target)
        if not namespace:
            raise NamespaceOwnershipError(
                f"cannot declare {name!r}: apiVersion {target!r} has no "
                f"namespace (it is a bare version). A workspace-authored Kind "
                f"must live under a namespace it owns, e.g. "
                f"'acme.example/v1' — the namespace is what keeps two "
                f"workspaces' Kinds of the same name apart."
            )

        reserved = is_reserved(namespace, reserved_namespaces(self._k.kind_ports()))
        if reserved is not None:
            raise NamespaceOwnershipError(
                f"workspace {writer!r} may not declare Kind "
                f"{(raw.get('spec') or {}).get('target_kind')!r} under "
                f"apiVersion {target!r}: the namespace {reserved!r} is "
                f"RESERVED — Kinds registered from code already live in it, so "
                f"declaring here would place a workspace Kind inside a system "
                f"namespace and take its alias space with it. Reserved "
                f"namespaces are not a list; they are wherever a built-in Kind "
                f"is registered. Declare under a namespace you own instead."
            )

        try:
            claims = await self._k.kind_namespaces()
        except Exception as e:  # noqa: BLE001 — see the module docstring
            logger.warning(
                "namespace ownership: the KindNamespace registry could not be "
                "read for scope %r (refusing the write — an unverifiable "
                "claim is not an approved one): %s", scope, e,
            )
            raise NamespaceOwnershipError(
                f"cannot verify that workspace {writer!r} owns the namespace "
                f"of apiVersion {target!r}: the KindNamespace registry is "
                f"unreadable. Refusing rather than assuming — a namespace "
                f"claim is an authorization record, and an unreadable one is "
                f"not a granted one."
            ) from e

        verdict = owner_of(namespace, claims)
        if verdict.owner is None:
            raise NamespaceOwnershipError(
                f"workspace {writer!r} may not declare Kinds under apiVersion "
                f"{target!r}: nothing claims the namespace {namespace!r}. "
                f"Namespaces are claimed, not taken — write a KindNamespace "
                f"instance (namespace: {namespace!r}, owner: {writer!r}) "
                f"first. Refusing an unclaimed namespace keeps 'who owns this "
                f"name' a recorded decision instead of a race between writers."
            )
        if verdict.owner != writer:
            raise NamespaceOwnershipError(
                f"workspace {writer!r} may not declare Kinds under apiVersion "
                f"{target!r}: the namespace {verdict.claimed_namespace!r} is "
                f"owned by workspace {verdict.owner!r}. The apiVersion is half "
                f"of a Kind's identity, so declaring here would define a Kind "
                f"inside somebody else's namespace — and take a globally "
                f"unique alias in it."
            )

    async def _scope_owner(self, scope: str) -> str | None:
        """The workspace a scope declares itself published by —
        ``Genome.spec.owner_tenant`` on the scope's root instance.

        Fail-soft to ``None`` (logged at debug): an unreadable base instance
        means the write is unattributed, which is the same verdict as a scope
        with no declared owner, and is the posture the LayerPolicy check
        already takes for the same read. It is not a hole: the ATTRIBUTED path
        that matters — a hosted face writing with the caller's workspace bound —
        never reaches here, because ``tenant`` already answered the question."""
        try:
            mi = await self._k._base_instance_cached_async(scope)
        except Exception as e:  # noqa: BLE001
            logger.debug(
                "namespace ownership: base instance unavailable for scope %r "
                "(write treated as unattributed): %r", scope, e,
            )
            return None
        root = getattr(mi, "root", None)
        spec = getattr(root, "spec", None) if root is not None else None
        owner: Any = None
        if isinstance(spec, dict):
            owner = spec.get("owner_tenant")
        elif spec is not None:
            owner = getattr(spec, "owner_tenant", None)
        return str(owner) if owner else None
