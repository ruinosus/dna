"""s-intel-portfolio-context — intel foundation Kinds (IntelSource + Insight).

Covers the two record Kinds shipped as the `intel` extension (F3 descriptors,
record plane, TENANTED — per-tenant user/generated data, NOT inheritable):

1. The `intel` extension registers IntelSource (alias ``intel-source``) and
   IntelInsight (alias ``intel-insight``, kind name ``IntelInsight`` — NOT
   ``Insight``, which belonged to the SDLC oracle Kind ``sdlc-insight`` until
   that Kind was deleted in censo-12-kinds; the shipped name stays IntelInsight).
2. Both are record-plane, TENANTED, declarative (synthesized from the
   descriptor), and do NOT collide with the SDLC ``Insight`` Kind.
3. IntelInsight is embeddable (``embed: [title, fact]``) so a later dedup story
   can do semantic recall; IntelSource is not.
4. A TENANTED write→read round-trip proves the schema validates and the doc
   round-trips under a tenant.

TS twin: tests/intel-extension.test.ts.
"""
from __future__ import annotations

import pytest

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.extensions.intel import IntelExtension
from dna.kernel import Kernel
from dna.kernel.protocols import TenantScope


# ---------------------------------------------------------------------------
# 1. Kind registration (descriptors)
# ---------------------------------------------------------------------------

def test_intel_source_registered_from_descriptor():
    k = Kernel()
    k.load(IntelExtension())
    kp = k.kind_port_for("IntelSource")
    assert kp is not None
    assert kp.alias == "intel-source"
    assert kp.plane == "record"
    # TENANTED — a source is the tenant's OWN watchlist (per-tenant data),
    # NOT a shared _lib default. It is deliberately NOT inheritable.
    assert kp.scope == TenantScope.TENANTED
    assert kp.storage.container == "intel-sources"
    assert getattr(kp, "__declarative__", False) is True


def test_intel_insight_registered_from_descriptor():
    k = Kernel()
    k.load(IntelExtension())
    kp = k.kind_port_for("IntelInsight")
    assert kp is not None
    assert kp.alias == "intel-insight"
    assert kp.plane == "record"
    assert kp.scope == TenantScope.TENANTED
    assert kp.storage.container == "intel-insights"
    assert getattr(kp, "__declarative__", False) is True
    # Embeddable so a later dedup story can recall semantically similar insights.
    assert kp.embed_fields == ["title", "fact"]


def test_intel_insight_named_intelinsight_not_insight():
    """The intel Insight registers as ``IntelInsight`` — the bare ``Insight``
    name belonged to the SDLC oracle Kind, and two api_versions sharing a kind
    name makes bare-name lookup ambiguous (i-195). That SDLC Kind is now gone
    (censo-12-kinds) but the shipped name stays IntelInsight; the bare
    ``Insight`` must resolve to nothing."""
    k = Kernel()
    k.load(IntelExtension())
    assert k.kind_port_for("IntelInsight") is not None
    assert k.kind_port_for("Insight") is None


def test_intel_kinds_register_under_auto_and_bare_insight_is_free():
    """Under full entry-point discovery the intel Kinds register cleanly.

    This test used to assert the intel Kinds COEXISTED with the SDLC
    ``Insight`` (alias sdlc-insight) without colliding. That Kind was deleted
    in censo-12-kinds (2026-07-20), so the bare name is now unclaimed —
    asserting THAT is what keeps the check honest: if anything ever registers
    a bare ``Insight`` again, the i-195 ambiguity is back."""
    k = Kernel.auto()
    assert k.kind_port_for("IntelSource") is not None
    assert k.kind_port_for("IntelInsight").alias == "intel-insight"
    assert k.kind_port_for("Insight") is None


# ---------------------------------------------------------------------------
# 2. TENANTED write→read round-trip (schema validates, doc round-trips)
# ---------------------------------------------------------------------------

def _bootstrap_scope(tmp_path, scope: str) -> None:
    """Create the base scope dir with a Genome manifest so a TENANTED write's
    overlay has a base scope to hang off (mirrors test_audit_extension.py)."""
    (tmp_path / scope).mkdir(parents=True, exist_ok=True)
    (tmp_path / scope / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
        f"metadata: {{name: {scope}}}\nspec: {{}}\n"
    )


async def _kernel(tmp_path) -> Kernel:
    k = Kernel()
    k.load(IntelExtension())
    _bootstrap_scope(tmp_path, "portfolio")
    src = FilesystemWritableSource(str(tmp_path), writers=list(k._writers), kernel=k)
    k.source(src)
    src.attach_kernel(k)
    return k


@pytest.mark.asyncio
async def test_intel_source_tenanted_round_trip(tmp_path):
    k = await _kernel(tmp_path)
    await k.write_document(
        "portfolio", "IntelSource", "copiloto-medico",
        {
            "apiVersion": "github.com/ruinosus/dna/intel/v1",
            "kind": "IntelSource",
            "metadata": {"name": "copiloto-medico"},
            "spec": {
                "name": "copiloto-medico",
                "type": "repo",
                "uri": "github.com/acme/copiloto-medico",
                "cadence": "weekly",
                "threshold": 0.7,
                "pirs": ["regulatory", "safety"],
                "muted": False,
            },
        },
        tenant="acme",
    )
    rows = [r async for r in k.query("portfolio", "IntelSource", tenant="acme")]
    assert len(rows) == 1
    spec = rows[0]["spec"]
    assert spec["type"] == "repo"
    assert spec["threshold"] == 0.7
    assert spec["pirs"] == ["regulatory", "safety"]


@pytest.mark.asyncio
async def test_intel_insight_tenanted_round_trip(tmp_path):
    k = await _kernel(tmp_path)
    await k.write_document(
        "portfolio", "IntelInsight", "new-cfr-rule",
        {
            "apiVersion": "github.com/ruinosus/dna/intel/v1",
            "kind": "IntelInsight",
            "metadata": {"name": "new-cfr-rule"},
            "spec": {
                "title": "New 21 CFR Part 11 guidance published",
                "fact": "FDA released updated Part 11 guidance on 2026-07-01.",
                "why": "Copiloto-medico must re-check its audit-trail claims.",
                "action": "Review audit-trail coverage against the new guidance.",
                "score": 0.82,
                "source_ref": "copiloto-medico",
                "pirs": ["regulatory"],
                "citations": [{"url": "https://fda.gov/part11", "title": "FDA"}],
                "state": "new",
                "evidence_rating": "evidence-based",
            },
        },
        tenant="acme",
    )
    rows = [r async for r in k.query("portfolio", "IntelInsight", tenant="acme")]
    assert len(rows) == 1
    spec = rows[0]["spec"]
    assert spec["score"] == 0.82
    assert spec["state"] == "new"
    assert spec["source_ref"] == "copiloto-medico"
    assert spec["citations"][0]["url"] == "https://fda.gov/part11"
