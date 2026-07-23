"""Phase 0 — Template contract tests."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dna.kernel.compose.templates import Template, materialize


def test_template_dataclass_roundtrip():
    t = Template(
        id="gaia/privacy",
        label="Privacy Assessment",
        kind="Assessment",
        description="GAIA privacy eval bundle",
        files_root=Path("/fake/path"),
        owner_extension="gaia",
    )
    assert t.id == "gaia/privacy"
    assert t.kind == "Assessment"
    assert t.files_root == Path("/fake/path")
    assert t.owner_extension == "gaia"
    assert t.post_init_hint is None


def test_materialize_copies_files_to_target():
    with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
        src_root = Path(src)
        (src_root / "program.md").write_text("hello")
        (src_root / "sub").mkdir()
        (src_root / "sub" / "nested.txt").write_text("world")

        t = Template(
            id="test/demo", label="Demo", kind="X",
            description="", files_root=src_root, owner_extension="test",
        )
        written = materialize(t, target_root=Path(dst))

        assert (Path(dst) / "program.md").read_text() == "hello"
        assert (Path(dst) / "sub" / "nested.txt").read_text() == "world"
        assert sorted(str(p.relative_to(dst)) for p in written) == ["program.md", "sub/nested.txt"]


def test_materialize_errors_on_existing_file_by_default():
    with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
        src_root = Path(src)
        (src_root / "program.md").write_text("new")
        (Path(dst) / "program.md").write_text("existing")

        t = Template(
            id="test/demo", label="Demo", kind="X",
            description="", files_root=src_root, owner_extension="test",
        )
        with pytest.raises(FileExistsError):
            materialize(t, target_root=Path(dst))


def test_materialize_overwrite_when_requested():
    with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
        src_root = Path(src)
        (src_root / "program.md").write_text("new")
        (Path(dst) / "program.md").write_text("existing")

        t = Template(
            id="test/demo", label="Demo", kind="X",
            description="", files_root=src_root, owner_extension="test",
        )
        materialize(t, target_root=Path(dst), on_conflict="overwrite")
        assert (Path(dst) / "program.md").read_text() == "new"


def test_materialize_preserves_binary_files():
    with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
        src_root = Path(src)
        payload = bytes(range(256))
        (src_root / "logo.png").write_bytes(payload)

        t = Template(
            id="test/demo", label="Demo", kind="X",
            description="", files_root=src_root, owner_extension="test",
        )
        materialize(t, target_root=Path(dst))
        assert (Path(dst) / "logo.png").read_bytes() == payload


def test_extension_without_templates_is_valid():
    """Extensions that predate Phase 0 must keep working (no templates() method)."""
    class LegacyExt:
        name = "legacy"
        version = "1.0.0"

        def register(self, kernel):
            pass

    ext = LegacyExt()
    assert not hasattr(ext, "templates")  # no method = opted out, still valid


def test_extension_with_templates_returns_list():
    class ModernExt:
        name = "modern"
        version = "1.0.0"

        def register(self, kernel):
            pass

        def templates(self):
            return [
                Template(
                    id="modern/one", label="One", kind="X",
                    description="", files_root=Path("/tmp"),
                    owner_extension="modern",
                )
            ]

    ext = ModernExt()
    out = ext.templates()
    assert len(out) == 1
    assert out[0].id == "modern/one"


def test_template_reexported_from_protocols():
    """Template must be importable from kernel.protocols for API convenience."""
    from dna.kernel.protocols import Template as ProtocolsTemplate
    from dna.kernel.compose.templates import Template as TemplatesTemplate

    # Same class object (re-export, not re-definition)
    assert ProtocolsTemplate is TemplatesTemplate


def test_kernel_list_templates_aggregates_from_extensions(tmp_path):
    from dna.kernel import Kernel

    files_root = tmp_path / "fake_template"
    files_root.mkdir()
    (files_root / "manifest.yaml").write_text("kind: Demo\n")

    class DemoExt:
        name = "demo"
        version = "1.0.0"

        def register(self, kernel):
            pass

        def templates(self):
            return [Template(
                id="demo/one", label="One", kind="Demo",
                description="", files_root=files_root,
                owner_extension="demo",
            )]

    k = Kernel()
    k.load(DemoExt())

    ts = k.list_templates()
    assert len(ts) == 1
    assert ts[0].id == "demo/one"


def test_kernel_scaffold_materializes_template(tmp_path):
    from dna.kernel import Kernel

    files_root = tmp_path / "src"
    files_root.mkdir()
    (files_root / "manifest.yaml").write_text("kind: Demo\n")
    target = tmp_path / "dst"

    class DemoExt:
        name = "demo"
        version = "1.0.0"

        def register(self, kernel):
            pass

        def templates(self):
            return [Template(
                id="demo/one", label="One", kind="Demo",
                description="", files_root=files_root,
                owner_extension="demo",
            )]

    k = Kernel()
    k.load(DemoExt())
    written = k.scaffold("demo/one", target_root=target)

    assert (target / "manifest.yaml").read_text() == "kind: Demo\n"
    assert [str(p.relative_to(target)) for p in written] == ["manifest.yaml"]


def test_kernel_scaffold_unknown_id_raises():
    from dna.kernel import Kernel

    k = Kernel()
    with pytest.raises(KeyError):
        k.scaffold("ghost/missing", target_root=Path("/tmp"))


def test_materialize_rejects_invalid_on_conflict(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "f.txt").write_text("x")
    t = Template(
        id="test/demo", label="Demo", kind="X", description="",
        files_root=src, owner_extension="test",
    )
    import pytest
    with pytest.raises(ValueError, match="unknown on_conflict"):
        from dna.kernel.compose.templates import materialize
        materialize(t, target_root=tmp_path / "dst", on_conflict="overwite")  # noqa: typo intentional


def test_kernel_scaffold_get_type_hints_works():
    """Regression: Path must be importable at module scope so get_type_hints succeeds."""
    from typing import get_type_hints
    from dna.kernel import Kernel
    hints = get_type_hints(Kernel.scaffold)
    assert "target_root" in hints
    from pathlib import Path
    assert hints["target_root"] is Path
