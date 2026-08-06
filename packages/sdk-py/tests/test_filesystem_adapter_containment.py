"""The filesystem adapter refuses a path that leaves its own base directory.

THE SECOND LAYER, and tested at the adapter ON PURPOSE — every test here calls
``FilesystemWritableSource`` / ``FilesystemSource`` methods DIRECTLY, never
``Kernel.write_instance`` / ``Kernel.fetch_bundle_entry``. A test that went
through the kernel would only re-prove the kernel guard
(``validate_instance_name`` / ``validate_scope_name``, see
``test_document_name_path_safety.py``) and would pass whether or not this layer
existed at all.

Why two layers, since the kernel guard already refuses the same names: the
kernel guard is the primary seam and the one that can say WHICH input was
wrong, but the adapter is reachable without it. ``dna.kernel.source.sync``
calls ``save_instance`` directly today (benignly — its names come from the
source being copied, not from a request), the public conformance kit drives
adapters on purpose, and a path-building adapter that trusts its inputs is one
refactor away from re-opening the hole the write guard closed. The redundancy
is the design; see ``dna.kernel.errors.PathEscapesStoreRoot``.

Geometry is measured, not assumed — and the earlier version of this note was
OFF BY ONE, which is worth writing down because an off-by-one here is what
makes a path-safety test pass against vulnerable code. Counting from
``<sandbox>/outer/store/<scope>/<container>``:

    1 ``..`` → ``<store>/<scope>``   inside
    2 ``..`` → ``<store>``           inside, AT the root
    3 ``..`` → ``<sandbox>/outer``   ALREADY OUTSIDE the store
    4 ``..`` → ``<sandbox>``         outside

So only ``..`` counts of TWO OR FEWER are absorbed by the leading segments; the
old claim that "a shorter traversal … stays INSIDE the store" holds for 1–2 and
is false for 3. The fixtures below use FOUR and are correct as written — it was
the explanation that was wrong, not the tests. Every escaping fixture asserts
its own geometry first regardless, which is the only reason the error stayed
harmless.
"""
from __future__ import annotations

import asyncio

import pytest

from dna.adapters.filesystem.source import FilesystemSource
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.kernel.errors import KernelRefusal, PathEscapesStoreRoot

# ``<store>/<scope>/<container>/<name>`` with the store two levels under the
# sandbox: four ``..`` reach the sandbox itself.
ESCAPING_NAME = "../../../../ESCAPED"
#: ``<store>/<scope>`` → two ``..`` reach the sandbox.
ESCAPING_SCOPE = "../../ESCAPED"


def _store(tmp_path):
    store = tmp_path / "outer" / "store"
    (store / "test-mod" / "agents").mkdir(parents=True)
    return store


def _writable(tmp_path):
    """A REAL writable adapter with a kernel bound only so ``_subdir_for`` can
    resolve containers. Every call below goes to the adapter, not the kernel."""
    from dna.extensions.helix import HelixExtension
    from dna.kernel import Kernel

    store = _store(tmp_path)
    k = Kernel()
    k.load(HelixExtension())
    src = FilesystemWritableSource(str(store), kernel=k)
    src.attach_kernel(k)
    return src, store


def _raw(name: str) -> dict:
    return {
        "apiVersion": "helix.dna.dev/v1", "kind": "Agent",
        "metadata": {"name": name}, "spec": {"model": "gpt-4o"},
    }


def _assert_escapes(path, store):
    """Fail loudly if the fixture's traversal does NOT actually leave the store
    — a containment test built on a traversal that stays inside is a test that
    passes against vulnerable code."""
    with pytest.raises(ValueError):
        path.relative_to(store)


def _nothing_outside(store, tmp_path):
    outside = [
        p for p in tmp_path.rglob("*")
        if p.is_file() and store not in p.parents and p != store
    ]
    assert outside == [], f"files landed outside the store root: {outside}"


# ── the error's contract ────────────────────────────────────────────────────

def test_the_refusal_shares_the_kernel_marker_base():
    assert issubclass(PathEscapesStoreRoot, KernelRefusal)
    assert issubclass(PathEscapesStoreRoot, ValueError)


def test_the_refusal_names_the_offending_path_and_the_root():
    src = FilesystemSource("/tmp/does-not-need-to-exist")
    with pytest.raises(PathEscapesStoreRoot) as exc:
        src._contained(src.base_dir / ".." / ".." / "ESCAPED")
    msg = str(exc.value)
    assert "ESCAPED" in msg
    assert str(src.base_dir) in msg


# ── the WRITE side, at the adapter ──────────────────────────────────────────

def test_save_document_refuses_a_name_that_leaves_the_store(tmp_path):
    src, store = _writable(tmp_path)
    _assert_escapes((store / "test-mod" / "agents" / ESCAPING_NAME).resolve(), store)
    before = {p for p in tmp_path.rglob("*")}

    with pytest.raises(PathEscapesStoreRoot):
        asyncio.run(src.save_instance(
            "test-mod", "Agent", ESCAPING_NAME, _raw(ESCAPING_NAME),
        ))

    assert {p for p in tmp_path.rglob("*")} == before, "the adapter created files"
    _nothing_outside(store, tmp_path)


def test_save_document_refuses_a_scope_that_leaves_the_store(tmp_path):
    src, store = _writable(tmp_path)
    _assert_escapes((store / ESCAPING_SCOPE).resolve(), store)

    with pytest.raises(PathEscapesStoreRoot):
        asyncio.run(src.save_instance(
            ESCAPING_SCOPE, "Agent", "a-agent", _raw("a-agent"),
        ))
    _nothing_outside(store, tmp_path)


def test_delete_document_refuses_a_name_that_leaves_the_store(tmp_path):
    """The worse half: this one ``rmtree``s the directory it resolves to."""
    src, store = _writable(tmp_path)
    victim = tmp_path / "ESCAPED"
    victim.mkdir()
    (victim / "keep.txt").write_text("still here")

    with pytest.raises(PathEscapesStoreRoot):
        asyncio.run(src.delete_instance("test-mod", "Agent", ESCAPING_NAME))

    assert (victim / "keep.txt").is_file(), "the adapter deleted outside the store"


def test_save_manifest_refuses_a_scope_that_leaves_the_store(tmp_path):
    src, store = _writable(tmp_path)
    with pytest.raises(PathEscapesStoreRoot):
        asyncio.run(src.save_manifest(ESCAPING_SCOPE, {"kind": "Genome"}))
    _nothing_outside(store, tmp_path)


def test_write_bundle_entry_refuses_a_name_that_leaves_the_store(tmp_path):
    src, store = _writable(tmp_path)
    with pytest.raises(PathEscapesStoreRoot):
        src.write_bundle_entry("test-mod", "agents", ESCAPING_NAME, "AGENT.md", "pwned")
    _nothing_outside(store, tmp_path)


def test_delete_bundle_entry_refuses_a_name_that_leaves_the_store(tmp_path):
    src, _ = _writable(tmp_path)
    victim = tmp_path / "ESCAPED"
    victim.mkdir()
    (victim / "AGENT.md").write_text("still here")

    with pytest.raises(PathEscapesStoreRoot):
        src.delete_bundle_entry("test-mod", "agents", ESCAPING_NAME, "AGENT.md")
    assert (victim / "AGENT.md").is_file()


# ── the READ side, at the adapter ───────────────────────────────────────────

def test_fetch_bundle_entry_refuses_a_name_that_leaves_the_store(tmp_path):
    src, store = _writable(tmp_path)
    secret = tmp_path / "ESCAPED"
    secret.mkdir()
    (secret / "AGENT.md").write_text("TOP SECRET")
    _assert_escapes(secret, store)

    with pytest.raises(PathEscapesStoreRoot):
        src.fetch_bundle_entry("test-mod", "agents", ESCAPING_NAME, "AGENT.md")


def test_list_bundle_entries_refuses_a_name_that_leaves_the_store(tmp_path):
    src, _ = _writable(tmp_path)
    secret = tmp_path / "ESCAPED"
    secret.mkdir()
    (secret / "AGENT.md").write_text("TOP SECRET")

    with pytest.raises(PathEscapesStoreRoot):
        src.list_bundle_entries("test-mod", "agents", ESCAPING_NAME)


def test_load_all_refuses_a_scope_that_leaves_the_store(tmp_path):
    """``scope`` is the read-path sibling: it reaches ``base_dir / scope`` on
    EVERY read facade (``instance``, ``list_instances``, ``get_instance``,
    ``query`` …), which is why it is guarded here — one adapter-level check
    rather than a validator sprinkled over a dozen kernel read doors, and it
    covers the read door somebody adds tomorrow."""
    src, store = _writable(tmp_path)
    (tmp_path / "ESCAPED").mkdir()
    _assert_escapes((store / ESCAPING_SCOPE).resolve(), store)

    with pytest.raises(PathEscapesStoreRoot):
        asyncio.run(src.load_all(ESCAPING_SCOPE))


def test_resolve_ref_refuses_a_ref_that_leaves_the_store(tmp_path):
    """``resolve_ref`` reads ``base_dir / scope / ref`` and ``ref`` is a
    RELATIVE PATH by contract — so it cannot be a single component, and only a
    containment check can bound it."""
    src, store = _writable(tmp_path)
    (tmp_path / "secret.md").write_text("outside")

    with pytest.raises(PathEscapesStoreRoot):
        asyncio.run(src.resolve_ref("test-mod", "../../../secret.md"))


def test_load_layer_refuses_a_layer_value_that_leaves_the_store(tmp_path):
    """``_validate_layer_segments`` guards the WRITE path only — ``load_layer``
    never went through it."""
    src, _ = _writable(tmp_path)
    with pytest.raises(PathEscapesStoreRoot):
        asyncio.run(src.load_layer("test-mod", "branch", "../../../../ESCAPED"))
    with pytest.raises(PathEscapesStoreRoot):
        asyncio.run(src.load_layer(ESCAPING_SCOPE, "branch", "main"))


def test_list_layer_values_refuses_a_scope_that_leaves_the_store(tmp_path):
    src, _ = _writable(tmp_path)
    with pytest.raises(PathEscapesStoreRoot):
        asyncio.run(src.list_layer_values(ESCAPING_SCOPE, "branch"))


def test_get_module_version_refuses_a_version_that_leaves_the_store(tmp_path):
    """``version`` is a path component too — ``<scope_dir>/versions/<v>/``."""
    src, _ = _writable(tmp_path)
    with pytest.raises(PathEscapesStoreRoot):
        asyncio.run(src.get_module_version("test-mod", "../../../../ESCAPED"))


# ── the controls: containment must not become the bug ───────────────────────

def test_the_ordinary_write_read_delete_round_trip_still_works(tmp_path):
    """A guard that refused everything would pass every test above."""
    src, store = _writable(tmp_path)
    name = "t-1a2b3c.node.internal--Overlay"

    asyncio.run(src.save_instance("test-mod", "Agent", name, _raw(name)))
    written = [p for p in store.rglob("*") if p.is_file()]
    assert written, "the safe write must still land"
    assert all(store in p.parents for p in written)

    src.write_bundle_entry("test-mod", "agents", name, "extra.md", "# hi")
    assert src.fetch_bundle_entry("test-mod", "agents", name, "extra.md") == b"# hi"
    assert "extra.md" in src.list_bundle_entries("test-mod", "agents", name)
    assert src.delete_bundle_entry("test-mod", "agents", name, "extra.md") is True

    # readers= explicitly: ``load_all``'s default is "no readers", which sees
    # YAML files only and would never detect a bundle Kind.
    docs = asyncio.run(src.load_all("test-mod", readers=src._effective_readers()))
    assert any(d.get("metadata", {}).get("name") == name for d in docs)

    asyncio.run(src.delete_instance("test-mod", "Agent", name))
    assert not (store / "test-mod" / "agents" / name).exists()


def test_a_dotted_and_double_hyphen_name_is_still_contained(tmp_path):
    """The rule is "cannot escape", not "looks like an identifier" — ``.`` and
    ``--`` in a name must survive the resolve/relative_to round trip."""
    src, store = _writable(tmp_path)
    for name in ("t-1a2b3c.node.internal", "t-1a2b3c.node.internal--Overlay",
                 "1.0.0", "i-065-layerpolicy-missing", "s-foo-bar"):
        root = src._bundle_root("test-mod", "agents", name)
        assert root.relative_to(store), name


def test_a_tenant_scoped_write_is_still_contained(tmp_path):
    """The tenant layout adds three segments before the scope; the containment
    check must not mistake it for an escape."""
    src, store = _writable(tmp_path)
    asyncio.run(src.save_instance(
        "test-mod", "Agent", "a-agent", _raw("a-agent"), tenant="t-1a2b3c",
    ))
    written = [p for p in store.rglob("*") if p.is_file()]
    assert written and all(store in p.parents for p in written)
    assert any("tenants" in p.parts for p in written)


# ── the cache adapter, found by the corrected sweep ─────────────────────────
#
# The previous sweep was anchored on ``grep "base_dir /"``. Every finding it
# produced was right, but the grep is structurally blind to a join on a DERIVED
# root — ``self._base / scope / key`` never mentions ``base_dir``, and neither
# does ``self._root / entry``, which is how the content-derived bundle-entry
# escape was missed entirely. Re-run as "every ``Path.__truediv__`` /
# ``os.path.join`` whose right operand is not a literal", ``FilesystemCache``
# is the one remaining adapter that joins caller-influenced segments with no
# containment at all — and its segments arrive from further away than the
# source adapter's do.

def _cache(tmp_path):
    from dna.adapters.filesystem.cache import FilesystemCache

    base = tmp_path / "outer" / "store"
    base.mkdir(parents=True)
    cache = FilesystemCache(str(base))
    return cache, tmp_path / "outer" / ".dna-cache"


def test_the_cache_refuses_a_remote_derived_item_name_that_escapes(tmp_path):
    """``item.name`` and ``item.kind`` are read STRAIGHT OUT OF REMOTE JSON by
    ``HttpResolver`` (``raw["metadata"]["name"]``, ``raw["kind"]``) and land in
    a ``shutil.copytree`` destination — after an ``rmtree`` of that same
    destination, which is the worse half. Nothing abuses it today; this is the
    layer that means nothing can."""
    from dna.kernel.protocols import CacheItem

    cache, cache_root = _cache(tmp_path)
    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "AGENT.md").write_text("x")
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "KEEP.md").write_text("must survive")

    item = CacheItem(name="../../../../victim", kind="", content_path=payload)
    with pytest.raises(PathEscapesStoreRoot):
        asyncio.run(cache.store("test-mod", "http-abc", [item]))

    assert (victim / "KEEP.md").read_text() == "must survive", (
        "the rmtree ran before containment did"
    )
    del cache_root


def test_the_cache_refuses_an_escaping_scope_on_read_and_write(tmp_path):
    cache, _ = _cache(tmp_path)
    for call in (
        lambda: asyncio.run(cache.has("../../ESCAPED", "k")),
        lambda: asyncio.run(cache.load_all("../../ESCAPED")),
        lambda: asyncio.run(cache.load_key("../../ESCAPED", "k")),
        lambda: asyncio.run(cache.store("../../ESCAPED", "k", [])),
    ):
        with pytest.raises(PathEscapesStoreRoot):
            call()


def test_the_cache_still_stores_and_reads_an_ordinary_item(tmp_path):
    """The control — the cache is on the dependency-resolution hot path and
    must keep working for every real key shape (``http-…``, ``github-…``,
    ``local-…``, all sanitised to ``[a-zA-Z0-9_-]`` by ``cache_key``)."""
    from dna.kernel.protocols import CacheItem

    cache, cache_root = _cache(tmp_path)
    payload = tmp_path / "payload" / "a-agent"
    payload.mkdir(parents=True)
    (payload / "AGENT.md").write_text("---\nname: a-agent\n---\nbody")

    item = CacheItem(name="a-agent", kind="Agent", content_path=payload)
    asyncio.run(cache.store("test-mod", "github-ruinosus-dna", [item]))

    assert asyncio.run(cache.has("test-mod", "github-ruinosus-dna"))
    stored = cache_root / "test-mod" / "github-ruinosus-dna" / "agents" / "a-agent"
    assert (stored / "AGENT.md").read_text().endswith("body")
