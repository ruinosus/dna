"""Story ``s-workspace-enforcement-opt-out`` — the workspace-enforcement SWITCH.

The pure policy behind the opt-out (``dna.tenancy.enforcement``): which mode a
door runs in, what it must announce at boot, and — when the boundary is open and
no workspace answers for a request — what the METERING key becomes.

The single most important assertion in this file is
:func:`test_default_is_enforce`: an unset / empty / misspelt / falsey value must
keep today's fail-closed behaviour EXACTLY. Getting that backwards silently
opens a multi-tenant deployment, so the opt-out is an explicit single-token
allowlist rather than a boolean — ``off``/``0``/``false``/``no`` all ENFORCE.

(No ``dna_cli`` import here — the sdk-py CI job does not install it.)
"""
from __future__ import annotations

import pytest

from dna.memory.personal import PersonalIdentityRequired, personal_tenant
from dna.tenancy.enforcement import (
    ENFORCE,
    OPEN,
    WORKSPACE_ENFORCEMENT_ENV,
    UnmeterableIdentityError,
    enforcement_boot_message,
    enforcement_is_open,
    unenforced_metering_key,
    workspace_enforcement,
)


# ── 1. the default is ENFORCE (the one way this feature can cause harm) ─────


def test_default_is_enforce():
    """THE test. No knob → today's fail-closed boundary, unchanged."""
    assert workspace_enforcement({}) == ENFORCE
    assert enforcement_is_open({}) is False


@pytest.mark.parametrize(
    "raw",
    [
        "",            # set but empty
        "   ",         # whitespace only
        "0", "false", "off", "no",     # falsey spellings — NOT an opt-out
        "1", "true", "yes", "on",      # truthy spellings — NOT an opt-out either
        "opem", "opne", "opened", "openn", " open-ish",   # misspellings
        "enforce", "ENFORCE", " Enforce ",                 # the explicit default
        "none", "disabled", "unenforced",
    ],
)
def test_anything_but_the_opt_out_token_enforces(raw):
    """Unset, empty, misspelt, falsey AND truthy values all keep fail-closed.

    A boolean reading is deliberately refused: ``=0`` could mean "enforcement
    off" to one operator and "not open" to another, and only one of those two
    misreadings is safe. So exactly one literal opts out, and it is not a
    boolean."""
    env = {WORKSPACE_ENFORCEMENT_ENV: raw}
    assert workspace_enforcement(env) == ENFORCE
    assert enforcement_is_open(env) is False


@pytest.mark.parametrize("raw", ["open", "OPEN", "Open", "  open  "])
def test_the_opt_out_token_opens(raw):
    env = {WORKSPACE_ENFORCEMENT_ENV: raw}
    assert workspace_enforcement(env) == OPEN
    assert enforcement_is_open(env) is True


def test_reads_the_process_environment_by_default(monkeypatch):
    monkeypatch.delenv(WORKSPACE_ENFORCEMENT_ENV, raising=False)
    assert workspace_enforcement() == ENFORCE
    monkeypatch.setenv(WORKSPACE_ENFORCEMENT_ENV, OPEN)
    assert workspace_enforcement() == OPEN


# ── 2. loud, not silent ─────────────────────────────────────────────────────


def test_no_boot_message_when_enforcing():
    assert enforcement_boot_message({}) is None
    assert enforcement_boot_message({WORKSPACE_ENFORCEMENT_ENV: "enforce"}) is None


def test_open_boot_message_names_the_knob_and_the_consequence():
    msg = enforcement_boot_message({WORKSPACE_ENFORCEMENT_ENV: "open"})
    assert msg is not None
    assert WORKSPACE_ENFORCEMENT_ENV in msg
    assert "open" in msg.lower()
    # It must say what is actually true of the running door, not just echo env.
    assert "membership" in msg.lower()
    assert "metered" in msg.lower() or "metering" in msg.lower()


def test_unrecognized_value_is_announced_as_ignored():
    """A typo must not be silent: it enforces (safe) AND says it was ignored."""
    msg = enforcement_boot_message({WORKSPACE_ENFORCEMENT_ENV: "opem"})
    assert msg is not None
    assert "opem" in msg
    assert "enforc" in msg.lower()


# ── 3. the metering key when no workspace resolves ──────────────────────────
#
# Requirements: stable across calls for one identity, never colliding across
# identities, and never silently metering one identity against another's.

_ENTRA = {"oid": "oid-alice", "email": "alice@a.com", "tid": "org-a"}
_WORKOS = {"sub": "user_01JQGLUE", "_dna_provider_type": "workos"}
_WORKOS_FAMILY_ONLY = {"sub": "user_01JQGLUE", "_dna_provider_family": "workos"}


def test_metering_key_is_stable_for_one_identity():
    assert unenforced_metering_key(_ENTRA) == unenforced_metering_key(dict(_ENTRA))


def test_metering_key_never_collides_across_identities():
    a = unenforced_metering_key({"oid": "oid-alice"})
    b = unenforced_metering_key({"oid": "oid-bob"})
    assert a != b


def test_metering_key_never_collides_across_providers_on_the_same_literal():
    """An Entra ``oid`` and a WorkOS ``sub`` that happen to be the same string
    are two different humans — they must never share a meter."""
    same = "collide-me"
    entra = unenforced_metering_key({"oid": same})
    workos = unenforced_metering_key({"sub": same, "_dna_provider_type": "workos"})
    assert entra != workos


def test_metering_key_is_the_identity_partition_entra():
    """Entra keeps the bare ``personal:<oid>`` — one identity, one meter, shared
    with the same identity's personal-memory usage by design."""
    assert unenforced_metering_key(_ENTRA) == personal_tenant("oid-alice")


def test_metering_key_is_the_identity_partition_consumer_lane():
    assert unenforced_metering_key(_WORKOS) == personal_tenant(
        "user_01JQGLUE", family="workos"
    )
    # The single-env-provider Lane-B path stamps only the FAMILY — same key.
    assert unenforced_metering_key(_WORKOS_FAMILY_ONLY) == unenforced_metering_key(
        _WORKOS
    )


def test_metering_key_reads_the_durable_subject_per_provider():
    """A WorkOS token carries no ``oid``; its durable subject is ``sub``. The
    key must follow the SAME per-provider derivation the membership resolver
    uses (i-072), never a second one."""
    from dna.tenancy.resolution import identity_from_token

    assert identity_from_token(_WORKOS).oid == "user_01JQGLUE"
    assert "user_01JQGLUE" in unenforced_metering_key(_WORKOS)


def test_metering_key_can_never_be_a_workspace_id():
    """The key lives in the RESERVED ``personal:`` scheme, which a caller-supplied
    tenant is refused, so an identity meter can never be confused for (or collide
    with) a workspace's."""
    from dna.memory.personal import is_personal_tenant

    assert is_personal_tenant(unenforced_metering_key(_ENTRA))


@pytest.mark.parametrize(
    "claims",
    [None, {}, {"email": "no-subject@x.com"}, {"oid": "   "}, {"sub": "x"}],
)
def test_no_durable_subject_is_refused_never_pooled(claims):
    """An authenticated request with no durable subject cannot be metered per
    identity — and pooling it into a shared bucket would meter one identity's
    usage against another's. So it is DENIED even with the boundary open. (The
    last case is a bare ``sub`` with NO provider stamp: an unstamped token keeps
    the ``oid`` derivation, so its ``sub`` is not a durable subject here.)"""
    with pytest.raises(UnmeterableIdentityError):
        unenforced_metering_key(claims)


def test_unmeterable_is_not_swallowed_as_a_personal_memory_error():
    """It is its own error, so a face maps it to the right transport status and
    an operator is not told to set ``DNA_PERSONAL_ID``."""
    assert not issubclass(UnmeterableIdentityError, PersonalIdentityRequired)
    assert issubclass(UnmeterableIdentityError, PermissionError)
