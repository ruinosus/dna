"""Story ``s-aob-port-contract`` — the ``ActOnBehalfPort`` contract.

The provider-agnostic "act on behalf of the user" seam (ADR-act-on-behalf-port
§4). These are SHAPE tests: the contract must be instantiable by a fake provider,
``ActContext`` must carry an OPTIONAL ``raw_token`` (Microsoft needs it as the OBO
assertion; Google OAuth/DWD does not — that asymmetry is the whole point), and
``UserCredential`` must be the request-lifetime output of step (A) that a
capability adapter (step B) consumes without seeing the acquire mechanism.

No provider machinery here — just that the abstraction is well-formed and a fake
satisfies it (the same pure-core, no-network style as ``test_mcp_auth.py``).
"""
from __future__ import annotations

import asyncio
import dataclasses

import pytest

from dna_cli.act_on_behalf import (
    ActContext,
    ActOnBehalfPort,
    ActOnBehalfUnavailable,
    UserCredential,
)


def _ctx(**over) -> ActContext:
    base = dict(
        provider_hint="microsoft",
        tenant="ws-1",
        subject="user-oid-1",
        raw_token="eyJ.inbound.sig",
        claims={"tid": "tid-1"},
    )
    base.update(over)
    return ActContext(**base)


# ── ActContext ─────────────────────────────────────────────────────────────


def test_act_context_carries_the_verified_inbound_shape():
    ctx = _ctx()
    assert ctx.provider_hint == "microsoft"
    assert ctx.tenant == "ws-1"
    assert ctx.subject == "user-oid-1"
    assert ctx.raw_token == "eyJ.inbound.sig"
    assert ctx.claims["tid"] == "tid-1"


def test_act_context_raw_token_is_optional_the_asymmetry():
    """The concrete proof the port abstracts the OUTCOME, not Microsoft's
    mechanism: a Google identity has no inbound assertion to exchange, so
    ``raw_token`` is Optional and defaults to ``None``."""
    ctx = ActContext(
        provider_hint="google", tenant="ws-1", subject="u@example.test",
        claims={"hd": "example.test"},
    )
    assert ctx.raw_token is None  # Google path needs no inbound assertion.


def test_act_context_is_frozen():
    ctx = _ctx()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.raw_token = "mutated"  # type: ignore[misc]


# ── UserCredential ─────────────────────────────────────────────────────────


def test_user_credential_is_the_common_step_a_output():
    cred = UserCredential(
        bearer="token-b", api_base="https://graph.microsoft.com/v1.0",
        expires_at=1_800_000_000.0,
    )
    assert cred.bearer == "token-b"
    assert cred.api_base.startswith("https://")
    assert cred.expires_at > 0


def test_user_credential_is_frozen():
    cred = UserCredential(bearer="t", api_base="https://x", expires_at=1.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cred.bearer = "leak"  # type: ignore[misc]


# ── the Protocol — a fake provider satisfies it ────────────────────────────


class _FakeProvider:
    """A minimal provider that structurally satisfies ``ActOnBehalfPort``."""

    provider = "fake"

    def supports(self, capability: str) -> bool:
        return capability == "calendar"

    async def credential_for(self, ctx, capability, scopes):
        if not self.supports(capability):
            raise ActOnBehalfUnavailable(
                f"the fake provider does not support {capability!r}."
            )
        return UserCredential(
            bearer="fake-token", api_base="https://api.fake.test", expires_at=1.0,
        )


def test_a_fake_provider_is_a_structural_actonbehalfport():
    prov = _FakeProvider()
    assert isinstance(prov, ActOnBehalfPort)  # runtime_checkable Protocol.


def test_supports_and_credential_for_round_trip():
    prov = _FakeProvider()
    assert prov.supports("calendar") is True
    assert prov.supports("mail") is False
    cred = asyncio.run(prov.credential_for(_ctx(), "calendar", ["scope.read"]))
    assert isinstance(cred, UserCredential)
    assert cred.bearer == "fake-token"


def test_unsupported_capability_raises_act_on_behalf_unavailable():
    prov = _FakeProvider()
    with pytest.raises(ActOnBehalfUnavailable):
        asyncio.run(prov.credential_for(_ctx(), "mail", ["m.read"]))
