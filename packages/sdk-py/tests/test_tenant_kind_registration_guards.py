"""i-080 items 2, 3 and 5 — a store-loaded (tenant-authored) Kind faces the same
registration guards a builtin does, can be EDITED without restarting the
process, and never wins a lookup by accident of registration order.

Before this:

* ``register_kind_definitions`` wrote ``self._kinds[key] = port`` directly,
  bypassing ``register_kind()`` — so the duplicate-alias guard, the BUNDLE
  ``(container, marker)`` collision guard and the i-195 name-collision guard
  never ran for a Kind that came from the store. Only the plane lint did.
* the funnel short-circuited on an already-registered declarative key with a
  comment telling callers to "clear ``self._kinds[key]`` via the explicit
  unregister path" — a path that did not exist. Creating a Kind was hot;
  EDITING one required restarting the process.
* ``port_for`` with a bare name fell to ``matches[0]`` between two per-scope
  ports (registration order), and warned once per process per NAME — so in a
  long-lived container the second, different collision on that name was silent.
  ``by_container`` returned the first match with no warning at all.
"""
from __future__ import annotations

import logging

import pytest

from dna.kernel import Kernel
from dna.kernel.kinds import registry as registry_mod


@pytest.fixture(autouse=True)
def _clear_process_wide_warn_caches():
    """The registry's warn-once caches are module-level (deliberately — some
    call sites build fresh kernel-like wrappers). Tests must not inherit them
    from each other."""
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
    schema: dict | None = None, storage: dict | None = None, name: str | None = None,
) -> dict:
    """A per-scope ``KindDefinition`` document, as it arrives from the store —
    APPROVED, because that is the precondition for reaching the registration
    guards this suite is about. An unapproved one is refused before them (see
    ``test_kind_approval_gate.py``), which would make every assertion below
    pass for the wrong reason."""
    return {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": name or alias},
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


def _kernel_with(*raws) -> Kernel:
    k = Kernel()
    k._register_kind_definitions(list(raws))
    return k


# ── item 2: the guards a builtin faces now run for a store-loaded Kind ───────


def test_two_tenants_in_their_own_namespaces_both_register():
    """The whole point of namespacing ``api_version``: this must NOT be a
    collision. Guarded first so the guards below cannot pass by refusing
    everything."""
    k = _kernel_with(
        kinddef(namespace="acme.example", kind="Deal", alias="acme-deal"),
        kinddef(namespace="globex.example", kind="Deal", alias="globex-deal"),
    )
    assert k.kind_port_for("Deal", api_version="acme.example/v1") is not None
    assert k.kind_port_for("Deal", api_version="globex.example/v1") is not None


def test_store_loaded_kind_faces_the_duplicate_alias_guard(caplog):
    """An alias is the globally-unique wire key of ``dep_filters`` and
    ``LayerPolicy``. A second Kind claiming a taken one used to register
    silently, leaving ``alias_for`` to pick one of them."""
    k = _kernel_with(
        kinddef(namespace="acme.example", kind="Deal", alias="acme-deal"),
    )
    with caplog.at_level(logging.WARNING):
        k._register_kind_definitions([
            kinddef(namespace="globex.example", kind="Lead", alias="acme-deal"),
        ])
    assert ("globex.example/v1", "Lead") not in k._kinds
    assert "alias" in caplog.text
    # the first claimant keeps it
    assert k._kindreg.resolve_dep_filter_target("acme-deal").kind == "Deal"


def test_store_loaded_kind_faces_the_bundle_marker_guard(caplog):
    bundle = {"type": "bundle", "container": "deals", "marker": "DEAL.yaml"}
    k = _kernel_with(
        kinddef(namespace="acme.example", kind="Deal", alias="acme-deal",
                storage=bundle),
    )
    with caplog.at_level(logging.WARNING):
        k._register_kind_definitions([
            kinddef(namespace="globex.example", kind="Deal", alias="globex-deal",
                    storage=dict(bundle)),
        ])
    assert ("globex.example/v1", "Deal") not in k._kinds
    assert "marker" in caplog.text.lower()


def test_store_loaded_kind_faces_the_name_collision_guard(caplog):
    """i-195: a tenant Kind may not reuse a BUILTIN Kind's name under its own
    namespace — every bare-name lookup for it would resolve to the builtin, so
    the Kind would be unreachable by name."""
    from dna.extensions.helix import HelixExtension

    k = Kernel()
    k.load(HelixExtension())
    with caplog.at_level(logging.WARNING):
        k._register_kind_definitions([
            kinddef(namespace="acme.example", kind="Agent", alias="acme-agent"),
        ])
    assert ("acme.example/v1", "Agent") not in k._kinds
    assert "Agent" in caplog.text
    # the builtin is untouched
    assert k.kind_port_for("Agent").alias == "helix-agent"


def test_a_refused_store_loaded_kind_never_takes_the_boot_down():
    """The per-scope funnel's standing contract: warn + skip, never raise —
    routing through ``register_kind`` must not change it."""
    k = _kernel_with(
        kinddef(namespace="acme.example", kind="Deal", alias="acme-deal"),
    )
    seen = []
    k.on("parse_error", lambda ctx: seen.append(ctx.data.get("error")))
    k._register_kind_definitions([
        kinddef(namespace="globex.example", kind="Lead", alias="acme-deal"),
    ])
    assert seen and "alias" in seen[0]


def test_a_store_loaded_kind_still_faces_the_plane_lint():
    """The one guard that already ran here keeps running."""
    raw = kinddef(namespace="acme.example", kind="Deal", alias="acme-deal")
    raw["spec"]["plane"] = "record"
    raw["spec"]["prompt_target"] = True
    k = _kernel_with(raw)
    assert ("acme.example/v1", "Deal") not in k._kinds


# ── item 3: editing a tenant Kind, hot ──────────────────────────────────────


_V1 = {"type": "object", "required": ["title"],
       "properties": {"title": {"type": "string"}}}
_V2 = {"type": "object", "required": ["title", "amount"],
       "properties": {"title": {"type": "string"},
                      "amount": {"type": "number"}}}


def test_editing_a_tenant_kinds_schema_takes_effect_without_restarting():
    k = _kernel_with(
        kinddef(namespace="acme.example", kind="Deal", alias="acme-deal",
                schema=_V1),
    )
    port = k.kind_port_for("Deal", api_version="acme.example/v1")
    assert "amount" not in port.schema().get("required", [])

    k._register_kind_definitions([
        kinddef(namespace="acme.example", kind="Deal", alias="acme-deal",
                schema=_V2),
    ])
    port2 = k.kind_port_for("Deal", api_version="acme.example/v1")
    assert port2 is not port
    assert "amount" in port2.schema()["required"]


def test_an_identical_descriptor_is_still_an_idempotent_no_op():
    """Re-registering the SAME descriptor must not churn the port — the
    rebuild cost is why the short-circuit exists."""
    raw = kinddef(namespace="acme.example", kind="Deal", alias="acme-deal",
                  schema=_V1)
    k = _kernel_with(raw)
    port = k.kind_port_for("Deal", api_version="acme.example/v1")
    k._register_kind_definitions([dict(raw)])
    assert k.kind_port_for("Deal", api_version="acme.example/v1") is port


def test_a_per_scope_edit_never_replaces_a_builtin_descriptor():
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
        },
    }])
    assert k.kind_port_for("Doc") is builtin


def test_unregister_kind_removes_the_port_and_its_generic_reader_writer():
    k = _kernel_with(
        kinddef(namespace="acme.example", kind="Deal", alias="acme-deal",
                storage={"type": "bundle", "container": "deals",
                         "marker": "DEAL.yaml"}),
    )
    assert any(getattr(r, "_kind", None) == "Deal" for r in k._readers)
    assert any(getattr(w, "_kind", None) == "Deal" for w in k._writers)

    removed = k.unregister_kind("acme.example/v1", "Deal")
    assert removed is not None
    assert k.kind_port_for("Deal", api_version="acme.example/v1") is None
    assert not any(getattr(r, "_kind", None) == "Deal" for r in k._readers)
    assert not any(getattr(w, "_kind", None) == "Deal" for w in k._writers)


def test_unregister_kind_is_idempotent():
    k = Kernel()
    assert k.unregister_kind("acme.example/v1", "Nope") is None


# ── item 5a: a bare name between two tenant ports ───────────────────────────


def _both_orders(a, b):
    return (
        _kernel_with(a, b).kind_port_for("Deal"),
        _kernel_with(b, a).kind_port_for("Deal"),
    )


def test_bare_lookup_between_two_tenant_ports_ignores_registration_order():
    a = kinddef(namespace="zebra.example", kind="Deal", alias="zebra-deal")
    b = kinddef(namespace="acme.example", kind="Deal", alias="acme-deal")
    first, second = _both_orders(a, b)
    assert first.api_version == second.api_version == "acme.example/v1"


def test_extension_ports_still_beat_per_scope_ones_on_a_bare_name():
    from dna.extensions.doc import DocExtension

    k = Kernel()
    k.load(DocExtension())
    builtin = k.kind_port_for("Doc")
    k._register_kind_definitions([
        kinddef(namespace="aaa.example", kind="Doc", alias="aaa-doc"),
    ])
    # the i-195 guard refuses the shadow outright; whatever survives, the
    # builtin must still be what a bare name resolves to.
    assert k.kind_port_for("Doc") is builtin


def test_a_second_collision_on_the_same_name_is_not_silent(caplog):
    """The hole: the warning was cached by NAME, so once ``Deal`` had warned,
    a THIRD tenant colliding on ``Deal`` never produced a line again."""
    k = _kernel_with(
        kinddef(namespace="acme.example", kind="Deal", alias="acme-deal"),
        kinddef(namespace="globex.example", kind="Deal", alias="globex-deal"),
    )
    with caplog.at_level(logging.WARNING):
        k.kind_port_for("Deal")
        first = caplog.text.count("Ambiguous bare kind-name lookup")
        k.kind_port_for("Deal")  # same ambiguity — stays quiet
        assert caplog.text.count("Ambiguous bare kind-name lookup") == first == 1

        k._register_kind_definitions([
            kinddef(namespace="initech.example", kind="Deal", alias="initech-deal"),
        ])
        k.kind_port_for("Deal")
        assert caplog.text.count("Ambiguous bare kind-name lookup") == 2


# ── item 5b: two tenants storing in the same container ──────────────────────


def test_by_container_ignores_registration_order():
    a = kinddef(namespace="zebra.example", kind="ZDeal", alias="zebra-deal",
                container="deals")
    b = kinddef(namespace="acme.example", kind="ADeal", alias="acme-deal",
                container="deals")
    assert (
        _kernel_with(a, b).kind_by_container("deals")
        == _kernel_with(b, a).kind_by_container("deals")
        == "ADeal"
    )


def test_by_container_says_so_when_the_container_is_ambiguous(caplog):
    k = _kernel_with(
        kinddef(namespace="acme.example", kind="ADeal", alias="acme-deal",
                container="deals"),
        kinddef(namespace="globex.example", kind="GDeal", alias="globex-deal",
                container="deals"),
    )
    with caplog.at_level(logging.WARNING):
        k.kind_by_container("deals")
    assert "deals" in caplog.text and "ambiguous" in caplog.text.lower()


def test_by_container_is_unchanged_for_the_ordinary_case():
    from dna.extensions.helix import HelixExtension
    from dna.extensions.agentskills import AgentSkillsExtension

    k = Kernel()
    k.load(HelixExtension())
    k.load(AgentSkillsExtension())
    assert k.kind_by_container("agents") == "Agent"
    assert k.kind_by_container("skills") == "Skill"
    assert k.kind_by_container("does-not-exist") is None
    assert k.kind_by_container("") is None
