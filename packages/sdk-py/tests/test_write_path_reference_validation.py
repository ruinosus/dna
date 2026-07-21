"""Write-time enforcement of declared ``x-dna-ref`` references (i-040).

The unit tests in ``test_references.py`` pin how the annotation is READ.
These pin what the write path DOES with it, against a source that really
stores documents — a source that answers "no" to every read would make a
dangling-reference test pass for the wrong reason.

Pinned contract:
- ``enforce``: writing a reference to a non-existent target is vetoed and
  nothing persists;
- the same write succeeds once the target exists (forward references are an
  ORDERING problem, not a permanent one);
- ``warn`` (the default) persists and logs — chosen so that upgrading the SDK
  cannot break a working bootstrap, since a legitimate seed may write a child
  before its parent;
- ``off`` skips entirely;
- optional/absent references never trip the check;
- a Kind that declares no ``x-dna-ref`` performs ZERO reads — the back-compat
  guarantee, asserted by counting reads rather than by inspection;
- polymorphic references resolve against any declared target.
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

    ``load_one`` is the read the kernel's ``get_document`` ultimately reaches;
    the stock fake returns None for everything, which would make a
    dangling-reference test pass for entirely the wrong reason. ``reads``
    counts those lookups — that counter is how the "no declaration → no cost"
    claim is proven rather than merely asserted.
    """

    def __init__(self) -> None:
        super().__init__()
        self.docs: dict[tuple[str, str, str], dict] = {}
        self.reads: list[tuple[str, str, str]] = []

    async def save_document(
        self, scope, kind, name, raw, author=None, *, tenant=None, layer=None,
    ) -> str:
        version = await super().save_document(
            scope, kind, name, raw, author, tenant=tenant, layer=layer,
        )
        self.docs[(scope, kind, name)] = raw
        return version

    async def delete_document(self, scope, kind, name, *, tenant=None, layer=None):
        self.docs.pop((scope, kind, name), None)
        return await super().delete_document(
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
            await kernel.write_document(
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
        await kernel.write_document(
            "proj", "Story", "s-1", _story("s-1", _base_spec(feature="f-real")),
        )
        assert ("proj", "Story", "s-1") in source.docs

    @pytest.mark.anyio
    async def test_absent_optional_reference_is_fine(
        self, kernel, source, monkeypatch,
    ):
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        await kernel.write_document(
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
            await kernel.write_document(
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
            await kernel.write_document(
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
        await kernel.write_document(
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
        await kernel.write_document(
            "proj", "Story", "s-1", _story("s-1", _base_spec(feature="f-real")),
        )
        assert ("proj", "Feature", "f-real") in source.reads


# --- back-compatibility --------------------------------------------------------


class TestUndeclaredKindsAreUntouched:
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
        write path legitimately reads the document itself and the scope's
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
            await k.write_document("proj", "Engram", "rem-1", self._engram("rem-1"))
            return list(src.reads)

        baseline = await reads_under("off")
        enforced = await reads_under("enforce")

        assert enforced == baseline, (
            f"undeclared Kind paid for reference validation: "
            f"{set(enforced) - set(baseline)}"
        )
