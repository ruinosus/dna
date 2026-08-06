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


class TestKeyAddressedRelationsAreNotFollowed:
    """``Project.workspace_id`` declares ``to: Workspace, by: workspace_id``.

    Declaring the addressing must install NO resolution rule. Resolving by key
    needs an expression index the store does not have, and — measured — a
    second rule beside a live one can veto data the live one accepts
    (``kernel.tier()`` resolves a PricingPlan by ``tier_id`` and THEN by
    ``aliases[]``; a declaration honouring only the first would refuse a valid
    alias). These tests are what stops that arriving by accident.
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
    async def test_enforce_does_not_even_LOOK_the_target_up(
        self, kernel, source, monkeypatch,
    ):
        """The sharper assertion: not "it did not refuse" but "it did not
        ask". A lookup that happened would be a resolution rule in waiting."""
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        source.reads.clear()
        await kernel.write_instance(
            "proj", "Project", "p-1", self._project("p-1", "ws-1"),
            tenant="acme",
        )
        assert [r for r in source.reads if r[1] == "Workspace"] == []


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
    async def test_tenant_slug_is_declared_and_still_not_followed(
        self, kernel, source, monkeypatch,
    ):
        """``TenantMembership.tenant_slug`` says ``by: slug`` — the target's
        REQUIRED spec field, not its ``metadata.name`` (which the reader sets
        from the bundle directory). The two agree today by filesystem
        convention; if this ever starts resolving, the write path has begun
        following a coincidence."""
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        source.reads.clear()
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
        assert [r for r in source.reads if r[1] == "Tenant"] == []
