"""The LOUD-FALLBACK + DECLARED-LOOKUP properties of layer policy (i-044).

The 2026-07-21 anatomy audit found ``DefaultLayerResolver._policy_for_kind``
resolving the doc→policy relation by STRING INFERENCE (exact → suffix →
CamelCase→kebab regex → suffix again) and then falling back to
``LayerPolicy.OPEN`` **silently**. That fallback is the strongest protection
in the system evaporating on a typo: an alias that doesn't string-match
degrades ``locked`` to ``open`` with no witness.

These tests pin the repaired contract as properties of the system:

* **Policy binding is DECLARED, not inferred.** The resolver consults the
  kind registry's declared Kind→alias map first; a policy keyed by the
  declared alias governs the Kind even when NO string heuristic could
  connect the two names.
* **A broken alias is NEVER silent.** When policies WERE declared and a Kind
  matches none of them, the OPEN fallback warns — a typo'd alias now fails a
  test instead of failing a tenant.
* **Opting out stays quiet.** A scope with no policies at all is not running
  a policy regime — no warning storm for the default OPEN.
* **A policy key that can never match anything warns at build time** (the
  instance builder's typo detector) — even if no document of the mistyped
  Kind appears in the overlay batch.

Unit-level against the resolver plus one end-to-end proof through
``Kernel.instance_async`` so a builder refactor can't unwire the map.
"""
from __future__ import annotations

import warnings

import pytest
import yaml

from dna.kernel.layer_resolver import DefaultLayerResolver
from dna.kernel.protocols import LayerPolicy


def _agent(name: str, instruction: str) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Agent",
        "metadata": {"name": name},
        "spec": {"instruction": instruction},
    }


class _Src:
    def __init__(self, overlays):
        self._overlays = overlays

    def load_layer(self, _scope, _lid, _lv):
        return self._overlays


def _resolve(resolver, base, overlay, policies):
    return resolver.resolve(base, {"tenant": "acme"}, _Src(overlay), "s", policies)


# ── the legitimate paths (so the loud-fallback tests are not vacuous) ───────


def test_policy_keyed_by_declared_alias_governs_even_when_no_heuristic_could():
    """THE declared-not-inferred property. The Kind 'Agent' carries the
    registry-declared alias 'wdg-x9' — a name NO suffix/kebab heuristic can
    derive from 'Agent'. Its LOCKED policy must still bind. Before i-044
    this silently degraded to OPEN (the overlay would have won)."""
    r = DefaultLayerResolver(kind_aliases={"Agent": "wdg-x9"})
    base = [_agent("brad", "base")]
    overlay = [_agent("brad", "tampered")]
    with pytest.warns(UserWarning, match="locked"):
        result = _resolve(r, base, overlay, {"wdg-x9": LayerPolicy.LOCKED})
    assert result[0]["spec"]["instruction"] == "base"  # LOCKED held


def test_exact_kind_name_and_suffix_heuristics_still_work_quietly():
    """Compat: the legacy lookup paths (exact Kind name; '-<kind>' alias
    suffix) keep working and — being MATCHES — never trip the new warning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any warning fails the test
        r = DefaultLayerResolver()
        assert (
            r._policy_for_kind("Agent", {"Agent": LayerPolicy.RESTRICTED})
            is LayerPolicy.RESTRICTED
        )
        assert (
            r._policy_for_kind("Agent", {"helix-agent": LayerPolicy.LOCKED})
            is LayerPolicy.LOCKED
        )


# ── SECURITY: the fallback must be loud ─────────────────────────────────────


def test_a_typoed_alias_no_longer_degrades_locked_to_open_in_silence():
    """THE audit finding. The operator declared 'helix-agnet: locked' (typo).
    The Agent doc matches nothing → policy falls back to OPEN — but now the
    degradation has a witness. A silent pass here is the bug coming back."""
    r = DefaultLayerResolver(kind_aliases={"Agent": "helix-agent"})
    base = [_agent("brad", "base")]
    overlay = [_agent("brad", "tampered")]
    with pytest.warns(UserWarning, match="No LayerPolicy entry matched Kind 'Agent'"):
        result = _resolve(r, base, overlay, {"helix-agnet": LayerPolicy.LOCKED})
    # ...and the behavior really IS open (the honest half of the warning):
    assert result[0]["spec"]["instruction"] == "tampered"


def test_the_fallback_warning_names_the_kind_and_the_assumed_policy():
    """The warning must carry enough to act on: the Kind, its declared
    alias, the assumed OPEN, and the keys that WERE declared."""
    r = DefaultLayerResolver(kind_aliases={"Agent": "helix-agent"})
    with pytest.warns(UserWarning) as rec:
        r._policy_for_kind("Agent", {"helix-agnet": LayerPolicy.LOCKED})
    msg = str(rec[0].message)
    assert "'Agent'" in msg
    assert "helix-agent" in msg     # the declared alias, for the diff
    assert "OPEN" in msg            # what the system is about to assume
    assert "helix-agnet" in msg     # the keys actually declared


def test_no_declared_policies_means_no_warning():
    """A scope with NO policies opted out of the regime — OPEN is its
    designed default, not a degradation. It must stay quiet, or every
    unpoliced scope becomes a warning storm."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        r = DefaultLayerResolver()
        assert r._policy_for_kind("Agent", {}) is LayerPolicy.OPEN


def test_the_warning_fires_once_per_kind_not_once_per_document():
    """Ten unmatched Soul docs are ONE misconfiguration, not ten."""
    r = DefaultLayerResolver()
    policies = {"helix-agent": LayerPolicy.LOCKED}
    with pytest.warns(UserWarning) as rec:
        for _ in range(10):
            r._policy_for_kind("Soul", policies)
    fallback_warnings = [
        w for w in rec if "No LayerPolicy entry matched" in str(w.message)
    ]
    assert len(fallback_warnings) == 1


# ── end-to-end: the kernel wires the declared map + the typo detector ───────


API = "coretest.io/v1"


def _write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")


def _fs_scope_with_policy_key(tmp_path, policy_key: str):
    """Genome + LayerPolicy({policy_key: locked}) + widget + branch overlay."""
    scope = tmp_path / "demo"
    _write(scope / "Genome.yaml", {
        "apiVersion": API, "kind": "Genome",
        "metadata": {"name": "demo"}, "spec": {},
    })
    _write(scope / "policies" / "branch.yaml", {
        "apiVersion": API, "kind": "LayerPolicy",
        "metadata": {"name": "branch-policy"},
        "spec": {"layer_id": "branch", "policies": {policy_key: "locked"}},
    })
    _write(scope / "widgets" / "hello.yaml", {
        "apiVersion": API, "kind": "Widget",
        "metadata": {"name": "hello"}, "spec": {"color": "red"},
    })
    _write(scope / "layers" / "branch" / "dev" / "widgets" / "hello.yaml", {
        "apiVersion": API, "kind": "Widget",
        "metadata": {"name": "hello"}, "spec": {"color": "tampered"},
    })
    return tmp_path


def _bare_kernel(base_dir):
    from dna.adapters.filesystem import FilesystemSource
    from dna.kernel import Kernel
    from dna.kernel.kinds.base import KindBase
    from dna.kernel.protocols import StorageDescriptor

    class _RootStub(KindBase):
        api_version = API
        kind = "Genome"
        alias = None
        alias_owner = "coretest"
        storage = StorageDescriptor.root("Genome.yaml")

    class _WidgetStub(KindBase):
        api_version = API
        kind = "Widget"
        alias = None
        alias_owner = "coretest"
        storage = StorageDescriptor.yaml("widgets")

    class _LayerPolicyStub(KindBase):
        api_version = API
        kind = "LayerPolicy"
        alias = None
        alias_owner = "coretest"
        storage = StorageDescriptor.yaml("policies")

    class _NoOpCache:
        async def has(self, scope, key):
            return True

        async def load_all(self, scope, readers=None):
            return []

        async def store(self, scope, key, items):
            pass

    k = Kernel()
    k.source(FilesystemSource(base_dir))
    k.cache(_NoOpCache())
    k.kind(_RootStub())
    k.kind(_WidgetStub())
    k.kind(_LayerPolicyStub())
    return k


@pytest.mark.asyncio
async def test_end_to_end_a_correct_lock_still_locks(tmp_path):
    """Anti-vacuity for the e2e pair below: with the RIGHT key
    ('coretest-widget', the registry-generated alias) the overlay is
    blocked. Proves the declared map reaches the resolver through the
    instance builder."""
    k = _bare_kernel(_fs_scope_with_policy_key(tmp_path, "coretest-widget"))
    with pytest.warns(UserWarning, match="locked"):
        mi = await k.instance_async("demo", layers={"branch": "dev"})
    hello = await mi.one_async("Widget", "hello")
    assert hello.spec.get("color") == "red"  # lock held


@pytest.mark.asyncio
async def test_end_to_end_a_typoed_key_warns_at_build_time(tmp_path):
    """The builder's typo detector: 'coretest-widgett' names NO registered
    Kind — it can never match, so the build itself says so, and the lock the
    operator intended is visibly (not silently) absent."""
    k = _bare_kernel(_fs_scope_with_policy_key(tmp_path, "coretest-widgett"))
    with pytest.warns(UserWarning, match="never match"):
        mi = await k.instance_async("demo", layers={"branch": "dev"})
    hello = await mi.one_async("Widget", "hello")
    assert hello.spec.get("color") == "tampered"  # the honest consequence
