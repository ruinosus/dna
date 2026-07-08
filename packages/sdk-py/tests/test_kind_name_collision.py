"""i-195 — kind-name collision guard + deterministic disambiguation.

Two builtin Kinds share the name ``Reference`` (github.com/ruinosus/dna/research/v1 +
github.com/ruinosus/dna/sdlc/v1). Every name-based lookup (``port_for``/``alias_for``/
``kind_plane``/write-path plane demotion) used to resolve by silent
first-match registration order — ``dna sdlc cite`` writes resolved the
*research* port (plane=composition) and skipped the record-plane
invalidation demotion, full-scope-rebuilding the MI on every citation.

Contract after i-195:

1. ``kernel.kind()`` (the extension/builtin funnel) REFUSES a new port
   whose ``kind`` name is already registered under a different
   ``api_version`` — unless the name is in the shrink-only
   ``KIND_NAME_COLLISION_ALLOWLIST`` (today: exactly ``{"Reference"}``,
   to be emptied by the Reference-family merge follow-up story).
2. The per-scope KindDefinition funnel keeps ALLOWING name collisions
   (live demo scopes ship Doc/EvalCase/EvalSuite shadow kinds under
   local apiVersions) — but bare-name lookups now prefer
   extension/builtin ports over per-scope declarative ones
   deterministically, and warn once per ambiguous name.
3. ``port_for``/``kind_plane``/``kind_port_for`` accept an optional
   ``api_version`` for exact resolution; ``write_document`` resolves the
   plane from the raw doc's ``apiVersion``; ``delete_document`` accepts
   an explicit ``api_version=`` kwarg.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from dna.kernel import Kernel
from dna.kernel.errors import KindRegistrationError
from dna.kernel.kind_base import KindBase
from dna.kernel.kind_registry import KIND_NAME_COLLISION_ALLOWLIST
from dna.kernel.protocols import StorageDescriptor

# -- reuse do harness (pytest põe tests/ no sys.path; SEM prefixo tests.) --
from test_kernel_invalidate_modes import _FakeWritableSource


# ---------- fakes: the allowlisted "Reference" pair, planes divergindo ----------

class _ResearchRefLike(KindBase):
    """Mirrors research-reference: plane composition (default), registra 1º."""
    api_version = "researchlike.test/v1"
    kind = "Reference"
    alias = "researchlike-reference"
    storage = StorageDescriptor.yaml("references")


class _SdlcRefLike(KindBase):
    """Mirrors sdlc-reference: plane record, registra 2º (perde o first-match)."""
    api_version = "sdlclike.test/v1"
    kind = "Reference"
    alias = "sdlclike-reference"
    storage = StorageDescriptor.yaml("references")
    plane = "record"


class _FooA(KindBase):
    api_version = "a.test/v1"
    kind = "FooCollide"
    alias = "a-foo-collide"
    storage = StorageDescriptor.yaml("foos")


class _FooB(KindBase):
    api_version = "b.test/v1"
    kind = "FooCollide"
    alias = "b-foo-collide"
    storage = StorageDescriptor.yaml("foos-b")


def _wire_reference_pair():
    src = _FakeWritableSource()
    k = Kernel()
    k._source = src  # type: ignore[assignment]
    k.kind(_ResearchRefLike())
    k.kind(_SdlcRefLike())
    k._kcache._base = {"scope-x": MagicMock(name="mi")}
    holder = MagicMock()
    holder.scope = "scope-x"
    holder.reload = MagicMock()
    holder.reload_async = AsyncMock()
    k.register_holder(holder)
    return k, src, holder


def _raw(api_version, kind, name):
    return {"apiVersion": api_version, "kind": kind,
            "metadata": {"name": name}, "spec": {}}


# ---------- 1. registration guard (extension funnel) ----------

def test_new_kind_name_collision_raises():
    k = Kernel()
    k.kind(_FooA())
    with pytest.raises(KindRegistrationError, match="i-195"):
        k.kind(_FooB())


def test_reference_collision_is_allowlisted():
    k = Kernel()
    k.kind(_ResearchRefLike())
    k.kind(_SdlcRefLike())  # must NOT raise — "Reference" is allowlisted
    assert len([p for p in k.kind_ports() if p.kind == "Reference"]) == 2


def test_allowlist_is_shrink_only_ratchet():
    # Emptied by the Reference-family merge; NEVER grows. New collisions
    # must rename instead (see i-195).
    assert KIND_NAME_COLLISION_ALLOWLIST == frozenset({"Reference"})


def test_same_api_version_reregistration_still_allowed():
    """Idempotent re-registration of the SAME (api_version, kind) must not
    trip the name-collision guard (descriptor digest path relies on it)."""
    k = Kernel()
    k.kind(_FooA())
    k.kind(_FooA())  # same key — existing H1 semantics, not a name collision
    assert len([p for p in k.kind_ports() if p.kind == "FooCollide"]) == 1


# ---------- 2. exact lookups via api_version ----------

def test_port_for_with_api_version_is_exact():
    k, _src, _h = _wire_reference_pair()
    reg = k._kindreg
    assert reg.port_for("Reference", api_version="researchlike.test/v1").alias \
        == "researchlike-reference"
    assert reg.port_for("Reference", api_version="sdlclike.test/v1").alias \
        == "sdlclike-reference"
    assert reg.port_for("Reference", api_version="nope/v1") is None


def test_kind_plane_with_api_version_is_exact():
    k, _src, _h = _wire_reference_pair()
    assert k.kind_plane("Reference", api_version="sdlclike.test/v1") == "record"
    assert k.kind_plane("Reference", api_version="researchlike.test/v1") \
        == "composition"
    # bare stays fail-safe first-match (documented back-compat)
    assert k.kind_plane("Reference") == "composition"


# ---------- 3. bare-lookup preference: extension beats per-scope declarative ----------

def test_bare_lookup_prefers_extension_over_per_scope_declarative():
    """A per-scope DeclarativeKindPort registered BEFORE the extension port
    must NOT win the bare lookup (live case: demo scopes shadow Doc/EvalCase
    under local apiVersions; builtins must stay the bare-name resolution)."""
    k = Kernel()
    declarative = _FooA()
    declarative.__declarative__ = True  # per-scope KindDefinition marker
    k._kinds[("a.test/v1", "FooCollide")] = declarative  # funil per-scope (bypassa kind())
    k.kind(_FooB())  # extension port, registered AFTER
    assert k._kindreg.port_for("FooCollide").alias == "b-foo-collide"


def test_ambiguous_bare_lookup_warns_once(caplog):
    from dna.kernel import kind_registry as kr
    kr._AMBIGUOUS_LOOKUP_WARNED.discard("Reference")  # cache é process-wide
    k, _src, _h = _wire_reference_pair()
    import logging
    with caplog.at_level(logging.WARNING, logger="dna.kernel.kind_registry"):
        k._kindreg.port_for("Reference")
        k._kindreg.port_for("Reference")
    hits = [r for r in caplog.records if "ambiguous" in r.getMessage().lower()]
    assert len(hits) == 1


# ---------- 4. write/delete path resolves plane by the doc's apiVersion ----------

@pytest.mark.asyncio
async def test_write_record_family_skips_scope_invalidate_despite_collision():
    """The i-195 headline bug: writing the RECORD-plane family (raw carries
    its apiVersion) must demote invalidation even though the bare name
    first-matches the composition family."""
    k, _src, holder = _wire_reference_pair()
    cached = k._kcache._base["scope-x"]
    await k.write_document(
        "scope-x", "Reference", "r-1",
        _raw("sdlclike.test/v1", "Reference", "r-1"),
    )
    assert k._kcache._base["scope-x"] is cached
    assert not holder.reload.called and not holder.reload_async.called


@pytest.mark.asyncio
async def test_write_composition_family_still_scope_invalidates():
    k, _src, holder = _wire_reference_pair()
    await k.write_document(
        "scope-x", "Reference", "r-2",
        _raw("researchlike.test/v1", "Reference", "r-2"),
    )
    assert "scope-x" not in k._kcache._base
    assert holder.reload_async.called or holder.reload.called


@pytest.mark.asyncio
async def test_delete_with_api_version_demotes_record_plane():
    k, _src, holder = _wire_reference_pair()
    await k.write_document(
        "scope-x", "Reference", "r-3",
        _raw("sdlclike.test/v1", "Reference", "r-3"),
    )
    await k.delete_document(
        "scope-x", "Reference", "r-3", api_version="sdlclike.test/v1",
    )
    assert not holder.reload.called and not holder.reload_async.called
