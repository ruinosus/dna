"""Usage test for the DNA REST Python client — drives the named read methods
against an ``httpx.MockTransport`` (no live server), asserting method, URL, path
substitution, query params (incl. client-level defaults), the bearer header, and
that it unwraps success + raises :class:`DnaApiError` on a non-2xx.
"""
from __future__ import annotations

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
