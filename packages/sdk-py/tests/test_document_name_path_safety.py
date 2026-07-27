"""A document name is a PATH COMPONENT — the kernel refuses one that escapes.

A document reaches the filesystem adapter as ``<scope>/<container>/<name>/…``
or ``<container>/<name>.yaml``. Nothing on the kernel write path validated
``name``, so a caller-supplied ``"../../../../ESCAPED"`` was accepted and wrote
a file ABOVE the store root — measured on a tenant-facing route, but the route
was never the bug: ``create_story`` and every other application-layer writer
take a raw caller ``name`` exactly the same way.

The guard therefore lives at ``Kernel.write_document`` / ``Kernel.delete_document``
— the documented facades that already own ``invalidate_mode`` validation, the
retired-Kind block and the tenant-slug check — so every door inherits it.

``scope`` is guarded here too, and for the same reason: the filesystem adapter
builds ``self.base_dir / scope`` with no validation at all, and ``scope`` IS
caller-supplied on the generic write door (the MCP/REST ``scope=`` argument)
whenever the deployment's scope-binding regime is the permissive one
(unauthenticated/stdio, multi-workspace off, or a ``*`` token grant). ``kind`` is
NOT guarded because it never reaches a path: the adapter routes it through
``Kernel.storage_for_kind`` → ``StorageDescriptor.container``, a registry-declared
value, and an unregistered kind resolves to ``None`` (write at the scope root)
rather than to the caller's string.

The rule is "cannot escape or address a directory", NOT "looks like an
identifier". Real names in DNA scopes include ``s-foo-bar``,
``i-065-layerpolicy-missing``, a generated id carrying a dotted host-style
suffix, and that id compounded with ``--``; so ``.``, ``-`` and ``--`` stay
legal and no charset is imposed. (The dotted/``--`` names below are neutral
stand-ins of the exact same shape — the kernel names no deployment.)
"""
from __future__ import annotations

import asyncio

import pytest

from dna.kernel.errors import (
    MAX_PATH_COMPONENT_BYTES,
    InvalidDocumentName,
    InvalidScopeName,
    KernelRefusal,
    validate_document_name,
    validate_scope_name,
)

# ── the corpus ───────────────────────────────────────────────────────────────
#
# Names that MUST be refused. Each one either escapes the container
# (``..``/``/``/``\``), addresses a directory instead of naming a document
# (``.``, ``..``, empty), truncates a C path string (NUL), or has no chance of
# becoming a filesystem component at all (over-long).
UNSAFE_NAMES = [
    pytest.param("../../../../ESCAPED", id="traversal"),
    pytest.param("..", id="dotdot"),
    pytest.param(".", id="dot"),
    pytest.param("a/b", id="slash-inside"),
    pytest.param("/etc/passwd", id="absolute"),
    pytest.param("nested/../../up", id="traversal-mid"),
    pytest.param("trailing/", id="trailing-slash"),
    pytest.param("..\\..\\windows", id="backslash"),
    pytest.param("a\\b", id="backslash-inside"),
    pytest.param("", id="empty"),
    pytest.param("   ", id="whitespace-only"),
    pytest.param("\t\n", id="whitespace-only-tabs"),
    pytest.param("evil\x00.yaml", id="nul-byte"),
    pytest.param("x" * (MAX_PATH_COMPONENT_BYTES + 1), id="over-long"),
]

# Names that MUST be accepted — every one of these is REAL. Measured by walking
# every ``.dna/`` scope and test fixture in this repo (1139 distinct names, max
# length 68) plus the names the application layer constructs
# (``dna.extensions.intel.engine._slug`` → ``ins-…``,
# ``dna.memory.interchange.engram_doc_name`` → ``rem-<sha>``,
# ``dna.application.runtime._slug`` → ``rem-<sha>-<base>``).
REAL_NAMES = [
    "s-foo-bar",
    "i-065-layerpolicy-missing",
    "t-1a2b3c.node.internal",
    "t-1a2b3c.node.internal--Overlay",
    "adr-dna-mcp-runtime-face",
    "digest-20260711-134928",
    "e-dna-dx",
    "feature-f-dna-docs-reflect-20260709-160107",
    "i-008-write-path-schema-validation-gap",
    "ins-copiloto-medico-hitl-n-o-blinda-o-m-dico-da-responsabilidade-leg",
    "rem-3f2a1b9c0d",
    "rem-3f2a1b9c0d-a-lembranca-que-importa",
    "speckit-spec-template",
    "AGENT",
    "some_name_with_underscores",
    "1.0.0",
    "x" * MAX_PATH_COMPONENT_BYTES,
]

REAL_SCOPES = [
    "dna-development",
    "_lib",
    "test-mod",
    "tenant-t-1a2b3c.node.internal",
    "acme-development",
    "s",
]


# ── the error vocabulary ─────────────────────────────────────────────────────

@pytest.mark.parametrize("cls", [InvalidDocumentName, InvalidScopeName])
def test_the_refusal_shares_the_kernel_marker_base(cls):
    """A face catches ONE type (``KernelRefusal``) and relays every deliberate
    refusal — the guard must not re-open that hole."""
    assert issubclass(cls, KernelRefusal)


@pytest.mark.parametrize("cls", [InvalidDocumentName, InvalidScopeName])
def test_the_refusal_is_also_a_valueerror(cls):
    """Belt and braces for a SECURITY refusal: a face that predates
    ``KernelRefusal`` and still catches ``(ValueError, LookupError,
    PermissionError)`` relays it as an honest denial instead of a masked 500."""
    assert issubclass(cls, ValueError)


# ── the validator ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", UNSAFE_NAMES)
def test_validate_document_name_refuses_an_unsafe_component(name):
    with pytest.raises(InvalidDocumentName):
        validate_document_name(name)


@pytest.mark.parametrize("name", REAL_NAMES)
def test_validate_document_name_accepts_every_real_name(name):
    validate_document_name(name)  # must not raise


@pytest.mark.parametrize("name", UNSAFE_NAMES)
def test_validate_scope_name_refuses_an_unsafe_component(name):
    with pytest.raises(InvalidScopeName):
        validate_scope_name(name)


@pytest.mark.parametrize("scope", REAL_SCOPES)
def test_validate_scope_name_accepts_every_real_scope(scope):
    validate_scope_name(scope)  # must not raise


def test_the_refusal_names_the_offending_value_and_the_reason():
    """Didactic failure: the message must say WHICH name and WHY, or the
    author of a legitimately-refused name has nothing to act on."""
    with pytest.raises(InvalidDocumentName) as exc:
        validate_document_name("../escape")
    msg = str(exc.value)
    assert "../escape" in msg
    assert "path component" in msg


def test_a_non_string_name_is_refused():
    """Defence in depth — a caller handing the kernel a Path or None must not
    reach ``Path.__truediv__`` and produce a surprise."""
    with pytest.raises(InvalidDocumentName):
        validate_document_name(None)  # type: ignore[arg-type]


# ── the kernel facade ────────────────────────────────────────────────────────

class _RecordingWritable:
    """Minimal WritableSourcePort — records what actually reached the adapter."""

    def __init__(self) -> None:
        self.saves: list[tuple] = []
        self.deletes: list[tuple] = []

    async def save_document(self, scope, kind, name, raw, author=None, *,
                            tenant=None, layer=None, **kw):
        self.saves.append((scope, kind, name))
        return "v1"

    async def delete_document(self, scope, kind, name, *, tenant=None,
                              layer=None, **kw):
        self.deletes.append((scope, kind, name))

    @property
    def supports_readers(self):
        return False

    async def load_bootstrap_docs(self, scope, *, tenant=None):
        return []

    async def load_all(self, scope, readers=None):
        return []

    async def load_layer(self, scope, layer, readers=None):
        return []

    async def load_one(self, scope, kind, name, **kw):
        return None

    async def load_drafts(self, scope, **kw):
        return []

    async def resolve_ref(self, scope, ref):
        return None

    async def list_scopes(self):
        return []

    async def list_doc_refs(self, scope, **kw):
        return []

    async def list_versions(self, scope, kind, name, **kw):
        return []

    async def get_version(self, scope, kind, name, version, **kw):
        return None

    async def publish(self, scope, kind, name, **kw):
        return None

    async def save_manifest(self, scope, manifest):
        return "v1"

    async def query(self, *a, **kw):
        return []

    async def count(self, *a, **kw):
        return 0

    def capabilities(self):
        return {}

    async def close(self):
        return None


def _kernel_with_recorder():
    from dna.kernel import Kernel

    k = Kernel()
    src = _RecordingWritable()
    k.source(src)
    return k, src


def _raw(name: str) -> dict:
    return {"kind": "Agent", "metadata": {"name": name}, "spec": {}}


@pytest.mark.parametrize("name", UNSAFE_NAMES)
def test_write_document_refuses_an_unsafe_name_before_the_adapter(name):
    k, src = _kernel_with_recorder()
    with pytest.raises(InvalidDocumentName):
        asyncio.run(k.write_document("test-mod", "Agent", name, _raw(name)))
    assert src.saves == [], "the adapter must never see an unsafe name"


@pytest.mark.parametrize("name", UNSAFE_NAMES)
def test_delete_document_refuses_an_unsafe_name_before_the_adapter(name):
    """A traversal DELETE is the worse half of the same bug — the filesystem
    adapter ``unlink``s / ``rmtree``s ``parent / name``."""
    k, src = _kernel_with_recorder()
    with pytest.raises(InvalidDocumentName):
        asyncio.run(k.delete_document("test-mod", "Agent", name))
    assert src.deletes == [], "the adapter must never see an unsafe name"


@pytest.mark.parametrize("scope", ["../../evil", "a/b", "..", "", "  ", "a\\b"])
def test_write_document_refuses_an_unsafe_scope_before_the_adapter(scope):
    k, src = _kernel_with_recorder()
    with pytest.raises(InvalidScopeName):
        asyncio.run(k.write_document(scope, "Agent", "bot", _raw("bot")))
    assert src.saves == []


def test_write_document_still_accepts_a_real_name_and_scope():
    """The guard must not become the bug: the ordinary write is untouched."""
    k, src = _kernel_with_recorder()
    version = asyncio.run(k.write_document(
        "dna-development", "Agent", "t-1a2b3c.node.internal--Overlay",
        _raw("t-1a2b3c.node.internal--Overlay"),
    ))
    assert version == "v1"
    assert src.saves == [
        ("dna-development", "Agent", "t-1a2b3c.node.internal--Overlay")
    ]


def test_write_document_documents_the_refusal():
    """The facade's docstring lists what it raises — a guard nobody can find in
    the contract is a guard callers write around."""
    from dna.kernel import Kernel

    doc = Kernel.write_document.__doc__ or ""
    assert "InvalidDocumentName" in doc
    assert "InvalidScopeName" in doc


# ── end to end: the exception is not the proof, the empty filesystem is ──────

@pytest.mark.asyncio
async def test_no_file_escapes_the_store_root(tmp_path):
    """Drive a REAL filesystem-backed write with a traversal name.

    A raised exception alone proves nothing — before the guard, this exact
    call returned version ``'1'`` and left ``<tmp>/ESCAPED/AGENT.md`` two
    levels ABOVE the store root, with the store itself empty. So assert BOTH:
    the refusal, and that not one byte landed anywhere outside the root.
    """
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.extensions.helix import HelixExtension
    from dna.kernel import Kernel

    store = tmp_path / "outer" / "store"
    (store / "test-mod").mkdir(parents=True)
    before = {p for p in tmp_path.rglob("*")}

    k = Kernel()
    k.load(HelixExtension())
    k.source(FilesystemWritableSource(str(store), kernel=k))

    evil = "../../../../ESCAPED"
    with pytest.raises(InvalidDocumentName):
        await k.write_document("test-mod", "Agent", evil, {
            "apiVersion": "helix.dna.dev/v1", "kind": "Agent",
            "metadata": {"name": evil}, "spec": {"model": "gpt-4o"},
        })

    after = {p for p in tmp_path.rglob("*")}
    assert after == before, f"the write path created {sorted(after - before)}"
    escaped = [p for p in tmp_path.rglob("*")
               if p.is_file() and store not in p.parents]
    assert escaped == [], f"files landed outside the store root: {escaped}"


@pytest.mark.asyncio
async def test_the_same_write_with_a_safe_name_still_lands_inside(tmp_path):
    """The control: the guard refuses the escape without refusing the write."""
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.extensions.helix import HelixExtension
    from dna.kernel import Kernel

    store = tmp_path / "outer" / "store"
    (store / "test-mod").mkdir(parents=True)

    k = Kernel()
    k.load(HelixExtension())
    k.source(FilesystemWritableSource(str(store), kernel=k))

    await k.write_document("test-mod", "Agent", "t-1a2b3c.node.internal--Overlay", {
        "apiVersion": "helix.dna.dev/v1", "kind": "Agent",
        "metadata": {"name": "t-1a2b3c.node.internal--Overlay"},
        "spec": {"model": "gpt-4o"},
    })

    written = [p for p in store.rglob("*") if p.is_file()]
    assert written, "the safe write must still land"
    assert all(store in p.parents for p in written)


# ── the SECOND write door: bundle entries ───────────────────────────────────
#
# ``write_document`` is not the only kernel method that takes a caller name
# into a path. ``write_bundle_entry_async`` does too, and it is live on
# ``PUT /v1/definitions/{kind}/{name}/entries/{entry:path}`` with ``name`` as a
# raw URL path parameter. The filesystem adapter DOES guard ``entry`` — but
# only relative to the bundle root, and ``scope``/``name`` are what build that
# root, so a traversing name moves the anchor and the entry check still passes.

def _fs_kernel(tmp_path):
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.extensions.helix import HelixExtension
    from dna.kernel import Kernel

    store = tmp_path / "outer" / "store"
    (store / "test-mod").mkdir(parents=True)
    k = Kernel()
    k.load(HelixExtension())
    k.source(FilesystemWritableSource(str(store), kernel=k))
    return k, store


@pytest.mark.asyncio
async def test_no_bundle_entry_escapes_the_store_root(tmp_path):
    k, store = _fs_kernel(tmp_path)
    before = {p for p in tmp_path.rglob("*")}

    with pytest.raises(InvalidDocumentName):
        await k.write_bundle_entry_async(
            "test-mod", "Agent", "../../../../ESCAPED", "AGENT.md", "pwned",
        )

    after = {p for p in tmp_path.rglob("*")}
    assert after == before, f"the bundle write created {sorted(after - before)}"


@pytest.mark.asyncio
async def test_bundle_entry_write_refuses_an_unsafe_scope(tmp_path):
    k, _ = _fs_kernel(tmp_path)
    with pytest.raises(InvalidScopeName):
        await k.write_bundle_entry_async(
            "../../evil", "Agent", "a-agent", "AGENT.md", "pwned",
        )


@pytest.mark.asyncio
async def test_bundle_entry_delete_refuses_an_unsafe_name(tmp_path):
    k, _ = _fs_kernel(tmp_path)
    with pytest.raises(InvalidDocumentName):
        await k.delete_bundle_entry_async(
            "test-mod", "Agent", "../../../../ESCAPED", "AGENT.md",
        )
    with pytest.raises(InvalidDocumentName):
        k.delete_bundle_entry(
            "test-mod", "Agent", "../../../../ESCAPED", "AGENT.md",
        )


@pytest.mark.asyncio
async def test_a_safe_bundle_entry_write_still_lands_inside(tmp_path):
    """The control for the second door."""
    k, store = _fs_kernel(tmp_path)
    await k.write_bundle_entry_async(
        "test-mod", "Agent", "a-skill", "AGENT.md", "# hello",
    )
    written = [p for p in store.rglob("AGENT.md")]
    assert written, "the safe bundle write must still land"
    assert all(store in p.parents for p in written)
