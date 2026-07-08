"""Integration tests for Layers — real SQLite, no mocks.

Proves: overlay merge, tenant isolation, edit propagation, policy enforcement.
Each class is an independent business scenario with its own fresh database.
"""
from __future__ import annotations

import warnings

import pytest
import pytest_asyncio

from dna.adapters.sqlite import SqliteSource
from dna.kernel import Kernel
from dna.kernel.protocols import LayerPolicy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODULE_RAW = {
    "apiVersion": "github.com/ruinosus/dna/v1",
    "kind": "Genome",
    "metadata": {"name": "test-mod", "description": "Test module"},
    "spec": {
        "default_agent": "brad",
        "layers": {"tenant": "open"},
    },
}

AGENT_BRAD_RAW = {
    "apiVersion": "github.com/ruinosus/dna/v1",
    "kind": "Agent",
    "metadata": {"name": "brad", "description": "Base architect"},
    "spec": {
        "instruction": "You are Brad, the base architect.",
        "soul": "brad",
    },
}

SOUL_BRAD_RAW = {
    "apiVersion": "github.com/ruinosus/dna/v1",
    "kind": "Soul",
    "metadata": {"name": "brad"},
    "spec": {
        "soul": "Calm and professional.",
    },
}


async def _seed_base(source: SqliteSource) -> None:
    """Seed the base documents (module + agent + soul) and publish them."""
    for kind, name, raw in [
        ("Genome", "test-mod", MODULE_RAW),
        ("Agent", "brad", AGENT_BRAD_RAW),
        ("Soul", "brad", SOUL_BRAD_RAW),
    ]:
        await source.save_document("test-mod", kind, name, raw)
        await source.publish("test-mod", kind, name)


def _make_kernel(source: SqliteSource) -> Kernel:
    """Build a Kernel wired to a SQLite source with all extensions loaded."""
    k = Kernel.auto()
    k.source(source)

    # SQLite doesn't need readers/resolvers, but Kernel.instance() requires a cache.
    # Provide a no-op cache since we have no dependencies.
    class _NoOpCache:
        async def has(self, scope, key):
            return True

        async def load_all(self, scope, readers=None):
            return []

        async def store(self, scope, key, items):
            pass

    k.cache(_NoOpCache())
    return k


def _overlay_agent(instruction: str, **extra_spec) -> dict:
    """Create an overlay document for brad with a custom instruction."""
    spec = {"instruction": instruction, **extra_spec}
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "brad"},
        "spec": spec,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sqlite_env(tmp_path):
    """Fresh SQLite + Kernel with base documents seeded."""
    db = tmp_path / "test.db"
    source = SqliteSource(str(db))
    await source.connect()
    await _seed_base(source)
    kernel = _make_kernel(source)
    yield kernel, source
    await source.close()


# ---------------------------------------------------------------------------
# Scenario 1: Overlay Merge
# ---------------------------------------------------------------------------


class TestOverlayMerge:
    """Resolving with a tenant layer merges the overlay into the base agent."""

    @pytest.mark.asyncio
    async def test_overlay_changes_instruction(self, sqlite_env):
        kernel, source = sqlite_env

        await source.save_layer_document(
            "test-mod", "tenant", "alpha",
            "Agent", "brad",
            _overlay_agent("Focus on compliance and regulatory requirements."),
        )

        mi = await kernel.instance_async("test-mod", layers={"tenant": "alpha"})
        brad = mi.one("Agent", "brad")

        assert brad is not None
        assert "compliance" in brad.spec.get("instruction", "").lower()

    @pytest.mark.asyncio
    async def test_overlay_reflected_in_build_prompt(self, sqlite_env):
        kernel, source = sqlite_env

        await source.save_layer_document(
            "test-mod", "tenant", "alpha",
            "Agent", "brad",
            _overlay_agent("Focus on compliance and regulatory requirements."),
        )

        mi = await kernel.instance_async("test-mod", layers={"tenant": "alpha"})
        prompt = await mi.build_prompt_async(agent="brad")

        assert "compliance" in prompt.lower()


# ---------------------------------------------------------------------------
# Scenario 2: Tenant Isolation
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    """Each tenant sees only its overlay; base and other tenants are unaffected."""

    @pytest.mark.asyncio
    async def test_three_tenants_three_instructions(self, sqlite_env):
        kernel, source = sqlite_env

        await source.save_layer_document(
            "test-mod", "tenant", "alpha",
            "Agent", "brad",
            _overlay_agent("Focus on compliance."),
        )
        await source.save_layer_document(
            "test-mod", "tenant", "beta",
            "Agent", "brad",
            _overlay_agent("Ship fast, iterate later."),
        )

        mi_base = await kernel.instance_async("test-mod")
        mi_alpha = await kernel.instance_async("test-mod", layers={"tenant": "alpha"})
        mi_beta = await kernel.instance_async("test-mod", layers={"tenant": "beta"})

        base_instr = mi_base.one("Agent", "brad").spec.get("instruction", "")
        alpha_instr = mi_alpha.one("Agent", "brad").spec.get("instruction", "")
        beta_instr = mi_beta.one("Agent", "brad").spec.get("instruction", "")

        assert "base architect" in base_instr.lower()
        assert "compliance" in alpha_instr.lower()
        assert "ship fast" in beta_instr.lower()

    @pytest.mark.asyncio
    async def test_base_prompt_unchanged(self, sqlite_env):
        kernel, source = sqlite_env

        await source.save_layer_document(
            "test-mod", "tenant", "alpha",
            "Agent", "brad",
            _overlay_agent("Focus on compliance."),
        )

        mi_base_for_prompt = await kernel.instance_async("test-mod")
        prompt_base = await mi_base_for_prompt.build_prompt_async(agent="brad")
        mi_alpha_for_prompt = await kernel.instance_async(
            "test-mod", layers={"tenant": "alpha"},
        )
        prompt_alpha = await mi_alpha_for_prompt.build_prompt_async(agent="brad")

        assert "compliance" not in prompt_base.lower()
        assert "compliance" in prompt_alpha.lower()


# ---------------------------------------------------------------------------
# Scenario 3: Edit Propagation
# ---------------------------------------------------------------------------


class TestEditPropagation:
    """Editing a layer overlay in SQLite is reflected on next instance() call."""

    @pytest.mark.asyncio
    async def test_edit_propagates_without_restart(self, sqlite_env):
        kernel, source = sqlite_env

        # Initial overlay
        await source.save_layer_document(
            "test-mod", "tenant", "alpha",
            "Agent", "brad",
            _overlay_agent("Focus on compliance."),
        )
        mi1 = await kernel.instance_async("test-mod", layers={"tenant": "alpha"})
        assert "compliance" in mi1.one("Agent", "brad").spec.get("instruction", "").lower()

        # Edit overlay in-place
        await source.save_layer_document(
            "test-mod", "tenant", "alpha",
            "Agent", "brad",
            _overlay_agent("Pirata do código. Arrr!"),
        )
        mi2 = await kernel.instance_async("test-mod", layers={"tenant": "alpha"})
        assert "pirata" in mi2.one("Agent", "brad").spec.get("instruction", "").lower()

    @pytest.mark.asyncio
    async def test_edit_does_not_affect_base(self, sqlite_env):
        kernel, source = sqlite_env

        await source.save_layer_document(
            "test-mod", "tenant", "alpha",
            "Agent", "brad",
            _overlay_agent("Pirata do código. Arrr!"),
        )

        mi_base = await kernel.instance_async("test-mod")
        assert "base architect" in mi_base.one("Agent", "brad").spec.get("instruction", "").lower()

    @pytest.mark.asyncio
    async def test_edit_does_not_affect_other_tenant(self, sqlite_env):
        kernel, source = sqlite_env

        await source.save_layer_document(
            "test-mod", "tenant", "alpha",
            "Agent", "brad",
            _overlay_agent("Pirata do código."),
        )
        await source.save_layer_document(
            "test-mod", "tenant", "beta",
            "Agent", "brad",
            _overlay_agent("Ship fast."),
        )

        # Edit alpha
        await source.save_layer_document(
            "test-mod", "tenant", "alpha",
            "Agent", "brad",
            _overlay_agent("Totally changed."),
        )

        mi_beta = await kernel.instance_async("test-mod", layers={"tenant": "beta"})
        assert "ship fast" in mi_beta.one("Agent", "brad").spec.get("instruction", "").lower()


# ---------------------------------------------------------------------------
# Scenario 4: Policy RESTRICTED
# ---------------------------------------------------------------------------


class TestPolicyRestricted:
    """RESTRICTED policy: can overwrite existing fields, cannot add new ones."""

    @pytest_asyncio.fixture
    async def restricted_env(self, tmp_path):
        db = tmp_path / "restricted.db"
        source = SqliteSource(str(db))
        await source.connect()

        module = {
            **MODULE_RAW,
            "spec": {
                **MODULE_RAW["spec"],
                "layers": [
                    {"id": "tenant", "source": "env:TENANT", "policy": {"Agent": "restricted"}},
                ],
            },
        }
        for kind, name, raw in [
            ("Genome", "test-mod", module),
            ("Agent", "brad", AGENT_BRAD_RAW),
            ("Soul", "brad", SOUL_BRAD_RAW),
        ]:
            await source.save_document("test-mod", kind, name, raw)
            await source.publish("test-mod", kind, name)

        kernel = _make_kernel(source)
        yield kernel, source
        await source.close()

    @pytest.mark.asyncio
    async def test_existing_field_overwritten(self, restricted_env):
        kernel, source = restricted_env

        await source.save_layer_document(
            "test-mod", "tenant", "alpha",
            "Agent", "brad",
            _overlay_agent("Overridden instruction."),
        )

        mi = await kernel.instance_async("test-mod", layers={"tenant": "alpha"})
        instr = mi.one("Agent", "brad").spec.get("instruction", "")
        assert "overridden" in instr.lower()

    @pytest.mark.asyncio
    async def test_new_field_ignored(self, restricted_env):
        kernel, source = restricted_env

        await source.save_layer_document(
            "test-mod", "tenant", "alpha",
            "Agent", "brad",
            _overlay_agent("Overridden instruction.", tone="formal"),
        )

        mi = await kernel.instance_async("test-mod", layers={"tenant": "alpha"})
        brad_spec = mi.one("Agent", "brad").spec
        assert brad_spec.get("tone") is None


# ---------------------------------------------------------------------------
# Scenario 5: Policy LOCKED
# ---------------------------------------------------------------------------


class TestPolicyLocked:
    """LOCKED policy: overlay changes are completely ignored."""

    @pytest_asyncio.fixture
    async def locked_env(self, tmp_path):
        db = tmp_path / "locked.db"
        source = SqliteSource(str(db))
        await source.connect()

        # Phase 16 — overlay rules live in LayerPolicy docs, not
        # Module.spec.layers. Policy keys by alias.
        module = {**MODULE_RAW, "spec": {**MODULE_RAW["spec"]}}
        layer_policy = {
            "apiVersion": "github.com/ruinosus/dna/policy/v1",
            "kind": "LayerPolicy",
            "metadata": {"name": "tenant-default"},
            "spec": {
                "layer_id": "tenant",
                "policies": {"helix-agent": "locked"},
            },
        }
        for kind, name, raw in [
            ("Genome", "test-mod", module),
            ("LayerPolicy", "tenant-default", layer_policy),
            ("Agent", "brad", AGENT_BRAD_RAW),
            ("Soul", "brad", SOUL_BRAD_RAW),
        ]:
            await source.save_document("test-mod", kind, name, raw)
            await source.publish("test-mod", kind, name)

        kernel = _make_kernel(source)
        yield kernel, source
        await source.close()

    @pytest.mark.asyncio
    async def test_instruction_unchanged(self, locked_env):
        kernel, source = locked_env

        await source.save_layer_document(
            "test-mod", "tenant", "alpha",
            "Agent", "brad",
            _overlay_agent("This should be ignored."),
        )

        mi = await kernel.instance_async("test-mod", layers={"tenant": "alpha"})
        instr = mi.one("Agent", "brad").spec.get("instruction", "")
        assert "base architect" in instr.lower()

    @pytest.mark.asyncio
    async def test_locked_emits_warning(self, locked_env):
        kernel, source = locked_env

        await source.save_layer_document(
            "test-mod", "tenant", "alpha",
            "Agent", "brad",
            _overlay_agent("This should be ignored."),
        )

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await kernel.instance_async("test-mod", layers={"tenant": "alpha"})
            locked_warnings = [x for x in w if "locked" in str(x.message).lower()]
            assert len(locked_warnings) > 0
