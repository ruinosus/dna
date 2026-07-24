"""``dna definition get|set|revert`` — CLI parity with the REST surface
(s-strain-customization-ui / Task 4).

Mirrors ``test_definitions_rest.py``'s fixture (a writable copy of
``examples/emitting-to-a-runtime/.dna``, one seeded ``LayerPolicy`` doc) but
drives the LOCAL kernel facade (``dna_cli._ctx.dna_client()``) via
``CliRunner`` instead of ``TestClient`` — ``dna_client()`` has no
session-injection seam (unlike ``dna_session()``'s ``SESSION_PROVIDER_KEY``),
it always boots a real kernel from ``DNA_BASE_DIR``/``DNA_SOURCE_URL``, so
these are real (if filesystem-local) end-to-end runs, not mocked.

Central assertion (this task's global constraint): ``set`` against a LOCKED
Kind does not swallow the ``LayerPolicyViolationError`` — it prints the veto
message and exits non-zero, the CLI-side mirror of the REST 403.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import shutil

import pytest
from click.testing import CliRunner

from dna_cli.definition_cmd import definition

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_WID = "ws-cli00000000000000000001"

# The scope already ships these (examples/emitting-to-a-runtime/.dna/concierge):
_AGENT = "concierge"          # Kind Agent, alias "helix-agent"
_FEDERATION = "dna-mcp"       # Kind MCPFederation, alias "federation-mcp"

_LAYER_POLICY_RAW = {
    "apiVersion": "github.com/ruinosus/dna/policy/v1",
    "kind": "LayerPolicy",
    "metadata": {"name": "tenant-default"},
    "spec": {
        "layer_id": "tenant",
        "policies": {"helix-agent": "open", "federation-mcp": "locked"},
    },
}


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    """A writable copy of the concierge scope, wired via DNA_BASE_DIR — same
    fixture shape as test_definitions_rest.py's ``dna_dir``."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _seed_layer_policy(dna_dir) -> None:
    """Write the LayerPolicy doc via the SAME composition root
    (``dna_cli._mcp_server.boot_live``) test_definitions_rest.py uses, on a
    fresh loop (the fixture's env vars are already set)."""
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        await live.kernel.write_document(
            _SCOPE, "LayerPolicy", "tenant-default", _LAYER_POLICY_RAW)

    asyncio.run(go())


@pytest.fixture
def runner():
    return CliRunner()


def _spec_file(tmp_path, content: str) -> str:
    f = tmp_path / "spec.yaml"
    f.write_text(content, encoding="utf-8")
    return str(f)


# ── get ──────────────────────────────────────────────────────────────────


def test_get_shows_base_when_not_overridden(dna_dir, runner):
    _seed_layer_policy(dna_dir)
    r = runner.invoke(definition, ["get", "Agent", _AGENT, "--scope", _SCOPE, "--json"])
    assert r.exit_code == 0, r.output
    body = json.loads(r.output)
    assert body["kind"] == "Agent"
    assert body["name"] == _AGENT
    assert body["overridden"] is False
    assert "Answer using the runbook" in body["effective"]["instruction"]


def test_get_human_readable_output_does_not_crash(dna_dir, runner):
    _seed_layer_policy(dna_dir)
    r = runner.invoke(definition, ["get", "Agent", _AGENT, "--scope", _SCOPE])
    assert r.exit_code == 0, r.output
    assert f"Agent/{_AGENT}" in r.output
    assert "overridden=False" in r.output


def test_get_unknown_name_fails_clean_not_a_traceback(dna_dir, runner):
    """Fix-now: `get` on an unknown kind/name must exit non-zero with a clean
    `fail()`-wrapped message — NOT a raw Python traceback from the impl's
    ``ValueError``."""
    _seed_layer_policy(dna_dir)
    r = runner.invoke(definition, ["get", "Agent", "no-such-agent", "--scope", _SCOPE])
    assert r.exit_code != 0, r.output
    combined = r.output + (r.stderr if r.stderr_bytes is not None else "")
    assert "Traceback" not in combined
    assert "no-such-agent" in combined


def test_revert_unknown_name_fails_clean_not_a_traceback(dna_dir, runner):
    """Same fix-now guard for `revert` on an unknown kind/name."""
    _seed_layer_policy(dna_dir)
    r = runner.invoke(definition, [
        "revert", "Agent", "no-such-agent", "--scope", _SCOPE, "--tenant", _WID,
    ])
    assert r.exit_code != 0, r.output
    combined = r.output + (r.stderr if r.stderr_bytes is not None else "")
    assert "Traceback" not in combined


# ── set ──────────────────────────────────────────────────────────────────


def test_set_then_get_shows_override(dna_dir, runner, tmp_path):
    _seed_layer_policy(dna_dir)
    spec_file = _spec_file(tmp_path, "spec:\n  instruction: Speak only in haiku.\n")

    set_result = runner.invoke(definition, [
        "set", "Agent", _AGENT, "--file", spec_file,
        "--scope", _SCOPE, "--tenant", _WID,
    ])
    assert set_result.exit_code == 0, set_result.output
    set_body = json.loads(set_result.output)
    assert set_body["overridden"] is True

    get_result = runner.invoke(definition, [
        "get", "Agent", _AGENT, "--scope", _SCOPE, "--tenant", _WID, "--json",
    ])
    assert get_result.exit_code == 0, get_result.output
    get_body = json.loads(get_result.output)
    assert get_body["overridden"] is True
    assert get_body["effective"]["instruction"] == "Speak only in haiku."

    # A different tenant (no override) still reads the unmodified base.
    other = runner.invoke(definition, [
        "get", "Agent", _AGENT, "--scope", _SCOPE,
        "--tenant", "ws-other0000000000000000002", "--json",
    ])
    assert other.exit_code == 0, other.output
    assert json.loads(other.output)["overridden"] is False


def test_set_locked_kind_surfaces_veto_not_swallowed(dna_dir, runner, tmp_path):
    """The central constraint this task exists to protect: `set` against a
    LOCKED Kind (MCPFederation, alias "federation-mcp") does not silently
    no-op — it exits non-zero with the LayerPolicy veto message visible."""
    _seed_layer_policy(dna_dir)
    spec_file = _spec_file(
        tmp_path,
        "spec:\n"
        "  transport: streamable_http\n"
        "  url: https://evil.example\n"
        "  allowed_tools: []\n",
    )

    r = runner.invoke(definition, [
        "set", "MCPFederation", _FEDERATION, "--file", spec_file,
        "--scope", _SCOPE, "--tenant", _WID,
    ])
    assert r.exit_code != 0, r.output
    combined = r.output + (r.stderr if r.stderr_bytes is not None else "")
    assert "federation-mcp" in combined and "LOCKED" in combined, combined


# ── revert ───────────────────────────────────────────────────────────────


def test_revert_falls_back_to_base(dna_dir, runner, tmp_path):
    _seed_layer_policy(dna_dir)
    spec_file = _spec_file(tmp_path, "spec:\n  instruction: Temporary override.\n")

    runner.invoke(definition, [
        "set", "Agent", _AGENT, "--file", spec_file,
        "--scope", _SCOPE, "--tenant", _WID,
    ])

    revert_result = runner.invoke(definition, [
        "revert", "Agent", _AGENT, "--scope", _SCOPE, "--tenant", _WID,
    ])
    assert revert_result.exit_code == 0, revert_result.output
    assert json.loads(revert_result.output)["overridden"] is False

    get_result = runner.invoke(definition, [
        "get", "Agent", _AGENT, "--scope", _SCOPE, "--tenant", _WID, "--json",
    ])
    assert get_result.exit_code == 0, get_result.output
    get_body = json.loads(get_result.output)
    assert get_body["overridden"] is False
    assert "Answer using the runbook" in get_body["effective"]["instruction"]
