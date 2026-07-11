"""s-dx-single-file-soul — a Soul is authorable as a single SOUL.md.

The soulspec.org standard is a 2-file bundle (SOUL.md + soul.json manifest
with specVersion + a files map). DNA reads SOUL.md DIRECTLY, so a Soul needs
no soul.json — a single file is a first-class authoring convenience. This
suite LOCKS that contract so a future refactor can't silently reintroduce the
ceremony, and proves the 2-file soulspec format is NOT regressed (that byte-
fidelity lives in test_market_conformance.py, referenced here).

Contract:
  * a single SOUL.md (minimal frontmatter OR none) reads → a valid typed Soul;
  * the name is inferred from the bundle dir when frontmatter omits it;
  * a single-file Soul COMPOSES into an agent prompt (flatten_in_context);
  * the write path stays single-file — no phantom soul.json is emitted;
  * the 2-file form still round-trips (soul.json preserved when present).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dna.extensions.soulspec import SoulReader, SoulWriter
from dna.kernel import Kernel
from dna.kernel.bundle_handle import FilesystemBundleHandle


def _emit(raw: dict) -> dict[str, str]:
    return {f["relativePath"]: f["content"] for f in SoulWriter().serialize(raw)}


class TestSingleFileRead:
    def test_no_frontmatter_no_json_reads(self, tmp_path):
        d = tmp_path / "persona"
        d.mkdir()
        (d / "SOUL.md").write_text("# Persona\n\nCalm and precise.")
        raw = SoulReader().read(FilesystemBundleHandle(d))
        assert raw["kind"] == "Soul"
        assert raw["metadata"]["name"] == "persona"  # inferred from dir
        assert "Calm and precise." in raw["spec"]["soul_content"]
        assert "soul_json" not in raw["spec"]

    def test_minimal_frontmatter_reads(self, tmp_path):
        d = tmp_path / "host"
        d.mkdir()
        (d / "SOUL.md").write_text("---\nname: host\n---\n# Host\n\nWarm.")
        raw = SoulReader().read(FilesystemBundleHandle(d))
        assert raw["metadata"]["name"] == "host"
        assert "Warm." in raw["spec"]["soul_content"]

    def test_typed_view_is_valid(self, tmp_path):
        d = tmp_path / "s1"
        d.mkdir()
        (d / "SOUL.md").write_text("# S1\n\nBody.")
        from dna.kernel.models import TypedSoul
        typed = TypedSoul.from_raw(SoulReader().read(FilesystemBundleHandle(d)))
        assert typed.metadata.name == "s1"


class TestSingleFileWriteStaysSingle:
    def test_write_emits_only_soul_md(self, tmp_path):
        d = tmp_path / "p"
        d.mkdir()
        (d / "SOUL.md").write_text("# P\n\nBody.")
        raw = SoulReader().read(FilesystemBundleHandle(d))
        files = _emit(raw)
        assert set(files) == {"SOUL.md"}, "single-file soul must not gain a soul.json"

    def test_roundtrip_is_fixpoint(self, tmp_path):
        d = tmp_path / "p"
        d.mkdir()
        (d / "SOUL.md").write_text("# P\n\nBody.")
        r1 = SoulReader().read(FilesystemBundleHandle(d))
        f1 = _emit(r1)
        d2 = tmp_path / "p2"
        d2.mkdir()
        (d2 / "SOUL.md").write_text(f1["SOUL.md"])
        r2 = SoulReader().read(FilesystemBundleHandle(d2))
        # name differs by dir; compare the authored content instead.
        assert r2["spec"]["soul_content"] == r1["spec"]["soul_content"]
        assert set(_emit(r2)) == {"SOUL.md"}


class TestSingleFileComposes:
    def test_single_file_soul_flattens_into_prompt(self, tmp_path):
        scope = "sfs"
        root = tmp_path / scope
        (root / "agents" / "a1").mkdir(parents=True)
        (root / "souls" / "s1").mkdir(parents=True)
        (root / "Genome.yaml").write_text(
            "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
            f"metadata:\n  name: {scope}\nspec:\n  default_agent: a1\n"
        )
        (root / "agents" / "a1" / "AGENT.md").write_text(
            "---\nname: a1\nsoul: s1\n---\n# A1\n\nDo the thing."
        )
        # single-file soul: SOUL.md only, no soul.json.
        (root / "souls" / "s1" / "SOUL.md").write_text("# S1\n\nWarm and precise voice.")
        mi = Kernel.quick(scope, base_dir=str(tmp_path))
        _ = mi.documents
        prompt = mi.build_prompt(agent="a1")
        assert "Warm and precise voice." in prompt


class TestTwoFileFidelityPreserved:
    def test_soul_json_preserved_when_present(self, tmp_path):
        """The 2-file soulspec form is NOT regressed: a soul.json present on
        disk is read and re-emitted (byte-fidelity proven in
        test_market_conformance.py::TestRealSouls)."""
        import json
        d = tmp_path / "brad"
        d.mkdir()
        (d / "SOUL.md").write_text("# Brad\n\nA persona.")
        (d / "soul.json").write_text(json.dumps({"specVersion": "0.4", "name": "brad"}))
        raw = SoulReader().read(FilesystemBundleHandle(d))
        assert raw["spec"]["soul_json"]["specVersion"] == "0.4"
        files = _emit(raw)
        assert set(files) == {"SOUL.md", "soul.json"}
