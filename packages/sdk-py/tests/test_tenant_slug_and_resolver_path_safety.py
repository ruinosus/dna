"""Two more places the same class survived: the TENANT slug and a REMOTE name.

The property this family defends: caller-supplied and content-supplied strings
reach the filesystem as PATH COMPONENTS, and the rule is always "cannot
escape", never a charset. ``606812c`` closed the document-name doors,
``887e858`` the read half, ``d962aa3`` bundle entries. Two doors were left.

1. ``tenant`` — ``dna.kernel.lock.module._lock_path`` builds
   ``<base>/tenants/<tenant>/.dna.lock`` and had no containment, while
   ``validate_tenant_slug`` explicitly disclaimed path safety ("path-traversal
   safety lives in the adapter"). This is not an adapter. It is reached from
   the COMPOSE and QUERY hot paths (``compose/resolver.py`` and
   ``query/engine.py``, both → ``Kernel._catalog_scopes`` →
   ``_compute_catalog_scopes`` → ``load_lockfile``), and a traversing slug read
   a ``.dna.lock`` from outside the store.

   THE GEOMETRY is why two earlier attempts looked negative: ``<base>/tenants``
   must EXIST for the OS to resolve ``..`` through it. Without that directory
   the probe reports "not found" and reads as safe. Every deployment that has
   ever had a tenant has it — so the fixtures below create it explicitly, and
   that line is load-bearing, not setup noise.

2. A remote ``name`` in ``HttpResolver`` — ``Path(tempfile.mkdtemp()) / name``
   then ``mkdir(parents=True)`` and a ``manifest.yaml`` write. A sweep recorded
   this as "escapes a directory that holds nothing"; that verdict was wrong.
   The fresh tempdir bounds nothing, because ``..`` leaves it.

MEASURED BEFORE CONSTRAINING, as every wave in this series has been: 33
distinct real tenant slugs across both repos (3 on-disk ``tenants/``
directories — ``acme``, ``demo``, ``personal%3Alocal-user`` — plus 31 literals
in ``.py``/``.yaml``/``.json``/``.ts``). Exactly 1 is refused by the new rule
and it is ``'../evil'``, an attack literal in ``test_kernel_write_layer.py``
that exists to assert refusal. Zero legitimate callers. Uppercase (``T1``,
``Acme``), dots (``t-1a2b3c.node.internal``) and the ``personal:`` scheme all
stay legal — the rule is escape, not charset.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dna.kernel.errors import KernelRefusal, PathEscapesStoreRoot
from dna.kernel.protocols import InvalidTenantSlug, validate_tenant_slug

#: Every real tenant slug shape found by the measurement above. None may be
#: refused — this is the corpus the rule was chosen against.
REAL_SLUGS = [
    "acme", "demo", "personal%3Alocal-user", "T1", "Acme", "a", "beta",
    "globex", "innovec", "other", "shared", "team-b", "vendor-1", "ws-1",
    "ws-acme", "ws-caller", "zeroed", "t-1a2b3c", "t-1a2b3c.node.internal",
]

#: The shapes that MOVE A PATH.
ESCAPING_SLUGS = ["../../../etc", "..", ".", "a/b", "../evil", "a\\b",
                  "/etc/passwd", "x\x00y"]


# ── the named early door ─────────────────────────────────────────────────────

@pytest.mark.parametrize("slug", REAL_SLUGS)
def test_validate_tenant_slug_accepts_every_real_slug(slug):
    """0 of the measured corpus may be refused. This is the test that would
    have caught a charset-shaped rule, which is the mistake this family keeps
    declining to make."""
    validate_tenant_slug(slug)


@pytest.mark.parametrize("slug", ESCAPING_SLUGS)
def test_validate_tenant_slug_refuses_a_traversing_slug(slug):
    with pytest.raises(InvalidTenantSlug):
        validate_tenant_slug(slug)


def test_the_tenant_refusal_relays_through_both_face_conventions():
    """``InvalidTenantSlug`` gained a ``ValueError`` base in the same change.

    Without it, moving the traversal refusal EARLIER — from the FS adapter's
    plain ``ValueError("Invalid layer segment: …")`` to the kernel-boundary
    validator — would have made faces that enumerate
    ``(ValueError, LookupError, PermissionError)`` stop relaying it. A fix that
    silently regresses the reporting it set out to improve is not a fix."""
    with pytest.raises(InvalidTenantSlug) as exc:
        validate_tenant_slug("../../etc")
    assert isinstance(exc.value, KernelRefusal)
    assert isinstance(exc.value, ValueError)


def test_the_personal_scheme_and_uppercase_are_still_legal():
    """The rule is escape, not charset — pinned because 'tighten the tenant
    slug to a DNS label' is the obvious next step and it would break 7 real
    ``personal:`` slugs and 2 uppercase ones."""
    validate_tenant_slug("personal:google:sub-9", allow_personal=True)
    validate_tenant_slug("Acme")
    validate_tenant_slug("t-1a2b3c.node.internal")


# ── the closing layer, where the path is actually built ─────────────────────

def _store_with_a_tenant(tmp_path: Path) -> Path:
    """A store whose ``tenants/`` directory EXISTS — the precondition that
    makes ``..`` resolvable. See the module docstring."""
    store = tmp_path / "store"
    (store / "tenants" / "acme").mkdir(parents=True)
    (store / "tenants" / "acme" / ".dna.lock").write_text(
        "lockVersion: 6\ntenant: acme\npackages: []\n"
    )
    return store


def _plant_outside_lockfile(tmp_path: Path) -> Path:
    outside = tmp_path / "outside"
    outside.mkdir(exist_ok=True)
    (outside / ".dna.lock").write_text(
        "lockVersion: 6\n"
        "tenant: acme\n"
        "packages:\n"
        "  - source: attacker/INJECTED-FROM-OUTSIDE-THE-STORE\n"
        "    version_constraint: '*'\n"
        "    resolved_version: '9.9.9'\n"
        "    resolved_sha256: 'x'\n"
        "    installed_at: 'now'\n"
        "    target_tenant: acme\n"
    )
    return outside


def test_load_lockfile_refuses_to_read_from_outside_the_store(tmp_path):
    """Asserted on WHICH FILE WAS READ, not on the exception.

    Before the fix this returned a ``GenomeLockfile`` whose packages were
    ``['attacker/INJECTED-FROM-OUTSIDE-THE-STORE']``."""
    from dna.kernel.lock.module import load_lockfile

    store = _store_with_a_tenant(tmp_path)
    _plant_outside_lockfile(tmp_path)

    with pytest.raises(PathEscapesStoreRoot):
        load_lockfile(store, "../../outside")

    # The CONTROL: the tenant's own lockfile is still readable, at the path it
    # has always been at.
    assert load_lockfile(store, "acme").tenant == "acme"


def test_the_lock_path_escape_is_closed_on_the_write_half_too(tmp_path):
    """``write_lockfile`` has no production caller today, which is a fact about
    THIS moment, not a property. Both halves go through ``_lock_path``, so both
    are covered — and the write half is strictly worse, since it
    ``mkdir(parents=True)``s on the way."""
    from dna.kernel.lock.module import GenomeLockfile, write_lockfile

    store = _store_with_a_tenant(tmp_path)
    lock = GenomeLockfile(tenant="../../outside", packages=[])

    with pytest.raises(PathEscapesStoreRoot):
        write_lockfile(lock, store)
    assert not (tmp_path / "outside").exists(), "the write created a dir outside"

    # CONTROL — an ordinary tenant still writes, and inside the store.
    ok = GenomeLockfile(tenant="acme", packages=[])
    p = write_lockfile(ok, store)
    assert p == store / "tenants" / "acme" / ".dna.lock"
    assert p.is_file()


def test_an_absolute_tenant_slug_cannot_relocate_the_lockfile(tmp_path):
    """A ``pathlib`` join DISCARDS the left operand when the right one is
    absolute, so no amount of store depth absorbs this one."""
    from dna.kernel.lock.module import load_lockfile

    store = _store_with_a_tenant(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    with pytest.raises(PathEscapesStoreRoot):
        load_lockfile(store, str(elsewhere))


def test_the_compose_and_query_hot_path_cannot_read_an_outside_lockfile(tmp_path):
    """THE CALLER, not the primitive — this is the path the reviewer built.

    ``Kernel._catalog_scopes`` is on both the compose (``compose/resolver.py``)
    and query (``query/engine.py``) hot paths. Before the fix
    ``_compute_catalog_scopes('../../outside', set())`` returned
    ``[('INJECTED-FROM-OUTSIDE-THE-STORE', 'acme')]`` — attacker-supplied
    content from outside the store reshaping the installed-package list.

    ``_compute_catalog_scopes`` is fail-soft around the lockfile read (it logs
    a warning and treats the tenant as having no installs), so the assertion is
    on the RESULT, which is what callers act on."""
    import asyncio

    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.kernel import Kernel

    store = _store_with_a_tenant(tmp_path)
    _plant_outside_lockfile(tmp_path)

    k = Kernel()
    k.source(FilesystemWritableSource(store))
    out = asyncio.run(k._catalog._compute_catalog_scopes("../../outside", set()))

    assert out == [], f"outside content reached the hot path: {out}"


# ── the remote name ─────────────────────────────────────────────────────────

def _bundle(name: str) -> list[dict]:
    return [{"apiVersion": "dna.io/v1", "kind": "Skill",
             "metadata": {"name": name}, "spec": {"a": 1}}]


@pytest.mark.parametrize("name", ["../HIJACKED", "../../HIJACKED", "a/b", ".", "..",
                                  "x\x00y"])
def test_the_http_resolver_refuses_a_traversing_remote_name(name, monkeypatch,
                                                            tmp_path):
    """Reproduced before the fix, on the FILESYSTEM: a remote ``name`` of
    ``'../HIJACKED'`` produced ``HIJACKED/manifest.yaml`` OUTSIDE the
    ``mkdtemp``. Arbitrary directory creation plus an attacker-chosen file
    path, from remote content — not "escapes a directory that holds nothing".

    ``tempfile.tempdir`` is pinned so the escape lands somewhere observable.
    An earlier probe scanned only the sandbox and reported "no files created"
    while the payload sat two levels up in ``$TMPDIR`` — a worse escape reading
    as no escape, the same trap recorded in the previous wave's report."""
    from dna.adapters.resolvers.http import HttpResolver

    sandbox = tmp_path / "tmproot"
    sandbox.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(sandbox))

    with pytest.raises(KernelRefusal):
        HttpResolver()._resolve_from_bundle(_bundle(name), None)

    # Nothing anywhere under the sandbox OR its parent — the parent is where a
    # single ``..`` lands.
    stray = [p for p in tmp_path.rglob("manifest.yaml")]
    assert stray == [], f"files created by a REFUSED resolve: {stray}"


def test_the_http_resolver_refuses_an_absolute_remote_name(monkeypatch, tmp_path):
    from dna.adapters.resolvers.http import HttpResolver

    sandbox = tmp_path / "tmproot"
    sandbox.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(sandbox))
    target = tmp_path / "ABSOLUTE_HIJACK"

    with pytest.raises(KernelRefusal):
        HttpResolver()._resolve_from_bundle(_bundle(str(target)), None)

    assert not target.exists(), "an absolute remote name created a directory"


def test_the_http_resolver_still_stages_an_ordinary_remote_item(monkeypatch,
                                                                tmp_path):
    """The CONTROL. Dots and hyphens stay legal — real document names carry
    them."""
    from dna.adapters.resolvers.http import HttpResolver

    sandbox = tmp_path / "tmproot"
    sandbox.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(sandbox))

    items = HttpResolver()._resolve_from_bundle(_bundle("brain-storming.v2"), None)

    assert len(items) == 1
    assert items[0].name == "brain-storming.v2"
    assert items[0].kind == "Skill"
    assert items[0].source_path.name == "brain-storming.v2"
    assert (items[0].source_path / "manifest.yaml").is_file()
