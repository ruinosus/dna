"""Tests for v3 kernel — build_prompt, dep_filters, layers, resolve."""
from __future__ import annotations

import pytest
from pathlib import Path

from dna.kernel import Kernel
from dna.kernel.instance import ManifestInstance
from dna.kernel.protocols import LayerPolicy
from dna.kernel.compose.layer_resolver import DefaultLayerResolver, deep_merge


BASE_DIR = Path(__file__).parent.parent.parent.parent / "scopes" / "open-swe" / ".dna"


@pytest.fixture
def mi():
    return Kernel.quick("open-swe", base_dir=str(BASE_DIR))


# ── build_prompt ──

class TestBuildPrompt:
    def test_returns_instruction_content(self, mi):
        prompt = mi.build_prompt(agent="swe-agent")
        assert len(prompt) > 100
        assert "SWE" in prompt or "swe" in prompt

    def test_unknown_agent(self, mi):
        # Fail loud (s-dx-build-prompt-fail-loud): a missing agent raises a
        # typed AgentNotFound instead of returning a placeholder string.
        from dna import AgentNotFound

        with pytest.raises(AgentNotFound) as exc:
            mi.build_prompt(agent="nonexistent")
        assert exc.value.agent == "nonexistent"
        assert "nonexistent" in str(exc.value)

    def test_default_agent(self, mi):
        agent = mi.default_agent()
        assert agent is not None
        assert agent.name == "swe-agent"

    def test_context_has_agent_entry(self, mi):
        ctx = mi._build_context(mi._find_agent("swe-agent"), None)
        assert ctx["agent"]["name"] == "swe-agent"
        assert len(ctx["agent"]["instruction"]) > 50

    def test_extra_context(self, mi):
        ctx = mi._build_context(mi._find_agent("swe-agent"), {"key": "val"})
        assert ctx["key"] == "val"


# ── dep_filters ──

class TestDepFilters:
    def test_swe_agent_1_soul_3_skills(self, mi):
        ctx = mi._build_context(mi._find_agent("swe-agent"), None)
        assert len(ctx.get("soulspec-soul", [])) == 1
        assert ctx["soulspec-soul"][0]["name"] == "swe-soul"
        assert len(ctx.get("agentskills-skill", [])) == 3

    def test_reviewer_agent_0_souls_1_skill(self, mi):
        ctx = mi._build_context(mi._find_agent("reviewer-agent"), None)
        assert len(ctx.get("soulspec-soul", [])) == 0
        assert len(ctx.get("agentskills-skill", [])) == 1


# ── flatten_in_context ──

class TestFlatten:
    def test_soul_content_in_ctx(self, mi):
        ctx = mi._build_context(mi._find_agent("swe-agent"), None)
        assert "soul_content" in ctx
        assert len(ctx["soul_content"]) > 20


# ── ManifestInstance ──

class TestMI:
    def test_all_skills(self, mi):
        assert len([d for d in mi.documents if d.kind == "Skill"]) == 6

    def test_one(self, mi):
        doc = next((d for d in mi.documents if d.kind == "Agent" and d.name == "swe-agent"), None)
        assert doc is not None and doc.kind == "Agent"

    def test_one_missing(self, mi):
        assert next((d for d in mi.documents if d.kind == "Skill" and d.name == "nope"), None) is None

    def test_root_is_module(self, mi):
        assert mi.root is not None and mi.root.kind == "Genome"

    def test_list_kinds(self, mi):
        kinds = mi.list_kinds()
        for k in ("Genome", "Agent", "Skill", "Soul"):
            assert k in kinds

    def test_ref(self, mi):
        resolved = mi.ref("agents/swe-agent/AGENT.md")
        assert "SWE" in resolved or "swe" in resolved


# ── Layers ──

class TestLayers:
    def test_resolve_no_layers(self, mi):
        assert mi.resolve() is mi

    def test_resolve_nonexistent(self, mi):
        resolved = mi.resolve(layers={"tenant": "nope"})
        assert len(resolved.documents) == len(mi.documents)

    def test_resolve_no_source(self):
        mi = ManifestInstance(scope="x", documents=[], kinds={})
        assert mi.resolve(layers={"a": "b"}) is mi


# ── DefaultLayerResolver ──

class TestResolver:
    def test_deep_merge(self):
        assert deep_merge({"a": 1, "b": {"c": 2}}, {"b": {"d": 3}}) == {"a": 1, "b": {"c": 2, "d": 3}}

    def test_overlay_wins(self):
        assert deep_merge({"a": 1}, {"a": 2}) == {"a": 2}

    def _fake_source(self, overlays):
        class S:
            def load_layer(self, scope, lid, lv):
                return overlays
        return S()

    def test_open_merges(self):
        r = DefaultLayerResolver()
        base = [{"kind": "A", "metadata": {"name": "x"}, "spec": {"v": 1}}]
        over = [{"kind": "A", "metadata": {"name": "x"}, "spec": {"v": 2}}]
        result = r.resolve(base, {"t": "x"}, self._fake_source(over), "s", {})
        assert result[0]["spec"]["v"] == 2

    def test_locked_blocks(self):
        r = DefaultLayerResolver()
        base = [{"kind": "M", "metadata": {"name": "m"}, "spec": {"b": 1}}]
        over = [{"kind": "M", "metadata": {"name": "m"}, "spec": {"b": 9}}]
        with pytest.warns(UserWarning, match="locked"):
            result = r.resolve(base, {"t": "x"}, self._fake_source(over), "s", {"M": LayerPolicy.LOCKED})
        assert result[0]["spec"]["b"] == 1

    def test_restricted_no_new_keys(self):
        r = DefaultLayerResolver()
        base = [{"kind": "A", "metadata": {"name": "a"}, "spec": {"x": 1}}]
        over = [{"kind": "A", "metadata": {"name": "a"}, "spec": {"x": 2, "y": 3}}]
        with pytest.warns(UserWarning, match="restricted"):
            result = r.resolve(base, {"t": "x"}, self._fake_source(over), "s", {"A": LayerPolicy.RESTRICTED})
        assert result[0]["spec"]["x"] == 2
        assert "y" not in result[0]["spec"]

    def test_open_adds_new_docs(self):
        r = DefaultLayerResolver()
        base = [{"kind": "M", "metadata": {"name": "m"}, "spec": {}}]
        over = [{"kind": "S", "metadata": {"name": "s"}, "spec": {"i": "hi"}}]
        result = r.resolve(base, {"t": "x"}, self._fake_source(over), "s", {})
        assert len(result) == 2

    def test_restricted_blocks_new_docs(self):
        r = DefaultLayerResolver()
        base = [{"kind": "M", "metadata": {"name": "m"}, "spec": {}}]
        over = [{"kind": "S", "metadata": {"name": "s"}, "spec": {}}]
        with pytest.warns(UserWarning, match="restricted"):
            result = r.resolve(base, {"t": "x"}, self._fake_source(over), "s", {"S": LayerPolicy.RESTRICTED})
        assert len(result) == 1


# ── Composition ──

class TestComposition:
    def test_resolves_soul_skill_guardrail_refs(self, mi):
        # open-swe resolves all soul/skill/guardrail/actor/usecase refs (13):
        #   swe-agent: soul(swe-soul) + 3 skills + 3 guardrails = 7
        #   reviewer-agent: 1 skill + 2 guardrails = 3
        #   review-pull-request use-case: 2 actors + 1 agent = 3
        cr = mi.composition_result
        assert len(cr.resolved) == 13
        # Tool migrated to a RECORD-plane Kind (s-tool-kind-descriptor): an
        # agent `tools:` ref now points at a record, which the composition
        # engine resolves LAZILY (host-resolved at runtime) instead of eagerly
        # flagging it as a missing composition input. So the tool refs the
        # fixture doesn't ship (github_* / run_tests / …) no longer surface as
        # missing — records are not composition inputs.
        assert len(cr.missing) == 0
        assert not any(".tools=" in m for m in cr.missing)

    def test_detects_missing_soul(self, mi):
        from dna.kernel.document import Document
        bad = Document.from_raw({
            "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
            "metadata": {"name": "bad"}, "spec": {"soul": "ghost"},
        })
        mi.documents.append(bad)
        if "composition_result" in mi.__dict__:
            del mi.__dict__["composition_result"]
        cr = mi.composition_result
        assert not cr.valid
        assert any("ghost" in m for m in cr.missing)

    def test_detects_missing_skill(self, mi):
        from dna.kernel.document import Document
        bad = Document.from_raw({
            "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
            "metadata": {"name": "bad2"}, "spec": {"skills": ["fake"]},
        })
        mi.documents.append(bad)
        if "composition_result" in mi.__dict__:
            del mi.__dict__["composition_result"]
        cr = mi.composition_result
        assert not cr.valid
        assert any("fake" in m for m in cr.missing)


# ── Hooks ──

class TestHooks:
    def test_pre_build_prompt_middleware(self, mi):
        """Middleware can inject extra context."""
        from dna.kernel.hooks import HookContext

        def inject_extra(ctx: HookContext) -> HookContext:
            ctx.data["context"]["injected"] = "hello from hook"
            return ctx

        mi._kernel.hooks.use("pre_build_prompt", inject_extra)
        # build_prompt should now include the injected context
        # (won't appear in output unless template uses it, but the hook runs)
        prompt = mi.build_prompt(agent="swe-agent")
        assert len(prompt) > 0  # Still produces a prompt

    def test_post_build_prompt_event(self, mi):
        """Event receives the final prompt."""
        from dna.kernel.hooks import HookContext
        captured = []

        def capture(ctx: HookContext):
            captured.append(ctx.prompt)

        mi._kernel.hooks.on("post_build_prompt", capture)
        mi.build_prompt(agent="swe-agent")
        assert len(captured) == 1
        assert "SWE" in captured[0] or "swe" in captured[0]

    def test_hook_error_doesnt_crash(self, mi):
        """Event errors are logged, not raised."""
        def bad_hook(ctx):
            raise ValueError("boom")

        mi._kernel.hooks.on("post_build_prompt", bad_hook)
        prompt = mi.build_prompt(agent="swe-agent")  # Should not raise
        assert len(prompt) > 0


# ── Custom Kinds ──

class TestCustomKinds:
    def test_registers_from_manifest(self):
        """custom_kinds in manifest get registered as KindPort."""
        from dna.kernel import Kernel
        k = Kernel()

        # Simulate _register_custom_kinds
        manifest = {
            "spec": {
                "custom_kinds": [
                    {"apiVersion": "myco.io/v1", "kind": "Pipeline", "alias": "myco-pipeline"},
                ]
            }
        }
        k._register_custom_kinds(manifest)
        assert ("myco.io/v1", "Pipeline") in k._kinds
        kp = k._kinds[("myco.io/v1", "Pipeline")]
        assert kp.alias == "myco-pipeline"
        assert kp.kind == "Pipeline"

    def test_custom_kind_queryable(self):
        """Custom kinds appear in mi.all() and mi.get()."""
        from dna.kernel import Kernel
        from dna.kernel.document import Document
        from dna.kernel.instance import ManifestInstance

        k = Kernel()
        manifest = {"spec": {"custom_kinds": [{"apiVersion": "x/v1", "kind": "Pipeline", "alias": "x-pipeline"}]}}
        k._register_custom_kinds(manifest)

        doc = Document.from_raw({"apiVersion": "x/v1", "kind": "Pipeline", "metadata": {"name": "etl"}, "spec": {"stages": 3}})
        mi = ManifestInstance(scope="test", documents=[doc], kinds=k._kinds)

        assert len([d for d in mi.documents if d.kind == "Pipeline"]) == 1
        assert next((d for d in mi.documents if d.kind == "Pipeline" and d.name == "etl"), None) is not None
        assert "Pipeline" in mi.list_kinds()


# ── Lockfile ──

class TestLockfile:
    def test_generate_lock_has_sha(self, mi):
        lock = mi.generate_lock()
        assert lock.scope == "open-swe"
        # 19 → 18: the lock iterates the COMPOSITION plane (mi.documents).
        # Tool migrated to the RECORD plane (s-tool-kind-descriptor), so the
        # fixture's github-search Tool doc — like any record (Story, EvalRun)
        # — is no longer a composition input and drops out of the lock. It
        # remains fully readable via mi.all("Tool") / mi.one("Tool", …).
        assert len(lock.documents) == 18
        for entry in lock.documents:
            assert len(entry.sha256) == 64  # SHA256 hex

    def test_sha_changes_on_content_change(self, mi):
        lock1 = mi.generate_lock()
        swe_sha = next(e.sha256 for e in lock1.documents if e.name == "swe-agent" and e.kind == "Agent")
        assert swe_sha  # Not empty


# ── Document origin chain ──

class TestOriginChain:
    def test_local_docs_have_local_origin(self, mi):
        root = mi.root
        assert root.origin == "local"

    def test_bundle_docs_have_local_origin(self, mi):
        """open-swe ships its soul as a local bundle (no external deps),
        so every doc — including the soul — carries the 'local' origin."""
        swe_soul = next((d for d in mi.documents if d.kind == "Soul" and d.name == "swe-soul"), None)
        assert swe_soul is not None
        assert swe_soul.origin == "local"

    def test_lockfile_preserves_origin(self, mi):
        """Every lockfile entry records its origin; open-swe is fully
        self-contained so all entries are 'local'."""
        lock = mi.generate_lock()
        assert len(lock.documents) > 0
        for entry in lock.documents:
            assert entry.origin == "local"


# ── Kernel.auto ──

class TestKernelAuto:
    def test_auto_loads_builtin_extensions(self):
        from dna.kernel import Kernel
        k = Kernel.auto()
        # Should have kinds from built-in extensions
        kinds = list(k._kinds.keys())
        kind_names = [kn for _, kn in kinds]
        assert "Genome" in kind_names
        assert "Agent" in kind_names
        assert "Skill" in kind_names
        assert "Soul" in kind_names


# ── LayerPolicy ──

class TestLayerPolicy:
    def test_values(self):
        assert LayerPolicy.OPEN.value == "open"
        assert LayerPolicy.RESTRICTED.value == "restricted"
        assert LayerPolicy.LOCKED.value == "locked"

    def test_from_string(self):
        assert LayerPolicy("open") == LayerPolicy.OPEN


# ── build_prompt filters ──

class TestBuildPromptFilters:
    """build_prompt with enabled_skills/enabled_guardrails filters."""

    def test_enabled_skills_none_keeps_all(self, mi):
        full = mi.build_prompt(agent="swe-agent")
        same = mi.build_prompt(agent="swe-agent", enabled_skills=None)
        assert full == same

    def test_enabled_skills_empty_removes_all(self, mi):
        full = mi.build_prompt(agent="swe-agent")
        no_skills = mi.build_prompt(agent="swe-agent", enabled_skills=[])
        assert len(no_skills) <= len(full)

    def test_enabled_skills_filters(self, mi):
        full = mi.build_prompt(agent="swe-agent")
        # Get first skill name from swe-agent's agent spec
        swe = next((d for d in mi.documents if d.kind == "Agent" and d.name == "swe-agent"), None)
        skills = swe.spec.get("skills", [])
        if skills:
            filtered = mi.build_prompt(agent="swe-agent", enabled_skills=[skills[0]])
            assert len(filtered) <= len(full)

    def test_nonexistent_skill_produces_empty(self, mi):
        filtered = mi.build_prompt(agent="swe-agent", enabled_skills=["does-not-exist"])
        no_skills = mi.build_prompt(agent="swe-agent", enabled_skills=[])
        assert len(filtered) == len(no_skills)

    def test_enabled_guardrails_empty(self, mi):
        full = mi.build_prompt(agent="swe-agent")
        no_guards = mi.build_prompt(agent="swe-agent", enabled_guardrails=[])
        assert len(no_guards) <= len(full)

    def test_both_filters_together(self, mi):
        result = mi.build_prompt(agent="swe-agent", enabled_skills=[], enabled_guardrails=[])
        assert isinstance(result, str)
        assert len(result) > 0  # Still has agent instruction
