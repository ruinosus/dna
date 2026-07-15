"""TDD for the **live spec-kit constitution** — Layer 3 governance (ADR §5).

`dna specify install-templates` maps `constitution.md` to a live `Guardrail`
(`speckit-constitution`). The ``spec_kit_constitution_guard`` (a pre_save veto in
the guardrails extension) turns that Guardrail into an ENFORCED write-time gate:
a ``severity: hard`` constitution requires every governed spec-kit Story/Plan to
trace to a Spec. The whole point is **no-deploy**: flip the constitution's
severity and the very next write is enforced differently — no restart.
"""
from __future__ import annotations

import asyncio
import pathlib

import pytest
from click.testing import CliRunner

from dna_cli import _mcp_server as M
from dna_cli.specify_cmd import specify
from dna.extensions.guardrails.write_guards import ConstitutionViolationError

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "speckit"
_SDLC = "github.com/ruinosus/dna/sdlc/v1"


@pytest.fixture
def gov_scope(tmp_path, monkeypatch):
    base = tmp_path / ".dna"
    (base / "gov").mkdir(parents=True)
    (base / "gov" / "Package.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Package\n"
        "metadata:\n  name: gov\nspec:\n  description: gov\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DNA_BASE_DIR", str(base))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    # install the toolkit → writes Guardrail speckit-constitution (severity=warn)
    r = CliRunner().invoke(
        specify, ["install-templates", str(FIXTURE), "--scope", "gov",
                  "--constitution-as", "guardrail"],
    )
    assert r.exit_code == 0, r.output
    return base


def _story(name, *, spec_kit=True, traceable=False):
    labels = ["spec-kit"] if spec_kit else []
    spec = {
        "title": name, "description": name, "status": "todo",
        "feature": "f-x", "labels": labels, "reporter": "test",
    }
    if traceable:
        spec["spec_refs"] = ["speckit-x"]
    return {"apiVersion": _SDLC, "kind": "Story", "metadata": {"name": name}, "spec": spec}


async def _set_severity(live, severity, *, tenant=None):
    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Guardrail",
        "metadata": {"name": "speckit-constitution"},
        "spec": {"rules": ["Trace every change to a spec."], "severity": severity,
                 "scope": "both", "pattern": "spec-kit"},
    }
    k = live.kernel.with_tenant(tenant) if tenant else live.kernel
    await k.write_document("gov", "Guardrail", "speckit-constitution", raw, tenant=tenant)


def test_warn_constitution_allows_untraceable(gov_scope):
    """As installed (severity=warn) a non-traceable spec-kit Story is advisory."""
    async def scenario():
        live = await M.boot_live(base_dir=str(gov_scope))
        await live.kernel.write_document("gov", "Story", "s-untraceable", _story("s-untraceable"))

    asyncio.run(scenario())  # no raise


def test_hard_constitution_vetoes_untraceable(gov_scope):
    async def scenario():
        live = await M.boot_live(base_dir=str(gov_scope))
        await _set_severity(live, "hard")
        await live.kernel.write_document("gov", "Story", "s-bad", _story("s-bad"))

    with pytest.raises(ConstitutionViolationError, match="trace to a Spec"):
        asyncio.run(scenario())


def test_hard_constitution_allows_traceable(gov_scope):
    async def scenario():
        live = await M.boot_live(base_dir=str(gov_scope))
        await _set_severity(live, "hard")
        await live.kernel.write_document(
            "gov", "Story", "s-ok", _story("s-ok", traceable=True)
        )

    asyncio.run(scenario())  # no raise


def test_hard_constitution_ignores_non_spec_kit(gov_scope):
    """The guard governs spec-kit work only — a plain Story is untouched."""
    async def scenario():
        live = await M.boot_live(base_dir=str(gov_scope))
        await _set_severity(live, "hard")
        await live.kernel.write_document(
            "gov", "Story", "s-plain", _story("s-plain", spec_kit=False)
        )

    asyncio.run(scenario())  # no raise


def test_no_deploy_governance_loop(gov_scope):
    """Flip the constitution severity → enforcement changes on the NEXT write,
    zero redeploy. hard vetoes; relax to warn and the same write succeeds."""
    async def scenario():
        live = await M.boot_live(base_dir=str(gov_scope))
        # 1. hard → the write is refused
        await _set_severity(live, "hard")
        vetoed = False
        try:
            await live.kernel.write_document("gov", "Story", "s-loop", _story("s-loop"))
        except ConstitutionViolationError:
            vetoed = True
        # 2. relax to warn (no redeploy) → the SAME write now succeeds
        await _set_severity(live, "warn")
        await live.kernel.write_document("gov", "Story", "s-loop", _story("s-loop"))
        return vetoed

    assert asyncio.run(scenario()) is True


def test_hard_constitution_vetoes_plan_without_spec_ref(gov_scope):
    async def scenario():
        live = await M.boot_live(base_dir=str(gov_scope))
        await _set_severity(live, "hard")
        plan = {"apiVersion": _SDLC, "kind": "Plan", "metadata": {"name": "p-bad"},
                "spec": {"title": "p", "status": "draft", "methodology": "spec-kit",
                         "body": "x"}}
        await live.kernel.write_document("gov", "Plan", "p-bad", plan)

    with pytest.raises(ConstitutionViolationError):
        asyncio.run(scenario())
