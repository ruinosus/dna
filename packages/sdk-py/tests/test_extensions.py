"""Tests for v3 Extensions — registration, readers, writers, kind properties.

GAP-19: Extension tests — validates that each extension correctly registers
its kinds, readers, and writers on the Kernel. Ensures KindPort properties
(is_root, is_prompt_target, flatten_in_context, dep_filters) are correct.
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel
from dna.kernel.bundle_handle import FilesystemBundleHandle
from dna.kernel.document import Document


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def kernel():
    """Kernel with all 4 built-in extensions loaded."""
    k = Kernel()
    from dna.extensions.helix import HelixExtension
    from dna.extensions.agentskills import AgentSkillsExtension
    from dna.extensions.soulspec import SoulSpecExtension
    from dna.extensions.agentsmd import AgentsMdExtension

    k.load(HelixExtension())
    k.load(AgentSkillsExtension())
    k.load(SoulSpecExtension())
    k.load(AgentsMdExtension())
    return k


# ── HelixExtension ──

class TestHelixExtension:
    def test_registers_three_kinds(self, kernel):
        """HelixExtension registers Genome, Agent, Actor (and others)."""
        kinds = {kn for (_, kn) in kernel._kinds}
        # Phase 16 — Module Kind no longer registered (replaced by Genome).
        assert "Genome" in kinds
        assert "Agent" in kinds
        assert "Actor" in kinds

    def test_package_is_root(self, kernel):
        # Phase 16 commit 4 — Genome is the root Kind. Module Kind
        # is no longer registered. Detailed Genome coverage lives in
        # tests/test_package_layerpolicy_kinds.py.
        pkg = kernel._kinds[("github.com/ruinosus/dna/v1", "Genome")]
        assert pkg.is_root is True
        assert pkg.is_prompt_target is False
        assert pkg.alias == "helix-genome"

    def test_module_kind_no_longer_registered(self, kernel):
        # Phase 16 cleanup — ModuleKind class deleted entirely.
        # Externally authored manifests with ``kind: Module`` no longer
        # parse — they need to migrate to ``kind: Genome``.
        assert ("github.com/ruinosus/dna/v1", "Module") not in kernel._kinds
        # Genome is the canonical root.
        pkg = kernel._kinds[("github.com/ruinosus/dna/v1", "Genome")]
        assert pkg.is_root is True

    def test_agent_is_prompt_target(self, kernel):
        kp = kernel._kinds[("github.com/ruinosus/dna/v1", "Agent")]
        assert kp.is_root is False
        assert kp.is_prompt_target is True
        assert kp.flatten_in_context is False
        assert kp.alias == "helix-agent"

    def test_agent_dep_filters(self, kernel):
        kp = kernel._kinds[("github.com/ruinosus/dna/v1", "Agent")]
        filters = kp.dep_filters()
        assert filters == {
            "soul": "soulspec-soul",
            "skills": "agentskills-skill",
            "guardrails": "guardrails-guardrail",
            "actors": "helix-actor",
            "tools": "helix-tool",
        }

    def test_actor_passive(self, kernel):
        kp = kernel._kinds[("github.com/ruinosus/dna/v1", "Actor")]
        assert kp.is_root is False
        assert kp.is_prompt_target is False
        assert kp.dep_filters() is None
        assert kp.alias == "helix-actor"

    def test_agent_prompt_template(self, kernel):
        kp = kernel._kinds[("github.com/ruinosus/dna/v1", "Agent")]
        # Triple braces disable HTML escaping; soul_content is markdown.
        # Template now also includes a guardrails section.
        template = kp.prompt_template()
        assert "{{{agent.instruction}}}" in template
        assert "{{{soul_content}}}" in template
        assert "{{#guardrails-guardrail}}" in template

    def test_agent_describe(self, kernel):
        kp = kernel._kinds[("github.com/ruinosus/dna/v1", "Agent")]
        doc = Document.from_raw({
            "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
            "metadata": {"name": "ag", "description": "An agent"},
            "spec": {"soul": "s1", "skills": ["a", "b"], "model": "gpt-4"},
        })
        desc = kp.describe(doc)
        assert "ag" in desc
        assert "Skills:" in desc
        assert "Soul:" in desc

    def test_agent_summary(self, kernel):
        kp = kernel._kinds[("github.com/ruinosus/dna/v1", "Agent")]
        doc = Document.from_raw({
            "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
            "metadata": {"name": "ag"}, "spec": {"skills": ["a", "b", "c"], "soul": "brad"},
        })
        s = kp.summary(doc)
        assert s["skills"] == 3
        assert s["soul"] == "brad"

    def test_registers_agent_reader_and_writer(self, kernel):
        """HelixExtension registers AgentReader and AgentWriter."""
        k = Kernel()
        from dna.extensions.helix import HelixExtension
        k.load(HelixExtension())
        assert len(k._readers) == 1  # AgentReader
        assert len(k._writers) == 1  # AgentWriter


# ── AgentSkillsExtension ──

class TestAgentSkillsExtension:
    def test_registers_kind_reader_writer(self):
        k = Kernel()
        from dna.extensions.agentskills import AgentSkillsExtension
        k.load(AgentSkillsExtension())
        assert ("agentskills.io/v1", "Skill") in k._kinds
        assert len(k._readers) == 1
        assert len(k._writers) == 1

    def test_skill_kind_properties(self, kernel):
        kp = kernel._kinds[("agentskills.io/v1", "Skill")]
        assert kp.is_root is False
        assert kp.is_prompt_target is False
        assert kp.flatten_in_context is False
        assert kp.dep_filters() is None
        assert kp.alias == "agentskills-skill"

    def test_skill_reader_detect(self, tmp_path):
        from dna.extensions.agentskills import SkillReader
        r = SkillReader()
        # No SKILL.md → False
        assert r.detect(FilesystemBundleHandle(tmp_path)) is False
        # Create SKILL.md → True
        (tmp_path / "SKILL.md").write_text("---\nname: test\n---\nHello")
        assert r.detect(FilesystemBundleHandle(tmp_path)) is True

    def test_skill_reader_reads_frontmatter(self, tmp_path):
        from dna.extensions.agentskills import SkillReader
        r = SkillReader()
        (tmp_path / "SKILL.md").write_text("---\nname: my-skill\ndescription: A skill\n---\nDo stuff")
        result = r.read(FilesystemBundleHandle(tmp_path))
        assert result["kind"] == "Skill"
        assert result["metadata"]["name"] == "my-skill"
        assert result["metadata"]["description"] == "A skill"
        assert result["spec"]["instruction"] == "Do stuff"

    def test_skill_reader_reads_scripts(self, tmp_path):
        from dna.extensions.agentskills import SkillReader
        r = SkillReader()
        (tmp_path / "SKILL.md").write_text("---\nname: s\n---\nBody")
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "validate.py").write_text("print('ok')")
        result = r.read(FilesystemBundleHandle(tmp_path))
        assert "validate.py" in result["spec"]["scripts"]

    def test_skill_reader_reads_extras(self, tmp_path):
        from dna.extensions.agentskills import SkillReader
        r = SkillReader()
        (tmp_path / "SKILL.md").write_text("---\nname: s\n---\nBody")
        custom = tmp_path / "agents"
        custom.mkdir()
        (custom / "bot.yaml").write_text("kind: Agent")
        result = r.read(FilesystemBundleHandle(tmp_path))
        assert "agents" in result["spec"]["extras"]
        assert "bot.yaml" in result["spec"]["extras"]["agents"]

    def test_skill_reader_skips_binary(self, tmp_path):
        from dna.extensions.agentskills import SkillReader
        r = SkillReader()
        (tmp_path / "SKILL.md").write_text("---\nname: s\n---\nBody")
        # Binary extension at root level
        (tmp_path / "data.png").write_bytes(b"\x89PNG")
        result = r.read(FilesystemBundleHandle(tmp_path))
        assert "data.png" not in result["spec"].get("root_files", {})

    def test_skill_writer_roundtrip(self, tmp_path):
        from dna.extensions.agentskills import SkillReader, SkillWriter
        r = SkillReader()
        w = SkillWriter()

        # Write
        raw = {
            "kind": "Skill",
            "metadata": {"name": "demo", "description": "A demo skill"},
            "spec": {
                "instruction": "Do the thing",
                "scripts": {"run.sh": "#!/bin/bash\necho hi"},
                "references": {"guide.md": "# Guide\nFollow this"},
            },
        }
        assert w.can_write(raw) is True
        out = tmp_path / "demo"
        w.write(FilesystemBundleHandle(out), raw)

        # Read back
        result = r.read(FilesystemBundleHandle(out))
        assert result["metadata"]["name"] == "demo"
        assert result["spec"]["instruction"] == "Do the thing"
        assert "run.sh" in result["spec"]["scripts"]
        assert "guide.md" in result["spec"]["references"]

    def test_skill_reader_preserves_extra_metadata_fields(self, tmp_path):
        """A human-edited SKILL.md with extras (tags, numbers, custom keys)
        survives read → write → read without loss or string-coercion."""
        from dna.extensions.agentskills import SkillReader, SkillWriter

        bundle = tmp_path / "my-skill"
        bundle.mkdir()
        (bundle / "SKILL.md").write_text(
            "---\n"
            "name: my-skill\n"
            "description: demo\n"
            "tags:\n  - one\n  - two\n"
            "priority: 7\n"
            "owner: alice\n"
            "---\n"
            "skill body"
        )

        reader = SkillReader()
        raw = reader.read(FilesystemBundleHandle(bundle))

        meta = raw["metadata"]
        assert meta["name"] == "my-skill"
        assert meta["description"] == "demo"
        assert meta["tags"] == ["one", "two"], f"tags dropped or coerced: {meta.get('tags')!r}"
        assert meta["priority"] == 7, f"int coerced: {meta.get('priority')!r}"
        assert meta["owner"] == "alice"

        # Round-trip: writer already preserves extras (since #39663a2); reader
        # must now do the same so the cycle is lossless.
        dest = tmp_path / "dest"
        SkillWriter().write(FilesystemBundleHandle(dest), raw)
        raw2 = reader.read(FilesystemBundleHandle(dest))
        assert raw2["metadata"]["tags"] == ["one", "two"]
        assert raw2["metadata"]["priority"] == 7
        assert raw2["metadata"]["owner"] == "alice"


# ── SoulSpecExtension ──

class TestSoulSpecExtension:
    def test_registers_kind_reader_writer(self):
        k = Kernel()
        from dna.extensions.soulspec import SoulSpecExtension
        k.load(SoulSpecExtension())
        assert ("soulspec.org/v1", "Soul") in k._kinds
        assert len(k._readers) == 1
        assert len(k._writers) == 1

    def test_soul_kind_properties(self, kernel):
        kp = kernel._kinds[("soulspec.org/v1", "Soul")]
        assert kp.is_root is False
        assert kp.is_prompt_target is True
        assert kp.flatten_in_context is True
        assert kp.alias == "soulspec-soul"

    def test_soul_reader_detect_soul_md(self, tmp_path):
        from dna.extensions.soulspec import SoulReader
        r = SoulReader()
        assert r.detect(FilesystemBundleHandle(tmp_path)) is False
        (tmp_path / "SOUL.md").write_text("# Soul")
        assert r.detect(FilesystemBundleHandle(tmp_path)) is True

    def test_soul_reader_detect_soul_json(self, tmp_path):
        from dna.extensions.soulspec import SoulReader
        r = SoulReader()
        (tmp_path / "soul.json").write_text('{"name": "test"}')
        assert r.detect(FilesystemBundleHandle(tmp_path)) is True

    def test_soul_reader_reads_bundle(self, tmp_path):
        from dna.extensions.soulspec import SoulReader
        r = SoulReader()
        (tmp_path / "SOUL.md").write_text("I am a soul")
        (tmp_path / "STYLE.md").write_text("My style")
        result = r.read(FilesystemBundleHandle(tmp_path))
        assert result["kind"] == "Soul"
        assert result["spec"]["soul_content"] == "I am a soul"
        assert result["spec"]["style_content"] == "My style"

    def test_soul_reader_json_fallback(self, tmp_path):
        from dna.extensions.soulspec import SoulReader
        r = SoulReader()
        (tmp_path / "soul.json").write_text('{"name": "test", "traits": ["kind"]}')
        result = r.read(FilesystemBundleHandle(tmp_path))
        assert result["spec"]["soul_json"]["name"] == "test"
        assert "soul_content" in result["spec"]  # Populated from JSON

    def test_soul_writer_roundtrip(self, tmp_path):
        from dna.extensions.soulspec import SoulReader, SoulWriter
        r = SoulReader()
        w = SoulWriter()

        raw = {
            "kind": "Soul",
            "metadata": {"name": "brad"},
            "spec": {
                "soul_content": "I am Brad",
                "style_content": "Brad style",
            },
        }
        assert w.can_write(raw) is True
        out = tmp_path / "brad"
        w.write(FilesystemBundleHandle(out), raw)

        result = r.read(FilesystemBundleHandle(out))
        assert result["spec"]["soul_content"] == "I am Brad"
        assert result["spec"]["style_content"] == "Brad style"

    def test_soul_prompt_template(self, kernel):
        kp = kernel._kinds[("soulspec.org/v1", "Soul")]
        assert kp.prompt_template() == "{{{soul_content}}}"

    def test_soul_reader_preserves_extra_metadata_fields(self, tmp_path):
        """A SOUL.md with extra metadata (tags, specVersion, custom keys) survives
        round-trip via SoulReader + SoulWriter."""
        from dna.extensions.soulspec import SoulReader, SoulWriter

        # Create a bundle with frontmatter + body + companion files
        bundle = tmp_path / "my-soul"
        bundle.mkdir()
        (bundle / "SOUL.md").write_text(
            "---\n"
            "name: my-soul\n"
            "specVersion: \"2.0\"\n"
            "tags:\n  - reflective\n  - warm\n"
            "owner: team-talent\n"
            "---\n"
            "soul body text"
        )
        (bundle / "IDENTITY.md").write_text("I am an identity")
        (bundle / "HEARTBEAT.md").write_text("heartbeat")

        reader = SoulReader()
        raw = reader.read(FilesystemBundleHandle(bundle))

        meta = raw["metadata"]
        assert meta["name"] == "my-soul"
        assert meta["specVersion"] == "2.0", f"specVersion dropped: {meta.get('specVersion')!r}"
        assert meta["tags"] == ["reflective", "warm"]
        assert meta["owner"] == "team-talent"

        # Body of SOUL.md should NOT include the frontmatter
        assert "soul body text" in raw["spec"]["soul_content"]
        assert "---" not in raw["spec"]["soul_content"].split("\n")[0], \
            "frontmatter still in soul_content body — reader didn't split it"

        # Round-trip: write then read again; extras preserved
        dest = tmp_path / "dest"
        SoulWriter().write(FilesystemBundleHandle(dest), raw)

        # Verify frontmatter made it onto disk
        written_soul = (dest / "SOUL.md").read_text()
        assert written_soul.startswith("---\n"), "writer didn't emit frontmatter"

        raw2 = reader.read(FilesystemBundleHandle(dest))
        assert raw2["metadata"]["specVersion"] == "2.0"
        assert raw2["metadata"]["tags"] == ["reflective", "warm"]
        assert raw2["metadata"]["owner"] == "team-talent"
        assert "soul body text" in raw2["spec"]["soul_content"]


# ── AgentsMdExtension ──

class TestAgentsMdExtension:
    def test_registers_kind_reader_writer(self):
        k = Kernel()
        from dna.extensions.agentsmd import AgentsMdExtension
        k.load(AgentsMdExtension())
        assert ("agents.md/v1", "AgentDefinition") in k._kinds
        assert len(k._readers) == 1
        assert len(k._writers) == 1  # B1.3: writer added for round-trip

    def test_agent_definition_properties(self, kernel):
        kp = kernel._kinds[("agents.md/v1", "AgentDefinition")]
        assert kp.is_prompt_target is True
        assert kp.flatten_in_context is True
        assert kp.dep_filters() is None  # Never filtered
        assert kp.alias == "agentsmd-agent"

    def test_reader_detect_agents_md(self, tmp_path):
        from dna.extensions.agentsmd import AgentDefinitionReader
        r = AgentDefinitionReader()
        assert r.detect(FilesystemBundleHandle(tmp_path)) is False
        (tmp_path / "AGENTS.md").write_text("# Context")
        assert r.detect(FilesystemBundleHandle(tmp_path)) is True

    def test_reader_skips_soul_bundle(self, tmp_path):
        """AGENTS.md inside a soul bundle is NOT an AgentDefinition."""
        from dna.extensions.agentsmd import AgentDefinitionReader
        r = AgentDefinitionReader()
        (tmp_path / "AGENTS.md").write_text("# Context")
        (tmp_path / "SOUL.md").write_text("# Soul")
        assert r.detect(FilesystemBundleHandle(tmp_path)) is False

    def test_reader_reads_content(self, tmp_path):
        from dna.extensions.agentsmd import AgentDefinitionReader
        r = AgentDefinitionReader()
        (tmp_path / "AGENTS.md").write_text("## Tools\n- grep\n- read")
        result = r.read(FilesystemBundleHandle(tmp_path))
        assert result["kind"] == "AgentDefinition"
        assert result["metadata"]["name"] == tmp_path.name
        assert "grep" in result["spec"]["content"]

    def test_agent_definition_prompt_template(self, kernel):
        kp = kernel._kinds[("agents.md/v1", "AgentDefinition")]
        assert kp.prompt_template() == "{{{content}}}"

    def test_reader_preserves_extra_metadata_fields(self, tmp_path):
        """A standalone AGENTS.md with frontmatter metadata (tags, version, owner)
        survives round-trip via AgentDefinitionReader (+ Writer if present)."""
        from dna.extensions.agentsmd import AgentDefinitionReader
        try:
            from dna.extensions.agentsmd import AgentDefinitionWriter
            has_writer = True
        except ImportError:
            has_writer = False

        bundle = tmp_path / "my-agent"
        bundle.mkdir()
        (bundle / "AGENTS.md").write_text(
            "---\n"
            "name: my-agent\n"
            "version: \"1.2\"\n"
            "tags:\n  - spec-driven\n  - internal\n"
            "owner: alice\n"
            "---\n"
            "agent body text"
        )

        reader = AgentDefinitionReader()
        raw = reader.read(FilesystemBundleHandle(bundle))

        meta = raw["metadata"]
        assert meta["name"] == "my-agent"
        assert meta["version"] == "1.2"
        assert meta["tags"] == ["spec-driven", "internal"]
        assert meta["owner"] == "alice"
        # Body preserved, without frontmatter
        assert "agent body text" in raw["spec"]["content"]
        assert not raw["spec"]["content"].lstrip().startswith("---")

        # Round-trip if Writer exists
        if has_writer:
            dest = tmp_path / "dest"
            AgentDefinitionWriter().write(FilesystemBundleHandle(dest), raw)
            written = (dest / "AGENTS.md").read_text()
            assert written.startswith("---\n"), "writer didn't emit frontmatter"
            raw2 = reader.read(FilesystemBundleHandle(dest))
            assert raw2["metadata"]["version"] == "1.2"
            assert raw2["metadata"]["tags"] == ["spec-driven", "internal"]

    def test_writer_byte_compat_when_only_name(self, tmp_path):
        """Byte-compat: AGENTS.md without extra frontmatter metadata stays plain."""
        try:
            from dna.extensions.agentsmd import AgentDefinitionWriter
        except ImportError:
            pytest.skip("AgentDefinitionWriter not present")

        dest = tmp_path / "plain"
        raw = {
            "apiVersion": "agents.md/v1",
            "kind": "AgentDefinition",
            "metadata": {"name": "plain"},
            "spec": {"content": "just the body"},
        }
        AgentDefinitionWriter().write(FilesystemBundleHandle(dest), raw)
        written = (dest / "AGENTS.md").read_text()
        assert written == "just the body"


# ── Cross-extension: KindPort uniqueness ──

class TestKindRegistration:
    def test_all_aliases_unique(self, kernel):
        """Every registered kind has a unique alias."""
        aliases = [kp.alias for kp in kernel._kinds.values()]
        assert len(aliases) == len(set(aliases))

    def test_all_api_version_kind_pairs_unique(self, kernel):
        """(apiVersion, kind) pairs are unique by construction (dict keys)."""
        keys = list(kernel._kinds.keys())
        assert len(keys) == len(set(keys))

    def test_exactly_one_root(self, kernel):
        roots = [kp for kp in kernel._kinds.values() if kp.is_root]
        assert len(roots) == 1
        # Phase 16 commit 3 — root flag transferred to Genome from Module.
        assert roots[0].kind == "Genome"

    def test_prompt_targets(self, kernel):
        targets = [kp.kind for kp in kernel._kinds.values() if kp.is_prompt_target]
        assert set(targets) == {"Agent", "Soul", "AgentDefinition"}

    def test_flatten_kinds(self, kernel):
        flatten = [kp.kind for kp in kernel._kinds.values() if kp.flatten_in_context]
        assert set(flatten) == {"Soul", "AgentDefinition"}

    def test_load_idempotent(self, kernel):
        """Loading the same extension twice doesn't duplicate kinds."""
        before = len(kernel._kinds)
        from dna.extensions.helix import HelixExtension
        kernel.load(HelixExtension())
        # Kinds overwritten (same key), so count stays the same
        assert len(kernel._kinds) == before

    def test_all_kinds_have_parse(self, kernel):
        for kp in kernel._kinds.values():
            assert callable(kp.parse)

    def test_all_kinds_have_origin(self, kernel):
        for kp in kernel._kinds.values():
            assert kp.origin is not None
