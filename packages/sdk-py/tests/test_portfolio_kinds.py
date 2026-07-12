"""s-portfolio-kinds — portfolio-console data foundation (5 record Kinds).

Covers the five record Kinds shipped as the `portfolio` extension (F3
descriptors, record plane, TENANTED — per-tenant portfolio data, NOT
inheritable), the data model of adr-portfolio-project-model:

  Organization (portfolio-org) · Project (portfolio-project) ·
  Repo (portfolio-repo) · Membership (portfolio-membership) · Role (portfolio-role)

1. Each registers from its descriptor with the expected alias, record plane,
   TENANTED scope, storage container, and __declarative__ marker.
2. The names do NOT collide with the pre-existing tenant Kinds (Tenant /
   TenantMembership) — Organization and Membership are distinct Kinds.
3. Project is the multi-repo container: repo_refs carries the N—N edge and the
   Repo Kind has no project back-ref.
4. A TENANTED write→read round-trip proves the Project and Membership schemas
   validate and round-trip under a tenant.
5. The four shipped seed Role docs (owner/admin/member/guest) validate against
   the Role schema and form the standard ladder (ranks strictly ordered).

TS twin: tests/portfolio-extension.test.ts.
"""
from __future__ import annotations

import pathlib

import pytest
import yaml

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.extensions.portfolio import PortfolioExtension
from dna.kernel import Kernel
from dna.kernel.protocols import TenantScope


# ---------------------------------------------------------------------------
# 1. Kind registration (descriptors)
# ---------------------------------------------------------------------------

_EXPECTED = {
    "Organization": ("portfolio-org", "organizations"),
    "Project": ("portfolio-project", "projects"),
    "Repo": ("portfolio-repo", "repos"),
    "Membership": ("portfolio-membership", "memberships"),
    "Role": ("portfolio-role", "roles"),
}


@pytest.mark.parametrize("kind_name,expected", _EXPECTED.items())
def test_portfolio_kind_registered_from_descriptor(kind_name, expected):
    alias, container = expected
    k = Kernel()
    k.load(PortfolioExtension())
    kp = k.kind_port_for(kind_name)
    assert kp is not None
    assert kp.alias == alias
    assert kp.plane == "record"
    # TENANTED — per-tenant portfolio data, NOT a shared _lib default, and
    # deliberately NOT inheritable (never in DEFAULT_INHERITABLE_KINDS_V1).
    assert kp.scope == TenantScope.TENANTED
    assert kp.storage.container == container
    assert getattr(kp, "__declarative__", False) is True
    # strict-schema-lint: every portfolio Kind is a closed schema.
    assert kp.schema().get("additionalProperties") is False


def test_all_five_portfolio_kinds_register():
    k = Kernel()
    k.load(PortfolioExtension())
    for kind_name in _EXPECTED:
        assert k.kind_port_for(kind_name) is not None


def test_portfolio_kinds_do_not_collide_with_tenant_kinds():
    """Organization/Membership are distinct from the pre-existing tenant Kinds
    (Tenant / TenantMembership) — no bare-name collision (cf. i-195). Under full
    entry-point discovery both families coexist."""
    k = Kernel.auto()
    assert k.kind_port_for("Organization").alias == "portfolio-org"
    assert k.kind_port_for("Membership").alias == "portfolio-membership"
    # The platform-level tenant Kinds are untouched — distinct names + aliases.
    assert k.kind_port_for("Tenant").alias == "tenant-tenant"
    assert k.kind_port_for("TenantMembership").alias == "tenant-membership"


def test_project_carries_the_nn_edge_and_repo_has_no_backref():
    """The N—N Repo↔Project edge lives on the Project side (repo_refs); the
    Repo Kind has NO project back-ref (single source of truth for the edge)."""
    k = Kernel()
    k.load(PortfolioExtension())
    project_props = k.kind_port_for("Project").schema()["properties"]
    assert "repo_refs" in project_props
    assert project_props["repo_refs"]["type"] == "array"
    # Project also owns board_scope + intel_source_refs (container of board+intel).
    assert "board_scope" in project_props
    assert "intel_source_refs" in project_props
    repo_props = k.kind_port_for("Repo").schema()["properties"]
    assert not any("project" in field for field in repo_props), (
        "Repo must not carry a project back-ref — the N—N edge is Project-side only"
    )


# ---------------------------------------------------------------------------
# 2. TENANTED write→read round-trip (schemas validate, docs round-trip)
# ---------------------------------------------------------------------------

def _bootstrap_scope(tmp_path, scope: str) -> None:
    (tmp_path / scope).mkdir(parents=True, exist_ok=True)
    (tmp_path / scope / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
        f"metadata: {{name: {scope}}}\nspec: {{}}\n"
    )


async def _kernel(tmp_path) -> Kernel:
    k = Kernel()
    k.load(PortfolioExtension())
    _bootstrap_scope(tmp_path, "acme-development")
    src = FilesystemWritableSource(str(tmp_path), writers=list(k._writers), kernel=k)
    k.source(src)
    src.attach_kernel(k)
    return k


@pytest.mark.asyncio
async def test_project_tenanted_round_trip(tmp_path):
    k = await _kernel(tmp_path)
    await k.write_document(
        "acme-development", "Project", "copiloto-medico",
        {
            "apiVersion": "github.com/ruinosus/dna/portfolio/v1",
            "kind": "Project",
            "metadata": {"name": "copiloto-medico"},
            "spec": {
                "name": "copiloto-medico",
                "slug": "copiloto-medico",
                "org_ref": "acme",
                "repo_refs": ["copiloto-medico-api", "copiloto-medico-web"],
                "board_scope": "copiloto-medico-development",
                "intel_source_refs": ["copiloto-medico"],
                "visibility": "private",
            },
        },
        tenant="acme",
    )
    rows = [r async for r in k.query("acme-development", "Project", tenant="acme")]
    assert len(rows) == 1
    spec = rows[0]["spec"]
    # The N—N edge round-trips: a project holds multiple repo refs.
    assert spec["repo_refs"] == ["copiloto-medico-api", "copiloto-medico-web"]
    assert spec["board_scope"] == "copiloto-medico-development"
    assert spec["visibility"] == "private"


@pytest.mark.asyncio
async def test_membership_tenanted_round_trip(tmp_path):
    k = await _kernel(tmp_path)
    await k.write_document(
        "acme-development", "Membership", "barna-at-acme",
        {
            "apiVersion": "github.com/ruinosus/dna/portfolio/v1",
            "kind": "Membership",
            "metadata": {"name": "barna-at-acme"},
            "spec": {
                "user": "barna@acme.example",
                "scope_type": "org",
                "scope_ref": "acme",
                "role": "owner",
                "status": "active",
            },
        },
        tenant="acme",
    )
    rows = [r async for r in k.query("acme-development", "Membership", tenant="acme")]
    assert len(rows) == 1
    spec = rows[0]["spec"]
    assert spec["role"] == "owner"
    assert spec["scope_type"] == "org"
    assert spec["status"] == "active"


# ---------------------------------------------------------------------------
# 3. Seed Role docs — the standard ladder as data
# ---------------------------------------------------------------------------

_ROLES_DIR = (
    pathlib.Path(__file__).resolve().parents[3]
    / "examples/dna-cloud/.dna/tenants/acme/scopes/acme-development/roles"
)


def test_seed_roles_are_the_standard_ladder():
    """The four shipped seed Role docs validate against the Role schema and form
    a strictly-ordered ladder (owner > admin > member > guest)."""
    import jsonschema

    k = Kernel()
    k.load(PortfolioExtension())
    schema = k.kind_port_for("Role").schema()

    ladder = {}
    for role_id in ("owner", "admin", "member", "guest"):
        raw = yaml.safe_load((_ROLES_DIR / f"{role_id}.yaml").read_text())
        assert raw["kind"] == "Role"
        spec = raw["spec"]
        jsonschema.validate(spec, schema)  # schema-valid seed data
        assert spec["role_id"] == role_id
        ladder[role_id] = spec["rank"]

    ranks = [ladder[r] for r in ("owner", "admin", "member", "guest")]
    assert ranks == sorted(ranks, reverse=True), "ladder must be strictly ordered"
    assert len(set(ranks)) == 4, "each rung has a distinct rank (highest-role-wins)"
