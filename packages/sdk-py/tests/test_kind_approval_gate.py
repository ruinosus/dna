"""An unapproved Kind never enters the registry — so it has no effect at all.

Registration is what CONFERS behaviour: a registered Kind validates documents
against its schema and routes their storage; an unregistered one does neither
(measured — an unknown Kind's documents are accepted unvalidated). So refusing
registration is not a soft gate, it is the absence of effect.
"""
from __future__ import annotations

from typing import Any

import pytest

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.extensions.helix import HelixExtension
from dna.extensions.kinddef import KindDefinitionExtension
from dna.kernel import Kernel
from dna.kernel.kinds import registry as registry_mod


@pytest.fixture(autouse=True)
def _clear_process_wide_warn_caches():
    """The approval refusal is warned ONCE per (scope, apiVersion, kind) per
    PROCESS (i-084), and a pytest session is one process — so without this the
    log tests below would depend on which sibling test ran first and burned the
    key. Same fixture, same reason, as ``test_tenant_kind_scope_isolation.py``.
    """
    registry_mod._GLOBAL_UNAPPROVED_KIND_WARNED.clear()
    registry_mod._GLOBAL_KINDDEF_CONFLICT_WARNED.clear()
    registry_mod._AMBIGUOUS_LOOKUP_WARNED.clear()
    yield
    registry_mod._GLOBAL_UNAPPROVED_KIND_WARNED.clear()
    registry_mod._GLOBAL_KINDDEF_CONFLICT_WARNED.clear()
    registry_mod._AMBIGUOUS_LOOKUP_WARNED.clear()


@pytest.fixture
def kernel_with_scope(tmp_path):
    """A writable Kernel over a filesystem scope — the store an authored
    ``KindDefinition`` really arrives from."""
    scope = "test-scope"
    scope_dir = tmp_path / scope
    scope_dir.mkdir(parents=True)
    (scope_dir / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\n"
        f"metadata:\n  name: {scope}\n"
        "spec: {}\n"
    )

    k = Kernel()
    k.load(HelixExtension())
    k.load(KindDefinitionExtension())
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))
    k.cache(FilesystemCache(str(tmp_path)))
    return k, scope


async def _write_kinddef(
    k: Kernel, scope: str, *, kind: str, approved: bool,
) -> None:
    """Author a ``KindDefinition`` into ``scope``'s store, approved or not.

    Same shape as the descriptors in ``test_kinddef.py``, written through the
    real write path so the document reaches the registration funnel exactly as
    an authored one would."""
    spec: dict[str, Any] = {
        "target_api_version": "example.com/v1",
        "target_kind": kind,
        "alias": f"example-{kind.lower()}",
        "origin": "example.com",
        "schema": {"type": "object", "additionalProperties": True},
        "storage": {
            "type": "bundle",
            "container": f"{kind.lower()}s",
            "marker": f"{kind.upper()}.md",
        },
    }
    if approved:
        spec["approved_by"] = "reviewer@example.com"
        spec["approved_at"] = "2026-07-25T12:00:00Z"
    await k.write_document(
        scope,
        "KindDefinition",
        kind.lower(),
        {
            "apiVersion": "github.com/ruinosus/dna/core/v1",
            "kind": "KindDefinition",
            "metadata": {"name": kind.lower()},
            "spec": spec,
        },
    )


@pytest.mark.asyncio
async def test_an_unapproved_kind_is_not_registered(kernel_with_scope):
    k, scope = kernel_with_scope
    await _write_kinddef(k, scope, kind="Widget", approved=False)
    await k.instance_async(scope)

    assert k.kind_port_for("Widget", scope=scope) is None, (
        "an unapproved KindDefinition must not register: registration is what "
        "gives a Kind schema enforcement and storage routing"
    )


@pytest.mark.asyncio
async def test_approval_is_what_registers_it(kernel_with_scope):
    k, scope = kernel_with_scope
    await _write_kinddef(k, scope, kind="Widget", approved=True)
    await k.instance_async(scope)

    port = k.kind_port_for("Widget", scope=scope)
    assert port is not None, "an approved Kind registers normally"
    assert port.kind == "Widget"


@pytest.mark.asyncio
async def test_the_refusal_is_logged_not_silent(kernel_with_scope, caplog):
    """A Kind that vanishes without a word is a support ticket."""
    k, scope = kernel_with_scope
    await _write_kinddef(k, scope, kind="Widget", approved=False)
    await k.instance_async(scope)

    assert any("Widget" in r.message and "approv" in r.message.lower()
               for r in caplog.records), (
        "the skip must name the Kind and the reason — the author has to be able "
        "to find out why their Kind does nothing"
    )


def test_the_scopeless_funnel_is_not_exempt(caplog):
    """Pins a decision that would otherwise be silently reversible.

    Exempting ``scope=None`` from the gate looks harmless — it reads like "the
    in-process caller owns the whole process, so it may register what it likes".
    It is not: ``scope=None`` is the funnel every in-process caller reaches, so
    the exemption would be a real bypass, and one nothing else here would catch,
    because every OTHER test in this file hands the funnel a real scope. This
    test is the fence: it drives the scope-less funnel directly and asserts the
    unapproved Kind still does not register.

    The raw document must be otherwise VALID (a real ``storage`` block, same
    shape as ``_write_kinddef`` below) — if it isn't, ``TypedKindDefinition
    .from_raw`` dies in the parse branch before the gate is ever reached, and
    the outcome (``kind_port_for`` returns ``None``) is then true for the wrong
    reason: a parse failure looks identical to an approval refusal from the
    outside. So the test also asserts on the LOG, not just the outcome — the
    only way to tell the two apart is the reason the refusal was logged for."""
    k = Kernel()
    k.load(HelixExtension())
    k.load(KindDefinitionExtension())

    raw = {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": "widget"},
        "spec": {
            "target_api_version": "example.com/v1",
            "target_kind": "Widget",
            "alias": "example-widget",
            "origin": "example.com",
            "schema": {"type": "object", "additionalProperties": True},
            "storage": {
                "type": "bundle",
                "container": "widgets",
                "marker": "WIDGET.md",
            },
        },
    }
    k._register_kind_definitions([raw])  # scope=None — the in-process funnel

    assert k.kind_port_for("Widget") is None, (
        "the gate must not be scoped-only: an unapproved Kind handed straight "
        "to the scope-less funnel registers nothing either"
    )
    assert any("Widget" in r.message and "approv" in r.message.lower()
               for r in caplog.records), (
        "the outcome must come from the APPROVAL refusal, not a parse "
        "failure — a missing/invalid 'storage' block would also leave "
        "kind_port_for() returning None, but for an unrelated reason, and "
        "this fence would then pass even if the scope=None exemption crept "
        "back in"
    )


# ── The refusal is loud ONCE, not loud forever (i-084) ──
#
# The three tests above pin that the refusal is AUDIBLE. These pin that it is
# BOUNDED, which after the authoring route is the other half of the same
# requirement: "authored but not approved" is a state a tenant creates by
# design, so it is a resting state, and an undeduped line about a resting state
# is one WARNING per MI rebuild per scope, forever, per tenant — on the hot path
# the lazy boot walks. Neither half may be traded for the other: a suppression
# that also silences the FIRST occurrence, or a NEW refusal, breaks the tests
# above or the two below respectively.


def _raw_kinddef(kind: str, *, api_version: str = "example.com/v1") -> dict[str, Any]:
    """An unapproved ``KindDefinition`` raw doc — otherwise valid, so the funnel
    reaches the approval gate rather than dying in the parse branch."""
    return {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": kind.lower()},
        "spec": {
            "target_api_version": api_version,
            "target_kind": kind,
            "alias": f"example-{kind.lower()}",
            "origin": "example.com",
            "schema": {"type": "object", "additionalProperties": True},
            "storage": {
                "type": "bundle",
                "container": f"{kind.lower()}s",
                "marker": f"{kind.upper()}.md",
            },
        },
    }


def _refusals(caplog, needle: str) -> list[str]:
    return [r.message for r in caplog.records
            if needle in r.message and "approv" in r.message.lower()]


def test_the_refusal_is_warned_once_per_process_not_once_per_rebuild(caplog):
    """Ten rebuilds, one line. Every MI build re-runs this funnel over the same
    documents, so an undeduped refusal scales with UPTIME rather than with
    events — and the event here (a Kind waiting for approval) does not recur, it
    persists."""
    k = Kernel()
    k.load(HelixExtension())
    k.load(KindDefinitionExtension())

    for _ in range(10):
        k._register_kind_definitions([_raw_kinddef("Widget")], scope="scope-a")

    assert k.kind_port_for("Widget", scope="scope-a") is None, (
        "the suppression is about the LOG only — the gate itself still refuses "
        "every time, or a second pass would register what the first refused"
    )
    assert len(_refusals(caplog, "Widget")) == 1, (
        "the refusal must be warned once per process, not once per MI rebuild"
    )


def test_a_second_scopes_refusal_is_still_audible(caplog):
    """The key is the EVENT, not the Kind name (the i-080 item 5 lesson that
    shaped ``_AMBIGUOUS_LOOKUP_WARNED``). Keyed by name alone, the first
    tenant's unapproved ``Widget`` would silence every LATER tenant's for the
    life of a long-lived container — which is precisely when a second tenant
    arrives, and precisely the author who cannot then find out why their Kind
    does nothing."""
    k = Kernel()
    k.load(HelixExtension())
    k.load(KindDefinitionExtension())

    k._register_kind_definitions([_raw_kinddef("Widget")], scope="scope-a")
    k._register_kind_definitions([_raw_kinddef("Widget")], scope="scope-b")
    k._register_kind_definitions(
        [_raw_kinddef("Widget", api_version="other.com/v1")], scope="scope-a",
    )

    messages = _refusals(caplog, "Widget")
    assert len(messages) == 3, (
        "a different scope — and a same-named Kind from a different apiVersion "
        "— are DIFFERENT refusals and must each be heard once"
    )
    assert any("'scope-b'" in m for m in messages), (
        "the second tenant's refusal must name the second tenant's scope"
    )


def test_both_doors_share_one_suppression(caplog):
    """The two store-loaded doors move together. They already fail closed
    identically; if only one of them deduped, the same Kind would be silent at
    one door and repeat forever at the other — a difference in the log that
    reflects nothing about the Kind, only about which door its author used."""
    k = Kernel()
    k.load(HelixExtension())
    k.load(KindDefinitionExtension())

    k._register_kind_definitions([_raw_kinddef("Widget")], scope="scope-a")
    k._register_custom_kinds(
        {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Genome",
            "metadata": {"name": "root"},
            "spec": {"custom_kinds": [
                {"apiVersion": "example.com/v1", "kind": "Widget",
                 "alias": "example-widget"},
            ]},
        },
        scope="scope-a",
    )

    assert len(_refusals(caplog, "Widget")) == 1, (
        "one Kind, one scope, one refusal — the door it arrived through is not "
        "part of the event"
    )
    assert ("example.com/v1", "Widget") not in k._kinds, (
        "and the second door still refuses it — sharing the cache must not "
        "share an exemption"
    )


# ── The same gate on the OTHER store-loaded registration path ──
#
# ``Module.spec.custom_kinds`` is the second way a Kind arrives from a store:
# whoever can write a scope's ROOT document declares Kinds there, and the
# entries go through ``register_custom_kinds`` instead of the KindDefinition
# funnel. Ungated, the feature's central claim ("não aprovado não tem efeito,
# mecanicamente") would be false process-wide — the gate would only cover the
# door the author did not have to use.


def _manifest(*entries: dict[str, Any]) -> dict[str, Any]:
    """A root document declaring ``custom_kinds`` — the shape
    ``instance_builder`` hands ``_register_custom_kinds`` on every build."""
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": "root"},
        "spec": {"custom_kinds": list(entries)},
    }


def _entry(kind: str, *, approved: bool) -> dict[str, Any]:
    e: dict[str, Any] = {
        "apiVersion": "myco.io/v1",
        "kind": kind,
        "alias": f"myco-{kind.lower()}",
    }
    if approved:
        e["approved_by"] = "reviewer@example.com"
        e["approved_at"] = "2026-07-25T12:00:00Z"
    return e


def test_an_unapproved_custom_kind_entry_is_not_registered():
    k = Kernel()
    k._register_custom_kinds(_manifest(_entry("Pipeline", approved=False)),
                             scope="test-scope")

    assert ("myco.io/v1", "Pipeline") not in k._kinds, (
        "a custom_kinds entry is a Kind declaration loaded from a store — it "
        "needs the same approval as a KindDefinition, or the root document is "
        "an ungated door onto the same registry"
    )
    assert k.kind_port_for("Pipeline", scope="test-scope") is None


def test_an_approved_custom_kind_entry_registers():
    k = Kernel()
    k._register_custom_kinds(_manifest(_entry("Pipeline", approved=True)),
                             scope="test-scope")

    port = k.kind_port_for("Pipeline", scope="test-scope")
    assert port is not None, "an approved custom kind registers normally"
    assert port.alias == "myco-pipeline"


def test_a_partly_approved_manifest_registers_exactly_the_approved_entries():
    """The gate is PER ENTRY: the entry is the Kind declaration, so one
    unapproved sibling must not hold back the approved ones (nor the reverse)."""
    k = Kernel()
    k._register_custom_kinds(
        _manifest(_entry("Pipeline", approved=True),
                  _entry("Stage", approved=False)),
        scope="test-scope",
    )

    assert k.kind_port_for("Pipeline", scope="test-scope") is not None
    assert k.kind_port_for("Stage", scope="test-scope") is None


def test_an_unapproved_entry_does_not_widen_an_existing_binding():
    """The gate runs BEFORE the already-registered early-return, or an
    unapproved entry would still scope-bind a Kind another scope approved —
    conferring that Kind's schema enforcement and storage routing here."""
    k = Kernel()
    k._register_custom_kinds(_manifest(_entry("Pipeline", approved=True)),
                             scope="scope-a")
    k._register_custom_kinds(_manifest(_entry("Pipeline", approved=False)),
                             scope="scope-b")

    assert k.kind_port_for("Pipeline", scope="scope-a") is not None
    assert k.kind_port_for("Pipeline", scope="scope-b") is None, (
        "binding is registration for a scope that had none — an unapproved "
        "entry must not acquire it via the conflict early-return"
    )


def test_a_non_string_approved_by_does_not_register():
    """A truthy non-string ``approved_by`` must not approve the entry.

    This door has no schema (unlike the ``KindDefinition`` funnel, where
    ``spec.approved_by`` is typed ``["string", "null"]``), so it is the one
    place a naive ``str(...)`` coercion around the read would fail OPEN:
    ``str({'name': 'Jane'})`` and ``str(True)`` are both non-empty strings, so
    ordinary — not adversarial — YAML like::

        custom_kinds:
          - kind: Pipeline
            approved_by:
              name: Jane
              at: 2026-01-01

    would register under a ``str()`` reading. It must not: only a real,
    non-blank string names someone."""
    k = Kernel()
    dict_entry = _entry("PipelineDict", approved=False)
    dict_entry["approved_by"] = {"name": "Jane", "at": "2026-01-01"}
    bool_entry = _entry("PipelineBool", approved=False)
    bool_entry["approved_by"] = True
    int_entry = _entry("PipelineInt", approved=False)
    int_entry["approved_by"] = 7

    k._register_custom_kinds(
        _manifest(dict_entry, bool_entry, int_entry), scope="test-scope",
    )

    assert k.kind_port_for("PipelineDict", scope="test-scope") is None, (
        "a dict approved_by must not register — only a string names someone"
    )
    assert k.kind_port_for("PipelineBool", scope="test-scope") is None, (
        "approved_by: true must not register — it names no one"
    )
    assert k.kind_port_for("PipelineInt", scope="test-scope") is None, (
        "a numeric approved_by must not register — it names no one"
    )


def test_the_custom_kind_refusal_is_logged_not_silent(caplog):
    k = Kernel()
    k._register_custom_kinds(_manifest(_entry("Pipeline", approved=False)),
                             scope="test-scope")

    assert any("Pipeline" in r.message and "approv" in r.message.lower()
               for r in caplog.records), (
        "same reason as the KindDefinition refusal: a Kind that does nothing "
        "has to be explainable to its author"
    )
