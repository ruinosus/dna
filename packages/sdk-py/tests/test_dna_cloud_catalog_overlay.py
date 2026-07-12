"""DNA Cloud starter catalog — inheritance + BYO tenant-overlay smoke.

Story ``s-dna-cloud-starter-catalog`` / ADR ``adr-dna-cloud-content``.

Proves the two properties the catalog + BYO product rests on, using DNA's
REAL composition/overlay APIs (no new machinery):

1. **Inheritance (the on-ramp).** A tenant scope that ships no agents of its
   own INHERITS the shared ``_lib`` catalog agent — ``resolve_document`` walks
   to ``_lib`` and marks the result ``is_inherited``.

2. **BYO overlay (the moat).** A tenant AUTHORS its own version of a base
   catalog agent as a tenant overlay; that tenant sees the overlay while a
   different tenant still sees the base — tenant isolation on the same doc.

The overlay half mirrors ``test_composition_v2_resolver.py`` (the canonical
resolver overlay test) with a ``MockSource`` so it needs no Postgres. A second
class loads the REAL on-disk catalog agents and asserts each composes its OWN
persona + guardrails — a guard on the shipped ``examples/dna-cloud/.dna/_lib``
content itself.
"""
from __future__ import annotations

import pathlib
from typing import Any

import pytest

from dna.kernel import Kernel

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_CATALOG_BASE = str(_REPO_ROOT / "examples" / "dna-cloud" / ".dna")


# ──────────────────────────────────────────────────────────────────────
# MockSource — same minimal SourcePort shim the resolver suite uses.
# ──────────────────────────────────────────────────────────────────────


class MockSource:
    def __init__(self) -> None:
        # (scope, kind, name, tenant) → raw doc dict
        self.docs: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    async def load_one(
        self, scope: str, kind: str, name: str, *,
        readers=None, tenant: str | None = None,
    ) -> dict[str, Any] | None:
        return self.docs.get((scope, kind, name, tenant or ""))

    async def query(
        self, scope: str, kind: str, *,
        filter=None, projection=None, limit=None, offset=None,
        order_by=None, tenant: str | None = None,
    ):
        if False:
            yield {}
        return

    async def load_bootstrap_docs(self, scope: str, **kw):
        return []

    async def load_all(self, scope: str, readers=None, **kw):
        return []


def _make_kernel_with_mock(mock: MockSource) -> Kernel:
    k = Kernel()
    k._source = mock  # type: ignore[assignment]
    return k


def _genome(scope: str, parent_scope: str | None = None) -> dict[str, Any]:
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": scope},
        "spec": {"owner_tenant": "acme", "parent_scope": parent_scope},
    }


def _catalog_assistant(instruction: str) -> dict[str, Any]:
    """A stand-in for the shared-catalog ``assistant`` Agent."""
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "assistant"},
        "spec": {"instruction": instruction, "soul": "helpful-assistant"},
    }


# ──────────────────────────────────────────────────────────────────────
# 1. Inheritance — a tenant scope inherits the _lib catalog agent
# ──────────────────────────────────────────────────────────────────────


class TestCatalogInheritance:
    @pytest.mark.asyncio
    async def test_tenant_scope_inherits_lib_catalog_agent(self):
        """A customer scope with no agents of its own resolves the catalog
        ``assistant`` from ``_lib`` — flagged ``is_inherited``."""
        src = MockSource()
        # customer scope declares _lib as its parent; ships NO assistant of its own.
        src.docs[("acme-corp", "Genome", "acme-corp", "")] = _genome(
            "acme-corp", parent_scope="_lib",
        )
        # the shared starter catalog lives in _lib.
        src.docs[("_lib", "Agent", "assistant", "")] = _catalog_assistant(
            "Help the user with any task, clearly and honestly.",
        )
        k = _make_kernel_with_mock(src)

        res = await k.resolve_document("acme-corp", "Agent", "assistant")

        assert res.doc is not None
        assert res.is_inherited is True
        assert res.provenance.effective_layer.scope == "_lib"
        assert "clearly and honestly" in res.doc["spec"]["instruction"]


# ──────────────────────────────────────────────────────────────────────
# 2. BYO overlay — a tenant overrides the base catalog agent (the moat)
# ──────────────────────────────────────────────────────────────────────


class TestByoTenantOverlay:
    @pytest.mark.asyncio
    async def test_tenant_overlay_wins_over_catalog_base(self):
        """Tenant ``acme`` authors its own ``assistant`` overlay; that tenant
        sees the overlay, while the base (and other tenants) are unaffected."""
        src = MockSource()
        src.docs[("dna-cloud", "Genome", "dna-cloud", "")] = _genome("dna-cloud")
        # base catalog agent (what Free tenants read)
        src.docs[("dna-cloud", "Agent", "assistant", "")] = _catalog_assistant(
            "The solid default catalog assistant.",
        )
        # acme's BYO overlay (a Pro tenant authored + pushed their own)
        src.docs[("dna-cloud", "Agent", "assistant", "acme")] = _catalog_assistant(
            "Answer only in the ACME house style; escalate billing to a human.",
        )
        k = _make_kernel_with_mock(src)

        res_acme = await k.resolve_document(
            "dna-cloud", "Agent", "assistant", tenant="acme",
        )
        res_base = await k.resolve_document("dna-cloud", "Agent", "assistant")
        res_globex = await k.resolve_document(
            "dna-cloud", "Agent", "assistant", tenant="globex",
        )

        # acme sees ITS overlay
        assert "ACME house style" in res_acme.doc["spec"]["instruction"]
        assert res_acme.provenance.effective_layer.tenant == "acme"
        assert res_acme.is_inherited is False

        # base is untouched
        assert "solid default" in res_base.doc["spec"]["instruction"]

        # a DIFFERENT tenant with no overlay falls through to the base
        assert "solid default" in res_globex.doc["spec"]["instruction"]
        assert res_globex.provenance.effective_layer.tenant in (None, "")


# ──────────────────────────────────────────────────────────────────────
# 3. Content guard — the REAL on-disk catalog agents compose correctly
# ──────────────────────────────────────────────────────────────────────


class TestCatalogContentComposes:
    """The three shipped ``_lib`` agents each compose their OWN persona +
    guardrails from the real files under examples/dna-cloud/.dna/_lib."""

    def _mi(self):
        return Kernel.quick("_lib", base_dir=_CATALOG_BASE)

    def test_assistant_composes_its_own_soul(self):
        prompt = self._mi().build_prompt("assistant")
        assert "# Helpful Assistant" in prompt
        assert "baseline-safety" in prompt
        # a wrapped guardrail rule must survive intact (single-line rule guard)
        assert "exploitation of minors" in prompt

    def test_code_reviewer_composes_its_own_soul_and_both_guardrails(self):
        prompt = self._mi().build_prompt("code-reviewer")
        assert "# Senior Engineer" in prompt
        assert prompt.count("## Guardrail:") == 2  # baseline-safety + review-integrity
        assert "review-integrity" in prompt

    def test_dna_copilot_composes_its_own_soul(self):
        prompt = self._mi().build_prompt("dna-copilot")
        assert "# DNA Mentor" in prompt
        assert "tenant overlay" in prompt.lower()

    def test_three_agents_have_three_distinct_personas(self):
        mi = self._mi()
        firsts = {
            a: mi.build_prompt(a).strip().splitlines()[0]
            for a in ("assistant", "code-reviewer", "dna-copilot")
        }
        # No collision — each agent leads with its OWN Soul.
        assert len(set(firsts.values())) == 3, firsts
