"""i-081 — the registration guards ask "taken WHERE THIS KIND WILL APPLY?".

The i-080 guards (duplicate alias, BUNDLE ``(container, marker)``, i-195 kind
NAME) compared a new port against every port in the process. Once a Kind is
bound to the scope that declared it, that comparison is wrong in both
directions:

* ACROSS scopes it refuses work it has no business refusing — one workspace
  taking the alias ``acme-deal`` would stop another workspace from registering
  its own Kind, in another scope, that the first can never see;
* WITHIN a scope it must keep biting, because there the collision is real.

The system-Kind protections are unchanged: a store-loaded Kind still cannot
claim a builtin's name (the builtin is global, so it is visible in EVERY scope)
and still loses a key a builtin descriptor owns.
"""
from __future__ import annotations

import logging

import pytest

from dna.kernel import Kernel
from dna.kernel.kinds import registry as registry_mod
from dna.kernel.kinds.registry import port_scopes

_A = "scope-a"
_B = "scope-b"


@pytest.fixture(autouse=True)
def _clear_process_wide_warn_caches():
    # All THREE process-wide warn caches, not two. _GLOBAL_UNAPPROVED_KIND_WARNED
    # arrived later (i-084) and only test_kind_approval_gate.py's copy of this
    # fixture was updated for it, which left every other file here able to burn
    # an approval-warning key that nothing in the file clears. No assertion
    # depends on that today, but it is precisely the shape of coupling that
    # makes a suite order-dependent — and under xdist "which file ran first"
    # stops being a property of the file listing (perf/testes-em-paralelo).
    registry_mod._AMBIGUOUS_LOOKUP_WARNED.clear()
    registry_mod._GLOBAL_KINDDEF_CONFLICT_WARNED.clear()
    registry_mod._GLOBAL_UNAPPROVED_KIND_WARNED.clear()
    yield
    registry_mod._AMBIGUOUS_LOOKUP_WARNED.clear()
    registry_mod._GLOBAL_KINDDEF_CONFLICT_WARNED.clear()
    registry_mod._GLOBAL_UNAPPROVED_KIND_WARNED.clear()


def kinddef(
    *, namespace: str, kind: str, alias: str, container: str | None = None,
    schema: dict | None = None, storage: dict | None = None,
) -> dict:
    """An APPROVED per-scope ``KindDefinition`` — approval is the precondition
    for reaching the scope binding this suite is about (an unapproved Kind
    never registers, so it binds to no scope at all)."""
    return {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": alias},
        "spec": {
            "target_api_version": f"{namespace}/v1",
            "target_kind": kind,
            "alias": alias,
            "origin": namespace,
            "storage": storage or {
                "type": "yaml", "container": container or alias + "s",
            },
            "schema": schema or {"type": "object"},
            "approved_by": "approver@example.com",
        },
    }


# ── across scopes: no false refusals ────────────────────────────────────────


def test_two_scopes_may_claim_the_same_alias():
    """An alias is unique per REGISTRY today; making it unique per PROCESS
    across tenants means the first workspace to boot decides which names the
    second may use."""
    k = Kernel()
    k._register_kind_definitions(
        [kinddef(namespace="acme.example", kind="Deal", alias="acme-deal")],
        scope=_A,
    )
    k._register_kind_definitions(
        [kinddef(namespace="acme.example", kind="Lead", alias="acme-lead")],
        scope=_B,
    )
    # scope-b claims the SAME alias for a Kind of its own.
    k._register_kind_definitions(
        [kinddef(namespace="acme.example", kind="Deal2", alias="acme-deal")],
        scope=_B,
    )
    assert k.kind_port_for("Deal2", scope=_B) is not None
    assert k.kind_port_for("Deal", scope=_A) is not None
    # …and each scope resolves the alias to its OWN Kind.
    assert k.resolve_dep_filter_target("acme-deal", scope=_A).kind == "Deal"
    assert k.resolve_dep_filter_target("acme-deal", scope=_B).kind == "Deal2"


def test_two_scopes_may_share_a_bundle_container_and_marker():
    bundle = {"type": "bundle", "container": "deals", "marker": "DEAL.yaml"}
    k = Kernel()
    k._register_kind_definitions(
        [kinddef(namespace="acme.example", kind="Deal", alias="acme-deal",
                 storage=dict(bundle))],
        scope=_A,
    )
    k._register_kind_definitions(
        [kinddef(namespace="globex.example", kind="GDeal", alias="globex-deal",
                 storage=dict(bundle))],
        scope=_B,
    )
    assert k.kind_port_for("GDeal", scope=_B) is not None
    assert k.kind_port_for("Deal", scope=_A) is not None


def test_two_scopes_may_use_the_same_kind_name():
    k = Kernel()
    k._register_kind_definitions(
        [kinddef(namespace="acme.example", kind="Widget", alias="acme-widget")],
        scope=_A,
    )
    k._register_kind_definitions(
        [kinddef(namespace="globex.example", kind="Widget", alias="globex-widget")],
        scope=_B,
    )
    assert k.kind_port_for("Widget", scope=_A).alias == "acme-widget"
    assert k.kind_port_for("Widget", scope=_B).alias == "globex-widget"


# ── within a scope: the guards still bite ───────────────────────────────────


def test_the_duplicate_alias_guard_still_bites_inside_one_scope(caplog):
    k = Kernel()
    k._register_kind_definitions(
        [kinddef(namespace="acme.example", kind="Deal", alias="acme-deal")],
        scope=_A,
    )
    with caplog.at_level(logging.WARNING):
        k._register_kind_definitions(
            [kinddef(namespace="acme.example", kind="Lead", alias="acme-deal")],
            scope=_A,
        )
    assert k.kind_port_for("Lead", scope=_A) is None
    assert "alias" in caplog.text


def test_the_bundle_marker_guard_still_bites_inside_one_scope(caplog):
    bundle = {"type": "bundle", "container": "deals", "marker": "DEAL.yaml"}
    k = Kernel()
    k._register_kind_definitions(
        [kinddef(namespace="acme.example", kind="Deal", alias="acme-deal",
                 storage=dict(bundle))],
        scope=_A,
    )
    with caplog.at_level(logging.WARNING):
        k._register_kind_definitions(
            [kinddef(namespace="acme.example", kind="Lead", alias="acme-lead",
                     storage=dict(bundle))],
            scope=_A,
        )
    assert k.kind_port_for("Lead", scope=_A) is None
    assert "marker" in caplog.text.lower()


def test_a_store_loaded_kind_still_cannot_claim_a_builtin_name_in_any_scope(caplog):
    """The builtin is GLOBAL, so it is visible from every scope — the i-195
    guard sees it wherever the tenant Kind tries to land."""
    from dna.extensions.helix import HelixExtension

    k = Kernel()
    k.load(HelixExtension())
    with caplog.at_level(logging.WARNING):
        k._register_kind_definitions(
            [kinddef(namespace="acme.example", kind="Agent", alias="acme-agent")],
            scope=_A,
        )
    assert ("acme.example/v1", "Agent") not in k._kinds
    assert k.kind_port_for("Agent", scope=_A).alias == "helix-agent"


def test_a_store_loaded_kind_still_loses_a_builtin_descriptors_key():
    from dna.extensions.doc import DocExtension

    k = Kernel()
    k.load(DocExtension())
    builtin = k.kind_port_for("Doc")
    k._register_kind_definitions([{
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": "doc"},
        "spec": {
            "target_api_version": builtin.api_version,
            "target_kind": "Doc",
            "alias": builtin.alias,
            "origin": "acme.example",
            "storage": {"type": "yaml", "container": "hijacked"},
            "schema": {"type": "object"},
            # Approved, so the builtin-wins branch is what refuses it — not
            # the approval gate (which would make this pass vacuously).
            "approved_by": "approver@example.com",
        },
    }], scope=_A)
    assert k.kind_port_for("Doc", scope=_A) is builtin
    assert builtin.storage.container != "hijacked"


# ── the binding itself ──────────────────────────────────────────────────────


def test_the_same_descriptor_in_two_scopes_is_one_port_governing_both():
    """Two scopes running the same published Kind must not need two ports —
    and the second scope must not be refused for claiming a taken key."""
    raw = kinddef(namespace="acme.example", kind="Deal", alias="acme-deal")
    k = Kernel()
    k._register_kind_definitions([dict(raw)], scope=_A)
    port = k.kind_port_for("Deal", scope=_A)
    k._register_kind_definitions([dict(raw)], scope=_B)
    assert k.kind_port_for("Deal", scope=_B) is port
    assert port_scopes(port) == frozenset({_A, _B})


def test_unregistering_from_one_scope_leaves_the_other_governed():
    raw = kinddef(namespace="acme.example", kind="Deal", alias="acme-deal")
    k = Kernel()
    k._register_kind_definitions([dict(raw)], scope=_A)
    k._register_kind_definitions([dict(raw)], scope=_B)

    k.unregister_kind("acme.example/v1", "Deal", scope=_A)
    assert k.kind_port_for("Deal", scope=_A) is None
    assert k.kind_port_for("Deal", scope=_B) is not None

    k.unregister_kind("acme.example/v1", "Deal", scope=_B)
    assert ("acme.example/v1", "Deal") not in k._kinds


def test_editing_a_shared_kind_in_one_scope_refuses_rather_than_diverging(caplog):
    """One key cannot hold two ports. When a second scope publishes DIFFERENT
    content under a key another scope already runs, the divergent scope gets NO
    Kind — never the other scope's schema."""
    v1 = kinddef(namespace="acme.example", kind="Deal", alias="acme-deal",
                 schema={"type": "object", "required": ["title"]})
    v2 = kinddef(namespace="acme.example", kind="Deal", alias="acme-deal",
                 schema={"type": "object", "required": ["title", "amount"]})
    k = Kernel()
    k._register_kind_definitions([dict(v1)], scope=_A)
    k._register_kind_definitions([dict(v1)], scope=_B)

    with caplog.at_level(logging.WARNING):
        k._register_kind_definitions([dict(v2)], scope=_B)
    assert k.kind_port_for("Deal", scope=_B) is None
    port_a = k.kind_port_for("Deal", scope=_A)
    assert port_a is not None
    assert "amount" not in port_a.schema()["required"]
    # The refusal must NAME the scope that still owns the key — "already
    # registered from a different descriptor" is unactionable when the other
    # descriptor lives in a scope the author cannot see.
    assert _A in caplog.text


def test_editing_a_kind_only_this_scope_runs_still_takes_effect_hot():
    """The i-080 item-3 hot edit is untouched for the ordinary single-scope
    case."""
    v1 = kinddef(namespace="acme.example", kind="Deal", alias="acme-deal",
                 schema={"type": "object", "required": ["title"]})
    v2 = kinddef(namespace="acme.example", kind="Deal", alias="acme-deal",
                 schema={"type": "object", "required": ["title", "amount"]})
    k = Kernel()
    k._register_kind_definitions([dict(v1)], scope=_A)
    k._register_kind_definitions([dict(v2)], scope=_A)
    assert "amount" in k.kind_port_for("Deal", scope=_A).schema()["required"]
