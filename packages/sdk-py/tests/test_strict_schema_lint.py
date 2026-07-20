"""s-strict-schema-lint — a ratchet that stops the ``additionalProperties: true``
anti-pattern from growing.

At authoring time 112 of 114 Kind top-level schemas were open
(``additionalProperties`` absent/True) → most Kinds accept arbitrary fields with
no validation (the schema is documentation, not a contract). Flipping the
grandfathered Kinds to strict is deferred (i-094): schemas ARE enforced on write
(``kernel/meta.py`` ``jsonschema.validate``), so a blind flip could reject
in-flight docs carrying extra fields.

This lint freezes the status quo and ratchets it tighter:
  - a NEW open Kind not in the grandfather allowlist FAILS CI (no new offenders);
  - a Kind that becomes strict but is still allowlisted FAILS (allowlist only
    shrinks — the ratchet tightens as i-094 flips Kinds);
  - the already-strict Kind(s) stay strict.

To bring a grandfathered Kind to strict: set ``additionalProperties: false`` on
its schema (after auditing stored docs per i-094) AND remove its alias below.
"""
from __future__ import annotations

from dna.kernel import Kernel

# Grandfathered open-schema Kinds (alias). Pre-existing at s-strict-schema-lint.
# This set may only SHRINK — adding an alias here to silence the lint for a NEW
# Kind is a code-review red flag (prefer additionalProperties:false on new Kinds).
_GRANDFATHERED_OPEN_SCHEMAS = frozenset({
    # "dna-doc" left this set on s-tier-a-doc-kind: the native Doc Kind
    # ships strict (additionalProperties: false) from day one.
    "agentskills-skill",
    "agentsmd-agent", "asset-asset", "audit-auditlog", "audit-userroleassignment",
    "autoagent-experiment", "autoagent-program", "autolab-run",
    "blocks-html",
    "blocks-html-template", "blocks-text", "helix-actor", "helix-canvas",
    "helix-engram",  # s-engram-rename (2026-07-19): was sdlc-lesson-learned.
    "helix-hook", "helix-genome", "helix-safety-policy",
    "helix-setting", "helix-theme", "helix-tool",
    "helix-usecase", "helix-user-profile", "helix-agent",
    "collab-comment",
    "eval-evalbaseline", "eval-evalcase", "eval-evalexperiment",
    "eval-evalrun", "eval-evalsuite", "eval-evolve-experiment",
    "eval-evolve-program", "eval-evolve-run", "eval-finding", "eval-judgeprofile",
    "eval-mitigation", "eval-scorecard", "evidence-evidence", "evidence-policy",
    "federation-mcp", "gaia-assessment", "gaia-assessmentreport",
    "gaia-assessmentrun", "graphify-artifact",
    "guardrails-guardrail", "htmlartifact-htmlartifact", "imageprompt-imageprompt",
    "jobs-job", "kinddef-kinddefinition",
    "knowledge-artifact", "lesson-lesson", "lottie-asset",
    "modelreg-model-profile",
    "pictogram-pictogram", "policy-layer-policy", "presidio-recognizer",
    "research-reference", "research-research", "sdlc-adr",
    "sdlc-agent-session", "sdlc-bug", "sdlc-changelog",
    "sdlc-epic", "sdlc-feature",
    # The cognitive-policy family (9 open aliases) left this set on
    # s-consolidate-cognitive-policies: 8 Kinds were retired and the unified
    # sdlc-cognitive-policy ships strict (additionalProperties: false).
    "sdlc-initiative", "sdlc-issue",
    "sdlc-narrative", "sdlc-plan", "sdlc-postmortem",
    "sdlc-prompt-template", "sdlc-reference", "sdlc-retrospective",
    "sdlc-risk-register", "sdlc-roadmap", "sdlc-spec",
    "sdlc-spike", "sdlc-status-report", "sdlc-story",
    "sdlc-task", "soulspec-soul",
    "tenant-membership", "tenant-tenant", "voice-voicepolicy",
})


def _schema_strictness() -> tuple[set[str], set[str], set[str]]:
    """Return (strict, open, no_schema) alias sets for all registered Kinds."""
    k = Kernel.auto()
    strict, open_, no_schema = set(), set(), set()
    for kp in k._kinds.values():
        alias = getattr(kp, "alias", "")
        try:
            schema = kp.schema() if hasattr(kp, "schema") else None
        except Exception:  # noqa: BLE001 — a broken schema() isn't this lint's concern
            schema = None
        if not isinstance(schema, dict):
            no_schema.add(alias)
        elif schema.get("additionalProperties", True) is False:
            strict.add(alias)
        else:
            open_.add(alias)
    return strict, open_, no_schema


def test_no_new_open_schemas():
    """A new Kind must be strict (additionalProperties:false) or explicitly
    grandfathered. This blocks the anti-pattern from growing."""
    _, open_, _ = _schema_strictness()
    new_offenders = sorted(open_ - _GRANDFATHERED_OPEN_SCHEMAS)
    assert not new_offenders, (
        "New open-schema Kind(s) — set additionalProperties:false on the schema, "
        "or (last resort) add the alias to _GRANDFATHERED_OPEN_SCHEMAS with "
        f"justification:\n  {new_offenders}"
    )


def test_no_stale_allowlist_entries():
    """The grandfather allowlist may only shrink: once a Kind is made strict
    (i-094), its alias must be removed here. A stale entry fails so the ratchet
    keeps tightening."""
    strict, open_, no_schema = _schema_strictness()
    present = strict | open_ | no_schema
    stale = sorted(
        a for a in _GRANDFATHERED_OPEN_SCHEMAS if a in present and a not in open_
    )
    assert not stale, (
        "Allowlisted Kind(s) are no longer open (strict or schema-less now) — "
        f"remove them from _GRANDFATHERED_OPEN_SCHEMAS:\n  {stale}"
    )


def test_at_least_one_kind_is_strict():
    """Sanity: the strict path is real (sdlc-workflow-event ships strict)."""
    strict, _, _ = _schema_strictness()
    assert "sdlc-workflow-event" in strict
