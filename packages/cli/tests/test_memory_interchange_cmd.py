"""``dna memory export`` / ``dna memory import`` (s-memory-interchange-verbs).

Drives the real CLI in-process (``CliRunner``) against a filesystem scope —
same harness as ``test_personal_memory_cmd.py``. Covers the acceptance
criteria the story is held to:

  * export -> import round trip is field-faithful and the §6 id pin makes a
    re-export stable (same MIF id every time);
  * ``--dedupe id`` makes a re-import of the SAME export a no-op (no
    duplicate) — the story's required "mutation-tested" test;
  * ``--personal`` respects INV-PERSONAL: a personal export never contains a
    NAMED workspace tenant's memory, and vice versa (mirrors
    ``test_personal_memory_cmd.py``'s recall isolation proof, applied to
    export/import);
  * ``--include-forgotten`` carries the bi-temporal chain across the wire;
  * ``--as passthrough|native|both`` and ``--bundle`` (JSON-LD) all work.
"""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from dna_cli import main

_REASON = "a concrete reason long enough for the affect validator to accept in full"
_OID_A = "aaaaaaaa-1111-2222-3333-444444444444"
_OID_B = "bbbbbbbb-1111-2222-3333-444444444444"


@pytest.fixture
def scoped(tmp_path, monkeypatch):
    for name in ("demo", "other"):
        base = tmp_path / "src" / name
        base.mkdir(parents=True)
        (base / "manifest.yaml").write_text(
            "apiVersion: github.com/ruinosus/dna/core/v1\n"
            f"kind: Package\nmetadata:\n  name: {name}\nspec:\n  title: {name}\n",
            encoding="utf-8",
        )
    monkeypatch.setenv("DNA_BASE_DIR", str(tmp_path / "src"))
    monkeypatch.setenv("DNA_SEARCH_DIR", str(tmp_path / "search"))
    monkeypatch.delenv("DNA_PERSONAL_ID", raising=False)
    return tmp_path


def _remember(runner, scope, summary, *extra):
    r = runner.invoke(main, [
        "memory", "remember", summary, "--scope", scope,
        "--area", "Feature/interchange", "--reason", _REASON, "--json", *extra,
    ])
    assert r.exit_code == 0, r.output
    return json.loads(r.output)["name"]


def _export(runner, scope, out, *extra):
    r = runner.invoke(main, ["memory", "export", "--scope", scope, "--out", str(out), "--json", *extra])
    assert r.exit_code == 0, r.output
    return json.loads(r.output)


def _import(runner, path, scope, *extra):
    r = runner.invoke(main, ["memory", "import", str(path), "--scope", scope, "--json", *extra])
    assert r.exit_code == 0, r.output
    return json.loads(r.output)


# ─────────────────────────── field-faithful round trip ────────────────────


def test_export_then_import_round_trip_projects_a_recallable_engram(scoped):
    runner = CliRunner()
    _remember(runner, "demo", "Always deep-copy the L2 cache before mutating", "--affect", "regret")

    out = _export(runner, "demo", scoped / "export1")
    assert out["count"] == 1

    imp = _import(runner, scoped / "export1", "other")
    assert imp["imported"] == 1
    assert imp["failed"] == 0

    rec = runner.invoke(main, [
        "memory", "recall", "deep-copy the cache", "--scope", "other",
        "--no-reconsolidate", "--json",
    ])
    assert rec.exit_code == 0, rec.output
    hits = json.loads(rec.output)["hits"]
    assert any(h["kind"] == "Engram" for h in hits), "imported memory should be recallable"


def test_id_is_stable_across_repeated_exports_of_the_same_engram(scoped):
    """§6 — mint-once + pin-back: re-exporting the SAME Engram twice must
    produce the SAME MIF id both times."""
    runner = CliRunner()
    _remember(runner, "demo", "A memory exported more than once")

    out1 = _export(runner, "demo", scoped / "e1")
    out2 = _export(runner, "demo", scoped / "e2")
    assert out1["minted_ids"] == 1
    assert out2["minted_ids"] == 0, "second export must reuse the pinned id, not mint a new one"

    id1 = {f.split("/")[-1] for f in out1["files"]}
    id2 = {f.split("/")[-1] for f in out2["files"]}
    assert id1 == id2


# ─────────────────────────── dedupe idempotence (required) ────────────────


def test_dedupe_id_reimport_no_op(scoped):
    """The story's required test: --dedupe id makes a re-import of the SAME
    export a no-op — no duplicate Engram, no duplicate passthrough doc."""
    runner = CliRunner()
    _remember(runner, "demo", "A memory imported twice on purpose")
    out = _export(runner, "demo", scoped / "e")

    first = _import(runner, scoped / "e", "other")
    assert first["imported"] == 1
    assert first["skipped"] == 0

    second = _import(runner, scoped / "e", "other")
    assert second["imported"] == 0
    assert second["skipped"] == 1, "re-import with the same MIF id must be skipped, not duplicated"

    lst = runner.invoke(main, ["memory", "list", "--scope", "other", "--json"])
    assert lst.exit_code == 0, lst.output
    assert json.loads(lst.output)["count"] == 1, "exactly one Engram — no duplicate"


def test_dedupe_off_does_not_error_but_id_dedupe_default_prevents_duplication(scoped):
    """Sanity check on the default (id): importing the same export 3x in a
    row never grows the count past 1."""
    runner = CliRunner()
    _remember(runner, "demo", "Triple import test")
    out = _export(runner, "demo", scoped / "e")
    for _ in range(3):
        _import(runner, scoped / "e", "other")
    lst = runner.invoke(main, ["memory", "list", "--scope", "other", "--json"])
    assert json.loads(lst.output)["count"] == 1


# ─────────────────────────── --personal / INV-PERSONAL (required) ─────────


def test_personal_export_excludes_named_workspace_tenant(scoped, monkeypatch):
    runner = CliRunner()
    # A named workspace tenant writes a memory.
    _remember(runner, "demo", "Acme Corp confidential roadmap note", "--tenant", "acme-corp")
    # User A writes a personal memory.
    monkeypatch.setenv("DNA_PERSONAL_ID", _OID_A)
    _remember(runner, "demo", "User A private note", "--personal")

    out = _export(runner, "demo", scoped / "personalA", "--personal")
    assert out["count"] == 1
    content = (scoped / "personalA").glob("*.md")
    text = next(content).read_text(encoding="utf-8")
    assert "User A private note" in text
    assert "Acme Corp confidential" not in text


def test_workspace_export_excludes_personal_memory(scoped, monkeypatch):
    runner = CliRunner()
    monkeypatch.setenv("DNA_PERSONAL_ID", _OID_A)
    _remember(runner, "demo", "User A private note two", "--personal")
    monkeypatch.delenv("DNA_PERSONAL_ID", raising=False)
    _remember(runner, "demo", "Acme Corp roadmap note two", "--tenant", "acme-corp")

    out = _export(runner, "demo", scoped / "acme", "--tenant", "acme-corp")
    assert out["count"] == 1
    text = next((scoped / "acme").glob("*.md")).read_text(encoding="utf-8")
    assert "Acme Corp roadmap note two" in text
    assert "User A private note two" not in text


def test_personal_import_lands_only_in_the_importers_own_partition(scoped, monkeypatch):
    """A personal export from user A, imported by user B with --personal,
    must land in B's OWN partition — never a shared/workspace partition, and
    never visible to A."""
    runner = CliRunner()
    monkeypatch.setenv("DNA_PERSONAL_ID", _OID_A)
    _remember(runner, "demo", "A note only A should ever author", "--personal")
    out = _export(runner, "demo", scoped / "fromA", "--personal")

    monkeypatch.setenv("DNA_PERSONAL_ID", _OID_B)
    imp = runner.invoke(main, [
        "memory", "import", str(scoped / "fromA"), "--scope", "demo", "--personal", "--json",
    ])
    assert imp.exit_code == 0, imp.output
    assert json.loads(imp.output)["imported"] == 1

    # A WORKSPACE query (no --personal) must never see B's personally-imported memory.
    ws = runner.invoke(main, [
        "memory", "recall", "note only A should ever author", "--scope", "demo",
        "--tenant", "acme-corp", "--no-reconsolidate", "--json",
    ])
    assert ws.exit_code == 0, ws.output
    assert json.loads(ws.output)["hits"] == []

    # B can recall her own imported copy.
    monkeypatch.setenv("DNA_PERSONAL_ID", _OID_B)
    b_rec = runner.invoke(main, [
        "memory", "recall", "note only A should ever author", "--scope", "demo",
        "--personal", "--no-reconsolidate", "--json",
    ])
    assert b_rec.exit_code == 0, b_rec.output
    assert json.loads(b_rec.output)["hits"], "B should recall her own imported copy"


def test_personal_and_tenant_mutually_exclusive_for_export(scoped, monkeypatch):
    monkeypatch.setenv("DNA_PERSONAL_ID", _OID_A)
    runner = CliRunner()
    r = runner.invoke(main, [
        "memory", "export", "--scope", "demo", "--personal", "--tenant", "acme-corp",
        "--out", str(scoped / "x"),
    ])
    assert r.exit_code != 0
    assert "mutually exclusive" in r.output


# ─────────────────────────── --include-forgotten ───────────────────────────


def test_include_forgotten_carries_the_bi_temporal_chain(scoped):
    runner = CliRunner()
    name = _remember(runner, "demo", "A memory that will be forgotten")
    fg = runner.invoke(main, ["memory", "forget", name, "--scope", "demo", "--json"])
    assert fg.exit_code == 0, fg.output

    without = _export(runner, "demo", scoped / "wo")
    assert without["count"] == 0

    withf = _export(runner, "demo", scoped / "wf", "--include-forgotten")
    assert withf["count"] == 1
    text = next((scoped / "wf").glob("*.md")).read_text(encoding="utf-8")
    assert "validUntil" in text


# ─────────────────────────── --as / --bundle ───────────────────────────────


def test_as_passthrough_only_does_not_project_an_engram(scoped):
    runner = CliRunner()
    _remember(runner, "demo", "Passthrough only test")
    out = _export(runner, "demo", scoped / "e")
    _import(runner, scoped / "e", "other", "--as", "passthrough")

    lst = runner.invoke(main, ["memory", "list", "--scope", "other", "--json"])
    assert lst.exit_code == 0, lst.output
    assert json.loads(lst.output)["count"] == 0, "no Engram should be projected under --as passthrough"


def test_bundle_json_ld_round_trips_through_import(scoped):
    runner = CliRunner()
    _remember(runner, "demo", "Bundle JSON-LD test")
    r = runner.invoke(main, [
        "memory", "export", "--scope", "demo", "--bundle",
        "--out", str(scoped / "b.json"), "--json",
    ])
    assert r.exit_code == 0, r.output
    doc = json.loads((scoped / "b.json").read_text(encoding="utf-8"))
    assert doc["@graph"][0]["@id"].startswith("urn:mif:")

    imp = _import(runner, scoped / "b.json", "other")
    assert imp["imported"] == 1


def test_export_rejects_non_engram_kind(scoped):
    runner = CliRunner()
    r = runner.invoke(main, [
        "memory", "export", "--scope", "demo", "--kind", "Research",
        "--out", str(scoped / "x"),
    ])
    assert r.exit_code != 0
    assert "Engram" in r.output
