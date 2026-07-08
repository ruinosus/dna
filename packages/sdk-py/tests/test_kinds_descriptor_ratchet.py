"""F3 D5: migration ratchet — record kinds still backed by a hand-written
class may only DECREASE.

Spec: docs/superpowers/specs/2026-06-10-kinds-descriptor-f3-design.md (D5).

The F3 target state is every builtin RECORD kind expressed as a
``kinds/*.kind.yaml`` descriptor (synthesized ``DeclarativeKindPort``,
``__declarative__``), with classes reserved for Tier-2 behavior
(composition / custom parse/summary logic). This test materializes the
still-class set at ratchet time and pins it:

- a NEW record kind registered as a class FAILS CI (new kinds ship as
  descriptors — see the Kaizen pilot recipe);
- a migrated kind whose alias is still listed FAILS (the allowlist only
  shrinks — remove the alias in the migration PR);
- Tier-2 kinds that intentionally STAY classes carry a justification
  comment instead of being deleted.

Pattern: test_strict_schema_lint.py / record-MI drift ratchets.
"""
from __future__ import annotations

from dna.kernel import Kernel

# Record kinds still implemented as classes at ratchet materialization
# (2026-06-10, post-Kaizen-pilot). This set may only SHRINK — adding an
# alias to silence the lint for a NEW class-based record kind is a
# code-review red flag (write a descriptor instead).
#
# Tier-2 annotations: kinds that stay classes ON PURPOSE get a trailing
# comment with the reason (custom behavior the descriptor can't express).
STILL_CLASS_ALLOWLIST = frozenset({
    # audit-auditlog: migrated to a descriptor in expr batch A (plan
    # 2026-06-11-descriptor-expressiveness) — first builtin Kind to carry the
    # new D2 ui: descriptor field.
    # autoagent-experiment + autolab-run: migrated to
    # descriptors in expr batch B (plan 2026-06-11-descriptor-expressiveness,
    # Chunk 4). The lote-3 skips are now expressible: the authored/computed
    # summaries via the D2 vocabulary (commit {path,truncate:7,default:""};
    # passed {format,all_or_empty}; avg_score/cost {path,round}; "iter m/n"
    # {format,placeholder_defaults}) and autolab's _DEFAULTS parse-merge via
    # the D5 spec_defaults: block.
    # cognitive-pattern-insight + cognitive-pre-mortem: migrated to
    # descriptors in F3 lote-1 (2026-06-10).
    # eval-evalexperiment: migrated to a descriptor in expr batch A (plan
    # 2026-06-11-descriptor-expressiveness) — D2 ui: + D3 describe:
    # ({path: description}) + D6 default_agent_field: agent_ref (now all
    # expressible; the dynamic get_default_agent_name reads spec.agent_ref
    # VERBATIM via the field declaration).
    # eval-evalrun + eval-finding: migrated to descriptors in F3 lote-3
    # (2026-06-11; Finding also left _EMBED_LEGACY via embed:).
    # eval-evolve-experiment + eval-evolve-run: migrated to descriptors in
    # expr batch B (plan 2026-06-11-descriptor-expressiveness, Chunk 4). The
    # lote-3 "parse retorna Document" / "summary computado" blockers are now
    # expressible: the descriptor port's schema-validating parse(raw) is
    # canonical (kernel wraps raw→Document) and the D2 summary vocabulary
    # (format placeholder_defaults + {path: applied_change.action}) reproduces
    # the deleted summaries 1:1.
    "sdlc-agent-session",  # Tier-2 (lote-3 skip): summary computado
                           # (title[:80], len(produced_artifacts)) + schema usa
                           # o enum VIVO compartilhado JOURNEY_PHASES
                           # (precedente sdlc-spike).
    "sdlc-bug",
    # sdlc-engram-strength-policy: migrated to a descriptor in expr batch B
    # (Chunk 4) — rule_count = {count_of: rules}.
    "sdlc-epic",
    "sdlc-feature",
    "sdlc-initiative",
    "sdlc-issue",
    # sdlc-lesson-learned: migrated to a descriptor in F3 lote-1.
    # sdlc-memory-policy: migrated to a descriptor in expr batch B (Chunk 4) —
    # applies_to = {paths:[…], filter_falsy:true} (leaf-keyed); default_visibility
    # = {path: defaults.visibility, default: shared}. The present-but-null
    # default_visibility delta is port-canonical, pinned in the equivalence test.
    "sdlc-plan",
    # sdlc-prompt-template: migrated to a descriptor in expr batch B (Chunk 4)
    # — ui_schema (D4 pass-through), describe {path: description} (D3),
    # description_fallback_field: body (D7), variables_count/body_length =
    # {count_of: …} (count_of over a string for body). The class's `or None`
    # empty-string describe coercion is the documented port-canonical delta.
    "sdlc-reference",
    # sdlc-retrospective: migrated to a descriptor in F3 lote-1.
    "sdlc-roadmap",
    "sdlc-spec",
    "sdlc-spike",          # Tier-2 (lote-2 skip): schema é composto de helpers
                           # VIVOS compartilhados (_timeline_field_schema /
                           # _produces_field_schema + enum TIMELINE_TYPES,
                           # compartilhados com Story/Bug/Task ainda classes) —
                           # congelar uma cópia no descriptor forkaria o
                           # contrato de timeline e o parse validante passaria
                           # a rejeitar novos timeline types.
    "sdlc-story",          # lote-2: precisa de D2-ui (StudioUIMetadata no descriptor)
    # sdlc-synthesizer-state: migrated to a descriptor in F3 lote-3
    # (DREAMER_METHODS agora vive só no descriptor).
    "sdlc-task",
    # sdlc-workflow-event: migrated to a descriptor in F3 lote-1.
    # voice-voiceepisode: migrated to a descriptor in F3 lote-3 (canônico =
    # superfície Py, sem schema; o schema TS-only morreu com a classe).
})


def _record_class_aliases() -> tuple[set[str], set[str]]:
    """Return (still_class, declarative) alias sets for record-plane kinds."""
    k = Kernel.auto()
    still_class: set[str] = set()
    declarative: set[str] = set()
    for kp in k.kind_ports():
        if getattr(kp, "plane", "composition") != "record":
            continue
        alias = getattr(kp, "alias", "")
        if getattr(kp, "__declarative__", False):
            declarative.add(alias)
        else:
            still_class.add(alias)
    return still_class, declarative


def test_no_new_class_based_record_kinds():
    """A new record kind must be a descriptor (kinds/*.kind.yaml) — class
    registration of records is grandfathered only."""
    still_class, _ = _record_class_aliases()
    offenders = sorted(still_class - STILL_CLASS_ALLOWLIST)
    assert not offenders, (
        "New class-based record Kind(s) — express them as kinds/*.kind.yaml "
        "descriptors (see the Kaizen pilot: extensions/sdlc/kinds/"
        "kaizen.kind.yaml + test_kaizen_descriptor_equivalence.py), or "
        f"(Tier-2 only, justified) add the alias here:\n  {offenders}"
    )


def test_no_stale_allowlist_entries():
    """The allowlist only shrinks: once a kind is migrated to a descriptor
    (or deleted), its alias must be removed here."""
    still_class, declarative = _record_class_aliases()
    present = still_class | declarative
    stale = sorted(
        a for a in STILL_CLASS_ALLOWLIST
        if a not in still_class
    )
    assert not stale, (
        "Allowlisted alias(es) are no longer class-based record kinds "
        f"(migrated or removed) — delete them from STILL_CLASS_ALLOWLIST:\n  {stale}"
        + (f"\n(currently declarative: {sorted(declarative & set(stale))})" if declarative else "")
    )


def test_descriptor_path_is_real():
    """Sanity: the declarative path exists (Kaizen pilot)."""
    _, declarative = _record_class_aliases()
    assert "sdlc-kaizen" in declarative
