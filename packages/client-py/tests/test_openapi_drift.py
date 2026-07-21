"""OpenAPI drift guard — keeps the committed generation source in sync with the
live DNA REST API.

The clients (``packages/client-ts`` + ``packages/client-py``) are generated from
``docs/openapi.json``, which is dumped from the FastAPI app by
``scripts/dump_openapi.py``. If a route/param changes and nobody re-dumps the
spec, the clients silently drift from the API. This test re-dumps the schema from
the live app and asserts it equals the committed file — so a stale spec fails CI
with a clear "run `python scripts/dump_openapi.py`" message.

The second half of this module is the COVERAGE guard: every operation in the
spec — of any HTTP method — must have a named method on the client. See the
``_COVERED`` comment for why it is keyed by ``(method, path)`` rather than by
path, and why the read-only version of this guard was a blind spot.

It needs the REST API face importable (``dna-cli[api]`` + ``dna-sdk``); when
those are absent (a minimal ``pip install dna-client`` with no dev extras) it
SKIPS rather than fails, so the published package's own install never depends on
the repo. CI installs the dev extra, so the guard runs for real there.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Repo root = packages/client-py/tests/ → up 3. scripts/ + docs/openapi.json live there.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "scripts"
_SPEC = _REPO_ROOT / "docs" / "openapi.json"

if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def _load_dumper():
    """Import scripts/dump_openapi.py, skipping if the REST API face is absent."""
    pytest.importorskip(
        "fastapi",
        reason="the drift test needs the REST API face — install dna-client[dev] "
        "(pulls dna-cli[api] + dna-sdk).",
    )
    pytest.importorskip("dna_cli._rest_api", reason="dna-cli not importable")
    import dump_openapi  # noqa: WPS433 — repo dev script on sys.path

    return dump_openapi


def test_committed_openapi_matches_live_api():
    dump_openapi = _load_dumper()
    assert _SPEC.exists(), f"missing committed spec: {_SPEC}"
    committed = _SPEC.read_text(encoding="utf-8")
    live = dump_openapi.dump()
    assert committed == live, (
        "docs/openapi.json is stale — the DNA REST API changed without "
        "regenerating the client spec. Run `python scripts/dump_openapi.py` "
        "(and `cd packages/client-ts && bun run gen`), then commit."
    )


# ---------------------------------------------------------------------------
# Operation coverage — EVERY operation, not just the reads.
#
# This map is keyed by ``(HTTP METHOD, path)``, not by path, and is checked
# against every operation in the spec. That is deliberate: the previous version
# of this guard enumerated GET paths only and declared writes out of scope
# ("writes stay behind .request"), so a new write route entered the spec, the
# API and CI in total silence — which is exactly how POST /v1/workspaces and
# POST /v1/projects shipped with no client coverage at all. A guard that only
# watches the surface you already covered is not a guard.
#
# Adding an operation to the API now REQUIRES either a named client method here
# or an explicit, justified entry in _UNCOVERED below.
_COVERED: dict[tuple[str, str], str] = {
    # -- reads ---------------------------------------------------------------
    ("GET", "/health"): "health",
    ("GET", "/v1/agents"): "list_agents",
    ("GET", "/v1/agents/{name}/prompt"): "agent_prompt",
    ("GET", "/v1/tools"): "list_tools",
    ("GET", "/v1/memories"): "list_memories",
    ("GET", "/v1/memories/personal"): "list_personal_memories",
    ("GET", "/v1/memories/search"): "search_memories",
    ("GET", "/v1/sources"): "list_sources",
    ("GET", "/v1/insights"): "list_insights",
    ("GET", "/v1/insights/metrics"): "insight_metrics",
    ("GET", "/v1/orgs"): "list_orgs",
    ("GET", "/v1/projects"): "list_projects",
    ("GET", "/v1/projects/{slug}"): "get_project",
    ("GET", "/v1/projects/{slug}/members"): "list_project_members",
    ("GET", "/v1/repos"): "list_repos",
    ("GET", "/v1/board"): "get_board",
    ("GET", "/v1/board/item"): "get_board_item",
    ("GET", "/v1/workspaces"): "list_workspaces",
    ("GET", "/v1/workspaces/{workspace_id}/members"): "list_workspace_members",
    # -- writes --------------------------------------------------------------
    ("POST", "/v1/memories"): "remember_memory",
    ("POST", "/v1/memories/import"): "import_memories",
    ("DELETE", "/v1/memories/{name}"): "delete_memory",
    ("PATCH", "/v1/insights/{name}/state"): "set_insight_state",
    ("POST", "/v1/projects"): "create_project",
    ("POST", "/v1/projects/{slug}/members"): "set_project_member",
    ("DELETE", "/v1/projects/{slug}/members/{user}"): "remove_project_member",
    ("POST", "/v1/tenants/{tid}/provision-owner"): "provision_tenant_owner",
    ("PUT", "/v1/account-plan"): "set_account_plan",
    ("POST", "/v1/workspaces"): "create_workspace",
    ("POST", "/v1/workspaces/accept"): "accept_invites",
    ("POST", "/v1/workspaces/{workspace_id}/invites"): "create_invite",
    ("POST", "/v1/workspaces/{workspace_id}/members/revoke"): "revoke_workspace_member",
    ("POST", "/v1/workspaces/{workspace_id}/provision-owner"): "provision_workspace_owner",
}

# Operations DELIBERATELY left without a named client method. Each entry needs a
# comment saying WHY — "it's a write" is not a reason. Empty today: every one of
# the spec's 31 operations is a single, self-contained call that a named method
# can honestly express. An operation belongs here only if a named method would
# LIE about how usable it is (e.g. it needs a multi-step handshake, or a
# credential the client has no way to hold).
_UNCOVERED: dict[tuple[str, str], str] = {}

# HTTP methods that carry an operation (OpenAPI path items also hold non-operation
# keys such as "parameters" / "summary", which must not be mistaken for one).
_HTTP_METHODS = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
)


def _spec_operations(schema: dict) -> set[tuple[str, str]]:
    """Every ``(METHOD, path)`` operation in the OpenAPI document."""
    return {
        (method.upper(), path)
        for path, item in schema["paths"].items()
        for method in item
        if method.lower() in _HTTP_METHODS
    }


def test_client_covers_every_operation():
    """EVERY operation in the spec — read or write — must have a named method on
    the client, or an explicit justified entry in ``_UNCOVERED``."""
    dump_openapi = _load_dumper()
    from dna_client import DnaClient

    operations = _spec_operations(dump_openapi.build_schema())

    uncovered = operations - _COVERED.keys() - _UNCOVERED.keys()
    assert not uncovered, (
        "operation(s) in the API with no named client method: "
        f"{sorted(uncovered)} — add a named method to dna_client/client.py and "
        "map it in _COVERED, or, if it genuinely should not have one, add it to "
        "_UNCOVERED with the reason. Do NOT leave it to `.request`."
    )

    for (verb, path), name in _COVERED.items():
        assert hasattr(DnaClient, name), f"client missing {name}() for {verb} {path}"


def test_coverage_map_has_no_stale_entries():
    """The maps must not outlive the spec — a removed route has to be removed here
    too, else the guard silently protects an operation that no longer exists."""
    dump_openapi = _load_dumper()
    operations = _spec_operations(dump_openapi.build_schema())

    stale = (_COVERED.keys() | _UNCOVERED.keys()) - operations
    assert not stale, (
        f"coverage map lists operation(s) absent from the spec: {sorted(stale)} "
        "— the route was removed/renamed; drop the entry (and its client method)."
    )


def test_every_uncovered_entry_states_a_reason():
    """An allowlist without reasons decays into a dumping ground."""
    for key, reason in _UNCOVERED.items():
        assert reason and reason.strip(), f"_UNCOVERED[{key}] needs a stated reason"
