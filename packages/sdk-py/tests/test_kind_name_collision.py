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
   ``api_version`` — with NO exception. The shrink-only
   ``KIND_NAME_COLLISION_ALLOWLIST`` held one name, ``Reference``, and
   i-127 emptied it: the ``research`` extension reuses the sdlc Kind
   instead of registering a second one, so the permission was open with
   nobody walking through it. **Emptying it was a behaviour change at
   this door**, not bookkeeping — see
   ``test_a_second_Reference_is_now_REFUSED_at_the_door``.
2. The per-scope KindDefinition funnel keeps ALLOWING name collisions
   (live demo scopes ship Doc/EvalCase/EvalSuite shadow kinds under
   local apiVersions) — but bare-name lookups now prefer
   extension/builtin ports over per-scope declarative ones
   deterministically, and warn once per ambiguous name.
3. ``port_for``/``kind_plane``/``kind_port_for`` accept an optional
   ``api_version`` for exact resolution; ``write_instance`` resolves the
   plane from the raw doc's ``apiVersion``; ``delete_instance`` accepts
   an explicit ``api_version=`` kwarg.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from dna.kernel import Kernel
from dna.kernel.errors import KindRegistrationError
from dna.kernel.kinds.base import KindBase
from dna.kernel.kinds.registry import KIND_NAME_COLLISION_ALLOWLIST
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
    """A registry in the AMBIGUOUS state, built through the funnel that can
    still produce it.

    ⚠️ Changed by i-127. This used to call ``k.kind()`` twice, which the
    ``Reference`` allowlist entry permitted; with the allowlist empty the second
    call is REFUSED (that refusal is the point, and it has its own test). The
    ambiguity these tests are about did not go away with it: the **per-scope
    KindDefinition funnel still allows two api_versions to share a name by
    design** — contract point 2 of this module, live today in the demo scopes'
    Doc/EvalCase/EvalSuite shadow Kinds — so the state below is reachable, just
    not through the extension door any more.

    Which is why the second port is marked ``__declarative__``: it is the honest
    label for the funnel it would now have to come from. Bare-name lookups
    therefore prefer the FIRST (extension) port here, which is the same answer
    the tests below already asserted.
    """
    src = _FakeWritableSource()
    k = Kernel()
    k._source = src  # type: ignore[assignment]
    k.kind(_ResearchRefLike())
    sdlc_like = _SdlcRefLike()
    sdlc_like.__declarative__ = True
    k._kinds[(sdlc_like.api_version, sdlc_like.kind)] = sdlc_like
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


def test_a_second_Reference_is_now_REFUSED_at_the_door():
    """⭐ i-127 — the proof that emptying the allowlist CHANGED BEHAVIOUR.

    This test is the inverse of the one it replaces
    (``test_reference_collision_is_allowlisted``, which asserted the pair
    registered fine). It is here because "the constant is empty" and "the door
    refuses" are two different claims, and a task that deletes a permission owes
    the second one: a permission nobody exercises still cannot be shown to be
    gone by reading the list it was written in.

    Measured before the deletion: this same registration ACCEPTED both ports and
    ``kind_ports()`` reported two ``Reference``. The live registry never
    exercised it — ``dna/extensions/research/__init__.py`` reuses the sdlc Kind
    — so no real Kind moved; what moved is that the hole is closed.
    """
    k = Kernel()
    k.kind(_ResearchRefLike())
    with pytest.raises(KindRegistrationError, match="i-195"):
        k.kind(_SdlcRefLike())
    assert len([p for p in k.kind_ports() if p.kind == "Reference"]) == 1


def test_no_kind_name_is_excepted_from_the_collision_guard():
    """The ratchet, asked as BEHAVIOUR rather than as a literal.

    Derived: it takes names the live registry actually serves (plus the one that
    used to be excepted) and tries to register a homonym under a foreign
    api_version. A name still holding an exception would slip through here while
    the equality assertion below stayed green only if somebody also edited the
    literal — and the whole point of i-127 is that the literal and the door had
    drifted apart, in the harmless direction, for long enough that nobody
    noticed.
    """
    booted = Kernel.auto()
    live = sorted({p.kind for p in booted.kind_ports()})
    assert len(live) >= 76, len(live)  # guard over the guard: not a bare kernel

    for name in ["Reference", *live[:5]]:
        k = Kernel()
        first = type("_First", (KindBase,), {
            "api_version": "first.test/v1", "kind": name,
            "alias": f"first-{name.lower()}",
            "storage": StorageDescriptor.yaml("firsts"),
        })
        second = type("_Second", (KindBase,), {
            "api_version": "second.test/v1", "kind": name,
            "alias": f"second-{name.lower()}",
            "storage": StorageDescriptor.yaml("seconds"),
        })
        k.kind(first())
        with pytest.raises(KindRegistrationError, match="i-195"):
            k.kind(second())


def test_allowlist_is_shrink_only_ratchet():
    # EMPTIED by i-127; NEVER grows. New collisions must rename instead
    # (see i-195). Kept alongside the behavioural test above on purpose: this
    # one sees the PERMISSION reappear before any Kind uses it, that one sees
    # the DOOR reopen even if the permission arrives by some other route.
    assert KIND_NAME_COLLISION_ALLOWLIST == frozenset()


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
    from dna.kernel.kinds import registry as kr
    # i-080 item 5: the cache is process-wide AND now keyed by the AMBIGUITY
    # (kind name + the colliding api_versions) rather than by the name alone,
    # so a SECOND, different collision on the same name is audible instead of
    # being swallowed for the life of the process. Clear it wholesale.
    kr._AMBIGUOUS_LOOKUP_WARNED.clear()
    k, _src, _h = _wire_reference_pair()
    import logging
    with caplog.at_level(logging.WARNING, logger="dna.kernel.kinds.registry"):
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
    await k.write_instance(
        "scope-x", "Reference", "r-1",
        _raw("sdlclike.test/v1", "Reference", "r-1"),
    )
    assert k._kcache._base["scope-x"] is cached
    assert not holder.reload.called and not holder.reload_async.called


@pytest.mark.asyncio
async def test_write_composition_family_still_scope_invalidates():
    k, _src, holder = _wire_reference_pair()
    await k.write_instance(
        "scope-x", "Reference", "r-2",
        _raw("researchlike.test/v1", "Reference", "r-2"),
    )
    assert "scope-x" not in k._kcache._base
    assert holder.reload_async.called or holder.reload.called


@pytest.mark.asyncio
async def test_delete_with_api_version_demotes_record_plane():
    k, _src, holder = _wire_reference_pair()
    await k.write_instance(
        "scope-x", "Reference", "r-3",
        _raw("sdlclike.test/v1", "Reference", "r-3"),
    )
    await k.delete_instance(
        "scope-x", "Reference", "r-3", api_version="sdlclike.test/v1",
    )
    assert not holder.reload.called and not holder.reload_async.called
