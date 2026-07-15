"""TDD for `dna specify export` + the round-trip fidelity acceptance test.

Export projects a DNA-stored Spec Kit run back to a `.specify/` tree, reusing
the Feature's `spec.specify_run` manifest (written at import). The headline
acceptance test (ADR §8.3, §10): `import` then `export` reproduces the source
`.specify/` artifacts BYTE-FOR-BYTE.
"""
from __future__ import annotations

import pathlib

import pytest
from click.testing import CliRunner

from dna_cli.specify_cmd import specify

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "speckit"

# The artifacts DNA mirrors (constitution + the feature run). Spec Kit toolkit
# internals (scripts/, templates/) are not ingested, so not round-tripped.
_MIRRORED = [
    ".specify/memory/constitution.md",
    "specs/001-taskify/spec.md",
    "specs/001-taskify/plan.md",
    "specs/001-taskify/tasks.md",
    "specs/001-taskify/research.md",
    "specs/001-taskify/data-model.md",
    "specs/001-taskify/quickstart.md",
    "specs/001-taskify/contracts/board-api.md",
]


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def temp_scope(tmp_path, monkeypatch):
    base = tmp_path / ".dna"
    scope = "proj"
    (base / scope).mkdir(parents=True)
    (base / scope / "Genome.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
        "metadata:\n  name: proj\nspec:\n  owner: dna\n"
    )
    monkeypatch.setenv("DNA_BASE_DIR", str(base))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return base, scope


def _import(runner, scope, *extra):
    r = runner.invoke(specify, ["import", str(FIXTURE), "--scope", scope, *extra],
                      catch_exceptions=False)
    assert r.exit_code == 0, r.output
    return r


def test_export_writes_manifest_files(runner, temp_scope, tmp_path):
    base, scope = temp_scope
    _import(runner, scope)
    out = tmp_path / "exported"
    r = runner.invoke(specify, ["export", "f-taskify", "--out", str(out), "--scope", scope],
                      catch_exceptions=False)
    assert r.exit_code == 0, r.output
    for rel in _MIRRORED:
        assert (out / rel).exists(), f"missing projected file {rel}"


def test_export_refuses_overwrite_without_force(runner, temp_scope, tmp_path):
    base, scope = temp_scope
    _import(runner, scope)
    out = tmp_path / "exported"
    runner.invoke(specify, ["export", "f-taskify", "--out", str(out), "--scope", scope],
                  catch_exceptions=False)
    r = runner.invoke(specify, ["export", "f-taskify", "--out", str(out), "--scope", scope],
                      catch_exceptions=False)
    assert r.exit_code != 0
    assert "force" in r.output.lower()


def test_export_missing_feature_fails(runner, temp_scope, tmp_path):
    base, scope = temp_scope
    r = runner.invoke(specify, ["export", "f-nope", "--out", str(tmp_path / "o"), "--scope", scope],
                      catch_exceptions=False)
    assert r.exit_code != 0
    assert "not found" in r.output.lower()


# ─── the headline acceptance test ────────────────────────────────────────────


def test_round_trip_byte_identical(runner, temp_scope, tmp_path):
    """import(.specify/) then export = byte-identical .specify/ artifacts."""
    base, scope = temp_scope
    _import(runner, scope)
    out = tmp_path / "exported"
    r = runner.invoke(specify, ["export", "f-taskify", "--out", str(out), "--scope", scope],
                      catch_exceptions=False)
    assert r.exit_code == 0, r.output

    mismatches = []
    for rel in _MIRRORED:
        src = (FIXTURE / rel).read_bytes()
        dst_path = out / rel
        if not dst_path.exists():
            mismatches.append(f"{rel}: NOT PROJECTED")
            continue
        dst = dst_path.read_bytes()
        if src != dst:
            mismatches.append(f"{rel}: differs ({len(src)}B vs {len(dst)}B)")
    assert not mismatches, "round-trip not byte-identical:\n  " + "\n  ".join(mismatches)


def test_round_trip_json_output(runner, temp_scope, tmp_path):
    import json
    base, scope = temp_scope
    _import(runner, scope)
    out = tmp_path / "exported"
    r = runner.invoke(specify, ["export", "f-taskify", "--out", str(out), "--scope", scope, "--json"],
                      catch_exceptions=False)
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["feature"] == "f-taskify"
    assert set(payload["files"]) == set(_MIRRORED)
