"""Market-fidelity conformance — REAL market artifacts, no adaptation (F3).

The thesis (README §2.1): market Kinds are not "converted" — DNA reads and
writes the STANDARD OWNER's native bundle, byte-faithful, under the owner's
namespace. Invented fixtures do not satisfy this AC, so every subject here is
a real artifact downloaded from the market:

  * Skill (``agentskills.io/v1``) — the 31 real Anthropic marketplace /
    community skill bundles in ``scopes/market-integration`` (xlsx, docx,
    pdf, pptx, ...), copied byte-faithful from the marketplace.
  * AgentDefinition (``agents.md/v1``) — the real ``AGENTS.md`` of
    openai/codex (``tests/market-fixtures``, provenance in NOTICE.md).
  * Soul (``soulspec.org/v1``) — the standard owner's published starter
    bundle (SOUL.md + IDENTITY.md + HEARTBEAT.md, clawsouls/soulclaw
    templates) plus the real community persona ``brad`` (clawsouls) in
    ``scopes/market-integration``.
  * CLAUDE.md — NOT covered: the SDK has no CLAUDE.md reader (the agentsmd
    extension handles AGENTS.md only).

Pattern per family: scan the native bundle → typed document under the
owner's namespace → composition (build_prompt) → write round-trip →
byte-identical diff.

DOCUMENTED NORMALIZATIONS (the only permitted byte deviations — each is
asserted explicitly, and each is idempotent):

  N1. YAML frontmatter re-emit is canonical: authoring style (quote style,
      list indentation) is not preserved; keys and values are. Affects only
      bundles whose marker file HAS authored frontmatter in a non-canonical
      style (5 of the 31 real skills; the soulspec template SOUL.md).
  N2. A bundle-derived ``name`` is materialized into frontmatter when other
      frontmatter keys exist (soulspec template SOUL.md).
  N3. ``soul.json`` is re-emitted as canonical JSON (2-space indent,
      unicode passthrough, no trailing newline) — content-equal, not
      byte-equal.
  N4. The single blank line between the closing ``---`` and the body is
      canonical: SKILL.md re-emits exactly one; SOUL.md-with-frontmatter
      re-emits none.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from dna.kernel import Kernel
from dna.kernel.bundle_handle import FilesystemBundleHandle
from dna.adapters.filesystem import FilesystemSource, FilesystemCache

REPO_ROOT = Path(__file__).resolve().parents[3]
MARKET_BASE = REPO_ROOT / "scopes" / "market-integration" / ".dna"
FIXTURE_BASE = REPO_ROOT / "tests" / "market-fixtures" / ".dna"

# Real skills whose authored frontmatter style is non-canonical (double-quoted
# description): N1 applies to their SKILL.md. Everything else must be
# byte-identical. Shrink-only ratchet — a new entry here is a fidelity
# REGRESSION.
SKILL_FM_STYLE_ALLOWLIST = {"brainstorming", "claude-api", "docx", "pptx", "xlsx"}


def _instance(base: Path, scope: str):
    k = Kernel.auto()
    k.source(FilesystemSource(str(base)))
    k.cache(FilesystemCache(str(base)))
    return k, k.instance(scope)


@pytest.fixture(scope="module")
def market():
    return _instance(MARKET_BASE, "market-demo")


@pytest.fixture(scope="module")
def fixture_scope():
    return _instance(FIXTURE_BASE, "market-conformance")


def _emitted_files(kernel, scope: str, doc) -> dict[str, str]:
    payload = kernel.serialize_document(scope, doc.kind, doc.name, doc.raw)
    return {f["relativePath"]: f["content"] for f in payload["files"]}


def _split_frontmatter(text: str) -> tuple[dict, str]:
    import re
    m = re.match(r"^---\n(.*?)---\n?(.*)$", text, re.DOTALL)
    assert m, "expected a frontmatter block"
    return yaml.safe_load(m.group(1)) or {}, m.group(2)


# ---------------------------------------------------------------------------
# Skill — 31 real marketplace bundles (agentskills.io/v1)
# ---------------------------------------------------------------------------


class TestRealSkills:
    def test_scan_finds_the_real_marketplace_skills_typed(self, market):
        _, mi = market
        skills = mi.all("Skill")
        names = {s.name for s in skills}
        assert len(skills) >= 3, "AC floor: at least 3 real Skills"
        assert {"xlsx", "docx", "pdf", "pptx"} <= names
        for s in skills:
            assert s.kind == "Skill"
            assert s.raw.get("apiVersion") == "agentskills.io/v1", (
                "market namespace must be the standard owner's, untouched"
            )
            assert s.typed is not None, f"Skill {s.name} did not type"
            assert len(s.spec.get("instruction", "")) > 50

    def test_write_roundtrip_byte_identical(self, market):
        """Every emitted file of every real Skill bundle matches the disk
        bytes exactly — except SKILL.md of the N1 allowlist (frontmatter
        style), whose deviation is asserted in the next test."""
        k, mi = market
        scope_dir = MARKET_BASE / "market-demo"
        checked = fm_style = 0
        for s in mi.all("Skill"):
            files = _emitted_files(k, "market-demo", s)
            assert "skills/%s/SKILL.md" % s.name in files
            for rel, content in files.items():
                disk = (scope_dir / rel).read_bytes()
                if disk == content.encode("utf-8"):
                    checked += 1
                    continue
                assert rel == f"skills/{s.name}/SKILL.md", (
                    f"non-SKILL.md bundle file diverged: {rel}"
                )
                assert s.name in SKILL_FM_STYLE_ALLOWLIST, (
                    f"SKILL.md of {s.name} is no longer byte-faithful — "
                    "fidelity regression (see SKILL_FM_STYLE_ALLOWLIST)"
                )
                fm_style += 1
        assert checked >= 350, f"suspiciously few byte-identical files: {checked}"
        assert fm_style <= len(SKILL_FM_STYLE_ALLOWLIST)

    def test_fm_style_allowlist_is_confined_to_frontmatter_style(self, market):
        """N1: for the allowlisted skills the ONLY deviation is YAML
        frontmatter authoring style — parsed frontmatter and body are equal."""
        k, mi = market
        scope_dir = MARKET_BASE / "market-demo"
        for name in sorted(SKILL_FM_STYLE_ALLOWLIST):
            doc = mi.one("Skill", name)
            emitted = _emitted_files(k, "market-demo", doc)[f"skills/{name}/SKILL.md"]
            disk = (scope_dir / "skills" / name / "SKILL.md").read_text()
            fm_e, body_e = _split_frontmatter(emitted)
            fm_d, body_d = _split_frontmatter(disk)
            assert fm_e == fm_d, f"{name}: frontmatter must be semantically equal"
            assert body_e == body_d, f"{name}: body must be byte-equal"

    def test_roundtrip_is_idempotent(self, market, tmp_path):
        """Write → read → write is a fixpoint: the first write is the only
        normalization that ever happens."""
        from dna.extensions.agentskills import SkillReader, SkillWriter
        k, mi = market
        reader, writer = SkillReader(), SkillWriter()
        for name in sorted(SKILL_FM_STYLE_ALLOWLIST) + ["algorithmic-art"]:
            doc = mi.one("Skill", name)
            files1 = {f["relativePath"]: f["content"] for f in writer.serialize(doc.raw)}
            bundle_dir = tmp_path / name
            for rel, content in files1.items():
                p = bundle_dir / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content)
            raw2 = reader.read(FilesystemBundleHandle(bundle_dir))
            files2 = {f["relativePath"]: f["content"] for f in writer.serialize(raw2)}
            assert files2 == files1, f"{name}: round-trip is not a fixpoint"

    def test_binary_assets_stay_on_disk(self, market):
        """Documented contract: binary bundle entries (fonts, images) are not
        surfaced in spec and not re-emitted — the writer never touches them."""
        k, mi = market
        doc = mi.one("Skill", "canvas-design")
        files = _emitted_files(k, "market-demo", doc)
        assert not any(rel.endswith((".ttf", ".png", ".pdf")) for rel in files)
        on_disk = list((MARKET_BASE / "market-demo/skills/canvas-design").rglob("*.ttf"))
        assert on_disk, "fixture invariant: canvas-design ships real font binaries"


# ---------------------------------------------------------------------------
# AgentDefinition — real openai/codex AGENTS.md (agents.md/v1)
# ---------------------------------------------------------------------------


class TestRealAgentsMd:
    def test_scan_typed_and_byte_roundtrip(self, fixture_scope):
        k, mi = fixture_scope
        doc = mi.one("AgentDefinition", "market-conformance")
        assert doc is not None, "scope-root AGENTS.md must scan as a document"
        assert doc.raw.get("apiVersion") == "agents.md/v1"
        assert doc.typed is not None
        assert "codex-rs" in doc.spec.get("content", "")
        emitted = _emitted_files(k, "market-conformance", doc)["AGENTS.md"]
        disk = (FIXTURE_BASE / "market-conformance" / "AGENTS.md").read_bytes()
        assert emitted.encode("utf-8") == disk, (
            "real AGENTS.md (openai/codex) must round-trip byte-identical"
        )

    def test_market_demo_agentsmd_roundtrip(self, market):
        k, mi = market
        doc = mi.one("AgentDefinition", "market-demo")
        assert doc is not None
        emitted = _emitted_files(k, "market-demo", doc)["AGENTS.md"]
        disk = (MARKET_BASE / "market-demo" / "AGENTS.md").read_bytes()
        assert emitted.encode("utf-8") == disk


# ---------------------------------------------------------------------------
# Soul — real soulspec.org bundles (soulspec.org/v1)
# ---------------------------------------------------------------------------


class TestRealSouls:
    def test_starter_bundle_scan_typed(self, fixture_scope):
        """NOTE: the TYPED SoulSpec view is canonical (soul/style/agents/
        soul_json) — identity_content/heartbeat_content travel on doc.raw
        only (soulspec canonical refactor). The write path is raw-based, so
        the bundle files still round-trip (next test)."""
        _, mi = fixture_scope
        soul = mi.one("Soul", "starter")
        assert soul is not None
        assert soul.raw.get("apiVersion") == "soulspec.org/v1"
        assert soul.typed is not None
        base = FIXTURE_BASE / "market-conformance/souls/starter"
        raw_spec = soul.raw.get("spec") or {}
        assert raw_spec["identity_content"] == (base / "IDENTITY.md").read_text()
        assert raw_spec["heartbeat_content"] == (base / "HEARTBEAT.md").read_text()

    def test_starter_companions_roundtrip_byte_identical(self, fixture_scope):
        """IDENTITY.md + HEARTBEAT.md — the native soulspec bundle files —
        must round-trip byte-identical (they carry authored frontmatter)."""
        k, mi = fixture_scope
        soul = mi.one("Soul", "starter")
        files = _emitted_files(k, "market-conformance", soul)
        base = FIXTURE_BASE / "market-conformance/souls/starter"
        for fname in ("IDENTITY.md", "HEARTBEAT.md"):
            assert files[f"souls/starter/{fname}"].encode("utf-8") == (base / fname).read_bytes()

    def test_starter_soulmd_normalization_is_confined(self, fixture_scope):
        """SOUL.md of the starter bundle HAS authored frontmatter → N1 + N2 +
        N4 apply: canonical fm style, materialized ``name``, no blank line
        after the closing ``---``. Frontmatter keys/values and the body are
        preserved exactly."""
        k, mi = fixture_scope
        soul = mi.one("Soul", "starter")
        emitted = _emitted_files(k, "market-conformance", soul)["souls/starter/SOUL.md"]
        disk = (FIXTURE_BASE / "market-conformance/souls/starter/SOUL.md").read_text()
        fm_e, body_e = _split_frontmatter(emitted)
        fm_d, body_d = _split_frontmatter(disk)
        assert fm_e == {**fm_d, "name": "starter"}  # N2
        assert body_e == body_d.lstrip("\n")  # N4
        assert body_e.rstrip("\n") in emitted

    def test_brad_real_persona_roundtrip_byte_identical(self, market):
        """brad (real clawsouls community persona): SOUL.md has NO authored
        frontmatter → SOUL.md, STYLE.md and the companion AGENTS.md must be
        byte-identical. In particular the parse-time DERIVED description must
        NOT leak into frontmatter that never existed on disk."""
        k, mi = market
        soul = mi.one("Soul", "brad")
        files = _emitted_files(k, "market-demo", soul)
        base = MARKET_BASE / "market-demo/souls/brad"
        for fname in ("SOUL.md", "STYLE.md", "AGENTS.md"):
            assert files[f"souls/brad/{fname}"].encode("utf-8") == (base / fname).read_bytes(), (
                f"brad/{fname} must round-trip byte-identical"
            )

    def test_brad_souljson_normalization(self, market):
        """N3: soul.json re-emits as canonical JSON — content-equal, unicode
        preserved (no \\uXXXX escapes), stable under re-emit."""
        k, mi = market
        soul = mi.one("Soul", "brad")
        emitted = _emitted_files(k, "market-demo", soul)["souls/brad/soul.json"]
        disk = (MARKET_BASE / "market-demo/souls/brad/soul.json").read_text()
        assert json.loads(emitted) == json.loads(disk)
        assert "\\u" not in emitted, "unicode must pass through (TS parity)"
        assert emitted == json.dumps(json.loads(disk), indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Composition — the market content lands in the prompt
# ---------------------------------------------------------------------------


class TestComposition:
    def test_build_prompt_flattens_the_real_soul(self, fixture_scope):
        _, mi = fixture_scope
        prompt = mi.build_prompt(agent="conductor")
        assert "You're not a chatbot" in prompt, "real SOUL.md must flatten in"
        assert "conductor agent" in prompt

    def test_agentsmd_is_a_full_prompt_target(self, fixture_scope):
        """agents.md/v1: an AGENTS.md is a FULL agent archetype — building a
        prompt with it as the target renders the real prose."""
        _, mi = fixture_scope
        prompt = mi.build_prompt(agent="market-conformance")
        assert "codex-rs" in prompt
