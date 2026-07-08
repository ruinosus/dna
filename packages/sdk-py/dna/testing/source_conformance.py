"""Source-adapter conformance kit (s-dna-source-conformance-kit).

The behavioral counterpart of the ``kernel.source()`` boot gate. The gate
checks that the SourcePort surface exists BY NAME (``runtime_checkable``
Protocols can't do more); THIS suite checks that the surface BEHAVES —
capability-aware: every case reads the adapter's declared
``SourceCapabilities`` and

  * SKIPS when the adapter honestly doesn't declare the capability, and
  * FAILS when the adapter declares a capability it doesn't honor.

Consumption contract
--------------------

``source_conformance_suite(factory)`` returns a list of
:class:`ConformanceCase`. Each ``case.run()`` builds a FRESH adapter via
``factory`` (isolation between cases), runs its assertions, and always
awaits the factory-provided cleanup.

``factory`` is an async callable returning ``(source, cleanup)`` where
``cleanup`` is an async zero-arg callable or ``None``. The factory owns
the environment: temp dirs, DB schemas, kernel wiring
(``Kernel.auto(source=src)``) where the adapter needs it, and — for
READ-ONLY sources — pre-seeding the canonical fixture (see
:func:`fixture_docs`) into the backing store under :data:`FIXTURE_SCOPE`.
Writable sources are seeded by the kit itself through their own write
surface (``save_document`` + ``publish``), which is part of what's being
tested.

Cases raise :class:`CaseNotApplicable` (a ``unittest.SkipTest`` subclass,
so pytest and unittest both report a skip) when the adapter doesn't
declare the required capability.
"""
from __future__ import annotations

import inspect
import unittest
from dataclasses import dataclass, replace
from typing import Any, Awaitable, Callable

from dna.kernel.capabilities import (
    SourceCapabilities,
    derive_capabilities,
    source_capabilities,
)
from dna.kernel.protocols import missing_source_port_members

#: The scope name every conformance fixture lives in. Read-only factories
#: MUST make :func:`fixture_docs` visible under this scope.
FIXTURE_SCOPE = "conformance-kit"

SourceCleanup = Callable[[], Awaitable[None]]
SourceFactory = Callable[[], Awaitable[tuple[Any, SourceCleanup | None]]]


class CaseNotApplicable(unittest.SkipTest):
    """Raised by a case when the adapter doesn't declare the capability
    the case exercises. pytest/unittest report it as a skip."""


def fixture_docs() -> list[dict[str, Any]]:
    """The canonical fixture: 1 Genome + 3 Story records.

    Writable adapters get these written through their own API; read-only
    factories must install them in their native storage (YAML files on
    disk, JSON objects in a bucket, rows in a table, ...).
    """
    docs: list[dict[str, Any]] = [{
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": FIXTURE_SCOPE},
        "spec": {"owner": "source-conformance-kit"},
    }]
    for name, priority in (("s-alpha", 1), ("s-bravo", 10), ("s-charlie", 100)):
        docs.append({
            "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
            "kind": "Story",
            "metadata": {"name": name},
            "spec": {"title": name, "priority": priority},
        })
    return docs


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

async def _aw(value: Any) -> Any:
    """Await ``value`` if awaitable (bundle-entry methods are sync on FS,
    async on the SQL adapters — the capability Protocols permit both)."""
    return await value if inspect.isawaitable(value) else value


async def _rows(it: Any) -> list:
    """Materialize an async OR sync iterator (``query`` return shape)."""
    if hasattr(it, "__aiter__"):
        return [r async for r in it]
    return list(it)


def _doc_name(raw: dict) -> str | None:
    meta = raw.get("metadata") or {}
    return meta.get("name") or raw.get("name")


class _Ctx:
    """Per-case context: fresh source + resolved capabilities."""

    def __init__(self, source: Any, caps: SourceCapabilities) -> None:
        self.source = source
        self.caps = caps

    @property
    def writable(self) -> bool:
        return callable(getattr(self.source, "save_document", None)) and \
            callable(getattr(self.source, "delete_document", None))

    async def publish(self, kind: str, name: str, *, tenant: str | None = None) -> None:
        """Publish if the adapter has a draft stage (write-through
        adapters no-op). PG's publish is tenant-aware; SQLite's isn't —
        forward ``tenant`` only when the signature accepts it."""
        pub = getattr(self.source, "publish", None)
        if not callable(pub):
            return
        if tenant is not None and "tenant" in _params(pub):
            await _aw(pub(FIXTURE_SCOPE, kind, name, tenant=tenant))
        else:
            await _aw(pub(FIXTURE_SCOPE, kind, name))

    async def seed_fixture(self) -> None:
        """Make :func:`fixture_docs` visible in :data:`FIXTURE_SCOPE`.

        Writable adapter → write through its own API. Read-only adapter →
        verify the factory pre-seeded; fail with a didactic message if not.
        """
        if self.writable:
            for raw in fixture_docs():
                kind, name = raw["kind"], _doc_name(raw)
                await _aw(self.source.save_document(FIXTURE_SCOPE, kind, name, raw))
                await self.publish(kind, name)
            return
        loaded = await _aw(self.source.load_all(FIXTURE_SCOPE, None))
        names = {_doc_name(d) for d in loaded}
        missing = {_doc_name(d) for d in fixture_docs()} - names
        assert not missing, (
            f"read-only source factory must pre-seed fixture_docs() under "
            f"scope {FIXTURE_SCOPE!r} in the adapter's native storage — "
            f"missing: {sorted(missing)}. (Writable adapters are seeded by "
            f"the kit through save_document; read-only ones can't be.)"
        )


def _params(fn: Any) -> set[str]:
    try:
        return set(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        return set()


# ---------------------------------------------------------------------------
# cases — each is ``async def _case_x(ctx)``; requirement predicates below
# ---------------------------------------------------------------------------

async def _case_port_surface(ctx: _Ctx) -> None:
    """Core SourcePort members present; declared capabilities imply the
    matching members (a declaration without the method is a lie)."""
    missing_core, _ = missing_source_port_members(ctx.source)
    assert not missing_core, (
        f"{type(ctx.source).__name__} is missing CORE SourcePort member(s): "
        f"{missing_core} — see docs/PORT-CONTRACT.md."
    )
    caps = ctx.caps
    implied = {
        "list_doc_refs": caps.granular_list,
        "load_one": caps.granular_one,
        "query": caps.query_pushdown,
        "count": caps.query_pushdown,
        "load_drafts": caps.drafts,
        "publish": caps.drafts,
        "get_version": caps.versions,
        "fetch_bundle_entry": caps.bundle_read,
        "write_bundle_entry": caps.bundle_write,
        "attach_kernel": caps.kernel_attachable,
    }
    lies = [m for m, declared in implied.items()
            if declared and not callable(getattr(ctx.source, m, None))]
    assert not lies, (
        f"{type(ctx.source).__name__} DECLARES capabilities whose methods "
        f"don't exist: {lies}. Fix the adapter or its capabilities()."
    )


async def _case_capabilities_honest(ctx: _Ctx) -> None:
    """declared capabilities() == reflection oracle (same invariant as the
    in-repo test_source_capabilities_conformance, generalized)."""
    declared = ctx.caps
    oracle = derive_capabilities(ctx.source, label=declared.source)
    assert declared == replace(oracle, source=declared.source), (
        f"{type(ctx.source).__name__} declares capabilities that diverge "
        f"from what it implements:\n  declared: {declared}\n"
        f"  oracle:   {oracle}"
    )


async def _case_load_bootstrap_docs(ctx: _Ctx) -> None:
    await ctx.seed_fixture()
    docs = await _aw(ctx.source.load_bootstrap_docs(FIXTURE_SCOPE))
    assert isinstance(docs, list)
    pkgs = [d for d in docs if d.get("kind") == "Genome"]
    assert pkgs and _doc_name(pkgs[0]) == FIXTURE_SCOPE, (
        f"load_bootstrap_docs must surface the scope Genome "
        f"(got kinds: {[d.get('kind') for d in docs]})"
    )


async def _case_load_all_round_trip(ctx: _Ctx) -> None:
    await ctx.seed_fixture()
    docs = await _aw(ctx.source.load_all(FIXTURE_SCOPE, None))
    by_name = {_doc_name(d): d for d in docs}
    for expected in fixture_docs():
        name = _doc_name(expected)
        assert name in by_name, f"doc {name!r} lost in round-trip"
        got = by_name[name]
        assert got.get("kind") == expected["kind"]
        for key, val in expected["spec"].items():
            assert (got.get("spec") or {}).get(key) == val, (
                f"{name}: spec.{key} lost/mutated in round-trip "
                f"(expected {val!r}, got {(got.get('spec') or {}).get(key)!r})"
            )


async def _case_resolve_ref_returns_str(ctx: _Ctx) -> None:
    out = await _aw(ctx.source.resolve_ref(FIXTURE_SCOPE, "does-not-exist.md"))
    assert isinstance(out, str), (
        f"resolve_ref must return str even on miss (got {type(out).__name__})"
    )


async def _case_load_layer_unknown_is_empty(ctx: _Ctx) -> None:
    out = await _aw(ctx.source.load_layer(
        FIXTURE_SCOPE, "env", "no-such-layer-value", None,
    ))
    assert out == [] or out is None or out == {}, (
        f"load_layer on a nonexistent layer must be empty, got {out!r}"
    )


async def _case_close_returns(ctx: _Ctx) -> None:
    result = await _aw(ctx.source.close())
    assert result is None, "close() must return None"


async def _case_list_doc_refs(ctx: _Ctx) -> None:
    await ctx.seed_fixture()
    refs = await _aw(ctx.source.list_doc_refs(FIXTURE_SCOPE))
    pairs = {(k, n) for k, n in refs}
    assert ("Story", "s-alpha") in pairs and ("Genome", FIXTURE_SCOPE) in pairs, (
        f"list_doc_refs missing seeded docs: {sorted(pairs)}"
    )
    stories = await _aw(ctx.source.list_doc_refs(FIXTURE_SCOPE, kind="Story"))
    kinds = {k for k, _ in stories}
    assert kinds == {"Story"}, f"kind filter leaked other kinds: {kinds}"
    assert len(list(stories)) == 3


async def _case_load_one(ctx: _Ctx) -> None:
    await ctx.seed_fixture()
    doc = await _aw(ctx.source.load_one(FIXTURE_SCOPE, "Story", "s-alpha"))
    assert doc is not None and (doc.get("spec") or {}).get("priority") == 1
    miss = await _aw(ctx.source.load_one(FIXTURE_SCOPE, "Story", "no-such-doc"))
    assert miss is None, f"load_one miss must be None, got {miss!r}"


async def _case_query_pushdown(ctx: _Ctx) -> None:
    await ctx.seed_fixture()
    gt9 = await _rows(ctx.source.query(
        FIXTURE_SCOPE, "Story", filter={"priority": {"gt": 9}},
    ))
    names = {_doc_name(d) for d in gt9}
    assert names == {"s-bravo", "s-charlie"}, (
        f"numeric gt pushdown broken (9-vs-10 case): {sorted(names)}"
    )
    top = await _rows(ctx.source.query(
        FIXTURE_SCOPE, "Story", order_by=["-name"], limit=1,
    ))
    assert [_doc_name(d) for d in top] == ["s-charlie"], (
        f"order_by/limit pushdown broken: {[_doc_name(d) for d in top]}"
    )


async def _case_count_pushdown(ctx: _Ctx) -> None:
    await ctx.seed_fixture()
    out = await _aw(ctx.source.count(FIXTURE_SCOPE, "Story"))
    assert isinstance(out, dict) and out.get("total") == 3, (
        f"count must return {{'total': 3, ...}} for the fixture, got {out!r}"
    )


async def _case_save_then_visible(ctx: _Ctx) -> None:
    await ctx.seed_fixture()
    raw = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Story",
        "metadata": {"name": "s-kit-new"},
        "spec": {"title": "s-kit-new", "priority": 7},
    }
    version = await _aw(ctx.source.save_document(
        FIXTURE_SCOPE, "Story", "s-kit-new", raw,
    ))
    assert isinstance(version, str) and version, (
        f"save_document must return a non-empty version id str, got {version!r}"
    )
    await ctx.publish("Story", "s-kit-new")
    docs = await _aw(ctx.source.load_all(FIXTURE_SCOPE, None))
    assert "s-kit-new" in {_doc_name(d) for d in docs}, (
        "saved+published doc not visible in load_all"
    )


async def _case_delete_removes(ctx: _Ctx) -> None:
    await ctx.seed_fixture()
    await _aw(ctx.source.delete_document(FIXTURE_SCOPE, "Story", "s-alpha"))
    docs = await _aw(ctx.source.load_all(FIXTURE_SCOPE, None))
    assert "s-alpha" not in {_doc_name(d) for d in docs}, (
        "deleted doc still visible in load_all"
    )


async def _case_declared_write_kwargs_accepted(ctx: _Ctx) -> None:
    """Every kwarg the adapter DECLARES in write_kwargs/delete_kwargs must
    be accepted without TypeError — declared-but-rejected is a lie."""
    await ctx.seed_fixture()
    values: dict[str, Any] = {
        "author": "conformance-kit", "tenant": None, "layer": None,
        "write_class": "substantive", "version_retention": None,
    }
    save_kwargs = {k: values[k] for k in ctx.caps.write_kwargs}
    raw = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Story",
        "metadata": {"name": "s-kit-kwargs"},
        "spec": {"title": "s-kit-kwargs", "priority": 0},
    }
    try:
        await _aw(ctx.source.save_document(
            FIXTURE_SCOPE, "Story", "s-kit-kwargs", raw, **save_kwargs,
        ))
    except TypeError as e:  # pragma: no cover — the failure being tested
        raise AssertionError(
            f"save_document rejected DECLARED write_kwargs "
            f"{sorted(ctx.caps.write_kwargs)}: {e}"
        ) from e
    # promote the draft first — drafting adapters only delete published docs
    await ctx.publish("Story", "s-kit-kwargs")
    delete_kwargs = {k: values[k] for k in ctx.caps.delete_kwargs}
    try:
        await _aw(ctx.source.delete_document(
            FIXTURE_SCOPE, "Story", "s-kit-kwargs", **delete_kwargs,
        ))
    except TypeError as e:  # pragma: no cover
        raise AssertionError(
            f"delete_document rejected DECLARED delete_kwargs "
            f"{sorted(ctx.caps.delete_kwargs)}: {e}"
        ) from e


async def _case_list_scopes(ctx: _Ctx) -> None:
    await ctx.seed_fixture()
    scopes = await _aw(ctx.source.list_scopes())
    assert FIXTURE_SCOPE in scopes, (
        f"list_scopes must include the seeded scope, got {scopes!r}"
    )


async def _case_drafts_lifecycle(ctx: _Ctx) -> None:
    """drafts=True → an unpublished save is staged (visible in load_drafts
    OR — for write-through adapters — already in load_all), and publish
    promotes it into load_all."""
    await ctx.seed_fixture()
    raw = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Story",
        "metadata": {"name": "s-kit-draft"},
        "spec": {"title": "s-kit-draft", "priority": 2},
    }
    await _aw(ctx.source.save_document(FIXTURE_SCOPE, "Story", "s-kit-draft", raw))
    drafts = await _aw(ctx.source.load_drafts(FIXTURE_SCOPE))
    published = await _aw(ctx.source.load_all(FIXTURE_SCOPE, None))
    staged = {_doc_name(d) for d in drafts} | {_doc_name(d) for d in published}
    assert "s-kit-draft" in staged, (
        "saved doc neither in load_drafts nor load_all — write went nowhere"
    )
    await ctx.publish("Story", "s-kit-draft")
    docs = await _aw(ctx.source.load_all(FIXTURE_SCOPE, None))
    assert "s-kit-draft" in {_doc_name(d) for d in docs}, (
        "publish() did not promote the draft into load_all"
    )


async def _case_versions_surface(ctx: _Ctx) -> None:
    """versions=True → list_versions returns a list after repeated saves;
    when history exists, get_version resolves a listed id. History DEPTH
    is adapter-specific (the write-through FS keeps none — an empty list
    is conformant; an exception is not)."""
    await ctx.seed_fixture()
    for title in ("v1", "v2"):
        raw = {
            "apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Story",
            "metadata": {"name": "s-kit-ver"},
            "spec": {"title": title, "priority": 3},
        }
        await _aw(ctx.source.save_document(FIXTURE_SCOPE, "Story", "s-kit-ver", raw))
        await ctx.publish("Story", "s-kit-ver")
    versions = await _aw(ctx.source.list_versions(FIXTURE_SCOPE, "Story", "s-kit-ver"))
    assert isinstance(versions, list), (
        f"list_versions must return a list, got {type(versions).__name__}"
    )
    if versions:
        # Version-id vocabulary differs per adapter today (SQLite resolves
        # the `version` number, PG a `version_id`) — accept any listed id
        # that get_version resolves; fail only when NONE resolves.
        row = versions[0]
        candidates = [row[k] for k in ("version_id", "version", "id") if row.get(k) is not None]
        assert candidates, f"list_versions rows carry no id field: {row!r}"
        errors: list[str] = []
        for vid in candidates:
            try:
                got = await _aw(ctx.source.get_version(
                    FIXTURE_SCOPE, "Story", "s-kit-ver", str(vid),
                ))
            except Exception as e:  # noqa: BLE001 — try the next id shape
                errors.append(f"{vid!r}: {type(e).__name__}: {e}")
                continue
            assert isinstance(got, dict), "get_version must return the raw dict"
            break
        else:
            raise AssertionError(
                f"get_version resolved NONE of the ids listed by "
                f"list_versions ({errors}) — list/get are inconsistent"
            )


async def _case_tenant_overlay_shadows_base(ctx: _Ctx) -> None:
    """First-class tenant writes: the overlay shadows the base on
    tenant-scoped reads and NEVER leaks into base reads."""
    await ctx.seed_fixture()

    async def _save(layer: str, tenant: str | None) -> None:
        raw = {
            "apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Story",
            "metadata": {"name": "s-kit-over"},
            "spec": {"title": "s-kit-over", "layer": layer},
        }
        await _aw(ctx.source.save_document(
            FIXTURE_SCOPE, "Story", "s-kit-over", raw, tenant=tenant,
        ))
        await ctx.publish("Story", "s-kit-over", tenant=tenant)

    await _save("base", None)
    await _save("acme", "acme")

    async def _layer_for(tenant: str | None) -> str | None:
        doc = await _aw(ctx.source.load_one(
            FIXTURE_SCOPE, "Story", "s-kit-over", tenant=tenant,
        ))
        return (doc.get("spec") or {}).get("layer") if doc else None

    assert await _layer_for("acme") == "acme", "tenant overlay must shadow base"
    assert await _layer_for(None) == "base", "overlay leaked into the base layer"


async def _case_bundle_entry_round_trip(ctx: _Ctx) -> None:
    """bundle_write+bundle_read → str AND bytes entries round-trip;
    a missing entry raises FileNotFoundError (uniform error contract)."""
    if ctx.writable:
        raw = {
            "apiVersion": "agentskills.io/v1", "kind": "Skill",
            "metadata": {"name": "kit-bundle"},
            "spec": {"name": "kit-bundle", "description": "kit",
                     "instruction": "x"},
        }
        await _aw(ctx.source.save_document(FIXTURE_SCOPE, "Skill", "kit-bundle", raw))
        await ctx.publish("Skill", "kit-bundle")
    await _aw(ctx.source.write_bundle_entry(
        FIXTURE_SCOPE, "Skill", "kit-bundle", "notes.txt", "olá — kit",
        kind="Skill",
    ))
    await _aw(ctx.source.write_bundle_entry(
        FIXTURE_SCOPE, "Skill", "kit-bundle", "blob.bin", b"\x00\x01\xff",
        kind="Skill",
    ))
    txt = await _aw(ctx.source.fetch_bundle_entry(
        FIXTURE_SCOPE, "Skill", "kit-bundle", "notes.txt", kind="Skill",
    ))
    assert txt == "olá — kit".encode("utf-8")
    blob = await _aw(ctx.source.fetch_bundle_entry(
        FIXTURE_SCOPE, "Skill", "kit-bundle", "blob.bin", kind="Skill",
    ))
    assert blob == b"\x00\x01\xff"
    try:
        await _aw(ctx.source.fetch_bundle_entry(
            FIXTURE_SCOPE, "Skill", "kit-bundle", "no-such-entry.json",
            kind="Skill",
        ))
    except FileNotFoundError:
        pass
    else:
        raise AssertionError(
            "fetch_bundle_entry on a missing entry must raise FileNotFoundError"
        )


async def _case_schema_migrations_idempotent(ctx: _Ctx) -> None:
    """SQL-backed adapters (docs/PORT-CONTRACT.md § "Schema migrations"):
    ``run_schema_migrations()`` returns the list of versions applied by
    that call, and a SECOND run right after is a no-op (``[]``) — the
    control table persisted in the backing store makes re-boot
    idempotent. Adapters without persistent SQL storage don't expose the
    method and skip."""
    first = await _aw(ctx.source.run_schema_migrations())
    assert isinstance(first, list) and all(isinstance(v, int) for v in first), (
        f"run_schema_migrations must return list[int] of versions applied "
        f"by the call, got {first!r}"
    )
    second = await _aw(ctx.source.run_schema_migrations())
    assert second == [], (
        f"re-running migrations on an up-to-date store must apply NOTHING "
        f"(control table must record every applied version) — got {second!r}"
    )


# ---------------------------------------------------------------------------
# requirement predicates — (human label, predicate over (_Ctx))
# ---------------------------------------------------------------------------

def _always(ctx: _Ctx) -> bool:
    return True


def _writable(ctx: _Ctx) -> bool:
    return ctx.writable


_CASES: list[tuple[str, str, Callable[[_Ctx], Any], Callable[[_Ctx], bool]]] = [
    # (name, requires-label, fn, predicate)
    ("port_surface", "always", _case_port_surface, _always),
    ("capabilities_declared_honestly", "always", _case_capabilities_honest, _always),
    ("load_bootstrap_docs_surfaces_package", "always", _case_load_bootstrap_docs, _always),
    ("load_all_round_trip", "always", _case_load_all_round_trip, _always),
    ("resolve_ref_returns_str", "always", _case_resolve_ref_returns_str, _always),
    ("load_layer_unknown_is_empty", "always", _case_load_layer_unknown_is_empty, _always),
    ("close_returns_none", "always", _case_close_returns, _always),
    ("list_doc_refs_and_kind_filter", "capabilities.granular_list",
     _case_list_doc_refs, lambda c: c.caps.granular_list),
    ("load_one_hit_and_miss", "capabilities.granular_one",
     _case_load_one, lambda c: c.caps.granular_one),
    ("query_numeric_gt_order_limit", "capabilities.query_pushdown",
     _case_query_pushdown, lambda c: c.caps.query_pushdown),
    ("count_total", "capabilities.query_pushdown",
     _case_count_pushdown, lambda c: c.caps.query_pushdown),
    ("save_then_visible", "writable", _case_save_then_visible, _writable),
    ("delete_removes", "writable", _case_delete_removes, _writable),
    ("declared_write_kwargs_accepted", "writable",
     _case_declared_write_kwargs_accepted,
     lambda c: c.writable and bool(c.caps.write_kwargs or c.caps.delete_kwargs)),
    ("list_scopes_includes_fixture", "writable", _case_list_scopes,
     lambda c: c.writable and callable(getattr(c.source, "list_scopes", None))),
    ("drafts_lifecycle", "writable + capabilities.drafts",
     _case_drafts_lifecycle, lambda c: c.writable and c.caps.drafts),
    ("versions_surface", "writable + capabilities.versions",
     _case_versions_surface, lambda c: c.writable and c.caps.versions),
    ("tenant_overlay_shadows_base",
     "writable + 'tenant' in write_kwargs + capabilities.granular_one",
     _case_tenant_overlay_shadows_base,
     lambda c: c.writable and "tenant" in c.caps.write_kwargs and c.caps.granular_one),
    ("bundle_entry_round_trip", "capabilities.bundle_read + bundle_write",
     _case_bundle_entry_round_trip,
     lambda c: c.caps.bundle_read and c.caps.bundle_write),
    # Duck-typed on the method (same pattern as list_scopes): SQL-backed
    # adapters expose run_schema_migrations(); FS/S3/proxy sources don't.
    ("schema_migrations_idempotent", "run_schema_migrations (SQL-backed schema)",
     _case_schema_migrations_idempotent,
     lambda c: callable(getattr(c.source, "run_schema_migrations", None))),
]


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConformanceCase:
    """One runnable conformance case bound to an adapter factory."""

    name: str
    requires: str
    factory: SourceFactory
    capabilities: SourceCapabilities | None
    _fn: Callable[[_Ctx], Any]
    _predicate: Callable[[_Ctx], bool]

    async def run(self) -> None:
        """Build a fresh source, check applicability, run, always cleanup.

        Raises :class:`CaseNotApplicable` (skip) when the adapter doesn't
        declare the capability this case exercises; ``AssertionError``
        when a declared capability isn't honored.
        """
        built = await self.factory()
        source, cleanup = built if isinstance(built, tuple) else (built, None)
        try:
            caps = self.capabilities or source_capabilities(source)
            ctx = _Ctx(source, caps)
            if not self._predicate(ctx):
                raise CaseNotApplicable(
                    f"{type(source).__name__} does not declare "
                    f"[{self.requires}] — case not applicable."
                )
            await self._fn(ctx)
        finally:
            if cleanup is not None:
                await _aw(cleanup())

    def __repr__(self) -> str:  # readable pytest ids
        return f"ConformanceCase({self.name})"


def source_conformance_suite(
    factory: SourceFactory,
    *,
    capabilities: SourceCapabilities | None = None,
) -> list[ConformanceCase]:
    """THE public conformance suite for Source adapters.

    Args:
        factory: async zero-arg callable returning ``(source, cleanup)``
            (``cleanup`` async zero-arg or ``None``). Called once PER CASE
            — each case runs against a fresh adapter. The factory owns
            environment setup (temp dirs, DB schemas, kernel wiring) and,
            for read-only sources, pre-seeding :func:`fixture_docs` under
            :data:`FIXTURE_SCOPE`.
        capabilities: explicit ``SourceCapabilities`` override. Default:
            read from the built source (declared ``capabilities()``, with
            the deprecated reflection fallback for legacy adapters).

    Returns:
        list of :class:`ConformanceCase` — parametrize them in pytest
        (``ids=lambda c: c.name``) and ``await case.run()``.
    """
    return [
        ConformanceCase(
            name=name, requires=requires, factory=factory,
            capabilities=capabilities, _fn=fn, _predicate=pred,
        )
        for name, requires, fn, pred in _CASES
    ]


@dataclass
class ConformanceReport:
    """Outcome of :func:`run_source_conformance` (non-pytest consumption)."""

    passed: list[str]
    failed: list[tuple[str, str]]      # (case name, error repr)
    skipped: list[tuple[str, str]]     # (case name, reason)

    @property
    def ok(self) -> bool:
        return not self.failed

    def raise_if_failed(self) -> None:
        if self.failed:
            lines = "\n".join(f"  - {n}: {e}" for n, e in self.failed)
            raise AssertionError(
                f"source conformance failed {len(self.failed)} case(s):\n{lines}"
            )


async def run_source_conformance(
    factory: SourceFactory,
    *,
    capabilities: SourceCapabilities | None = None,
) -> ConformanceReport:
    """Run the whole suite programmatically (scripts, CI without pytest)."""
    report = ConformanceReport(passed=[], failed=[], skipped=[])
    for case in source_conformance_suite(factory, capabilities=capabilities):
        try:
            await case.run()
        except CaseNotApplicable as skip:
            report.skipped.append((case.name, str(skip)))
        except Exception as exc:  # noqa: BLE001 — reported, not swallowed
            report.failed.append((case.name, f"{type(exc).__name__}: {exc}"))
        else:
            report.passed.append(case.name)
    return report
