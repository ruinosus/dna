"""Usage test for the DNA REST Python client — drives the named read methods
against an ``httpx.MockTransport`` (no live server), asserting method, URL, path
substitution, query params (incl. client-level defaults), the bearer header, and
that it unwraps success + raises :class:`DnaApiError` on a non-2xx.
"""
from __future__ import annotations

import json

import httpx
import pytest

from dna_client import DnaApiError, DnaClient


def _recorder(body: object, status: int = 200):
    """A MockTransport that records each request and returns a canned JSON body."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler), calls


BASE = "http://dna.test"


def test_health_unwraps_body():
    transport, calls = _recorder({"ok": True})
    with DnaClient(BASE, transport=transport) as dna:
        assert dna.health() == {"ok": True}
    assert calls[0].url.path == "/health"


def test_bearer_token_sent():
    transport, calls = _recorder({"agents": []})
    with DnaClient(BASE, token="sekret", transport=transport) as dna:
        dna.list_agents(scope="s")
    assert calls[0].headers["authorization"] == "Bearer sekret"


def test_scope_tenant_query_params():
    transport, calls = _recorder({"agents": []})
    with DnaClient(BASE, transport=transport) as dna:
        dna.list_agents(scope="dna-development", tenant="acme")
    url = calls[0].url
    assert url.path == "/v1/agents"
    assert url.params["scope"] == "dna-development"
    assert url.params["tenant"] == "acme"


def test_client_defaults_apply_and_per_call_overrides_win():
    transport, calls = _recorder({"memories": []})
    with DnaClient(BASE, tenant="acme", scope="base", transport=transport) as dna:
        dna.list_memories()               # uses defaults
        dna.list_memories(tenant="other")  # overrides tenant
    assert calls[0].url.params["tenant"] == "acme"
    assert calls[0].url.params["scope"] == "base"
    assert calls[1].url.params["tenant"] == "other"
    assert calls[1].url.params["scope"] == "base"


def test_none_params_are_dropped():
    transport, calls = _recorder({"agents": []})
    with DnaClient(BASE, transport=transport) as dna:
        dna.list_agents()  # no scope/tenant/defaults → empty query
    assert str(calls[0].url) == f"{BASE}/v1/agents"


def test_path_substitution_and_typed_query():
    transport, calls = _recorder({"ok": 1})
    with DnaClient(BASE, transport=transport) as dna:
        dna.agent_prompt("jarvis", scope="s")
        dna.get_project("my-proj")
        dna.search_memories("hello", k=3)
        dna.get_board("dna-development", recent=5)
        dna.get_board_item("dna-development", "s-foo")
    assert calls[0].url.path == "/v1/agents/jarvis/prompt"
    assert calls[1].url.path == "/v1/projects/my-proj"
    assert calls[2].url.path == "/v1/memories/search"
    assert calls[2].url.params["q"] == "hello"
    assert calls[2].url.params["k"] == "3"
    assert calls[3].url.params["recent"] == "5"
    assert calls[4].url.params["name"] == "s-foo"


def test_agent_prompt_explain_opt_in():
    # Provenance on the wire (i-045): explain is OPT-IN. The default call sends
    # NO explain param at all (the request is byte-identical to the historical
    # plain compose); explain=True sends explain=true.
    transport, calls = _recorder({"prompt": "p"})
    with DnaClient(BASE, transport=transport) as dna:
        dna.agent_prompt("jarvis", scope="s")
        dna.agent_prompt("jarvis", scope="s", explain=True)
        dna.agent_prompt("jarvis", scope="s", explain=False)
    assert "explain" not in calls[0].url.params
    assert calls[1].url.params["explain"] == "true"
    assert "explain" not in calls[2].url.params


def test_workspace_members_no_scope_tenant_default():
    # /v1/workspaces/* boundary routes do NOT take scope/tenant — the client
    # must not inject its defaults there.
    transport, calls = _recorder({"members": []})
    with DnaClient(BASE, tenant="acme", scope="base", transport=transport) as dna:
        dna.list_workspace_members("ws-1", actor_email="a@b.com")
    url = calls[0].url
    assert url.path == "/v1/workspaces/ws-1/members"
    assert "tenant" not in url.params
    assert "scope" not in url.params
    assert url.params["actor_email"] == "a@b.com"


def test_list_personal_memories_never_sends_a_tenant():
    # The personal read is IDENTITY-scoped: the partition comes from the
    # token, server-side. The client-level default `tenant` must not be
    # merged (sending one would imply a choice the caller does not have);
    # an explicit `scope` still travels.
    transport, calls = _recorder({"scope": "base", "partition": "personal",
                                  "memories": []})
    with DnaClient(BASE, tenant="acme", scope="base", transport=transport) as dna:
        dna.list_personal_memories(scope="concierge")
    url = calls[0].url
    assert url.path == "/v1/memories/personal"
    assert "tenant" not in url.params
    assert url.params["scope"] == "concierge"


def test_non_2xx_raises_dna_api_error():
    transport, _ = _recorder({"detail": "unknown project 'nope'"}, status=404)
    with DnaClient(BASE, transport=transport) as dna:
        with pytest.raises(DnaApiError) as exc:
            dna.get_project("nope")
    assert exc.value.status == 404
    assert "unknown project" in str(exc.value)


def test_request_reaches_full_surface_incl_writes():
    transport, calls = _recorder({"deleted": "s-foo"})
    with DnaClient(BASE, transport=transport) as dna:
        out = dna.request("DELETE", "/v1/memories/s-foo", params={"tenant": "acme"})
    assert out == {"deleted": "s-foo"}
    assert calls[0].method == "DELETE"
    assert calls[0].url.path == "/v1/memories/s-foo"
    assert calls[0].url.params["tenant"] == "acme"


# -- the named write surface -------------------------------------------------


def test_named_writes_use_the_right_verb_and_path():
    transport, calls = _recorder({"ok": 1})
    with DnaClient(BASE, transport=transport) as dna:
        dna.remember_memory("a lesson", scope="s")
        dna.delete_memory("s-foo", scope="s")
        dna.set_insight_state("i-1", "dismissed")
        dna.set_workspace_plan("w1", "pro")
        dna.revoke_workspace_member("w1", target_email="a@b.c")
        dna.remove_project_member("proj", "user@x.y", actor="boss@x.y")
    seen = [(c.method, c.url.path) for c in calls]
    assert seen == [
        ("POST", "/v1/memories"),
        ("DELETE", "/v1/memories/s-foo"),
        ("PATCH", "/v1/insights/i-1/state"),
        ("PUT", "/v1/workspace-plan"),
        ("POST", "/v1/workspaces/w1/members/revoke"),
        ("DELETE", "/v1/projects/proj/members/user@x.y"),
    ]


def test_write_body_drops_none_so_server_defaults_apply():
    transport, calls = _recorder({"ok": 1})
    with DnaClient(BASE, transport=transport) as dna:
        dna.create_workspace("Acme")  # slug + claims omitted
    body = json.loads(calls[0].content)
    assert body == {"name": "Acme"}, "None-valued optional keys must not be sent"


def test_write_body_carries_explicit_values():
    transport, calls = _recorder({"ok": 1})
    with DnaClient(BASE, transport=transport) as dna:
        dna.remember_memory("a lesson", area="ops", tags=["x"], affect="scar")
    body = json.loads(calls[0].content)
    assert body == {
        "summary": "a lesson", "area": "ops", "tags": ["x"],
        "affect": "scar", "owner": "portal",
    }


def test_workspace_boundary_writes_get_no_scope_tenant_default():
    # The workspace boundary is resolved from the caller's VERIFIED identity, so a
    # client-level tenant default must never leak onto these routes and imply the
    # caller may choose their own boundary.
    transport, calls = _recorder({"ok": 1})
    with DnaClient(BASE, tenant="acme", scope="base", transport=transport) as dna:
        dna.list_workspaces()
        dna.create_workspace("Acme")
        dna.accept_invites()
        dna.create_project("w1", "P")
        dna.create_invite("w1", "a@b.c")
        dna.provision_workspace_owner("w1")
        dna.set_workspace_plan("w1", "pro")
    for call in calls:
        assert "tenant" not in call.url.params, f"tenant leaked onto {call.url.path}"
        assert "scope" not in call.url.params, f"scope leaked onto {call.url.path}"


def test_scope_tenant_defaults_still_reach_the_scoped_writes():
    transport, calls = _recorder({"ok": 1})
    with DnaClient(BASE, tenant="acme", scope="base", transport=transport) as dna:
        dna.remember_memory("x")
        dna.set_project_member("proj", "u@x.y", "admin")
    for call in calls:
        assert call.url.params["tenant"] == "acme"
        assert call.url.params["scope"] == "base"


def test_provision_tenant_owner_takes_scope_but_never_tenant():
    # The tenant IS the {tid} path segment — a default tenant must not shadow it.
    transport, calls = _recorder({"ok": 1})
    with DnaClient(BASE, tenant="acme", scope="base", transport=transport) as dna:
        dna.provision_tenant_owner("tid-1", "u@x.y")
    assert calls[0].url.path == "/v1/tenants/tid-1/provision-owner"
    assert calls[0].url.params["scope"] == "base"
    assert "tenant" not in calls[0].url.params
