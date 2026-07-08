"""Tests for CompositeFilesystemSource — multi-base-dir source."""
from __future__ import annotations

from pathlib import Path

import pytest

from dna.adapters.filesystem.composite import CompositeFilesystemSource


def _make_scope(parent: Path, child_name: str, scope_name: str) -> Path:
    """Create a `<parent>/<child_name>/.dna/<scope_name>/manifest.yaml` tree."""
    scope_dir = parent / child_name / ".dna" / scope_name
    scope_dir.mkdir(parents=True)
    (scope_dir / "manifest.yaml").write_text(
        f"apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\nmetadata:\n  name: {scope_name}\nspec: {{}}\n"
    )
    return scope_dir


@pytest.mark.asyncio
async def test_discovers_multiple_examples(tmp_path: Path) -> None:
    _make_scope(tmp_path, "ex-one", "alpha")
    _make_scope(tmp_path, "ex-two", "beta")
    _make_scope(tmp_path, "ex-three", "gamma")

    src = CompositeFilesystemSource(tmp_path)
    scopes = await src.list_scopes()
    assert scopes == ["alpha", "beta", "gamma"]


@pytest.mark.asyncio
async def test_routes_bootstrap_docs_to_correct_child(tmp_path: Path) -> None:
    from dna.kernel.protocols import package_doc_for_scope
    _make_scope(tmp_path, "ex-one", "alpha")
    _make_scope(tmp_path, "ex-two", "beta")

    src = CompositeFilesystemSource(tmp_path)
    alpha = await package_doc_for_scope(src, "alpha")
    beta = await package_doc_for_scope(src, "beta")

    assert alpha is not None and alpha["metadata"]["name"] == "alpha"
    assert beta is not None and beta["metadata"]["name"] == "beta"


@pytest.mark.asyncio
async def test_unknown_scope_raises_clear_error(tmp_path: Path) -> None:
    _make_scope(tmp_path, "ex-one", "alpha")
    src = CompositeFilesystemSource(tmp_path)
    with pytest.raises(FileNotFoundError, match="missing-scope"):
        await src.load_bootstrap_docs("missing-scope")


def test_collision_raises_at_construction(tmp_path: Path) -> None:
    """Two children exposing the same scope name → loud failure at boot."""
    _make_scope(tmp_path, "ex-one", "shared-name")
    _make_scope(tmp_path, "ex-two", "shared-name")
    with pytest.raises(ValueError, match="duplicated|exposed by both"):
        CompositeFilesystemSource(tmp_path)


def test_ignores_dirs_without_dna(tmp_path: Path) -> None:
    """Random subdirs (no .dna) are skipped silently."""
    _make_scope(tmp_path, "ex-one", "alpha")
    (tmp_path / "not-an-example").mkdir()
    (tmp_path / "not-an-example" / "README.md").write_text("hi")

    src = CompositeFilesystemSource(tmp_path)
    assert "alpha" in src.children
    assert len(src.children) == 1


def test_ignores_hidden_dirs(tmp_path: Path) -> None:
    _make_scope(tmp_path, "ex-one", "alpha")
    hidden = tmp_path / ".cache" / ".dna" / "ghost"
    hidden.mkdir(parents=True)
    (hidden / "manifest.yaml").write_text("kind: Genome\n")

    src = CompositeFilesystemSource(tmp_path)
    assert "ghost" not in src.children


def test_skips_dna_subdirs_without_manifest(tmp_path: Path) -> None:
    """A child with .dna/scope/ but no manifest.yaml inside is skipped."""
    no_manifest = tmp_path / "ex-one" / ".dna" / "incomplete"
    no_manifest.mkdir(parents=True)
    # No manifest.yaml file — should be skipped
    _make_scope(tmp_path, "ex-two", "real-scope")

    src = CompositeFilesystemSource(tmp_path)
    assert list(src.children.keys()) == ["real-scope"]


def test_empty_parent_dir_yields_empty_composite(tmp_path: Path) -> None:
    src = CompositeFilesystemSource(tmp_path)
    assert src.children == {}


def test_capabilities_reports_composite_kind(tmp_path: Path) -> None:
    # s-capabilities-dataclass — capabilities() is sync + returns a typed
    # SourceCapabilities derived from the Protocols satisfied. The composite
    # router implements publish/load_drafts/get_version/load_layer, so it
    # truthfully reports drafts/versions/layers (the old dict lied: False/False).
    _make_scope(tmp_path, "ex-one", "alpha")
    _make_scope(tmp_path, "ex-two", "beta")
    src = CompositeFilesystemSource(tmp_path)
    caps = src.capabilities()
    assert caps.source == "composite-filesystem"
    assert caps.drafts is True
    assert caps.versions is True
    assert caps.layers is True


def test_one_child_can_expose_multiple_scopes(tmp_path: Path) -> None:
    """A single child .dna dir with N scopes registers N entries
    pointing at the same child source — efficient + correct."""
    _make_scope(tmp_path, "ex-one", "alpha")
    _make_scope(tmp_path, "ex-one", "beta")  # same parent, second scope

    src = CompositeFilesystemSource(tmp_path)
    assert sorted(src.children.keys()) == ["alpha", "beta"]
    # Both scopes route to the same underlying child source
    assert src.children["alpha"] is src.children["beta"]
