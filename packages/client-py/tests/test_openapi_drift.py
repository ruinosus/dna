"""OpenAPI drift guard — keeps the committed generation source in sync with the
live DNA REST API.

The clients (``packages/client-ts`` + ``packages/client-py``) are generated from
``docs/openapi.json``, which is dumped from the FastAPI app by
``scripts/dump_openapi.py``. If a route/param changes and nobody re-dumps the
spec, the clients silently drift from the API. This test re-dumps the schema from
the live app and asserts it equals the committed file — so a stale spec fails CI
with a clear "run `python scripts/dump_openapi.py`" message.

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


def test_client_covers_every_get_read_endpoint():
    """Every ``/v1/*`` GET in the spec must have a named method on the client —
    the read surface is fully covered (writes stay behind ``.request``)."""
    dump_openapi = _load_dumper()
    from dna_client import DnaClient

    schema = dump_openapi.build_schema()
    get_paths = {
        p for p, ops in schema["paths"].items()
        if "get" in ops and p != "/health"
    }
    # Map each GET path to the method that must exist for it.
    covered = {
        "/v1/agents": "list_agents",
        "/v1/agents/{name}/prompt": "agent_prompt",
        "/v1/tools": "list_tools",
        "/v1/memories": "list_memories",
        "/v1/memories/search": "search_memories",
        "/v1/sources": "list_sources",
        "/v1/insights": "list_insights",
        "/v1/insights/metrics": "insight_metrics",
        "/v1/orgs": "list_orgs",
        "/v1/projects": "list_projects",
        "/v1/projects/{slug}": "get_project",
        "/v1/projects/{slug}/members": "list_project_members",
        "/v1/repos": "list_repos",
        "/v1/board": "get_board",
        "/v1/board/item": "get_board_item",
        "/v1/workspaces/{workspace_id}/members": "list_workspace_members",
    }
    missing_from_map = get_paths - covered.keys()
    assert not missing_from_map, (
        f"new GET read endpoint(s) with no client method: {sorted(missing_from_map)} "
        "— add a named method (client.py) + map it here."
    )
    for path, method in covered.items():
        assert hasattr(DnaClient, method), f"client missing {method}() for {path}"
