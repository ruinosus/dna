"""Vocab Phase 4 + Wave 0 regression tests.

Ensure legacy Kind classes Dream e DreamInterpretation NÃO existem
mais (phase 4 rename) e que canonical names SynthesisRun + PatternInsight
estão registered com storage path correto (Wave 0 fix).

Story s-cleanup-legacy-dreams-bundle-dir-26052026.
"""
from __future__ import annotations

import importlib
import pytest


SDLC_MODULE = "dna.extensions.sdlc"


def test_legacy_dream_kind_class_does_not_exist():
    """Phase 4 — DreamKind class removida em favor de SynthesisRunKind."""
    mod = importlib.import_module(SDLC_MODULE)
    assert not hasattr(mod, "DreamKind"), (
        "DreamKind ressurgiu — Phase 4 vocab rename foi revertida? "
        "Use SynthesisRunKind."
    )


def test_legacy_dream_interpretation_kind_class_does_not_exist():
    """Phase 4 — DreamInterpretationKind removida em favor de PatternInsightKind."""
    mod = importlib.import_module(SDLC_MODULE)
    assert not hasattr(mod, "DreamInterpretationKind"), (
        "DreamInterpretationKind ressurgiu — use PatternInsightKind."
    )


def test_synthesis_run_kind_storage_path_is_synthesis_runs():
    """Wave 0 — SynthesisRun storage container deve ser 'synthesis-runs'.

    F3 lote-2 (2026-06-11): a classe SynthesisRunKind foi deletada — o
    port é sintetizado de kinds/synthesis-run.kind.yaml; o invariante de
    storage vale igual no port registrado."""
    from dna.extensions.sdlc import SdlcExtension
    from dna.kernel import Kernel

    mod = importlib.import_module(SDLC_MODULE)
    assert not hasattr(mod, "SynthesisRunKind"), (
        "SynthesisRunKind class ressurgiu — o descriptor é a fonte (F3)."
    )
    k = Kernel()
    k.load(SdlcExtension())
    storage = k.kind_port_for("SynthesisRun").storage
    assert storage.container == "synthesis-runs", (
        f"SynthesisRun storage.container = {storage.container!r}, "
        "expected 'synthesis-runs' (legacy 'dreams' deprecated)"
    )
    assert storage.marker == "SYNTHESIS_RUN.md", (
        f"SynthesisRun storage.marker = {storage.marker!r}, "
        "expected 'SYNTHESIS_RUN.md' (legacy 'DREAM.md' deprecated)"
    )


def test_pattern_insight_kind_storage_path_is_pattern_insights():
    """Wave 0 BUG fix — PatternInsight storage não pode ser 'dream-interpretations'.

    F3 lote-1 (2026-06-10): a classe PatternInsightKind foi deletada — o
    port é sintetizado de kinds/pattern-insight.kind.yaml; o invariante de
    storage vale igual no port registrado."""
    from dna.extensions.sdlc import SdlcExtension
    from dna.kernel import Kernel

    mod = importlib.import_module(SDLC_MODULE)
    assert not hasattr(mod, "PatternInsightKind"), (
        "PatternInsightKind class ressurgiu — o descriptor é a fonte (F3)."
    )
    k = Kernel()
    k.load(SdlcExtension())
    storage = k.kind_port_for("PatternInsight").storage
    assert storage.container == "pattern-insights", (
        f"PatternInsight storage.container = {storage.container!r}, "
        "expected 'pattern-insights' (legacy 'dream-interpretations' was a Phase 4 miss, "
        "fixed in Story s-fix-pattern-insight-storage-path-26052026)"
    )
    assert storage.marker == "PATTERN_INSIGHT.md", (
        f"PatternInsight storage.marker = {storage.marker!r}, "
        "expected 'PATTERN_INSIGHT.md' (legacy 'INTERPRETATION.md' deprecated)"
    )


def test_legacy_kind_strings_not_in_registered_kinds():
    """Kernel registry não deve aceitar 'Dream' nem 'DreamInterpretation' como kind names.

    Importa kernel + Runtime e verifica via Kernel.auto() (entry-point discovery).
    """
    from dna.kernel import Kernel
    k = Kernel.auto()
    registered_kinds = {kn for (_api, kn) in k._kinds.keys()}
    forbidden = {"Dream", "DreamInterpretation"}
    leaked = forbidden & registered_kinds
    assert not leaked, (
        f"Legacy kind names ressurgiram no registry: {sorted(leaked)}. "
        "Phase 4 vocab rename foi quebrada."
    )
    # Positive: canonical kinds present
    assert "SynthesisRun" in registered_kinds
    assert "PatternInsight" in registered_kinds


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
