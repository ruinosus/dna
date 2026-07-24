"""s-strain-bundle-fork / Task 4 — the ``/v1/definitions/{kind}/{name}/entries``
REST surface has ZERO business logic of its own (it delegates verbatim to the
same ``*_bundle_entry(ies)_impl`` core Tasks 1-3 added), but the FACE mapping —
the exceptions the core raises into the HTTP statuses the portal's editor
depends on — has no committed coverage before this test:

    list_bundle_entries_impl  ValueError               → 404 (non-bundle Kind)
    read_bundle_entry_impl    ValueError               → 404 (unknown entry)
    write_bundle_entry_impl   LayerPolicyViolationError → 403 (LOCKED Kind)
    write_bundle_entry_impl   ValueError (no tenant)    → 400
    revert_bundle_entry_impl  ValueError (no tenant)    → 400

Mirrors ``test_definitions_rest.py``'s app-construction + seeding pattern
(``TestClient`` over the real FastAPI app, a writable copy of the ``concierge``
example scope wired via ``DNA_BASE_DIR``), plus
``test_bundle_entry_overlay_pg.py``'s Skill-bundle seed (SKILL.md +
scripts/hello.py) and its LayerPolicy shape (Kind ALIASES, i-049:
``SkillKind.alias = "agentskills-skill"``). The concierge scope ships no Skill
of its own, so this module seeds ONE (``greeter``) directly on disk — the same
way ``test_bundle_entry_impls.py``'s ``live`` fixture does for the filesystem
adapter (no ``write_document`` call needed for a bundle-pattern Kind; the
SKILL.md file itself is the doc).
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

pytest.importorskip("fastapi", reason="the REST read-API needs the optional 'fastapi' extra")

from fastapi.testclient import TestClient  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_WID = "ws-rest0000000000000000001"
_OTHER_WID = "ws-other0000000000000000002"

_SKILL = "greeter"
SKILL_MD_BASE = "---\nname: greeter\n---\nBase.\n"
HELLO_PY_BASE = "print('base')\n"


def _layer_policy_raw(*, skill_policy: str) -> dict:
    """Policy keys by Kind ALIAS (i-049): SkillKind.alias = "agentskills-skill"."""
    return {
        "apiVersion": "github.com/ruinosus/dna/policy/v1",
        "kind": "LayerPolicy",
        "metadata": {"name": "tenant-default"},
        "spec": {
            "layer_id": "tenant",
            "policies": {"agentskills-skill": skill_policy},
        },
    }


def _seed_skill_bundle(dna_dir: pathlib.Path) -> None:
    """Write a base Skill bundle (``greeter``) directly on disk — mirrors
    ``test_bundle_entry_impls.py``'s ``live`` fixture: a bundle-pattern Kind's
    base file IS the document, no ``write_document`` needed."""
    d = dna_dir / _SCOPE / "skills" / _SKILL
    (d / "scripts").mkdir(parents=True)
    (d / "SKILL.md").write_text(SKILL_MD_BASE)
    (d / "scripts" / "hello.py").write_text(HELLO_PY_BASE)


def _seed_layer_policy(dna_dir: pathlib.Path, *, skill_policy: str) -> None:
    """Write the LayerPolicy doc into the ``concierge`` scope itself (a
    bootstrap Kind — one per (layer_id, scope), never per-tenant) — mirrors
    ``test_definitions_rest.py``'s ``_seed_layer_policy``, on the filesystem
    source via ``boot_live`` on a fresh loop."""
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        await live.kernel.write_document(
            _SCOPE, "LayerPolicy", "tenant-default",
            _layer_policy_raw(skill_policy=skill_policy),
        )

    asyncio.run(go())


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    """A writable copy of the concierge scope + a base Skill bundle, wired via
    DNA_BASE_DIR (same fixture shape as ``test_definitions_rest.py``'s
    ``dna_dir``). The LayerPolicy is NOT seeded here — each test seeds its own
    (open vs. locked), since a bundle Kind can only be one or the other."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    _seed_skill_bundle(dst)
    return dst


def _client(dna_dir) -> TestClient:
    """auth=none — the definitions routes are auth-guarded but not
    plan-gated, so the default (unauthenticated) client exercises the same
    handler code the token/config lanes would."""
    return TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE))


# ── GET (list) ────────────────────────────────────────────────────────────


def test_list_entries_returns_200_with_both_files_not_overridden(dna_dir):
    _seed_layer_policy(dna_dir, skill_policy="open")
    with _client(dna_dir) as c:
        r = c.get(f"/v1/definitions/Skill/{_SKILL}/entries")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["kind"] == "Skill"
        assert body["name"] == _SKILL
        by_entry = {e["entry"]: e["overridden"] for e in body["entries"]}
        assert by_entry == {"SKILL.md": False, "scripts/hello.py": False}


def test_list_entries_404_for_non_bundle_kind(dna_dir):
    """MCPFederation (``dna-mcp``, already shipped by the concierge example)
    stores a single YAML doc (``StorageDescriptor.yaml``), not a bundle — it
    has no file entries to list."""
    _seed_layer_policy(dna_dir, skill_policy="open")
    with _client(dna_dir) as c:
        r = c.get("/v1/definitions/MCPFederation/dna-mcp/entries")
        assert r.status_code == 404, r.text


# ── GET (read) ────────────────────────────────────────────────────────────


def test_read_entry_returns_base_content(dna_dir):
    _seed_layer_policy(dna_dir, skill_policy="open")
    with _client(dna_dir) as c:
        r = c.get(f"/v1/definitions/Skill/{_SKILL}/entries/scripts/hello.py")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["content"] == HELLO_PY_BASE
        assert body["overridden"] is False
        assert body["binary"] is False


def test_read_entry_404_for_unknown_entry(dna_dir):
    _seed_layer_policy(dna_dir, skill_policy="open")
    with _client(dna_dir) as c:
        r = c.get(f"/v1/definitions/Skill/{_SKILL}/entries/nope.txt")
        assert r.status_code == 404, r.text


# ── PUT (write) ───────────────────────────────────────────────────────────


def test_write_entry_returns_200_and_overridden_true(dna_dir):
    _seed_layer_policy(dna_dir, skill_policy="open")
    with _client(dna_dir) as c:
        r = c.put(
            f"/v1/definitions/Skill/{_SKILL}/entries/scripts/hello.py",
            params={"tenant": _WID},
            json={"content": "print('mine')\n"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["kind"] == "Skill"
        assert body["name"] == _SKILL
        assert body["entry"] == "scripts/hello.py"
        assert body["overridden"] is True


def test_write_entry_403_on_locked_skill_layer_policy(dna_dir):
    """The central constraint this task exists to protect: a fork write to a
    LOCKED Kind (Skill, alias "agentskills-skill") is vetoed by the kernel's
    LayerPolicy check and surfaced as 403, never silently dropped and never a
    500."""
    _seed_layer_policy(dna_dir, skill_policy="locked")
    with _client(dna_dir) as c:
        r = c.put(
            f"/v1/definitions/Skill/{_SKILL}/entries/scripts/hello.py",
            params={"tenant": _WID},
            json={"content": "print('evil')\n"},
        )
        assert r.status_code == 403, r.text


def test_write_entry_without_tenant_is_400(dna_dir):
    _seed_layer_policy(dna_dir, skill_policy="open")
    with _client(dna_dir) as c:
        r = c.put(
            f"/v1/definitions/Skill/{_SKILL}/entries/scripts/hello.py",
            json={"content": "no tenant given"},
        )
        assert r.status_code == 400, r.text


# ── DELETE + full round-trip ──────────────────────────────────────────────


def test_write_then_list_then_read_then_revert_round_trips(dna_dir):
    """PUT forks the entry (overridden true for that tenant's list/read);
    DELETE reverts it — the exact state the editor's Save / Reset-to-default
    renders, at file grain."""
    _seed_layer_policy(dna_dir, skill_policy="open")
    with _client(dna_dir) as c:
        before = c.get(
            f"/v1/definitions/Skill/{_SKILL}/entries/scripts/hello.py",
            params={"tenant": _WID},
        )
        assert before.status_code == 200, before.text
        assert before.json()["overridden"] is False
        assert before.json()["content"] == HELLO_PY_BASE

        put = c.put(
            f"/v1/definitions/Skill/{_SKILL}/entries/scripts/hello.py",
            params={"tenant": _WID},
            json={"content": "print('mine')\n"},
        )
        assert put.status_code == 200, put.text

        listing = c.get(
            f"/v1/definitions/Skill/{_SKILL}/entries", params={"tenant": _WID}
        )
        assert listing.status_code == 200, listing.text
        by_entry = {e["entry"]: e["overridden"] for e in listing.json()["entries"]}
        assert by_entry["scripts/hello.py"] is True
        assert by_entry["SKILL.md"] is False

        after_write = c.get(
            f"/v1/definitions/Skill/{_SKILL}/entries/scripts/hello.py",
            params={"tenant": _WID},
        )
        assert after_write.status_code == 200, after_write.text
        assert after_write.json()["overridden"] is True
        assert after_write.json()["content"] == "print('mine')\n"

        # A DIFFERENT tenant (no fork) still reads the unmodified base.
        other = c.get(
            f"/v1/definitions/Skill/{_SKILL}/entries/scripts/hello.py",
            params={"tenant": _OTHER_WID},
        )
        assert other.status_code == 200, other.text
        assert other.json()["overridden"] is False
        assert other.json()["content"] == HELLO_PY_BASE

        delete = c.delete(
            f"/v1/definitions/Skill/{_SKILL}/entries/scripts/hello.py",
            params={"tenant": _WID},
        )
        assert delete.status_code == 200, delete.text
        assert delete.json()["overridden"] is False

        after_delete = c.get(
            f"/v1/definitions/Skill/{_SKILL}/entries/scripts/hello.py",
            params={"tenant": _WID},
        )
        assert after_delete.status_code == 200, after_delete.text
        assert after_delete.json()["overridden"] is False
        assert after_delete.json()["content"] == HELLO_PY_BASE


def test_revert_without_tenant_is_400(dna_dir):
    _seed_layer_policy(dna_dir, skill_policy="open")
    with _client(dna_dir) as c:
        r = c.delete(f"/v1/definitions/Skill/{_SKILL}/entries/scripts/hello.py")
        assert r.status_code == 400, r.text
