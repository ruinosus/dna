"""The DEEP-MERGE property of ``merge_field_level``, pinned on its own.

Why this file exists: the 2026-07-21 anatomy audit (i-043) found that the
function whose docstring promised *"Deep-merge spec dicts"* actually did
``merged_spec[k] = v`` per TOP-LEVEL key — an inherited ``spec.config.model``
was erased wholesale by a local ``spec.config.temperature``, and
``contributions_by_field`` could only ever name top-level keys. These tests
pin the repaired contract as properties of the system:

* **Nested fields from different layers COEXIST.** Overriding one leaf of a
  subtree must not evaporate its siblings.
* **Provenance tells the truth at leaf granularity.** Every final leaf maps
  to the scope that actually set it — including leaves inside subtrees.
* **Lists are atomic.** A higher-priority list replaces a lower one wholesale
  — the SAME semantics as ``layer_resolver.deep_merge``, so the composition
  resolver and the overlay engine never disagree about what a list merge
  means.
* **Provenance never points at fields that no longer exist** (a subtree
  replaced by a scalar purges its descendants' records).

Unit-level, calling the pure function directly — no kernel, no source,
nothing a resolver refactor can move out from under them.
"""
from __future__ import annotations

from dna.kernel.compose.layer_resolver import deep_merge
from dna.kernel.query.resolver import ResolutionLayer, merge_field_level


def _layer(scope: str) -> ResolutionLayer:
    return ResolutionLayer(scope=scope, tenant=None, found=True)


def _doc(spec: dict) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Agent",
        "metadata": {"name": "jarvis"},
        "spec": spec,
    }


# ── baseline (so the deep-merge properties below are not vacuous) ──────────


def test_flat_specs_still_merge_per_field():
    """Anti-vacuity baseline: the ORIGINAL contract (flat per-field shadowing
    with top-level provenance) must keep answering exactly as before. If this
    fails, the deep-merge fix changed behavior it had no business changing."""
    merged, primary, fields = merge_field_level([
        (_layer("app"), _doc({"model": "gpt-5.4"})),
        (_layer("_lib"), _doc({"model": "gpt-5", "persona": "jarvis-style"})),
    ])
    assert merged["spec"] == {"model": "gpt-5.4", "persona": "jarvis-style"}
    assert primary.scope == "app"
    assert fields == {"spec.model": "app", "spec.persona": "_lib"}


# ── THE audit finding: nested fields must survive a sibling override ────────


def test_a_nested_override_does_not_erase_its_siblings():
    """THE i-043 property. A local ``spec.config.temperature`` must not
    delete the inherited ``spec.config.model`` — before the fix, the local
    ``config`` dict replaced the inherited one wholesale."""
    merged, _, _ = merge_field_level([
        (_layer("app"), _doc({"config": {"temperature": 0.2}})),
        (_layer("_lib"), _doc({"config": {"model": "gpt-5", "temperature": 0.7}})),
    ])
    assert merged["spec"]["config"] == {"model": "gpt-5", "temperature": 0.2}


def test_provenance_is_recorded_at_leaf_paths_not_containers():
    """The provenance the docstring promises: each final LEAF names the scope
    that set it — ``spec.config.model ← _lib`` next to
    ``spec.config.temperature ← app``, inside the same subtree."""
    _, _, fields = merge_field_level([
        (_layer("app"), _doc({"config": {"temperature": 0.2}})),
        (_layer("_lib"), _doc({"config": {"model": "gpt-5", "temperature": 0.7}})),
    ])
    assert fields["spec.config.model"] == "_lib"
    assert fields["spec.config.temperature"] == "app"
    # The container itself is not a leaf — it must not shadow its children.
    assert "spec.config" not in fields


def test_deep_nesting_merges_at_every_level():
    """The merge recurses arbitrarily deep, not just one level down."""
    merged, _, fields = merge_field_level([
        (_layer("app"), _doc({"a": {"b": {"c": 1}}})),
        (_layer("_lib"), _doc({"a": {"b": {"d": 2}, "e": 3}})),
    ])
    assert merged["spec"] == {"a": {"b": {"c": 1, "d": 2}, "e": 3}}
    assert fields == {"spec.a.b.c": "app", "spec.a.b.d": "_lib", "spec.a.e": "_lib"}


# ── lists are atomic — the ONE list semantics both engines share ────────────


def test_lists_replace_wholesale_exactly_like_layer_resolver_deep_merge():
    """Lists are replaced, never concatenated or element-merged — and the
    answer must be the SAME one ``layer_resolver.deep_merge`` gives, so the
    composition resolver and the overlay engine cannot drift apart."""
    lib_spec = {"tools": ["search", "calc"], "config": {"model": "gpt-5"}}
    app_spec = {"tools": ["browse"]}

    merged, _, fields = merge_field_level([
        (_layer("app"), _doc(app_spec)),
        (_layer("_lib"), _doc(lib_spec)),
    ])
    assert merged["spec"]["tools"] == ["browse"]
    assert merged["spec"]["config"] == {"model": "gpt-5"}
    assert fields["spec.tools"] == "app"

    # The overlay engine agrees byte-for-byte on the same inputs.
    assert deep_merge(lib_spec, app_spec) == merged["spec"]


# ── provenance hygiene when subtrees are replaced ──────────────────────────


def test_replacing_a_subtree_with_a_scalar_purges_stale_leaf_provenance():
    """When a higher layer replaces ``spec.config`` (a dict) with a scalar,
    provenance must not keep pointing at ``spec.config.model`` — a field
    that no longer exists in the merged doc."""
    merged, _, fields = merge_field_level([
        (_layer("app"), _doc({"config": "disabled"})),
        (_layer("_lib"), _doc({"config": {"model": "gpt-5"}})),
    ])
    assert merged["spec"]["config"] == "disabled"
    assert fields["spec.config"] == "app"
    assert "spec.config.model" not in fields


def test_replacing_a_scalar_with_a_subtree_drops_the_stale_leaf_record():
    """The mirror case: a higher layer turns ``spec.config`` from a scalar
    into a dict — the old scalar record must not survive alongside the new
    leaf records."""
    merged, _, fields = merge_field_level([
        (_layer("app"), _doc({"config": {"model": "local"}})),
        (_layer("_lib"), _doc({"config": "off"})),
    ])
    assert merged["spec"]["config"] == {"model": "local"}
    assert fields == {"spec.config.model": "app"}


def test_empty_dict_contribution_is_recorded_at_its_container_path():
    """An empty-dict leaf is still a contribution — it must appear in
    provenance (documented edge case, not an accident)."""
    merged, _, fields = merge_field_level([
        (_layer("app"), _doc({"config": {}})),
    ])
    assert merged["spec"]["config"] == {}
    assert fields == {"spec.config": "app"}


# ── the merged doc is not a window into the source cache ───────────────────


def test_merged_doc_does_not_alias_the_input_layer_docs():
    """Mutating the merged result must never write through into the raw
    layer documents (which come from the kernel's granular cache)."""
    lib_raw = _doc({"config": {"model": "gpt-5"}, "tools": ["search"]})
    merged, _, _ = merge_field_level([(_layer("_lib"), lib_raw)])
    merged["spec"]["config"]["model"] = "tampered"
    merged["spec"]["tools"].append("tampered")
    assert lib_raw["spec"]["config"]["model"] == "gpt-5"
    assert lib_raw["spec"]["tools"] == ["search"]


# ── unchanged edges (the fix must not move these answers) ───────────────────


def test_all_none_contributions_still_resolve_to_nothing():
    merged, primary, fields = merge_field_level([
        (_layer("app"), None),
        (_layer("_lib"), None),
    ])
    assert merged is None and primary is None and fields == {}


def test_envelope_and_metadata_still_come_from_the_primary_layer():
    """Highest-priority hit stays the semantic owner of apiVersion / kind /
    metadata — deep merge applies to spec ONLY."""
    merged, primary, _ = merge_field_level([
        (_layer("app"), {
            "apiVersion": "v2", "kind": "Agent",
            "metadata": {"name": "jarvis", "labels": {"origin": "app"}},
            "spec": {"model": "local"},
        }),
        (_layer("_lib"), {
            "apiVersion": "v1", "kind": "Agent",
            "metadata": {"name": "jarvis", "labels": {"origin": "lib"}},
            "spec": {"persona": "calm"},
        }),
    ])
    assert primary.scope == "app"
    assert merged["apiVersion"] == "v2"
    assert merged["metadata"]["labels"] == {"origin": "app"}
    # ...while spec still deep-merges across layers.
    assert merged["spec"] == {"model": "local", "persona": "calm"}
