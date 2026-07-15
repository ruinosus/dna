"""TDD for **serving** the ingested Spec Kit toolkit over the DNA faces
(ADR ADR-spec-kit-adoption §5, Layer 3 — the payoff).

`dna specify install-templates` lands the toolkit as PromptTemplate + Skill
Kinds. These use-cases (``dna.application`` — the shared core the MCP server is
a thin adapter over) serve them LIVE and tenant-aware, so a per-workspace/tenant
overlay of a template or slash-command wins with **zero redeploy**. That is the
Layer 3 thesis: the spec-kit toolkit becomes versioned, governed, portable
policy rather than per-repo files.
"""
from __future__ import annotations

import asyncio
import pathlib

import pytest
from click.testing import CliRunner

pytest.importorskip("fastmcp", reason="the MCP runtime face needs the optional 'fastmcp' extra")

from dna_cli import _mcp_server as M  # noqa: E402
from dna_cli.specify_cmd import specify  # noqa: E402

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "speckit"


@pytest.fixture
def toolkit_scope(tmp_path, monkeypatch):
    """A fs scope with the fixture toolkit installed via the real CLI path."""
    base = tmp_path / ".dna"
    (base / "kit").mkdir(parents=True)
    (base / "kit" / "Package.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Package\n"
        "metadata:\n  name: kit\nspec:\n  description: kit\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DNA_BASE_DIR", str(base))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    r = CliRunner().invoke(
        specify, ["install-templates", str(FIXTURE), "--scope", "kit",
                  "--constitution-as", "guardrail"],
    )
    assert r.exit_code == 0, r.output
    return base


def test_list_and_get_templates(toolkit_scope):
    async def scenario():
        live = await M.boot_live(base_dir=str(toolkit_scope))
        listing = await M.list_templates_impl(live, scope="kit")
        one = await M.get_template_impl(live, "speckit-spec-template", scope="kit")
        return listing, one

    listing, one = asyncio.run(scenario())
    names = {t["name"] for t in listing["templates"]}
    assert "speckit-spec-template" in names
    assert "speckit-constitution-template" in names
    # full body is served (byte-source), not just a summary
    assert one["body"] == (FIXTURE / ".specify/templates/spec-template.md").read_text(
        encoding="utf-8"
    )


def test_list_and_get_skills(toolkit_scope):
    async def scenario():
        live = await M.boot_live(base_dir=str(toolkit_scope))
        listing = await M.list_skills_impl(live, scope="kit")
        one = await M.get_skill_impl(live, "speckit-specify", scope="kit")
        scripts = await M.get_skill_impl(live, "speckit-scripts", scope="kit")
        return listing, one, scripts

    listing, one, scripts = asyncio.run(scenario())
    names = {s["name"] for s in listing["skills"]}
    assert {"speckit-specify", "speckit-plan", "speckit-tasks", "speckit-scripts"} <= names
    # the served slash-command instruction is the verbatim command definition
    assert one["instruction"] == (
        FIXTURE / ".specify/templates/commands/specify.md"
    ).read_text(encoding="utf-8")
    assert one["description"].startswith("Create or update the feature specification")
    # the scripts Skill exposes its bundled files
    assert "bash/create-new-feature.sh" in scripts["scripts"]


def test_get_template_unknown_raises(toolkit_scope):
    async def scenario():
        live = await M.boot_live(base_dir=str(toolkit_scope))
        await M.get_template_impl(live, "nope", scope="kit")

    with pytest.raises(ValueError, match="not found"):
        asyncio.run(scenario())


def test_template_override_per_workspace_no_redeploy(toolkit_scope):
    """The Layer 3 payoff: a per-workspace/tenant overlay of a spec-kit template
    wins LIVE — no redeploy. Base scope keeps the original; the tenant view
    returns the override."""
    sentinel = "# ACME house spec format — overridden without redeploy\n"

    async def scenario():
        live = await M.boot_live(base_dir=str(toolkit_scope))
        base = await M.get_template_impl(live, "speckit-spec-template", scope="kit")
        # Write a per-tenant (workspace) overlay of the template — same name,
        # different body — through the kernel's tenant writer.
        overlay = {
            "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
            "kind": "PromptTemplate",
            "metadata": {"name": "speckit-spec-template"},
            "spec": {"body": sentinel, "tags": ["spec-kit"], "pattern": "spec-kit"},
        }
        await live.kernel.with_tenant("acme").write_document(
            "kit", "PromptTemplate", "speckit-spec-template", overlay
        )
        overridden = await M.get_template_impl(
            live, "speckit-spec-template", scope="kit", tenant="acme"
        )
        base_again = await M.get_template_impl(live, "speckit-spec-template", scope="kit")
        return base, overridden, base_again

    base, overridden, base_again = asyncio.run(scenario())
    assert overridden["tenant"] == "acme"
    assert overridden["body"] == sentinel          # overlay wins for the tenant
    assert base["body"] != sentinel                # base untouched
    assert base_again["body"] == base["body"]      # still untouched, no redeploy


def test_tools_wired_into_fastmcp(toolkit_scope):
    """The four toolkit tools are actually registered on the MCP protocol surface."""
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(toolkit_scope))
        async with Client(server) as client:
            return {t.name for t in await client.list_tools()}

    names = asyncio.run(scenario())
    assert {"list_templates", "get_template", "list_skills", "get_skill"} <= names
