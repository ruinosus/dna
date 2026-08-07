"""``spec.presentation`` — ONE declaration of how a Kind's data reads.

The same Kind used to be described twice: once for a portal screen, once for
an MCP Apps card. Two descriptions of one thing drift, and a new Kind needed
both. What is shared between those two surfaces is NOT the framework — a React
screen and a sandboxed prefab iframe cannot and should not share one — it is
what the DATA MEANS: which fields a human reads, in what order, what to call
them, which one names the instance, which one is its state, and which are
machinery.

So this is deliberately NOT a layout language. There is no column, no width,
no section, no colour, no variant and no widget anywhere in the vocabulary —
a schema that said how a card looks would be wrong for the first surface that
adopted it afterwards. Each entry says what the field IS; the surface decides
what that becomes on it.

The suite pins four things:

1. the vocabulary is CLOSED and small, and every role is evidenced by a real
   field on a real Kind;
2. a descriptor declares it, a TENANT ``KindDefinition`` declares it in the
   very same words (a presentation only builtins could declare would make
   tenant Kinds second-class, which is the whole point of the constraint);
3. it is normalized ONCE — the shorthand, the derived labels and the
   validation live in one module, so the card, the REST face and the portal
   cannot each invent their own reading of it;
4. the projection ``list_stories`` publishes is DERIVED from it — the
   provenance test that a hardcoded column list cannot pass.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from dna._yaml import safe_load
from dna.kernel.kinds.presentation import (
    PRESENTATION_ROLES,
    SINGULAR_ROLES,
    Presentation,
    PresentationField,
    derive_label,
    normalize_presentation,
    presentation_of,
    presentation_wire,
    project_row,
)

_SDK = pathlib.Path(__file__).resolve().parents[1]
_REPO = _SDK.parents[1]


# ── 1. the vocabulary ──────────────────────────────────────────────────────


def test_the_role_vocabulary_is_closed_and_stated_here():
    """A CLOSED vocabulary, and small. Open roles would let each surface guess
    at a word nobody defined; a large one would be speculation about surfaces
    that do not exist yet. Every role below is evidenced by a field that a Kind
    in this repo actually carries."""
    assert PRESENTATION_ROLES == frozenset({
        "identifier", "title", "subtitle", "status",
        "owner", "parent", "rank", "tag", "timestamp", "metric", "body",
    })


def test_the_roles_a_document_can_only_have_one_of_are_declared():
    """An instance has one name, one headline and one state. Two fields
    claiming ``status`` is a declaration error, not a rendering choice the
    surface should have to break the tie for."""
    assert SINGULAR_ROLES == ("identifier", "title", "subtitle", "status")


def test_an_unknown_role_is_refused_by_name():
    with pytest.raises(ValueError, match="badge"):
        normalize_presentation({"fields": [{"field": "status", "role": "badge"}]})


def test_a_layout_word_is_not_smuggled_in_as_a_key():
    """The trap this schema exists to avoid: a key that describes pixels. An
    unknown entry key is refused rather than tolerated, so ``width``/``column``
    /``variant`` cannot arrive as a de-facto extension."""
    for layout_key in ("width", "column", "variant", "widget", "colour"):
        with pytest.raises(ValueError, match=layout_key):
            normalize_presentation(
                {"fields": [{"field": "status", layout_key: "x"}]}
            )


def test_two_fields_cannot_claim_the_same_singular_role():
    with pytest.raises(ValueError, match="status"):
        normalize_presentation({"fields": [
            {"field": "status", "role": "status"},
            {"field": "phase", "role": "status"},
        ]})


def test_a_field_cannot_be_both_shown_and_hidden():
    with pytest.raises(ValueError, match="created_at"):
        normalize_presentation(
            {"fields": ["created_at"], "hidden": ["created_at"]}
        )


def test_a_duplicate_field_is_refused():
    with pytest.raises(ValueError, match="status"):
        normalize_presentation({"fields": ["status", "status"]})


def test_an_unknown_top_level_key_is_refused():
    with pytest.raises(ValueError, match="sections"):
        normalize_presentation({"fields": ["status"], "sections": []})


# ── 2. the shorthand and the derived label ─────────────────────────────────


def test_the_bare_list_shorthand_is_the_whole_declaration():
    """``presentation: [name, title, status]`` — the ergonomics a tenant gets
    for free, mirroring the shorthand ``spec.summary`` already accepts."""
    p = normalize_presentation(["name", "title", "status"])
    assert [f.field for f in p.fields] == ["name", "title", "status"]
    assert all(f.role is None for f in p.fields)


def test_an_undeclared_label_is_derived_from_the_field_name():
    """A tenant that declares only field NAMES still gets a usable card. The
    derivation is deterministic and overridable, never a guess presented as
    authorship."""
    assert derive_label("status") == "Status"
    assert derive_label("spec_refs") == "Spec refs"
    assert derive_label("business_value") == "Business value"
    p = normalize_presentation(["spec_refs"])
    assert p.fields[0].label == "Spec refs"


def test_a_declared_label_wins_over_the_derivation():
    p = normalize_presentation({"fields": [{"field": "name", "label": "Story"}]})
    assert p.fields[0].label == "Story"


def test_normalizing_an_already_normalized_presentation_is_identity():
    p = normalize_presentation(["name", "status"])
    assert normalize_presentation(p) is p


def test_the_wire_form_is_stable_and_carries_the_kinds_own_label():
    """What travels to BOTH consumers. ``label``/``icon`` are the two
    presentation attrs the protocol already carried (``display_label`` /
    ``ascii_icon``) — composed into the same envelope so a surface asks one
    question instead of three."""
    p = normalize_presentation({
        "fields": [{"field": "name", "label": "Story", "role": "identifier"},
                   {"field": "status", "role": "status"}],
        "hidden": ["updated_at", "created_at"],
    })
    assert p.to_wire(label="Stories", icon="X") == {
        "label": "Stories",
        "icon": "X",
        "fields": [
            {"field": "name", "label": "Story", "role": "identifier"},
            {"field": "status", "label": "Status", "role": "status"},
        ],
        # Sorted: hidden has no reading order, and a stable wire beats an
        # authored one nobody reads.
        "hidden": ["created_at", "updated_at"],
    }


# ── 3. the projection ──────────────────────────────────────────────────────


def test_the_projection_reads_name_from_the_envelope_and_the_rest_from_spec():
    """``name`` is the instance's envelope identity — it is not a spec field
    on any Kind, and every list surface in the repo already treats it that
    way. Everything else resolves under ``spec``."""
    p = normalize_presentation(["name", "title", "status"])
    row = project_row(p, name="s-cards", spec={"title": "Cards", "status": "todo"})
    assert row == {"name": "s-cards", "title": "Cards", "status": "todo"}


def test_a_field_the_document_does_not_carry_projects_as_none():
    """Absent is reported, never invented. ``None`` is the honest answer and
    the surface decides how to print it."""
    p = normalize_presentation(["name", "title"])
    assert project_row(p, name="s-bare", spec={}) == {"name": "s-bare", "title": None}


# ── 4. a KIND declares it — builtin and tenant alike ───────────────────────


def test_the_story_descriptor_declares_its_presentation():
    """The builtin proof. Read through ``dna._yaml`` — the repo's one YAML
    seam; a raw ``yaml.safe_load`` here fails the loader ratchet."""
    raw = safe_load(
        (_SDK / "dna" / "extensions" / "sdlc" / "kinds" / "story.kind.yaml")
        .read_text(encoding="utf-8")
    )
    p = normalize_presentation(raw["spec"]["presentation"])
    assert [f.field for f in p.fields] == [
        "name", "title", "status", "feature", "priority",
    ]
    assert p.field_with_role("identifier").field == "name"
    assert p.field_with_role("status").field == "status"


def test_the_registered_story_port_exposes_it():
    from dna.kernel import Kernel

    k = Kernel.auto()
    port = k.kind_port_for("Story")
    p = presentation_of(port)
    assert p is not None, "the Story port lost its declared presentation"
    assert [f.label for f in p.fields] == [
        "Story", "Title", "Status", "Feature", "Priority",
    ]
    wire = presentation_wire(port)
    # ``display_label``/``ascii_icon`` are the Kind's, not the card's.
    assert wire["label"] == "Stories"
    assert wire["icon"] == port.ascii_icon


def test_a_kind_that_declares_none_reports_none():
    """Absence is meaningful — a surface falls back to its generic renderer
    rather than being handed an empty presentation that looks declared."""
    from dna.kernel import Kernel

    k = Kernel.auto()
    port = k.kind_port_for("ADR")
    assert presentation_of(port) is None
    assert presentation_wire(port) is None


def test_a_tenant_kind_definition_declares_it_in_the_same_words():
    """THE constraint. A presentation only a builtin extension could declare
    would make every tenant-authored Kind second-class, and the feature would
    serve nobody but us. A ``KindDefinition`` instance carries the identical
    block, through the identical normalizer, onto the identical port
    attribute."""
    from dna.kernel.meta import DeclarativeKindPort
    from dna.kernel.models import TypedKindDefinition

    doc = {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": "contrato"},
        "spec": {
            "target_api_version": "example.test/tenant/v1",
            "target_kind": "Contrato",
            "alias": "tenant-contrato",
            "origin": "example.test/tenant",
            "storage": {"type": "yaml", "container": "contratos"},
            "display_label": "Contratos",
            "presentation": {
                "fields": [
                    {"field": "name", "label": "Contrato", "role": "identifier"},
                    {"field": "parte", "role": "owner"},
                    {"field": "situacao", "label": "Situação", "role": "status"},
                ],
                "hidden": ["assinado_em"],
            },
        },
    }
    port = DeclarativeKindPort(TypedKindDefinition.from_raw(doc))
    p = presentation_of(port)
    assert [f.field for f in p.fields] == ["name", "parte", "situacao"]
    assert p.field_with_role("status").label == "Situação"
    assert p.hidden == frozenset({"assinado_em"})
    assert presentation_wire(port)["label"] == "Contratos"


def test_a_malformed_tenant_declaration_fails_at_load_not_at_render():
    from dna.kernel.models import KindDefinitionSpec

    with pytest.raises(ValueError, match="presentation"):
        KindDefinitionSpec.from_raw({
            "target_api_version": "example.test/tenant/v1",
            "target_kind": "Contrato",
            "alias": "tenant-contrato",
            "origin": "example.test/tenant",
            "storage": {"type": "yaml", "container": "contratos"},
            "presentation": {"fields": [{"field": "x", "role": "chip"}]},
        })


# ── 5. both schema copies stay byte-identical ──────────────────────────────


def test_the_two_kind_definition_schema_copies_are_byte_identical():
    canonical = (_REPO / "docs" / "schemas" / "kind-definition.schema.json")
    runtime = (_SDK / "dna" / "kernel" / "schemas" / "kind-definition.schema.json")
    assert canonical.read_bytes() == runtime.read_bytes()


def test_the_schema_declares_presentation_with_the_closed_role_vocabulary():
    """The JSON Schema is what a tenant's editor autocompletes against, so the
    role enum must be the SAME closed set the normalizer enforces — two lists
    that drift would let an instance validate and then fail to load."""
    schema = json.loads(
        (_SDK / "dna" / "kernel" / "schemas" / "kind-definition.schema.json")
        .read_text(encoding="utf-8")
    )
    pres = schema["properties"]["spec"]["properties"]["presentation"]
    entry = pres["properties"]["fields"]["items"]["anyOf"][1]
    assert set(entry["properties"]["role"]["enum"]) == PRESENTATION_ROLES
    assert entry["additionalProperties"] is False


# ── 6. provenance — the projection is DERIVED, not restated ────────────────


def test_list_stories_projects_the_fields_the_kind_declares(monkeypatch):
    """The false green this test is shaped to avoid: asserting that
    ``list_stories`` returns a ``status`` column passes whether that column
    came from the Story Kind or from a literal in the impl.

    So the Kind's declaration is CHANGED and the payload must change with it.
    A hardcoded projection cannot pass this."""
    import asyncio

    from dna.application import runtime as R
    from dna.kernel import Kernel

    kernel = Kernel.auto()
    port = kernel.kind_port_for("Story")

    class _Live:
        kernel = None

        def default_scope(self, tenant=None):
            return "s"

    live = _Live()
    live.kernel = kernel

    async def _one_story(scope, kind, tenant=None, **kw):
        yield {
            "metadata": {"name": "s-one"},
            "spec": {
                "title": "One", "status": "todo", "feature": "f-x",
                "priority": "high", "owner": "barna", "estimate": 3,
            },
        }
        return

    monkeypatch.setattr(kernel, "query", _one_story)

    baseline = asyncio.run(R.list_stories_impl(live))
    assert baseline["stories"][0] == {
        "name": "s-one", "title": "One", "status": "todo",
        "feature": "f-x", "priority": "high",
    }
    assert baseline["presentation"]["label"] == "Stories"

    # Re-declare the Kind: a different field set, a different order, a
    # different label. Nothing in the impl or the card knows these words.
    monkeypatch.setattr(port, "presentation", normalize_presentation({
        "fields": [
            {"field": "name", "label": "Ficha", "role": "identifier"},
            {"field": "owner", "role": "owner"},
            {"field": "estimate", "role": "metric"},
        ],
    }), raising=False)
    monkeypatch.setattr(port, "display_label", "Fichas", raising=False)

    changed = asyncio.run(R.list_stories_impl(live))
    assert changed["stories"][0] == {
        "name": "s-one", "owner": "barna", "estimate": 3,
    }, "the projection did not follow the Kind — it is still hardcoded"
    assert changed["presentation"]["label"] == "Fichas"
    assert [f["label"] for f in changed["presentation"]["fields"]] == [
        "Ficha", "Owner", "Estimate",
    ]


def test_list_stories_still_answers_for_a_kind_with_no_presentation(monkeypatch):
    """A Kind that declares nothing must keep working — the fallback is the
    projection that existed before this feature, not an empty row."""
    import asyncio

    from dna.application import runtime as R
    from dna.kernel import Kernel

    kernel = Kernel.auto()
    port = kernel.kind_port_for("Story")
    monkeypatch.setattr(port, "presentation", None, raising=False)

    class _Live:
        kernel = None

        def default_scope(self, tenant=None):
            return "s"

    live = _Live()
    live.kernel = kernel

    async def _one_story(scope, kind, tenant=None, **kw):
        yield {
            "metadata": {"name": "s-one"},
            "spec": {"title": "One", "status": "todo", "feature": "f-x",
                     "priority": "high"},
        }
        return

    monkeypatch.setattr(kernel, "query", _one_story)
    out = asyncio.run(R.list_stories_impl(live))
    assert out["stories"][0] == {
        "name": "s-one", "title": "One", "status": "todo",
        "feature": "f-x", "priority": "high",
    }
    assert out["presentation"] is None


# ── 7. the authored-Kind read carries it (the portal's consumer) ───────────


def test_the_authored_kind_projection_publishes_the_presentation():
    """``GET /v1/kinds/{kind}`` is the portal's read. Presentation belongs
    beside ``schema`` and ``traits`` for the same reason those two are there:
    it is part of what a reviewer would be conferring effect on."""
    from dna.application.kind_authoring import authored_kind_presentation

    assert authored_kind_presentation({
        "target_kind": "Contrato",
        "display_label": "Contratos",
        "presentation": {"fields": ["name", "situacao"]},
    }) == {
        "label": "Contratos",
        "icon": None,
        "fields": [
            {"field": "name", "label": "Name", "role": None},
            {"field": "situacao", "label": "Situacao", "role": None},
        ],
        "hidden": [],
    }
    assert authored_kind_presentation({"target_kind": "Contrato"}) is None


def test_a_stored_declaration_that_no_longer_normalizes_reads_as_none():
    """An instance stored before a validation tightened must not crash the
    audit read. It reports ``None`` — "this Kind declares no presentation I can
    read" — rather than half a declaration that looks authored."""
    from dna.application.kind_authoring import authored_kind_presentation

    assert authored_kind_presentation({
        "target_kind": "Contrato",
        "presentation": {"fields": [{"field": "x", "role": "chip"}]},
    }) is None


# ── 8. the ratchet: presentation stays OFF the runtime_checkable port ──────


def test_presentation_is_a_capability_never_a_requirement():
    """The ``is_runtime_artifact`` precedent: a member on the
    runtime_checkable ``KindPort`` starts being REQUIRED by the H1
    isinstance gate, which would un-register every minimal third-party Kind."""
    import typing

    from dna.kernel.protocols import KindPort, KindPresentation

    def members(cls):
        get = getattr(typing, "get_protocol_members", None)
        return set(get(cls)) if get else set(cls.__protocol_attrs__)

    assert "presentation" not in members(KindPort)
    assert "presentation" in members(KindPresentation)


def test_presentation_field_is_immutable():
    f = PresentationField(field="status", label="Status", role="status")
    with pytest.raises(Exception):
        f.field = "other"  # type: ignore[misc]
    assert isinstance(normalize_presentation(["a"]), Presentation)
