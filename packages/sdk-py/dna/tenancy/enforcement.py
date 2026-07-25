"""``dna.tenancy.enforcement`` — the workspace-boundary SWITCH, as pure policy.

:mod:`dna.tenancy.resolution` decides *which workspace* a verified identity may
run against, and denies the request when the answer is "none" (fail-closed).
That boundary is the crown jewel the moment a second identity exists. It is also,
for a **single-operator deployment**, a door with no key: an operator who has not
created a `WorkspaceMembership` for themselves is denied the entire tenant-scoped
surface — the shared memory, the registry, the whole SDLC board — even though
they are the only person the deployment serves.

This module is the explicit, configurable way out, and nothing more:

* **the mode** — :func:`workspace_enforcement`, read from
  :data:`WORKSPACE_ENFORCEMENT_ENV`. The default is :data:`ENFORCE` and the
  opt-out is a single literal (:data:`OPEN`). It is deliberately **not** a
  boolean: ``=0`` reads as "enforcement off" to one operator and "not open" to
  another, and only one of those misreadings is safe. Unset, empty, misspelt,
  falsey *and* truthy values all enforce.
* **the announcement** — :func:`enforcement_boot_message`, the line a door must
  emit at boot when it is running open (or ignoring a value it did not
  recognise). An operator must never learn this from behaviour.
* **the metering key** — :func:`unenforced_metering_key`, what usage counts
  against when the boundary is open and no workspace answered for the request.

What the switch does NOT touch is as important as what it does. It governs
exactly one decision: whether a resolved-or-absent workspace *denies* the call.
Token verification, the per-provider identity derivation, the personal-identity
guard, scope binding and the plan/quota gates are all untouched — an open
boundary is not an unauthenticated one, and it is emphatically not an unmetered
one ("só registra os chamados" is the requirement, not "stop counting").

The knob is vendor-neutral by construction: it names a *property of the
deployment* (is this one operator, or many?), not a customer, a host or a plan.
"""
from __future__ import annotations

import os
from typing import Any, Mapping

from dna.memory.personal import PERSONAL_IMPLICIT_FAMILY, personal_tenant
from dna.tenancy.accounts import provider_type_from_claims
from dna.tenancy.resolution import identity_from_token

#: The environment variable that selects the mode. Named for the *boundary*, not
#: for a vendor or a lane, so it means the same thing to any self-hoster.
WORKSPACE_ENFORCEMENT_ENV = "DNA_WORKSPACE_ENFORCEMENT"

#: The DEFAULT. Today's behaviour, unchanged: a verified identity with no active
#: membership is denied the tenant-scoped surface.
ENFORCE = "enforce"

#: The opt-out. The membership boundary stops DENYING; everything else — token
#: verification, identity derivation, scope binding, plan + quota — stands.
OPEN = "open"

#: Every value that means anything at all. Anything else is a typo, and a typo
#: must land on the SAFE side (and say so — see :func:`enforcement_boot_message`).
KNOWN_MODES = frozenset({ENFORCE, OPEN})


class UnmeterableIdentityError(PermissionError):
    """An authenticated request resolved no workspace AND carries no durable
    subject, so its usage cannot be attributed to anyone.

    Raised by :func:`unenforced_metering_key` and surfaced by each face as an
    access denial. It is deliberately its own error — not
    :class:`~dna.memory.personal.PersonalIdentityRequired` — so a face maps it to
    the right status and an operator is not told to set ``DNA_PERSONAL_ID`` for
    something that has nothing to do with personal memory.

    Why this stays fail-closed even with the boundary OPEN: the alternative is a
    shared metering bucket, which means one identity's usage counted against
    another's. The opt-out exists to stop denying *access*, never to start
    mis-attributing *usage*.
    """


def _raw_mode(env: Mapping[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    return (env.get(WORKSPACE_ENFORCEMENT_ENV) or "").strip()


def workspace_enforcement(env: Mapping[str, str] | None = None) -> str:
    """The mode this process runs in — :data:`ENFORCE` (default) or :data:`OPEN`.

    Case-insensitive and trimmed, matched against :data:`KNOWN_MODES`. **Every**
    other input — unset, empty, whitespace, a misspelling, ``0``/``false``/``off``
    *and* ``1``/``true``/``on`` — resolves to :data:`ENFORCE`. There is exactly
    one string that opens the boundary, and it is not a boolean.

    Read per call rather than cached, so the mode is testable and a corrected
    environment does not need a code change to be observed.
    """
    raw = _raw_mode(env).lower()
    return raw if raw in KNOWN_MODES else ENFORCE


def enforcement_is_open(env: Mapping[str, str] | None = None) -> bool:
    """True only when the workspace boundary has been EXPLICITLY opened."""
    return workspace_enforcement(env) == OPEN


def enforcement_boot_message(env: Mapping[str, str] | None = None) -> str | None:
    """The line a door must emit at boot, or ``None`` when nothing needs saying.

    Two cases speak:

    * the boundary is **open** — the loud one. It names the knob, states what is
      no longer enforced, and states what still is (so the line cannot be read as
      "nothing is enforced any more");
    * a value was set that this build does not recognise — silently enforcing
      would be correct but dishonest: the operator asked for *something*. The
      line quotes what they wrote and says it was ignored.

    An unset knob, or an explicit ``enforce``, says nothing — a door in its
    default posture should not add noise to every boot.
    """
    raw = _raw_mode(env)
    if not raw:
        return None
    if raw.lower() not in KNOWN_MODES:
        return (
            f"{WORKSPACE_ENFORCEMENT_ENV}={raw!r} is not a recognised value "
            f"(expected {ENFORCE!r} or {OPEN!r}) — IGNORING it and ENFORCING the "
            f"workspace boundary. Fix the value if you meant to open it."
        )
    if raw.lower() == ENFORCE:
        return None
    return (
        f"workspace enforcement is OPEN ({WORKSPACE_ENFORCEMENT_ENV}={OPEN}): a "
        "verified identity with no active workspace membership is SERVED instead "
        "of denied, and a workspace selector it names is taken at face value. "
        "Every call is still authenticated, scope-bound, plan-gated and METERED "
        "(usage with no workspace meters against the caller's own identity). "
        "This is intended for a single-operator deployment — unset the variable "
        "to restore the fail-closed boundary."
    )


def unenforced_metering_key(claims: dict[str, Any] | None) -> str:
    """The metering key for an authenticated request that resolved NO workspace.

    With the boundary open, a call can be served without a workspace answering
    for it — but "só registra os chamados" is the whole requirement, so it must
    still count against *someone*. The only thing such a request is guaranteed to
    carry is its **verified identity**, so that is what it meters against.

    The key is the reserved identity partition
    (:func:`~dna.memory.personal.personal_tenant`) built from:

    * the **durable subject** the membership resolver itself would use
      (:func:`~dna.tenancy.resolution.identity_from_token`, i-072's one
      per-provider derivation — Entra ``oid``, a consumer-lane IdP's ``sub``), and
    * the **provider type** as the namespace segment, so two IdPs whose subjects
      happen to share a literal can never share a meter.

    That satisfies the three properties the key needs, by construction:

    1. **stable** — it is a verified, durable claim, identical on every call;
    2. **collision-free across identities** — different subjects give different
       keys, and different providers give different namespaces;
    3. **never another identity's** — it is derived only from *this* token, and a
       token with no durable subject raises :class:`UnmeterableIdentityError`
       instead of falling into a shared bucket.

    It also cannot collide with a workspace's meter: ``personal:`` is a reserved
    tenant scheme that a caller-supplied tenant is refused
    (``assert_no_personal_override``), so no workspace id can ever look like this.

    One deliberate consequence: an identity's workspace-less usage meters into the
    SAME bucket as that identity's personal-memory usage. That is the honest
    reading — one identity, one meter — and it avoids minting a parallel counter
    that a billing job would then have to reconcile.
    """
    identity = identity_from_token(claims)
    if not identity.oid:
        raise UnmeterableIdentityError(
            "this request resolved no workspace and its token carries no durable "
            "identity claim, so its usage cannot be attributed — access denied "
            "(pooling it into a shared meter would count one identity's usage "
            "against another's)."
        )
    family = provider_type_from_claims(claims) or PERSONAL_IMPLICIT_FAMILY
    return personal_tenant(identity.oid, family=family)


__all__ = [
    "ENFORCE",
    "KNOWN_MODES",
    "OPEN",
    "WORKSPACE_ENFORCEMENT_ENV",
    "UnmeterableIdentityError",
    "enforcement_boot_message",
    "enforcement_is_open",
    "unenforced_metering_key",
    "workspace_enforcement",
]
