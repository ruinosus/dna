"""T1 — schema validation tests for ``Engram``, the surviving member of
what was once the "Cognitive Memory Triad".

``Engram`` (alias ``helix-engram``) — affective recall artifact. Renamed
from ``LessonLearned`` (s-engram-rename, 2026-07-19) and moved OUT of
SdlcExtension into HelixExtension (``github.com/ruinosus/dna/v1``).

censo-12-kinds (2026-07-20): the other two members, ``SynthesisRun`` and
``ArchiveProposal``, were DELETED — along with ``Forecast``, whose tests
also lived here. Nothing in this distribution ever produced or consumed
them: the cognition-engine family they were designed to receive output
from never existed here (it came in with an unrelated extraction). Engram
stays because it is a real platform memory primitive with live consumers.

Original spec (historical): ``docs/superpowers/specs/2026-05-11-cognitive-memory-triad.md`` §3.

Engram uses BUNDLE storage with the ``LESSON_LEARNED.md`` marker file,
mirroring the SPEC.md / PLAN.md convention.
"""
from __future__ import annotations


from dna.kernel import Kernel
from dna.extensions.helix import HelixExtension
from dna.extensions.sdlc import SdlcExtension


def _kernel() -> Kernel:
    """Both extensions loaded: Engram lives in HelixExtension
    (s-engram-rename); SdlcExtension is still loaded so the registration
    test can assert on the sdlc api_version bucket."""
    k = Kernel()
    k.load(SdlcExtension())
    k.load(HelixExtension())
    return k


def _port(kind: str):
    """F3 lote-1/lote-2: the triad classes were deleted — ports are
    synthesized from kinds/*.kind.yaml (same registration funnel)."""
    return _kernel().kind_port_for(kind)


def _engram_port():
    return _port("Engram")


# ----------------------------------------------------------------------
# Registration
# ----------------------------------------------------------------------


def test_extension_registers_engram():
    """Engram is registered by HelixExtension (s-engram-rename), NOT by
    SdlcExtension. Its two former triad siblings are gone entirely
    (censo-12-kinds)."""
    k = _kernel()
    sdlc_kinds = sorted(kn for (av, kn) in k._kinds if av == "github.com/ruinosus/dna/sdlc/v1")
    helix_kinds = sorted(kn for (av, kn) in k._kinds if av == "github.com/ruinosus/dna/v1")
    assert "Engram" in helix_kinds
    assert "SynthesisRun" not in sdlc_kinds
    assert "ArchiveProposal" not in sdlc_kinds
    assert "Forecast" not in sdlc_kinds


def test_extension_version_is_post_cognitive_triad():
    """v1.9.0 added the cognitive triad. Test pins minimum version, not
    exact — exact bumps churn every Kind addition. Cross-Stack Parity
    oracle still reads .version."""
    import packaging.version
    actual = packaging.version.parse(SdlcExtension().version)
    assert actual >= packaging.version.parse("1.9.0"), (
        f"SdlcExtension.version regressed below 1.9.0: {actual}"
    )


# ----------------------------------------------------------------------
# Storage descriptors — bundle marker per Spec §3
# ----------------------------------------------------------------------


def test_engram_storage_bundle():
    sd = _engram_port().storage
    assert sd.pattern.value == "bundle"
    assert sd.container == "lessons-learned"
    assert sd.marker == "LESSON_LEARNED.md"


def test_cognitive_display_labels_are_market_aligned():
    """Surface labels use enterprise pt-BR (PMBOK 'Lessons Learned' etc.),
    not the deprecated poetic terms (s-sdlcv2-memorias-market-viz).
    Engram's label became "Engrama" on the rename (s-engram-rename,
    2026-07-19) — the founder-approved identity for the renamed Kind."""
    assert _engram_port().display_label == "Engrama"


# ----------------------------------------------------------------------
# Lembrança schema
# ----------------------------------------------------------------------


LEMBRANCA_MIN = {
    "area": "Feature/f-cognitive-memory",
    "surface_when": ["feature_touched"],
    "source_refs": ["Narrative/cycle-f-X-20260510"],
    "affect": "wistful",
    "summary": "Lembre-se daquele ciclo onde resolvemos com Spec real.",
}


def test_remembrance_required_fields():
    schema = _engram_port().schema()
    assert set(schema["required"]) == {
        "area", "surface_when", "source_refs", "affect", "summary",
    }


def test_remembrance_affect_enum_is_evocative():
    """Per Spec §15 decision: evocative palette, not neutral pos/neg/neutral/mixed."""
    schema = _engram_port().schema()
    affect_enum = schema["properties"]["affect"]["enum"]
    assert set(affect_enum) == {"triumph", "regret", "surprise", "wistful", "ominous"}


def test_remembrance_surface_when_enum():
    schema = _engram_port().schema()
    items = schema["properties"]["surface_when"]["items"]
    assert set(items["enum"]) == {"feature_touched", "cycle_open", "session_start", "oracle_consult"}


def test_remembrance_relevance_decay_seed_default():
    """Decay seed defaults to 0.95/24h per Spec §3.1."""
    schema = _engram_port().schema()
    props = schema["properties"]
    assert props["relevance_decay_seed"]["default"] == 0.95


# ----------------------------------------------------------------------
# Aliases — match Cross-Stack Parity expectations
# ----------------------------------------------------------------------


def test_aliases_follow_sdlc_convention():
    # Engram (s-engram-rename) moved to HelixExtension — its alias follows
    # the helix convention now, not sdlc.
    assert _engram_port().alias == "helix-engram"
