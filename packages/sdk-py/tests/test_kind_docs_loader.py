"""Tests for the DOCS.md override loader and Phase A docs class attrs."""
from __future__ import annotations

from pathlib import Path

import pytest

from dna.kernel import Kernel, _load_kind_docs


# --- Phase A: every built-in kind has a non-empty `docs` class attribute -----

BUILTIN_KINDS = [
    ("dna.extensions.helix", "GenomeKind"),
    ("dna.extensions.helix", "AgentKind"),
    ("dna.extensions.helix", "ActorKind"),
    ("dna.extensions.helix", "UseCaseKind"),
    ("dna.extensions.soulspec", "SoulKind"),
    ("dna.extensions.agentskills", "SkillKind"),
    ("dna.extensions.guardrails", "GuardrailKind"),
    ("dna.extensions.agentsmd", "AgentDefinitionKind"),
]


@pytest.mark.parametrize("module_name,class_name", BUILTIN_KINDS)
def test_every_builtin_kind_has_docs_class_attr(module_name, class_name):
    import importlib
    mod = importlib.import_module(module_name)
    cls = getattr(mod, class_name)
    docs = getattr(cls, "docs", None)
    assert docs, f"{class_name} is missing `docs` class attr"
    assert len(docs) >= 100, f"{class_name}.docs is too short ({len(docs)} chars)"


# --- Phase B: _load_kind_docs resolution order --------------------------------


class _FakeKind:
    """Minimal KindPort for unit-testing the resolver."""
    api_version = "fake/v1"
    kind = "FakeKind"
    docs = "Fallback class attribute docs."


def test_resolver_falls_back_to_class_attr_when_no_docs_md():
    # _FakeKind lives in this test module; no DOCS.md ships here.
    resolved = _load_kind_docs(_FakeKind())
    assert resolved == "Fallback class attribute docs."


def test_resolver_returns_none_when_no_docs_at_all():
    class NoDocsKind:
        api_version = "fake/v1"
        kind = "NoDocs"
    assert _load_kind_docs(NoDocsKind()) is None


def test_resolver_reads_shipped_docs_md_for_single_kind_extension():
    """soulspec ships DOCS.md — loader should pick it up."""
    from dna.extensions.soulspec import SoulKind
    resolved = _load_kind_docs(SoulKind())
    assert resolved is not None
    assert "# Soul" in resolved
    assert len(resolved) >= 500


def test_resolver_reads_per_kind_docs_for_multi_kind_extension():
    """helix ships DOCS-<KindName>.md files — one per kind."""
    from dna.extensions.helix import (
        ActorKind, GenomeKind, UseCaseKind, AgentKind,
    )
    assert "# Genome" in _load_kind_docs(GenomeKind())
    assert "# Agent" in _load_kind_docs(AgentKind())
    assert "# Actor" in _load_kind_docs(ActorKind())
    assert "# UseCase" in _load_kind_docs(UseCaseKind())


def test_per_kind_docs_md_wins_over_extension_wide_docs_md(tmp_path, monkeypatch):
    """If both DOCS-<Kind>.md and DOCS.md exist, the per-kind file wins."""
    # Create a fake package directory on disk with both files.
    pkg_dir = tmp_path / "fake_ext"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "DOCS.md").write_text("# Generic extension docs")
    (pkg_dir / "DOCS-Special.md").write_text("# Special per-kind docs")

    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        import importlib
        fake_ext = importlib.import_module("fake_ext")

        # Create a kind class living inside fake_ext
        class SpecialKind:
            api_version = "fake/v1"
            kind = "Special"
            docs = "class-attr fallback"
        SpecialKind.__module__ = "fake_ext.kinds"
        # Create the kinds submodule so importlib can find __file__
        (pkg_dir / "kinds.py").write_text("")
        importlib.invalidate_caches()
        importlib.import_module("fake_ext.kinds")

        resolved = _load_kind_docs(SpecialKind())
        assert "Special per-kind docs" in resolved
    finally:
        sys.path.remove(str(tmp_path))
        for mod_name in list(sys.modules):
            if mod_name == "fake_ext" or mod_name.startswith("fake_ext."):
                del sys.modules[mod_name]


def test_kernel_load_populates_resolved_docs_and_describe_kind():
    """After `kernel.kind(k)`, the port has `_resolved_docs` set and
    `describe_kind` returns it."""
    from dna.extensions.helix import HelixExtension
    k = Kernel()
    k.load(HelixExtension())

    for (av, kn), kp in k._kinds.items():
        assert getattr(kp, "_resolved_docs", None), (
            f"Kind {kn} has no _resolved_docs after load"
        )

    info = k.describe_kind("Genome")
    assert info is not None
    assert info["kind"] == "Genome"
    assert "# Genome" in info["docs"]


def test_all_builtin_kinds_have_resolved_docs_after_kernel_load():
    """Smoke test: load every built-in extension, every kind ends up with
    non-empty resolved docs."""
    from dna.extensions.agentskills import AgentSkillsExtension
    from dna.extensions.agentsmd import AgentsMdExtension
    from dna.extensions.helix import HelixExtension
    from dna.extensions.guardrails import GuardrailExtension
    from dna.extensions.soulspec import SoulSpecExtension

    k = Kernel()
    for ext in [
        HelixExtension(),
        SoulSpecExtension(),
        AgentSkillsExtension(),
        GuardrailExtension(),
        AgentsMdExtension(),
    ]:
        k.load(ext)

    # 4 helix + 1 soul + 1 skill + 1 guardrail + 1 agentcontext = 8
    assert len(k._kinds) >= 8
    for (av, kn), kp in k._kinds.items():
        rd = getattr(kp, "_resolved_docs", None)
        assert rd, f"{kn} has no resolved docs"
        assert len(rd) >= 100, f"{kn} resolved docs too short"
