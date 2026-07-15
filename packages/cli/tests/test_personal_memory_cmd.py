"""`dna memory --personal` + the MCP oid seam — personal / private per-user memory.

Covers ``s-personal-memory-surfaces`` (CLI face) + the ``enforce_oid_from_context``
pure policy (``s-personal-memory-partition`` oid seam). Drives the real CLI
in-process against a filesystem scope; personal targets the ``personal:<oid>``
partition keyed from ``DNA_PERSONAL_ID``, and a round-trip proves personal is
isolated from workspace (and vice-versa) end-to-end through the CLI.
"""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from dna_cli import main
from dna_cli._mcp_auth import (
    oid_from_token,
    resolve_personal_oid,
)
from dna.memory.personal import PersonalIdentityRequired

_REASON = "a concrete reason long enough for the affect validator to accept in full"
_OID = "aaaaaaaa-1111-2222-3333-444444444444"


@pytest.fixture
def scoped(tmp_path, monkeypatch):
    base = tmp_path / "src" / "demo"
    base.mkdir(parents=True)
    (base / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/core/v1\n"
        "kind: Package\nmetadata:\n  name: demo\nspec:\n  title: Demo\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DNA_BASE_DIR", str(tmp_path / "src"))
    monkeypatch.setenv("DNA_SEARCH_DIR", str(tmp_path / "search"))
    monkeypatch.delenv("DNA_PERSONAL_ID", raising=False)
    return tmp_path


# ── the oid seam (pure policy, fail-closed) ─────────────────────────────────


def test_oid_from_token():
    assert oid_from_token({"oid": _OID}) == _OID
    assert oid_from_token({"oid": "  "}) is None
    assert oid_from_token({}) is None
    assert oid_from_token(None) is None


def test_resolve_personal_oid_authenticated():
    # token present WITH oid → that oid.
    assert resolve_personal_oid(token_present=True, token_oid=_OID, env_oid=None) == _OID
    # token present WITHOUT oid → DENIED (fail-closed), even if env is set.
    with pytest.raises(PersonalIdentityRequired):
        resolve_personal_oid(token_present=True, token_oid=None, env_oid="env-id")


def test_resolve_personal_oid_offline():
    # no token → DNA_PERSONAL_ID.
    assert resolve_personal_oid(token_present=False, token_oid=None, env_oid=_OID) == _OID
    # no token + no env → DENIED (personal needs an identity).
    with pytest.raises(PersonalIdentityRequired):
        resolve_personal_oid(token_present=False, token_oid=None, env_oid=None)


# ── CLI: --personal round-trip + isolation ──────────────────────────────────


def _remember(runner, summary, *extra):
    return runner.invoke(main, [
        "memory", "remember", summary, "--scope", "demo",
        "--area", "Feature/personal", "--reason", _REASON, "--json", *extra,
    ])


def test_personal_requires_identity_fail_closed(scoped):
    runner = CliRunner()
    r = _remember(runner, "a private note", "--personal")  # no DNA_PERSONAL_ID
    assert r.exit_code != 0
    assert "DNA_PERSONAL_ID" in r.output


def test_personal_and_tenant_mutually_exclusive(scoped, monkeypatch):
    monkeypatch.setenv("DNA_PERSONAL_ID", _OID)
    runner = CliRunner()
    r = _remember(runner, "note", "--personal", "--tenant", "acme")
    assert r.exit_code != 0
    assert "mutually exclusive" in r.output


def test_raw_personal_tenant_override_rejected(scoped):
    runner = CliRunner()
    r = _remember(runner, "note", "--tenant", f"personal:{_OID}")
    assert r.exit_code != 0
    assert "personal" in r.output.lower()


def test_personal_roundtrip_isolated_from_workspace(scoped, monkeypatch):
    monkeypatch.setenv("DNA_PERSONAL_ID", _OID)
    runner = CliRunner()
    # remember privately
    r = _remember(runner, "my private deploy trick step seven", "--personal")
    assert r.exit_code == 0, r.output

    # recall --personal surfaces it
    rec = runner.invoke(main, [
        "memory", "recall", "private deploy trick", "--scope", "demo",
        "--personal", "--no-reconsolidate", "--json",
    ])
    assert rec.exit_code == 0, rec.output
    names = {h["name"] for h in json.loads(rec.output)["hits"]}
    assert names, "personal recall should surface the private memory"

    # a WORKSPACE recall (no --personal) must NOT see it.
    ws = runner.invoke(main, [
        "memory", "recall", "private deploy trick", "--scope", "demo",
        "--no-reconsolidate", "--json",
    ])
    assert ws.exit_code == 0, ws.output
    ws_names = {h["name"] for h in json.loads(ws.output)["hits"]}
    assert not (names & ws_names), "personal memory leaked into the workspace recall"
