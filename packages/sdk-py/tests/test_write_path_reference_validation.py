"""Write-time enforcement of declared relations (i-040,
f-modelagem-das-relacoes).

The unit tests in ``test_relations.py`` pin how a relation is READ. These pin
what the write path DOES with it, against a source that really stores
instances — a source that answers "no" to every read would make a
dangling-reference test pass for entirely the wrong reason.

Pinned contract, each clause a deliberate refusal to break something:

- ``enforce``: writing a relation to a non-existent target is vetoed and
  nothing persists;
- the same write succeeds once the target exists (forward references are an
  ORDERING problem, not a permanent one);
- ``warn`` (the default) persists and logs — chosen so that upgrading the SDK
  cannot break a working bootstrap, since a legitimate seed may write a child
  before its parent;
- ``off`` skips entirely;
- optional/absent relations never trip the check;
- a Kind that declares no resolvable relation performs ZERO extra reads,
  asserted by counting reads rather than by inspection;
- polymorphic relations resolve against any declared target;
- **reciprocity is REPORTED and never enforced** — in EVERY mode, including
  ``enforce``. That is the promise ``inverse_of`` makes, and the class that
  pins it (``TestReciprocityIsReportedNeverImposed``) is the one that would
  catch somebody "strengthening" it into a veto and deadlocking every pair.
- **a relation addressed by a key is NOT resolved** — declaring `by:
  workspace_id` must install no resolution rule, or the write path starts
  vetoing data the live lookup accepts.
"""
from __future__ import annotations

import logging

import pytest

from dna.kernel import Kernel
from dna.kernel.protocols import SpecValidationError
from tests.test_kernel_invalidate_modes import _FakeWritableSource

_SDLC_API = "github.com/ruinosus/dna/sdlc/v1"


class _StatefulSource(_FakeWritableSource):
    """The suite's conformant fake source, taught to REMEMBER what it stored.

    ``load_one`` is the read the kernel's ``get_instance`` ultimately reaches;
    the stock fake returns None for everything, which would make a
    dangling-reference test pass for entirely the wrong reason. ``reads``
    counts those lookups — that counter is how the "no declaration → no cost"
    claim is proven rather than merely asserted.
    """

    def __init__(self) -> None:
        super().__init__()
        self.docs: dict[tuple[str, str, str], dict] = {}
        self.reads: list[tuple[str, str, str]] = []
        self.key_reads: list[tuple[str, str, str, str]] = []

    async def save_instance(
        self, scope, kind, name, raw, author=None, *, tenant=None, layer=None,
    ) -> str:
        version = await super().save_instance(
            scope, kind, name, raw, author, tenant=tenant, layer=layer,
        )
        self.docs[(scope, kind, name)] = raw
        return version

    async def delete_instance(self, scope, kind, name, *, tenant=None, layer=None):
        self.docs.pop((scope, kind, name), None)
        return await super().delete_instance(
            scope, kind, name, tenant=tenant, layer=layer,
        )

    def seed(self, scope: str, kind: str, name: str) -> None:
        self.docs[(scope, kind, name)] = {
            "apiVersion": _SDLC_API, "kind": kind,
            "metadata": {"name": name}, "spec": {},
        }

    async def load_one(self, scope, kind, name, *, readers=None, tenant=None):
        self.reads.append((scope, kind, name))
        return self.docs.get((scope, kind, name))

    async def find_instances_by_spec_key(
        self, scope, kind, key, value, *, tenant=None, limit=2,
    ):
        """The by-KEY read (fatia 5), over the same in-memory ``docs``.

        It is on this double for the reason ``load_one`` is, and the reason is
        sharper here: WITHOUT it every by-key assertion in this file passes
        because ``Kernel.find_instance_by_key`` refuses on an adapter that
        cannot answer — the store's incapacity standing in for the kernel's
        restraint, green either way, checking nothing. ``key_reads`` counts the
        lookups so "it looked" and "it did not veto" stay two separate claims.
        """
        self.key_reads.append((scope, kind, key, value))
        out = []
        for (s, k, n), raw in sorted(self.docs.items()):
            if s != scope or k != kind:
                continue
            if (raw.get("spec") or {}).get(key) != value:
                continue
            out.append({
                "scope": s, "kind": k,
                "api_version": raw.get("apiVersion", "") or "",
                "name": n, "tenant": tenant or "", "raw": raw,
            })
            if len(out) >= max(1, limit):
                break
        return out


def _story(name: str, spec: dict) -> dict:
    return {
        "apiVersion": _SDLC_API, "kind": "Story",
        "metadata": {"name": name}, "spec": spec,
    }


def _base_spec(**extra) -> dict:
    spec = {"description": "d", "status": "todo"}
    spec.update(extra)
    return spec


@pytest.fixture()
def source() -> _StatefulSource:
    return _StatefulSource()


@pytest.fixture()
def kernel(source) -> Kernel:
    k = Kernel.auto()
    k.source(source)
    return k


@pytest.fixture(autouse=True)
def _default_mode(monkeypatch):
    """Most tests state their mode explicitly; start from a known baseline."""
    monkeypatch.delenv("DNA_REF_VALIDATION", raising=False)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")


# --- enforce -----------------------------------------------------------------


class TestEnforce:
    @pytest.mark.anyio
    async def test_dangling_reference_is_vetoed_and_nothing_persists(
        self, kernel, source, monkeypatch,
    ):
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        with pytest.raises(SpecValidationError) as exc:
            await kernel.write_instance(
                "proj", "Story", "s-1",
                _story("s-1", _base_spec(feature="f-does-not-exist")),
            )
        assert "f-does-not-exist" in str(exc.value)
        assert "Feature" in str(exc.value)
        assert source.save_calls == []

    @pytest.mark.anyio
    async def test_same_write_succeeds_once_the_target_exists(
        self, kernel, source, monkeypatch,
    ):
        """A forward reference is an ordering problem, not a permanent one."""
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        source.seed("proj", "Feature", "f-real")
        await kernel.write_instance(
            "proj", "Story", "s-1", _story("s-1", _base_spec(feature="f-real")),
        )
        assert ("proj", "Story", "s-1") in source.docs

    @pytest.mark.anyio
    async def test_absent_optional_reference_is_fine(
        self, kernel, source, monkeypatch,
    ):
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        await kernel.write_instance(
            "proj", "Story", "s-1", _story("s-1", _base_spec()),
        )
        assert ("proj", "Story", "s-1") in source.docs

    @pytest.mark.anyio
    async def test_array_reference_flags_only_the_missing_item(
        self, kernel, source, monkeypatch,
    ):
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        source.seed("proj", "Story", "s-ok")
        with pytest.raises(SpecValidationError) as exc:
            await kernel.write_instance(
                "proj", "Story", "s-1",
                _story("s-1", _base_spec(dependencies=["s-ok", "s-missing"])),
            )
        assert "s-missing" in str(exc.value)
        assert "s-ok" not in str(exc.value)


# --- warn (the default) --------------------------------------------------------


class TestWarnIsTheDefault:
    @pytest.mark.anyio
    async def test_default_mode_persists_and_logs(
        self, kernel, source, caplog,
    ):
        """No env var set → warn. A dangling reference is loud but not fatal.

        This is the clause that makes the feature safe to ship: an existing
        bootstrap that writes children before parents keeps working, and the
        operator still sees the problem.
        """
        with caplog.at_level(logging.WARNING, logger="dna.kernel"):
            await kernel.write_instance(
                "proj", "Story", "s-1",
                _story("s-1", _base_spec(feature="f-missing")),
            )
        assert ("proj", "Story", "s-1") in source.docs
        assert "f-missing" in caplog.text
        assert "DNA_REF_VALIDATION=warn" in caplog.text

    @pytest.mark.anyio
    async def test_off_performs_no_reference_lookup(
        self, kernel, source, monkeypatch,
    ):
        """``off`` must not look the target up at all.

        Measured as a lookup for the TARGET Kind specifically — the write path
        does other reads of its own (the doc itself, the scope Genome), and
        counting those would make this assertion about the wrong thing.
        """
        monkeypatch.setenv("DNA_REF_VALIDATION", "off")
        source.reads.clear()
        await kernel.write_instance(
            "proj", "Story", "s-1", _story("s-1", _base_spec(feature="f-missing")),
        )
        assert ("proj", "Story", "s-1") in source.docs
        assert [r for r in source.reads if r[1] == "Feature"] == []

    @pytest.mark.anyio
    async def test_enforce_does_look_the_target_up(
        self, kernel, source, monkeypatch,
    ):
        """The counterpart of the test above — proving it measures something."""
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        source.seed("proj", "Feature", "f-real")
        source.reads.clear()
        await kernel.write_instance(
            "proj", "Story", "s-1", _story("s-1", _base_spec(feature="f-real")),
        )
        assert ("proj", "Feature", "f-real") in source.reads


# --- back-compatibility --------------------------------------------------------


class TestUndeclaredKindsAreUntouched:
    """Engram declares three relations and the kernel resolves NONE of them —
    all three carry their target Kind in the value (``to: "*"``).

    That makes this class prove something stronger than it used to. It was "a
    Kind that never opted in costs what it always cost"; it is now "a Kind that
    opted IN, with relations the runtime does not follow, still costs what it
    always cost". If a future change starts resolving ``to: "*"`` or ``by:
    <key>``, this goes red on the read count before anything downstream
    notices.
    """

    @staticmethod
    def _engram(name: str) -> dict:
        return {
            "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Engram",
            "metadata": {"name": name},
            "spec": {
                "area": "x", "surface_when": ["feature_touched"], "summary": "s",
            },
        }

    @pytest.mark.anyio
    async def test_undeclared_kind_adds_no_reads_even_under_enforce(
        self, kernel, source, monkeypatch,
    ):
        """A Kind that did not opt in costs exactly what it cost before.

        Proven differentially: the same write is performed with reference
        validation ``off`` and then ``enforce``, and the source reads must be
        IDENTICAL. An absolute "zero reads" assertion would be wrong — the
        write path legitimately reads the instance itself and the scope's
        Genome — and would hide the only number that matters here, which is
        the DELTA this feature introduces.
        """
        async def reads_under(mode: str) -> list[tuple[str, str, str]]:
            # A FRESH kernel + source per half: the kernel's caches survive a
            # write, so reusing one would make the second half look cheaper
            # for reasons that have nothing to do with this feature.
            monkeypatch.setenv("DNA_REF_VALIDATION", mode)
            src = _StatefulSource()
            k = Kernel.auto()
            k.source(src)
            await k.write_instance("proj", "Engram", "rem-1", self._engram("rem-1"))
            return list(src.reads)

        baseline = await reads_under("off")
        enforced = await reads_under("enforce")

        assert enforced == baseline, (
            f"undeclared Kind paid for reference validation: "
            f"{set(enforced) - set(baseline)}"
        )


# --- reciprocity: reported, never imposed, never derived -----------------------


class TestReciprocityIsReportedNeverImposed:
    """``Feature.stories`` and ``Story.feature`` declare each other as inverses.

    Both halves are STORED, in two instances, written by two writes — which is
    why they can disagree, and why the promise here is a REPORT. The three
    promises available were: impose (deadlocks — neither half of a pair can be
    written first), derive (a cascade write into an instance the author never
    touched), report (free, because the existence check already loaded the
    target). These tests pin the third and, more importantly, pin that it is
    NOT one of the other two.
    """

    @staticmethod
    def _feature(name: str, stories: list[str] | None = None) -> dict:
        return {
            "apiVersion": _SDLC_API, "kind": "Feature",
            "metadata": {"name": name},
            "spec": {"description": "d", "status": "discovery",
                     "stories": stories or []},
        }

    @pytest.mark.anyio
    async def test_a_one_sided_pair_is_logged(self, kernel, source, caplog):
        source.docs[("proj", "Feature", "f-1")] = self._feature("f-1")
        with caplog.at_level(logging.WARNING, logger="dna.kernel"):
            await kernel.write_instance(
                "proj", "Story", "s-1", _story("s-1", _base_spec(feature="f-1")),
            )
        assert "does not name this instance back" in caplog.text
        assert "stories" in caplog.text

    @pytest.mark.anyio
    async def test_a_one_sided_pair_still_PERSISTS(self, kernel, source):
        source.docs[("proj", "Feature", "f-1")] = self._feature("f-1")
        await kernel.write_instance(
            "proj", "Story", "s-1", _story("s-1", _base_spec(feature="f-1")),
        )
        assert ("proj", "Story", "s-1") in source.docs

    @pytest.mark.anyio
    async def test_ENFORCE_does_not_veto_a_one_sided_pair(
        self, kernel, source, monkeypatch,
    ):
        """The mutant this kills: somebody folding ``discords`` into
        ``problems`` so that the strict mode "also checks the inverse". It
        would make every pair unwritable in EITHER order — the Story cannot
        name a Feature that does not list it, and the Feature cannot list a
        Story that does not exist yet."""
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        source.docs[("proj", "Feature", "f-1")] = self._feature("f-1")
        await kernel.write_instance(
            "proj", "Story", "s-1", _story("s-1", _base_spec(feature="f-1")),
        )
        assert ("proj", "Story", "s-1") in source.docs

    @pytest.mark.anyio
    async def test_a_reciprocated_pair_logs_NOTHING(
        self, kernel, source, caplog,
    ):
        """The counterpart that proves the test above measures something."""
        source.docs[("proj", "Feature", "f-1")] = self._feature("f-1", ["s-1"])
        with caplog.at_level(logging.WARNING, logger="dna.kernel"):
            await kernel.write_instance(
                "proj", "Story", "s-1", _story("s-1", _base_spec(feature="f-1")),
            )
        assert "does not name this instance back" not in caplog.text

    @pytest.mark.anyio
    async def test_the_kernel_NEVER_writes_the_other_half(
        self, kernel, source, monkeypatch,
    ):
        """Deriving the missing side would mean the kernel mutating an instance
        the author did not touch, inside somebody else's version and etag. The
        Feature must come back untouched, and no save may have been issued for
        it."""
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        source.docs[("proj", "Feature", "f-1")] = self._feature("f-1")
        await kernel.write_instance(
            "proj", "Story", "s-1", _story("s-1", _base_spec(feature="f-1")),
        )
        assert source.docs[("proj", "Feature", "f-1")]["spec"]["stories"] == []
        assert [c for c in source.save_calls if "Feature" in c] == []

    @pytest.mark.anyio
    async def test_the_edge_carries_the_tri_state(self, kernel, source):
        """``reciprocal`` is what a durable report would read. ``None`` is the
        third state and is NOT ``False``: ``spec_refs`` declares no inverse, so
        the question was never asked of it."""
        source.docs[("proj", "Feature", "f-1")] = self._feature("f-1", ["s-1"])
        source.seed("proj", "Feature", "f-2")
        source.seed("proj", "Spec", "sp-1")
        pipeline = kernel._write_pipeline
        port = kernel.kind_port_for("Story")

        async def edges_for(spec: dict):
            edges, _ = await pipeline._resolve_references(
                "proj", "Story", "s-1", _story("s-1", spec), port, tenant=None,
            )
            return {e.field: e.reciprocal for e in edges}

        assert await edges_for(_base_spec(feature="f-1")) == {"feature": True}
        assert await edges_for(_base_spec(feature="f-2")) == {"feature": False}
        assert await edges_for(_base_spec(spec_refs=["sp-1"])) == {
            "spec_refs": None,
        }


# --- a relation the kernel does NOT resolve stays unresolved -------------------


class TestKeyAddressedRelationsAreFollowedAndNeverVeto:
    """``Project.workspace_id`` declares ``to: Workspace, by: workspace_id``.

    This class used to be called ``…AreNotFollowed`` and asserted that the
    write path never even LOOKED. Fatia 5 split the two halves of that claim
    and kept only one of them:

    * *"resolving by key needs an expression index the store does not have"* —
      **false, and measured false**: ``dna_insts_spec_gin_idx`` has been in the
      baseline schema since revision 0001. So the kernel looks.
    * *"a second rule beside a live one can veto data the live one accepts"* —
      **true, and still true**: ``kernel.tier()`` resolves a PricingPlan by
      ``tier_id`` and THEN by ``aliases[]``, so a resolver knowing only the
      first would refuse a valid alias. So the kernel does not veto.

    What these tests now stop from arriving by accident is the VETO, which is
    the half that was ever dangerous.
    """

    @staticmethod
    def _project(name: str, workspace_id: str) -> dict:
        return {
            "apiVersion": "github.com/ruinosus/dna/portfolio/v1",
            "kind": "Project",
            "metadata": {"name": name},
            "spec": {"name": name, "slug": name, "workspace_id": workspace_id},
        }

    @pytest.mark.anyio
    async def test_enforce_does_not_veto_a_key_addressed_value(
        self, kernel, source, monkeypatch,
    ):
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        await kernel.write_instance(
            "proj", "Project", "p-1", self._project("p-1", "ws-nobody-has"),
            tenant="acme",
        )
        assert ("proj", "Project", "p-1") in source.docs

    @pytest.mark.anyio
    async def test_enforce_LOOKS_the_target_up_by_key_and_still_does_not_veto(
        self, kernel, source, monkeypatch,
    ):
        """⚠️ The inversion, and the two assertions have to stay SEPARATE.

        The previous version asserted "it did not ask", on the reasoning that a
        lookup was a resolution rule in waiting. It is a resolution rule that
        arrived — and the danger was never the lookup, it was ACTING on the
        answer by refusing a write.

        Asserting only "it did not veto" would now be satisfied by a kernel
        that never looked at all, which is exactly how this test would have
        gone green-and-blind when the double did not implement
        ``find_instances_by_spec_key``. So: it looked, BY THE KEY, and the
        write survived anyway.
        """
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        source.reads.clear()
        source.key_reads.clear()
        await kernel.write_instance(
            "proj", "Project", "p-1", self._project("p-1", "ws-nobody-has"),
            tenant="acme",
        )
        assert ("proj", "Project", "p-1") in source.docs, (
            "a by-key miss vetoed the write — the alias-tolerant live lookups "
            "accept addresses this resolver cannot see"
        )
        assert [r for r in source.key_reads if r[1] == "Workspace"], (
            "the write path never looked the Workspace up by key, so the "
            "'did not veto' assertion above proves nothing"
        )
        # …and it asked by the KEY, never by the name. A by-name probe would be
        # the second resolution rule, right by coincidence wherever a Workspace
        # file happens to be named after its id.
        assert [r for r in source.reads if r[1] == "Workspace"] == []


class TestTheAliasSurvivesTheNewPlanBindingDeclaration:
    """``PlanBinding.tier_id`` declares ``to: PricingPlan, by: tier_id``
    (i-119, 06/08/2026) — and this class is the exact fear that declaration had
    to answer before it could be written.

    For months the Kind refused to declare the field, and the reason written in
    its own descriptor was that a relation keyed on ``tier_id`` would be a
    SECOND resolution rule beside ``kernel.tier()``, free to veto an
    ALIAS-keyed binding the live lookup happily resolves. The claim is testable
    and it is tested here rather than argued: ``kernel.tier()`` matches
    ``PricingPlan.spec.tier_id`` FIRST and ``spec.aliases[]`` SECOND, so a
    binding written against an alias is VALID DATA, and the write path must not
    develop an opinion about it.

    ⚠️ The mutant this class exists to kill is one deleted line: drop ``by:
    tier_id`` from the descriptor and the relation becomes ``by: name`` — the
    kernel resolves it, looks for a PricingPlan INSTANCE named ``pro-annual``,
    finds none, and refuses a binding the live resolver accepts. Both tests go
    red, and they go red for the two different reasons that matter: one because
    the write was refused, one because a lookup happened at all.
    """

    _PRICING = "github.com/ruinosus/dna/cloud/v1"

    @staticmethod
    def _binding(name: str, tier_id: str) -> dict:
        return {
            "apiVersion": "github.com/ruinosus/dna/cloud/v1",
            "kind": "PlanBinding",
            "metadata": {"name": name},
            "spec": {"account_id": name, "tier_id": tier_id},
        }

    @pytest.mark.anyio
    async def test_a_binding_keyed_on_an_ALIAS_is_not_vetoed(
        self, kernel, source, monkeypatch,
    ):
        """The live resolver reaches this row through ``aliases[]``. Nothing on
        the write path may disagree with it."""
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        source.docs[("_lib", "PricingPlan", "plan-pro")] = {
            "apiVersion": self._PRICING, "kind": "PricingPlan",
            "metadata": {"name": "plan-pro"},
            "spec": {"tier_id": "pro", "aliases": ["pro-annual"]},
        }
        await kernel.write_instance(
            "_lib", "PlanBinding", "acct-1",
            self._binding("acct-1", "pro-annual"),
        )
        assert ("_lib", "PlanBinding", "acct-1") in source.docs

    @pytest.mark.anyio
    async def test_the_alias_binding_is_LOOKED_UP_missed_and_still_persisted(
        self, kernel, source, monkeypatch,
    ):
        """⭐ The single most important assertion of fatia 5.

        ``pro-annual`` is a real, live, resolvable address: ``kernel.tier()``
        reaches that PricingPlan through ``spec.aliases[]``. The by-key
        resolver knows only ``spec.tier_id`` and therefore MISSES it — and that
        miss must cost the author nothing. This is the whole reason
        ``Relation.enforced`` is narrower than ``Relation.resolved``.

        Three claims, deliberately not two: it looked (else the rest proves
        nothing), it missed (else the miss is not being exercised), and the
        write landed anyway.
        """
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        source.docs[("_lib", "PricingPlan", "plan-pro")] = {
            "apiVersion": self._PRICING, "kind": "PricingPlan",
            "metadata": {"name": "plan-pro"},
            "spec": {"tier_id": "pro", "aliases": ["pro-annual"]},
        }
        source.reads.clear()
        source.key_reads.clear()
        await kernel.write_instance(
            "_lib", "PlanBinding", "acct-2", self._binding("acct-2", "pro-annual"),
        )
        assert [r for r in source.key_reads if r[1] == "PricingPlan"], (
            "the write path never looked — so nothing below is being tested"
        )
        assert ("_lib", "PlanBinding", "acct-2") in source.docs, (
            "a binding keyed on a live ALIAS was refused: the write path grew "
            "an opinion the live resolver does not share, which is the exact "
            "second-resolution-rule failure this Kind spent months avoiding"
        )
        # It never fell back to a name probe either. That fallback is how a
        # poorer resolver hides: it would resolve `pro-annual` iff somebody
        # happened to name the instance after the alias.
        assert [r for r in source.reads if r[1] == "PricingPlan"] == []


class TestTheKindNamespaceOwnerIsAddressedByWorkspaceId:
    """``KindNamespace.owner`` declares ``to: Workspace, by: workspace_id``
    (i-119, 06/08/2026).

    ``owner`` holds a ``Workspace.spec.workspace_id`` — the opaque value the
    kernel ``tenant`` column carries and the one ``owner_of()`` compares the
    writer against. ``metadata.name`` agrees with it only by the convention
    that the container writes ``workspaces/<workspace_id>.yaml``.

    ⚠️ The mutant: drop ``by: workspace_id`` and the relation resolves by
    instance name. It would pass on every claim whose Workspace file happens to
    be named after its id and refuse the first one that is not — a rule right
    by coincidence, which is the failure mode ``TenantMembership.tenant_slug``
    was written to avoid. Seeding a Workspace under a DIFFERENT instance name
    than its ``workspace_id`` is what makes the coincidence unavailable here,
    so the mutant cannot hide behind it.
    """

    _TENANT = "github.com/ruinosus/dna/tenant/v1"

    @staticmethod
    def _claim(name: str, owner: str) -> dict:
        return {
            "apiVersion": "github.com/ruinosus/dna/tenant/v1",
            "kind": "KindNamespace",
            "metadata": {"name": name},
            "spec": {
                "namespace": "acme.example", "owner": owner,
                "claimed_at": "2026-08-06T00:00:00Z",
            },
        }

    @pytest.mark.anyio
    async def test_a_claim_owned_by_a_workspace_id_is_not_vetoed(
        self, kernel, source, monkeypatch,
    ):
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        # The Workspace EXISTS and its instance name is deliberately NOT its
        # workspace_id — so a `by: name` resolution has nothing to find.
        source.docs[("_lib", "Workspace", "barnabe-labs")] = {
            "apiVersion": self._TENANT, "kind": "Workspace",
            "metadata": {"name": "barnabe-labs"},
            "spec": {"workspace_id": "ws-3f9a", "name": "Barnabé Labs",
                     "created_by": "a@b.c", "created_at": "2026-08-06T00:00:00Z"},
        }
        await kernel.write_instance(
            "_lib", "KindNamespace", "acme-example",
            self._claim("acme-example", "ws-3f9a"),
        )
        assert ("_lib", "KindNamespace", "acme-example") in source.docs

    @pytest.mark.anyio
    async def test_the_write_path_asks_by_KEY_and_only_by_key(
        self, kernel, source, monkeypatch,
    ):
        """The coincidence trap, now measured from BOTH sides.

        The Workspace is seeded under an instance name that is deliberately not
        its ``workspace_id``, so a by-NAME probe can only ever miss. Two
        assertions: the key lookup happened (the relation is followed), and no
        name lookup happened (the mutant that drops ``by: workspace_id`` puts
        one there, and it would be right only where the file happens to be
        named after the id).
        """
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        source.docs[("_lib", "Workspace", "barnabe-labs")] = {
            "apiVersion": self._TENANT, "kind": "Workspace",
            "metadata": {"name": "barnabe-labs"},
            "spec": {"workspace_id": "ws-3f9a", "name": "Barnabé Labs",
                     "created_by": "a@b.c", "created_at": "2026-08-06T00:00:00Z"},
        }
        source.reads.clear()
        source.key_reads.clear()
        await kernel.write_instance(
            "_lib", "KindNamespace", "beta-example",
            self._claim("beta-example", "ws-3f9a"),
        )
        assert ("_lib", "Workspace", "workspace_id", "ws-3f9a") in source.key_reads
        assert [r for r in source.reads if r[1] == "Workspace"] == [], (
            "the write path probed a Workspace by NAME — the resolution rule "
            "that is right by coincidence and wrong the first time somebody "
            "names a Workspace file anything but its id"
        )

    @pytest.mark.anyio
    async def test_a_claim_owned_by_NOBODY_is_still_not_vetoed(
        self, kernel, source, monkeypatch,
    ):
        """No Workspace carries this id. The claim still lands, under
        ``enforce``, and the graph records the break — which is the split
        between ``resolved`` and ``enforced`` doing its job."""
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        await kernel.write_instance(
            "_lib", "KindNamespace", "gamma-example",
            self._claim("gamma-example", "ws-nobody-has"),
        )
        assert ("_lib", "KindNamespace", "gamma-example") in source.docs


class TestTheNewlyDeclaredReferencesGoThroughTheDoor:
    """The 06/08/2026 sweep (i-108) turned REAL references that nothing
    declared into resolved relations. A declaration is worth exactly what the
    write path does with it, so each is exercised HERE: write the instance with
    a target that exists and watch the read happen; write it with one that does
    not and watch the refusal happen.

    ``Spike.research_refs`` is the sharp one — the runtime already read the
    value as a Research name (``resolve_work_item_outputs``) and only the
    declaration was missing. If it is ever quietly dropped, this class fails
    instead of the graph silently losing a line.
    """

    @staticmethod
    def _spike(name: str, **spec) -> dict:
        base = {"title": "t", "question_to_answer": "q", "status": "open"}
        base.update(spec)
        return {
            "apiVersion": _SDLC_API, "kind": "Spike",
            "metadata": {"name": name}, "spec": base,
        }

    @staticmethod
    def _adr(name: str, **spec) -> dict:
        base = {"title": "t", "status": "proposed", "context": "c",
                "decision": "d"}
        base.update(spec)
        return {
            "apiVersion": _SDLC_API, "kind": "ADR",
            "metadata": {"name": name}, "spec": base,
        }

    @pytest.mark.anyio
    async def test_spike_research_refs_resolves_a_real_research(
        self, kernel, source, monkeypatch,
    ):
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        source.seed("proj", "Research", "rsh-real")
        await kernel.write_instance(
            "proj", "Spike", "sp-1",
            self._spike("sp-1", research_refs=["rsh-real"]),
        )
        assert ("proj", "Spike", "sp-1") in source.docs
        assert ("proj", "Research", "rsh-real") in source.reads

    @pytest.mark.anyio
    async def test_spike_research_refs_vetoes_a_dangling_one(
        self, kernel, source, monkeypatch,
    ):
        """The refusal that could not happen before: the field was
        reference-shaped, read as a Research name by the output resolver, and
        checked by nobody."""
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        with pytest.raises(SpecValidationError) as exc:
            await kernel.write_instance(
                "proj", "Spike", "sp-1",
                self._spike("sp-1", research_refs=["rsh-nobody-wrote"]),
            )
        assert "rsh-nobody-wrote" in str(exc.value)
        assert "Research" in str(exc.value)
        assert source.save_calls == []

    @pytest.mark.anyio
    async def test_adr_leaves_its_island_through_covers_features(
        self, kernel, source, monkeypatch,
    ):
        """ADR declared nothing at all and was an island — a decision record
        pointing at nothing, in a spec-driven-development product. Three of its
        links sat in ``dep_filters``, which is never checked against stored
        data; as relations the kernel resolves them."""
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        source.seed("proj", "Feature", "f-real")
        await kernel.write_instance(
            "proj", "ADR", "adr-1",
            self._adr("adr-1", covers_features=["f-real"]),
        )
        assert ("proj", "ADR", "adr-1") in source.docs
        with pytest.raises(SpecValidationError) as exc:
            await kernel.write_instance(
                "proj", "ADR", "adr-2",
                self._adr("adr-2", covers_features=["f-ghost"]),
            )
        assert "f-ghost" in str(exc.value)

    @pytest.mark.anyio
    async def test_the_adr_supersession_pair_reports_and_never_vetoes(
        self, kernel, source, monkeypatch,
    ):
        """``superseded_by``/``supersedes`` are declared inverses. Writing one
        half while the other is silent is REPORTED, never refused — imposing it
        would deadlock the pair, which is the promise ``inverse_of`` makes."""
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        source.seed("proj", "ADR", "adr-old")
        await kernel.write_instance(
            "proj", "ADR", "adr-new",
            self._adr("adr-new", supersedes=["adr-old"]),
        )
        assert ("proj", "ADR", "adr-new") in source.docs

    @pytest.mark.anyio
    async def test_the_eval_spine_resolves_and_refuses(
        self, kernel, source, monkeypatch,
    ):
        """All four Eval Kinds were islands. An EvalRun that does not point at
        the suite it executed is modelling that did not happen — and every link
        was already spelled out in the schema descriptions ("Name of the
        EvalSuite that was executed"). Nothing was declared, so nothing was
        checked."""
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        source.seed("proj", "EvalSuite", "suite-a")
        run = {
            "apiVersion": "github.com/ruinosus/dna/eval/v1", "kind": "EvalRun",
            "metadata": {"name": "run-1"},
            "spec": {"suite": "suite-a", "total": 1, "passed": 1, "failed": 0,
                     "results": []},
        }
        await kernel.write_instance("proj", "EvalRun", "run-1", run)
        assert ("proj", "EvalRun", "run-1") in source.docs

        run["metadata"]["name"] = "run-2"
        run["spec"] = dict(run["spec"], suite="suite-that-never-ran")
        with pytest.raises(SpecValidationError) as exc:
            await kernel.write_instance("proj", "EvalRun", "run-2", run)
        assert "suite-that-never-ran" in str(exc.value)
        assert "EvalSuite" in str(exc.value)

    @pytest.mark.anyio
    async def test_tenant_slug_is_followed_BY_SLUG_and_never_by_name(
        self, kernel, source, monkeypatch,
    ):
        """``TenantMembership.tenant_slug`` says ``by: slug`` — the target's
        REQUIRED spec field, not its ``metadata.name`` (which the reader sets
        from the bundle directory). The two agree today by filesystem
        convention, and following the NAME would be following that
        coincidence.

        Fatia 5 made the slug itself followable, so the assertion moved from
        "nothing was read" to "the SLUG was read and the name was not" — which
        is the claim that was always meant, and the one the old wording could
        not distinguish from doing nothing at all."""
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        source.reads.clear()
        source.key_reads.clear()
        await kernel.write_instance(
            "proj", "TenantMembership", "acme--a-example-com",
            {
                "apiVersion": "github.com/ruinosus/dna/tenant/v1",
                "kind": "TenantMembership",
                "metadata": {"name": "acme--a-example-com"},
                "spec": {
                    "tenant_slug": "no-such-tenant",
                    "user_email": "a@example.com",
                    "role": "member",
                    "joined_at": "2026-08-06T00:00:00Z",
                },
            },
        )
        assert ("proj", "TenantMembership", "acme--a-example-com") in source.docs
        assert ("proj", "Tenant", "slug", "no-such-tenant") in source.key_reads
        assert [r for r in source.reads if r[1] == "Tenant"] == []
