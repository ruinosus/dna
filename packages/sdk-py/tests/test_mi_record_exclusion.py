"""F2.5 two-planes Task 2: records are EXCLUDED from the MI build
(O(composição)) and composition refs to record kinds become ``deferred``
in CompositionResult instead of false-``missing`` (spec D6).
"""
import pytest

from dna.kernel import Kernel
from dna.kernel.kind_base import KindBase
from dna.kernel.protocols import CompositionResult, StorageDescriptor

# -- reuse do harness (pytest põe tests/ no sys.path; SEM prefixo tests.) --
from test_kernel_invalidate_modes import _FakeWritableSource


class _StoryLike(KindBase):
    api_version = "test.io/v1"
    kind = "StoryLike"
    alias = "test-storylike"
    storage = StorageDescriptor.yaml("storylikes")
    plane = "record"


class _AgentLike(KindBase):
    api_version = "test.io/v1"
    kind = "AgentLike"
    alias = "test-agentlike"
    storage = StorageDescriptor.yaml("agentlikes")
    # plane default = composition


class _MitigationLike(KindBase):
    """Composition kind whose dep_filters point at BOTH planes —
    the Mitigation→Finding shape from the spec (D6)."""
    api_version = "test.io/v1"
    kind = "MitigationLike"
    alias = "test-mitigationlike"
    storage = StorageDescriptor.yaml("mitigationlikes")

    def dep_filters(self):
        return {"story": "test-storylike", "agent": "test-agentlike"}


def _raw(kind, name, **spec):
    return {"apiVersion": "test.io/v1", "kind": kind,
            "metadata": {"name": name}, "spec": spec}


def _kernel():
    k = Kernel()
    k._source = _FakeWritableSource()  # type: ignore[assignment]
    k.kind(_StoryLike())
    k.kind(_AgentLike())
    k.kind(_MitigationLike())
    return k


# ---------- builder exclusion ----------

def test_build_excludes_record_docs_from_materialization():
    k = _kernel()
    mi = k.build(
        [_raw("AgentLike", "a-1"), _raw("StoryLike", "s-1"),
         _raw("StoryLike", "s-2"), _raw("MitigationLike", "m-1")],
        "scope-x",
    )
    kinds = {d.kind for d in mi.documents}
    assert "StoryLike" not in kinds, "records must NOT be materialized in the MI"
    assert kinds == {"AgentLike", "MitigationLike"}


def test_build_keeps_unregistered_kinds():
    """Unknown kinds (no KindPort) keep today's behavior — _parse_doc
    decides; the plane filter only skips REGISTERED record kinds."""
    k = _kernel()
    mi = k.build(
        [_raw("AgentLike", "a-1"), _raw("StoryLike", "s-1")],
        "scope-x",
    )
    assert {d.kind for d in mi.documents} == {"AgentLike"}


def test_build_excludes_record_docs_with_variant_api_version():
    """Real datasets hold record docs under LEGACY apiVersions (e.g.
    github.com/ruinosus/dna/cognitive/v1 LessonLearned vs registered github.com/ruinosus/dna/sdlc/v1) — the exact
    (apiVersion, kind) lookup misses them. The builder must fall back to
    kind_plane (by NAME), matching the mi.all/one delegation criterion;
    otherwise they materialize yet are unreachable through the MI.
    Caught live by test_mi_exclusion_integration_pg against dev data."""
    k = _kernel()
    legacy = {"apiVersion": "legacy.io/v9", "kind": "StoryLike",
              "metadata": {"name": "s-legacy"}, "spec": {}}
    mi = k.build([_raw("AgentLike", "a-1"), legacy], "scope-x")
    assert {d.kind for d in mi.documents} == {"AgentLike"}


# ---------- buildPrompt smoke (composição intacta) ----------

def test_build_prompt_smoke_with_records_present():
    """Real extensions: an agent + skill compose normally while a record
    doc (Evidence) sits in the same scope — and never enters the MI."""
    from dna.extensions.helix import HelixExtension
    from dna.extensions.agentskills import AgentSkillsExtension
    from dna.extensions.evidence import EvidenceExtension

    k = Kernel()
    k.load(HelixExtension())
    k.load(AgentSkillsExtension())
    k.load(EvidenceExtension())

    raws = [
        {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
         "metadata": {"name": "demo"}, "spec": {"agents": []}},
        {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
         "metadata": {"name": "helper"},
         "spec": {"instruction": "Help the user.", "skills": ["greet"]}},
        {"apiVersion": "agentskills.io/v1", "kind": "Skill",
         "metadata": {"name": "greet"},
         "spec": {"description": "Greets people.",
                  "instructions": "Always greet warmly."}},
        {"apiVersion": "github.com/ruinosus/dna/evidence/v1", "kind": "Evidence",
         "metadata": {"name": "ev-1"}, "spec": {"event": "x"}},
    ]
    mi = k.build(raws, "demo")
    assert {d.kind for d in mi.documents} >= {"Agent", "Skill"}
    assert "Evidence" not in {d.kind for d in mi.documents}
    prompt = mi.prompt.build(agent="helper")
    assert "Help the user." in prompt


# ---------- composition validate: record refs → deferred ----------

def test_validate_record_ref_is_deferred_not_missing():
    k = _kernel()
    mi = k.build(
        [_raw("AgentLike", "a-1"),
         _raw("MitigationLike", "m-1", story="s-77", agent="a-1")],
        "scope-x",
    )
    result = mi.composition.validate()
    assert any("s-77" in d for d in result.deferred), (
        f"record ref must be deferred, got deferred={result.deferred}"
    )
    assert not any("s-77" in m for m in result.missing), (
        "record refs must never be reported missing (false-missing, spec D6)"
    )
    assert any("a-1" in r for r in result.resolved)
    assert result.valid is True


def test_validate_missing_composition_ref_still_missing():
    k = _kernel()
    mi = k.build(
        [_raw("MitigationLike", "m-1", story="s-77", agent="a-ghost")],
        "scope-x",
    )
    result = mi.composition.validate()
    assert any("a-ghost" in m for m in result.missing)
    assert result.valid is False


def test_composition_result_deferred_defaults_empty():
    """Back-compat: existing constructors (nav_kernel, admin) omit
    deferred and get []."""
    r = CompositionResult(resolved=[], missing=[], warnings=[])
    assert r.deferred == []
    assert r.valid is True
