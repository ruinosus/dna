"""The ratchet, CLI half — see ``packages/sdk-py/tests/test_kind_name_literal_ratchet.py``.

Same scanner, same rule, same shrink-only allowlist; a separate file because the
sdk-py suite must not import ``dna_cli``.

The CLI is where the thirteen work-item lists mostly lived: ``_DIGEST_KINDS`` (10)
next to ``_GALLERY_WI_KINDS`` (9) next to ``_WORK_ITEM_KINDS`` (5), plus
``_gallery.WORK_ITEM_KINDS`` — a byte-identical duplicate of the second that
nothing linked to it. All of them now resolve through one derivation.
"""
from __future__ import annotations

from pathlib import Path

from dna.kernel import Kernel
from dna.testing.kind_literal_scan import scan_tree

_CLI_ROOT = Path(__file__).resolve().parents[1] / "dna_cli"


ALLOWLIST: dict[str, str] = {
    "specify_toolkit.py::_BODY_FIELD": (
        "IRREDUCIBLE-for-now. Kind -> the spec field carrying the verbatim "
        "exported body (PromptTemplate.body / Skill.instruction / "
        "Guardrail.instruction). The declarative home for this is the storage "
        "descriptor's `body_field`, but all three are CLASS Kinds whose storage "
        "is not bundle-shaped, so the field does not reach them yet. It is one "
        "table rather than two: `export_templates` now iterates THIS mapping "
        "instead of repeating the same three names in a loop, so the mapping "
        "and the walk cannot disagree about what is exportable."
    ),
    "specify_cmd.py::_constitution_only_plan::<inline>": (
        "IRREDUCIBLE. Not a family — a two-branch choice made three lines "
        "earlier by the `--soul` flag ('Soul' if want_soul else 'Guardrail'). "
        "The filter re-states the two outcomes of that one conditional; a trait "
        "would be a claim about Soul and Guardrail in general, and this is a "
        "claim about what THIS command just wrote."
    ),
}


def _findings():
    kernel = Kernel.auto()
    names = {p.kind for p in kernel.kind_ports()}
    assert len(names) > 50, "the registry oracle looks empty — the scan is blind"
    return scan_tree(_CLI_ROOT, kind_names=names)


def test_no_unjustified_hardcoded_kind_name_sets():
    offenders = [f for f in _findings() if f.key not in ALLOWLIST]
    assert not offenders, (
        "New hardcoded Kind-name set(s):\n"
        + "\n".join(f"  {f.describe()}" for f in offenders)
        + "\n\nDeclare a trait on the Kinds and ask "
          "`dna.application.sdlc_family` (or `kernel.kinds_with_trait`). If the "
          "site is genuinely irreducible, add its key to ALLOWLIST in this file "
          "WITH THE REASON."
    )


def test_no_stale_allowlist_entries():
    live = {f.key for f in _findings()}
    stale = sorted(set(ALLOWLIST) - live)
    assert not stale, (
        f"ALLOWLIST entries whose site no longer exists: {stale}. Delete them."
    )


def test_every_allowlist_entry_carries_a_real_reason():
    thin = sorted(k for k, v in ALLOWLIST.items() if len(v.strip()) < 40)
    assert not thin, (
        f"ALLOWLIST entries with no argument: {thin}. 'legacy' is not a reason."
    )


def test_the_families_the_cli_exposes_are_all_derived():
    """The four lists this package used to keep, resolved through one source."""
    import dna_cli._gallery as G
    import dna_cli.sdlc_cmd as C
    from dna.application.sdlc_family import (
        digest_kinds,
        producer_kinds,
        work_item_kinds,
    )

    k = Kernel.auto()
    assert C._DIGEST_KINDS == digest_kinds(k)
    assert C._GALLERY_WI_KINDS == producer_kinds(k)
    assert G.WORK_ITEM_KINDS == producer_kinds(k)
    assert set(C._WORK_ITEM_KINDS) == set(work_item_kinds(k))
    assert set(C._PRODUCER_KINDS) == set(producer_kinds(k))
