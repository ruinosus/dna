"""Descriptor-conversion pattern proposal — the converted ports must be
byte-for-byte equivalent to the classes they replace.

FOUR representative Kinds of the 23 that a Kind census flagged as
class-only-for-no-reason (their only overrides are ``schema`` / ``summary`` /
``describe`` / ``dep_filters`` — all first-class descriptor fields):

  * **Comment** (collab) — the simplest of the 23: 58 lines of Python, and the
    only one in an extension that had NO ``load_descriptors`` loop yet, so it
    proves the pattern lands in a virgin extension.
  * **Plan** (sdlc) — carries real ``dep_filters`` (2 typed entries), BUNDLE
    storage (vs Story's yaml), ``scope_inheritable = False``, and a
    ``(title or "")[:80]`` summary that needs the D2 ``truncate`` combinator.
  * **Story** (sdlc) — the flagship of the largest cluster: 248 lines for four
    things, the only one of the 23 carrying ``StudioUIMetadata`` (the D1 ``ui:``
    field), a ``len(spec_refs)`` summary (``count_of``), and a schema built from
    the LIVE shared helpers ``_timeline_field_schema`` /
    ``_produces_field_schema`` — reached through a **schema fragment** so the
    descriptor does not fork the timeline contract away from Bug/Task/Spike,
    which stay classes.
  * **Reference** (sdlc) — the awkward one. See ``to_card`` below.

GOLDENS: ``tests/goldens/descriptor_pattern/<Kind>.golden.json``, captured
from the LIVE classes at the parent of the conversion commit, through the real
funnel (``Kernel().load(Extension())`` → ``kind_port_for``). Cases run on REAL
repository documents (``.dna/dna/{stories,plans,references}``) plus an
empty-spec probe; Comment has no document anywhere in the repo, so its cases
are fixtures. Each case pins ``summary`` / ``describe`` / ``get_default_agent_name``
/ ``get_layer_policies`` / ``canonical_digest`` / ``parse`` round-trip.

**The canonical digest is the load-bearing assertion.** If it moved, stored
documents would change identity and this would be a migration, not a
refactor. It does not move: ``DeclarativeKindPort`` shares ``KindBase``'s
``_canonical_spec`` / ``canonical_digest`` function objects verbatim, and none
of the four descriptors declares ``volatile_spec_fields``.

DELTAS — deliberately NONE for the surface above. Two behaviours change in a
direction the earlier descriptor batches already established:

  - **parse validates.** The classes were pass-through
    (``validate_on_parse = False``); the descriptor port validates ``spec``
    against the schema. ``test_every_real_document_still_validates`` walks
    every Story/Plan/Reference document in this repo's own board and proves
    none of them starts failing. (An invalid doc would not crash a load
    either — the kernel turns it into ``typed=None`` + a ``parse_error`` event.)
  - **``preview()`` appears.** The classes had none, so consumers fell back to
    the generic renderer; the port derives preview blocks from the schema.
    Strictly additive.

And one thing is DROPPED:

  - **``Reference.to_card``** — the descriptor format has no field for it.
    This is the honest crack in the census's claim: Reference is the one of
    the four that overrides something the format cannot express. It is dead
    code (zero consumers in the repo, mirroring the LessonLearned /
    StatusReport / Engram / PromptTemplate ``to_card``s that the earlier
    batches dropped for the same reason), so the drop is precedented — but it
    means each remaining candidate needs an individual check, not a blanket
    sweep.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from dna.extensions.collab import CollabExtension
from dna.extensions.sdlc import SdlcExtension
from dna.kernel import Kernel
from dna.kernel.kinds.base import KindBase
from dna.kernel.protocols import TenantScope

GOLDEN_DIR = Path(__file__).parent / "goldens" / "descriptor_pattern"
REPO_ROOT = Path(__file__).resolve().parents[3]

# Kind → the extension that registers it.
KINDS = {
    "Comment": CollabExtension,
    "Plan": SdlcExtension,
    "Story": SdlcExtension,
    "Reference": SdlcExtension,
}


def _golden(kind: str) -> dict:
    return json.loads((GOLDEN_DIR / f"{kind}.golden.json").read_text())


@pytest.fixture(scope="module")
def ports() -> dict[str, object]:
    """Ports exactly as the extensions register them — the real funnel."""
    out: dict[str, object] = {}
    for kind, ext_cls in KINDS.items():
        k = Kernel()
        k.load(ext_cls())
        kp = k.kind_port_for(kind)
        assert kp is not None, f"{kind} not registered by {ext_cls.__name__}"
        out[kind] = kp
    return out


def _doc(raw: dict) -> SimpleNamespace:
    return SimpleNamespace(
        kind=raw.get("kind"),
        name=(raw.get("metadata") or {}).get("name"),
        spec=raw.get("spec") or {},
    )


def _case_doc(kind: str, case: dict) -> SimpleNamespace:
    return SimpleNamespace(kind=kind, name=case["name"], spec=case["spec"])


ALL = list(KINDS)


# --- identity ---------------------------------------------------------------

@pytest.mark.parametrize("kind", ALL)
def test_identity_matches_golden(ports, kind):
    g = _golden(kind)["identity"]
    p = ports[kind]
    assert p.api_version == g["api_version"]
    assert p.kind == g["kind"]
    assert p.alias == g["alias"]
    assert p.origin == g["origin"]
    assert p.model.__name__ == g["model"]
    assert p.display_label == g["display_label"]
    assert p.ascii_icon == g["ascii_icon"]
    assert p.graph_style == g["graph_style"]
    assert p.docs == g["docs"]


# --- flags ------------------------------------------------------------------

@pytest.mark.parametrize("kind", ALL)
def test_flags_match_golden(ports, kind):
    g = _golden(kind)["flags"]
    p = ports[kind]
    assert getattr(p, "plane", "composition") == g["plane"]
    # ``scope`` is only SET when tenancy was declared — an undeclared Kind must
    # stay permissive (Kernel._kind_scope reads getattr(kp, "scope", None)).
    assert hasattr(p, "scope") is g["scope_declared"]
    if g["scope_declared"]:
        assert p.scope == TenantScope(g["scope"])
    assert p.is_prompt_target is g["is_prompt_target"]
    assert p.flatten_in_context is g["flatten_in_context"]
    assert p.prompt_target_priority == g["prompt_target_priority"]
    assert p.is_root is g["is_root"]
    assert getattr(p, "is_runtime_artifact", False) is g["is_runtime_artifact"]
    assert getattr(p, "is_schema_affecting", False) is g["is_schema_affecting"]
    assert getattr(p, "is_overlayable", True) is g["is_overlayable"]
    assert getattr(p, "scope_inheritable", True) is g["scope_inheritable"]
    assert getattr(p, "is_catalog_identity", False) is g["is_catalog_identity"]
    assert getattr(p, "visible_in_backend", None) == g["visible_in_backend"]
    assert getattr(p, "embed_fields", None) == g["embed_fields"]
    assert getattr(p, "description_fallback_field", None) == g["description_fallback_field"]
    assert getattr(p, "ui_schema", None) == g["ui_schema"]
    assert getattr(p, "marker_shared_allowed", False) is g["marker_shared_allowed"]


@pytest.mark.parametrize("kind", ALL)
def test_volatile_spec_fields_are_kindbase_defaults(ports, kind):
    """The canonical-digest contract: no descriptor widens the volatile set,
    so the digest of a stored document cannot move."""
    p = ports[kind]
    assert sorted(p.VOLATILE_SPEC_FIELDS) == _golden(kind)["flags"]["volatile_spec_fields"]
    assert p.VOLATILE_SPEC_FIELDS == KindBase.VOLATILE_SPEC_FIELDS


@pytest.mark.parametrize("kind", ALL)
def test_studio_ui_matches_golden(ports, kind):
    """D1 ``ui:`` — Story is the only one of the four that carries Studio
    metadata; the port must rebuild the real dataclass (``/kinds/manifest``
    calls both ``to_dict()`` and ``resolve_label()``)."""
    g = _golden(kind)["ui"]
    ui = getattr(ports[kind], "ui", None)
    if g is None:
        assert ui is None
        return
    assert ui is not None
    assert ui.to_dict() == g["to_dict"]
    assert ui.resolve_label("en") == g["resolve_label_en"]
    assert ui.resolve_label("pt-BR") == g["resolve_label_pt"]


# --- storage ----------------------------------------------------------------

@pytest.mark.parametrize("kind", ALL)
def test_storage_matches_golden(ports, kind):
    g = _golden(kind)["storage"]
    sd = ports[kind].storage
    assert sd.pattern.value == g["pattern"]
    assert sd.container == g["container"]
    assert sd.marker == g["marker"]
    assert getattr(sd, "body_field", None) == g["body_field"]
    assert getattr(getattr(sd, "body_as", None), "value", None) == g["body_as"]


# --- dep_filters + schema ---------------------------------------------------

@pytest.mark.parametrize("kind", ALL)
def test_dep_filters_match_golden(ports, kind):
    """Exactly equal, including the empty ``{}`` that Comment and Reference
    returned — declaring ``dep_filters: {}`` in the descriptor reproduces it,
    so this conversion has no falsy-delta to excuse."""
    g = _golden(kind)["dep_filters"]
    assert ports[kind].dep_filters() == g
    assert ports[kind].dependencies() == _golden(kind)["dependencies"]


@pytest.mark.parametrize("kind", ALL)
def test_schema_deep_equals_golden(ports, kind):
    assert ports[kind].schema() == _golden(kind)["schema"]


@pytest.mark.parametrize("kind", ALL)
def test_prompt_template_unchanged(ports, kind):
    assert ports[kind].prompt_template() == _golden(kind)["prompt_template"]


# --- per-document surface ---------------------------------------------------

def _cases(kind: str):
    return [(c["label"], c) for c in _golden(kind)["cases"]]


@pytest.mark.parametrize("kind", ALL)
def test_summary_matches_golden_on_every_case(ports, kind):
    p = ports[kind]
    for label, case in _cases(kind):
        assert p.summary(_case_doc(kind, case)) == case["summary"], f"{kind} :: {label}"


@pytest.mark.parametrize("kind", ALL)
def test_describe_matches_golden_on_every_case(ports, kind):
    p = ports[kind]
    for label, case in _cases(kind):
        assert p.describe(_case_doc(kind, case)) == case["describe"], f"{kind} :: {label}"


@pytest.mark.parametrize("kind", ALL)
def test_default_agent_and_layer_policies_match_golden(ports, kind):
    p = ports[kind]
    for label, case in _cases(kind):
        d = _case_doc(kind, case)
        assert p.get_default_agent_name(d) == case["default_agent"], f"{kind} :: {label}"
        assert p.get_layer_policies(d) == case["layer_policies"], f"{kind} :: {label}"


@pytest.mark.parametrize("kind", ALL)
def test_canonical_digest_is_unmoved(ports, kind):
    """THE assertion that separates a refactor from a migration: the identity
    hash of a real stored document is bit-identical to the class's."""
    p = ports[kind]
    for label, case in _cases(kind):
        got = p.canonical_digest(_case_doc(kind, case))
        assert got == case["canonical_digest"], (
            f"{kind} :: {label} — canonical digest MOVED "
            f"({case['canonical_digest']} → {got}). Stored documents would "
            f"change identity; this would be a migration, not a refactor."
        )


@pytest.mark.parametrize("kind", ALL)
def test_summary_on_a_bare_dict_is_the_documented_port_delta(ports, kind):
    """The one input shape where class and port disagree: all four classes
    wrote ``doc.spec if hasattr(doc, "spec") else doc``, i.e. they treated a
    bare dict AS the spec. The port reads ``getattr(doc, "spec", None) or {}``
    and projects the declared defaults instead. Every real call site
    (``nav.py``, ``navigator.py``, ``compose/resolver.py``) passes a Document,
    so nothing in the system takes this path — pinned, not hidden. Same
    delta the earlier descriptor batches pinned."""
    empty = next(c for _, c in _cases(kind) if c["spec"] == {})
    for _, case in _cases(kind):
        assert ports[kind].summary(dict(case["spec"])) == empty["summary"]


# --- parse ------------------------------------------------------------------

def _envelope(kind: str, case: dict) -> dict:
    return {
        "apiVersion": _golden(kind)["identity"]["api_version"],
        "kind": kind,
        "metadata": {"name": case["name"]},
        "spec": case["spec"],
    }


@pytest.mark.parametrize("kind", ALL)
def test_parse_round_trips_every_real_document(ports, kind):
    """Every real (non-probe) case still parses to itself, unchanged."""
    p = ports[kind]
    for label, case in _cases(kind):
        if not case["spec"]:
            continue  # the empty-spec probe — see the test below
        raw = _envelope(kind, case)
        assert p.parse(dict(raw)) == raw, f"{kind} :: {label}"
        assert case["parse_roundtrip"] is True


@pytest.mark.parametrize("kind", ALL)
def test_the_empty_spec_probe_is_where_parse_starts_biting(ports, kind):
    """The classes accepted an empty spec (pass-through); the port rejects it
    because every one of the four declares ``required``. Pinned as the exact
    boundary of the parse delta — and ``test_every_real_document_still_validates``
    proves no document in this repo's board is on the wrong side of it."""
    probe = next(c for _, c in _cases(kind) if not c["spec"])
    assert probe["parse_roundtrip"] is True  # what the class did
    with pytest.raises(ValueError, match="is a required property"):
        ports[kind].parse(_envelope(kind, probe))


@pytest.mark.parametrize("kind,missing", [
    ("Comment", "target_ref"),
    ("Plan", "date"),
    ("Story", "status"),
    ("Reference", "kind_of"),
])
def test_parse_now_rejects_a_doc_missing_a_required_field(ports, kind, missing):
    """The one behaviour that changes: the port validates where the class was
    pass-through. Upgrade, not regression — in the kernel this becomes
    ``typed=None`` + a ``parse_error`` event, never a failed load."""
    g = _golden(kind)
    full = max((c for c in g["cases"]), key=lambda c: len(c["spec"]))
    spec = {k: v for k, v in full["spec"].items() if k != missing}
    with pytest.raises(ValueError, match=missing):
        ports[kind].parse({
            "apiVersion": g["identity"]["api_version"],
            "kind": kind,
            "metadata": {"name": full["name"]},
            "spec": spec,
        })


_REAL_DOC_DIRS = {
    "Story": REPO_ROOT / ".dna" / "dna" / "stories",
    "Plan": REPO_ROOT / ".dna" / "dna" / "plans",
    "Reference": REPO_ROOT / ".dna" / "dna" / "references",
}


@pytest.mark.parametrize("kind", sorted(_REAL_DOC_DIRS))
def test_every_real_document_still_validates(ports, kind):
    """Because parse now validates, a single non-conforming document in this
    repo's own board would start loading untyped. Walk them all."""
    directory = _REAL_DOC_DIRS[kind]
    if not directory.is_dir():
        pytest.skip(f"{directory} not present in this checkout")
    paths = sorted(directory.glob("*.yaml"))
    assert paths, f"no {kind} documents under {directory}"
    for path in paths:
        raw = yaml.safe_load(path.read_text())
        if not isinstance(raw, dict) or raw.get("kind") != kind:
            continue
        ports[kind].parse(raw)  # raises ValueError on a schema violation


# --- the classes are gone ---------------------------------------------------

def test_converted_classes_no_longer_exist():
    import dna.extensions.collab as collab
    import dna.extensions.sdlc as sdlc

    assert not hasattr(collab, "CommentKind")
    for cls in ("PlanKind", "StoryKind", "ReferenceKind"):
        assert not hasattr(sdlc, cls), f"{cls} came back — the descriptor is the source"


@pytest.mark.parametrize("kind", ALL)
def test_ports_are_builtin_descriptors(ports, kind):
    p = ports[kind]
    assert getattr(p, "__declarative__", False) is True, kind
    assert getattr(p, "__builtin_descriptor__", False) is True, kind
    assert isinstance(getattr(p, "__descriptor_digest__", None), str), kind


@pytest.mark.parametrize("kind", ALL)
def test_preview_is_the_additive_delta(ports, kind):
    """The classes had no ``preview`` at all (consumers fall back to the
    generic renderer); the port derives blocks from the schema. Pinned so the
    addition is a decision, not a surprise."""
    p = ports[kind]
    assert callable(getattr(p, "preview", None))
    blocks = p.preview(_case_doc(kind, _golden(kind)["cases"][0]))
    assert blocks and all(getattr(b, "kind", None) for b in blocks)


def test_reference_to_card_was_dropped():
    """The census's claim is not quite true for Reference: its ``to_card`` is
    an override the descriptor format cannot express. Dropped because it is
    dead code — pinned here so nobody re-discovers it as a regression."""
    assert not hasattr(_kind_port_for("Reference"), "to_card")


def _kind_port_for(kind: str):
    k = Kernel()
    k.load(KINDS[kind]())
    return k.kind_port_for(kind)


# --- schema fragments -------------------------------------------------------

def test_story_reaches_the_live_timeline_helpers_through_a_fragment(ports):
    """Story's ``timeline`` / ``produces`` sub-schemas come from the SAME live
    Python helpers Bug/Task/Spike (still classes) use — via the
    ``sdlc/work-item-activity`` schema fragment, not a frozen YAML copy. This
    is what unblocks the ``sdlc-spike`` Tier-2 note in the migration ratchet
    ("freezing a copy in the descriptor would fork the timeline contract").
    """
    from dna.extensions.sdlc import (
        _produces_field_schema,
        _timeline_field_schema,
    )
    from dna.kernel.meta import _lookup_schema_fragment, list_schema_fragments

    assert "sdlc/work-item-activity" in list_schema_fragments()
    frag = _lookup_schema_fragment("sdlc/work-item-activity")
    assert frag["properties"]["timeline"] == _timeline_field_schema()
    assert frag["properties"]["produces"] == _produces_field_schema()

    schema = ports["Story"].schema()
    assert schema["properties"]["timeline"] == _timeline_field_schema()
    assert schema["properties"]["produces"] == _produces_field_schema()


def test_the_fragment_registry_is_populated_before_descriptors_load():
    """Ordering guard: ``register_schema_fragment`` must run BEFORE the
    ``load_descriptors`` loop, because ``DeclarativeKindPort.__init__``
    resolves fragment IDs at load time and silently skips unknown ones. If the
    order regresses, Story's schema loses timeline/produces entirely — which
    this asserts against."""
    k = Kernel()
    k.load(SdlcExtension())
    props = k.kind_port_for("Story").schema()["properties"]
    assert "timeline" in props and "produces" in props
