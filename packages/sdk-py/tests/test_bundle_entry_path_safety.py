"""A bundle ENTRY is a relative path inside its bundle — and it is built from
document CONTENT, which is why guarding ``name`` and ``scope`` was not enough.

``606812c`` / ``887e858`` closed ``name`` and ``scope`` on both the write and
the read half. The class was still open: a bundle ``entry`` reaches the
filesystem as ``<bundle_root>/<entry>`` and the writers DERIVE that entry from
caller-supplied ``spec`` — ``spec.source_files`` (a kind-AGNOSTIC documented
convention shared by Agent, Skill, Tenant and TenantMembership),
``spec.root_files``, ``spec.scripts|references|assets``, ``spec.extras`` and
``spec.instruction_file``. ``apply_definition_impl`` copies the caller's
``spec`` verbatim into ``raw`` and ``PUT /v1/definitions/{kind}/{name}`` takes
it as an untyped body, so every one of those is caller input.

Measured at HEAD, through ``Kernel.write_document`` on the default ``Agent``
Kind (not through the handle in isolation): each field wrote a real file
OUTSIDE the store root — on the base lane and the tenant lane alike — and an
ABSOLUTE entry wrote to an arbitrary absolute path, because a ``pathlib`` join
DISCARDS the left operand when the right one is absolute. An arbitrary file
write through the kernel's own documented write facade, with a version id
returned and no refusal.

THE SEAM. The guard closes at ``FilesystemBundleHandle`` — the one door every
writer must pass — not at each writer. Eight in-repo writers call
``bundle.write_text(f["relativePath"], …)`` directly rather than the shared
``write_entries_to_handle`` sink, so guarding the sink alone would have
repeated the exact enumeration mistake that caused the miss. The sink and
``serialize_document`` are guarded TOO, as the early, named layer that can say
which field was wrong — same two-layer shape as ``validate_document_name`` +
``FilesystemSource._contained``, and for the same reason. Neither is dead code.

THE RULE IS MEASURED. 492 distinct real bundle entry paths across both repos'
``.dna/`` trees and fixtures: 482 carry a ``/``, 467 are two or more levels
deep, the deepest is 8 segments, the longest 96 bytes, EVERY one contains a
dot — and zero have a ``..`` or ``.`` segment, are absolute, carry a backslash
or a NUL, or exceed the bound. Subdirectories and dots therefore stay legal;
refusing them would break every Skill and Agent bundle in both repos.

GEOMETRY, measured rather than assumed. A base-lane bundle root is
``<sandbox>/outer/store/<scope>/agents/<name>`` — FIVE segments under the
sandbox — so exactly 4 ``..`` land on ``<sandbox>/outer``, the first directory
outside the store. A ``scripts/`` prefix absorbs one. The tenant lane's root is
``<store>/tenants/<t>/scopes/<scope>/agents/<name>``, so it takes 7. Getting
this wrong is how a draft test in an earlier wave passed against vulnerable
code; the counts below are the measured ones.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dna.kernel.bundle.handle import DictBundleHandle, FilesystemBundleHandle
from dna.kernel.errors import (
    MAX_BUNDLE_ENTRY_BYTES,
    MAX_PATH_COMPONENT_BYTES,
    InvalidBundleEntry,
    KernelRefusal,
    PathEscapesStoreRoot,
    validate_bundle_entry,
)

# ── the corpus ───────────────────────────────────────────────────────────────

UNSAFE_ENTRIES = [
    pytest.param("../../../../ESCAPED.md", id="traversal"),
    pytest.param("..", id="dotdot"),
    pytest.param(".", id="dot"),
    pytest.param("scripts/../../../../ESCAPED.md", id="traversal-mid"),
    pytest.param("a/./b", id="dot-segment-mid"),
    pytest.param("/etc/cron.d/pwn", id="absolute"),
    pytest.param("/tmp/anywhere.md", id="absolute-tmp"),
    pytest.param("C:/Windows/system32/x", id="windows-drive"),
    pytest.param("..\\..\\windows", id="backslash-traversal"),
    pytest.param("a\\b", id="backslash-inside"),
    pytest.param("", id="empty"),
    pytest.param("   ", id="whitespace-only"),
    pytest.param("evil\x00.md", id="nul-byte"),
    pytest.param("a//b", id="doubled-slash"),
    pytest.param("trailing/", id="trailing-slash"),
    pytest.param("x" * (MAX_PATH_COMPONENT_BYTES + 1), id="over-long-segment"),
    pytest.param("/".join(["seg"] * 260), id="over-long-path"),
]

#: Every one of these is REAL — taken from the 492-entry measurement. If a
#: change to the rule reddens any of these, the rule is wrong, not the entry.
REAL_ENTRIES = [
    "AGENT.md",
    "SKILL.md",
    "AGENTS.md",
    "Genome.yaml",
    "instruction.md",
    "scripts/run.py",
    "references/spec.md",
    "assets/logo.svg",
    "skills/foo/SKILL.md",
    "skills/docx/scripts/office/schemas/ISO-IEC29500-4_2016/shared-documentPropertiesVariantTypes.xsd",
    "skills/xlsx/scripts/office/schemas/ecma/fouth-edition/opc-digSig.xsd",
    "composition/cases/01-inherit-simple.yaml",
    "actors/developer.yaml",
    ".hidden-but-legal.md",
    "x" * MAX_PATH_COMPONENT_BYTES,
]


# ── the error vocabulary ─────────────────────────────────────────────────────

def test_the_refusal_shares_the_kernel_marker_base():
    """A face catches ONE type and relays every deliberate refusal."""
    assert issubclass(InvalidBundleEntry, KernelRefusal)


def test_the_refusal_is_also_a_valueerror():
    """Belt and braces for a SECURITY refusal — a face that predates
    ``KernelRefusal`` still reports it instead of masking a 500."""
    assert issubclass(InvalidBundleEntry, ValueError)


# ── the validator ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("entry", UNSAFE_ENTRIES)
def test_validate_bundle_entry_refuses_an_unsafe_path(entry):
    with pytest.raises(InvalidBundleEntry):
        validate_bundle_entry(entry)


@pytest.mark.parametrize("entry", REAL_ENTRIES)
def test_validate_bundle_entry_accepts_every_real_entry(entry):
    """Measured, not assumed: subdirectories and dots are the NORM — 482 of the
    492 real entries carry a '/', and all 492 carry a dot."""
    validate_bundle_entry(entry)


@pytest.mark.parametrize("bad", [None, 42, b"bytes.md", ["a"], {"a": 1}])
def test_validate_bundle_entry_refuses_a_non_string(bad):
    with pytest.raises(InvalidBundleEntry):
        validate_bundle_entry(bad)


def test_the_bound_is_a_byte_bound_not_a_character_bound():
    """``PATH_MAX``/``NAME_MAX`` are byte limits, so the check must be too — a
    multibyte name that fits in characters can still be refused by the OS."""
    validate_bundle_entry("é" * (MAX_PATH_COMPONENT_BYTES // 2))
    with pytest.raises(InvalidBundleEntry):
        validate_bundle_entry("é" * (MAX_PATH_COMPONENT_BYTES // 2 + 1))


def test_the_whole_path_has_its_own_bound_above_the_segment_bound():
    """An entry is a PATH, so a thousand legal 3-byte segments is still a path
    no filesystem will take."""
    assert MAX_BUNDLE_ENTRY_BYTES > MAX_PATH_COMPONENT_BYTES
    with pytest.raises(InvalidBundleEntry):
        validate_bundle_entry("/".join(["seg"] * 300))


def test_the_message_names_the_door_when_the_caller_knows_it():
    with pytest.raises(InvalidBundleEntry, match=r"spec\.root_files key"):
        validate_bundle_entry("../x", where="spec.root_files key")


# ── layer 2: the handle contains every entry it joins ────────────────────────
#
# ``FilesystemBundleHandle`` is where the class CLOSES, because it is the one
# door every writer goes through. Tested AT THE HANDLE, bypassing the kernel
# entirely — or it would not be testing the second layer at all.

_HANDLE_METHODS = [
    pytest.param(lambda h, e: h.write_text(e, "pwned"), id="write_text"),
    pytest.param(lambda h, e: h.write_bytes(e, b"pwned"), id="write_bytes"),
    pytest.param(lambda h, e: h.read_text(e), id="read_text"),
    pytest.param(lambda h, e: h.read_bytes(e), id="read_bytes"),
    pytest.param(lambda h, e: h.exists(e), id="exists"),
    pytest.param(lambda h, e: h.is_file(e), id="is_file"),
]


@pytest.mark.parametrize("call", _HANDLE_METHODS)
@pytest.mark.parametrize("entry", UNSAFE_ENTRIES)
def test_every_handle_method_that_joins_an_entry_refuses_an_unsafe_one(
    tmp_path, call, entry,
):
    """Not only ``write_text`` / ``write_bytes``: ``read_text``, ``read_bytes``,
    ``exists`` and ``is_file`` build a path from ``entry`` too, and a read that
    escapes is the disclosure twin of a write that escapes."""
    root = tmp_path / "outer" / "store" / "test-mod" / "agents" / "a"
    root.mkdir(parents=True)
    handle = FilesystemBundleHandle(root)
    with pytest.raises(KernelRefusal):
        call(handle, entry)


def test_the_handle_refuses_an_absolute_entry_and_writes_nothing(tmp_path):
    """The sharpest case: a pathlib join DISCARDS the bundle root when the
    right operand is absolute, so this is an arbitrary absolute write, not a
    traversal that a deep-enough store would absorb."""
    root = tmp_path / "outer" / "store" / "test-mod" / "agents" / "a"
    root.mkdir(parents=True)
    target = tmp_path / "arbitrary" / "ABSOLUTE_ESCAPED.md"
    target.parent.mkdir(parents=True)

    with pytest.raises(InvalidBundleEntry):
        FilesystemBundleHandle(root).write_text(str(target), "pwned")
    assert not target.exists(), "the absolute write must not have happened"


def test_the_handle_still_round_trips_a_legitimate_nested_entry(tmp_path):
    """The control. Subdirectories are the NORM, not the exception."""
    root = tmp_path / "store" / "agents" / "a"
    root.mkdir(parents=True)
    handle = FilesystemBundleHandle(root)

    handle.write_text("skills/foo/SKILL.md", "# legit")
    handle.write_bytes("assets/logo.svg", b"<svg/>")
    handle.write_text("AGENT.md", "# marker")

    assert handle.read_text("skills/foo/SKILL.md") == "# legit"
    assert handle.read_bytes("assets/logo.svg") == b"<svg/>"
    assert handle.exists("skills/foo/SKILL.md")
    assert handle.is_file("skills/foo/SKILL.md")
    assert not handle.is_file("skills")
    assert sorted(handle.iter_entries(recursive=True)) == [
        "AGENT.md", "assets/logo.svg", "skills/foo/SKILL.md",
    ]
    assert all(root in p.parents for p in root.rglob("*"))


def test_the_handle_containment_is_a_second_layer_under_the_validator(tmp_path):
    """The validator refuses by SHAPE; containment refuses by RESOLVED LOCATION.
    Both run, and the second is not redundant: it is what survives a symlinked
    subDIRECTORY pointing out of the bundle, which no textual rule can see —
    everything written beneath such a link lands wherever it points."""
    root = tmp_path / "store" / "agents" / "a"
    root.mkdir(parents=True)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(PathEscapesStoreRoot):
        FilesystemBundleHandle(root).write_text("link/PWNED.md", "pwned")
    assert not (outside / "PWNED.md").exists()


def test_a_symlinked_FILE_entry_is_allowed_on_purpose(tmp_path):
    """THE CARVE-OUT, pinned so nobody 'tightens' it into a regression.

    Only the entry's PARENT CHAIN is resolved. A symlinked LEAF is followed and
    allowed, because it is a real supported pattern: this repo's own root
    ``AGENTS.md`` is symlinked INTO a scope (``tests/test_agents_md_root.py``)
    and read through this handle. Resolving the leaf too broke that test — with
    the adapter logging 'Reader error … outside the bundle root' and the
    document silently vanishing from the scan — which is how the line got
    drawn where ``FilesystemSource._contained`` had already drawn it.

    The distinction is not arbitrary: a symlinked FILE moves exactly one file
    and is a deliberate act by whoever owns the bundle dir; a symlinked
    DIRECTORY relocates a whole subtree including everything written into it
    later."""
    root = tmp_path / "store" / "agents" / "a"
    root.mkdir(parents=True)
    real = tmp_path / "elsewhere" / "AGENTS.md"
    real.parent.mkdir(parents=True)
    real.write_text("# the real root AGENTS.md")
    (root / "AGENTS.md").symlink_to(real)

    handle = FilesystemBundleHandle(root)
    assert handle.exists("AGENTS.md")
    assert handle.is_file("AGENTS.md")
    assert handle.read_text("AGENTS.md") == "# the real root AGENTS.md"


def test_the_in_memory_handle_holds_the_same_rule(tmp_path):
    """``DictBundleHandle`` builds no path — but it is how the SQL adapters
    serve bundles, and its keys become ``dna_bundle_entries`` rows that a later
    ``emit`` MATERIALISES onto a filesystem. A traversing key stored there is
    the same escape, deferred."""
    handle = DictBundleHandle("a", {})
    handle.write_text("skills/foo/SKILL.md", "legit")
    assert handle.read_text("skills/foo/SKILL.md") == "legit"
    with pytest.raises(InvalidBundleEntry):
        handle.write_text("../../../../ESCAPED.md", "pwned")
    with pytest.raises(InvalidBundleEntry):
        handle.write_bytes("/etc/cron.d/pwn", b"pwned")


# ── layer 1: through Kernel.write_document, the way it was found ─────────────

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


def _agent(spec: dict) -> dict:
    return {"apiVersion": "helix.dna.dev/v1", "kind": "Agent",
            "metadata": {"name": "innocent"}, "spec": spec}


#: The five ``spec`` fields the writers turn into bundle entries, each with the
#: measured traversal depth for the BASE lane (4 ``..`` to reach the first
#: directory outside the store; a ``scripts/`` prefix absorbs one, so 5).
CONTENT_DERIVED_ENTRIES = [
    pytest.param(
        {"root_files": {"../../../../ROOT_FILES_ESCAPED.md": "pwned"}},
        "ROOT_FILES_ESCAPED.md", id="spec.root_files",
    ),
    pytest.param(
        {"source_files": {"../../../../SOURCE_FILES_ESCAPED.md": "pwned"}},
        "SOURCE_FILES_ESCAPED.md", id="spec.source_files",
    ),
    pytest.param(
        {"instruction_file": "../../../../INSTRUCTION_ESCAPED.md",
         "instruction": "pwned"},
        "INSTRUCTION_ESCAPED.md", id="spec.instruction_file",
    ),
    pytest.param(
        {"extras": {"../../../..": {"EXTRAS_ESCAPED.md": "pwned"}}},
        "EXTRAS_ESCAPED.md", id="spec.extras",
    ),
    pytest.param(
        {"scripts": {"../../../../../SCRIPTS_ESCAPED.md": "pwned"}},
        "SCRIPTS_ESCAPED.md", id="spec.scripts",
    ),
    pytest.param(
        {"references": {"../../../../../REFERENCES_ESCAPED.md": "pwned"}},
        "REFERENCES_ESCAPED.md", id="spec.references",
    ),
    pytest.param(
        {"assets": {"../../../../../ASSETS_ESCAPED.md": "pwned"}},
        "ASSETS_ESCAPED.md", id="spec.assets",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("spec,escaped", CONTENT_DERIVED_ENTRIES)
async def test_no_content_derived_entry_escapes_the_store_root(
    tmp_path, spec, escaped,
):
    """Driven through the FACADE, and proven by the TREE — not by the exception
    alone. Before the fix each of these returned version '1' and left a real
    file at ``<sandbox>/outer/<escaped>``."""
    k, store = _fs_kernel(tmp_path)
    before = {p for p in tmp_path.rglob("*")}

    with pytest.raises(KernelRefusal):
        await k.write_document(
            "test-mod", "Agent", "innocent", _agent({"model": "gpt-4o", **spec}),
        )

    strays = [p for p in tmp_path.rglob("*")
              if p.is_file() and not str(p).startswith(str(store) + "/")]
    assert not strays, f"the write escaped the store root: {strays}"
    assert not (tmp_path / "outer" / escaped).exists()
    del before


@pytest.mark.asyncio
async def test_an_absolute_content_derived_entry_writes_nowhere(tmp_path):
    """The absolute case has no depth to absorb it: ``pathlib`` discards the
    bundle root entirely, so this reached an arbitrary path on the machine."""
    k, _ = _fs_kernel(tmp_path)
    target = tmp_path / "arbitrary" / "ABSOLUTE_ESCAPED.md"
    target.parent.mkdir(parents=True)

    with pytest.raises(KernelRefusal):
        await k.write_document(
            "test-mod", "Agent", "innocent",
            _agent({"model": "gpt-4o", "root_files": {str(target): "pwned"}}),
        )
    assert not target.exists(), "an ABSOLUTE entry wrote to an arbitrary path"


@pytest.mark.asyncio
async def test_the_tenant_lane_is_closed_too(tmp_path):
    """Same escape, one layout deeper — the tenant bundle root is
    ``<store>/tenants/<t>/scopes/<scope>/agents/<name>``, so it takes 7 ``..``.
    Measured; a 4-deep traversal here would be absorbed and prove nothing."""
    k, store = _fs_kernel(tmp_path)
    with pytest.raises(KernelRefusal):
        await k.write_document(
            "test-mod", "Agent", "innocent",
            _agent({"model": "gpt-4o",
                    "root_files": {"../" * 7 + "TENANT_ESCAPED.md": "pwned"}}),
            tenant="t-1a2b3c.node.internal",
        )
    strays = [p for p in tmp_path.rglob("*")
              if p.is_file() and not str(p).startswith(str(store) + "/")]
    assert not strays, f"the tenant write escaped the store root: {strays}"


@pytest.mark.asyncio
async def test_the_ordinary_bundle_write_still_round_trips(tmp_path):
    """THE CONTROL, and the one that decides whether the rule is right: real
    bundles carry nested subdirectories and dotted filenames everywhere."""
    k, store = _fs_kernel(tmp_path)
    version = await k.write_document(
        "test-mod", "Agent", "innocent",
        _agent({
            "model": "gpt-4o",
            "root_files": {"skills/foo/SKILL.md": "# legit"},
            "scripts": {"run.py": "print(1)"},
            "references": {"spec.md": "ref"},
            "source_files": {"assets/logo.svg": "<svg/>"},
        }),
    )
    assert version == "1"
    bundle = store / "test-mod" / "agents" / "innocent"
    written = sorted(p.relative_to(bundle).as_posix()
                     for p in bundle.rglob("*") if p.is_file())
    assert written == [
        "AGENT.md", "assets/logo.svg", "references/spec.md",
        "scripts/run.py", "skills/foo/SKILL.md",
    ]
    assert (bundle / "skills" / "foo" / "SKILL.md").read_text() == "# legit"


@pytest.mark.asyncio
async def test_the_refusal_names_the_entry_so_the_caller_can_fix_it(tmp_path):
    k, _ = _fs_kernel(tmp_path)
    with pytest.raises(InvalidBundleEntry, match="ESCAPED"):
        await k.write_document(
            "test-mod", "Agent", "innocent",
            _agent({"model": "gpt-4o",
                    "root_files": {"../../../../ESCAPED.md": "pwned"}}),
        )


# ── the shared sink ──────────────────────────────────────────────────────────

def test_write_entries_to_handle_refuses_before_it_reaches_a_handle():
    """The EARLY layer. It does not close the class on its own — 8 in-repo
    writers bypass it and call ``bundle.write_text`` directly, which is why the
    handle is the closing layer — but a writer that DOES use the shared sink
    gets refused before a single byte is dispatched."""
    from dna.kernel.write.helpers import write_entries_to_handle

    handle = DictBundleHandle("a", {})
    with pytest.raises(InvalidBundleEntry):
        write_entries_to_handle(handle, [
            {"relativePath": "AGENT.md", "content": "ok"},
            {"relativePath": "../../../../ESCAPED.md", "content": "pwned"},
        ])
    assert "AGENT.md" not in handle._entries, (
        "the sink must validate the WHOLE batch before writing any of it — a "
        "partial write leaves the bundle in a state no caller asked for"
    )


def test_write_entries_to_handle_still_writes_a_legitimate_batch():
    from dna.kernel.write.helpers import write_entries_to_handle

    handle = DictBundleHandle("a", {})
    write_entries_to_handle(handle, [
        {"relativePath": "AGENT.md", "content": "# marker"},
        {"relativePath": "scripts/run.py", "content": "print(1)"},
        {"relativePath": "assets/logo.png", "content_bytes": b"\x89PNG"},
    ])
    assert handle.read_text("AGENT.md") == "# marker"
    assert handle.read_bytes("assets/logo.png") == b"\x89PNG"


def test_pop_source_files_as_entries_is_kind_agnostic_and_therefore_shared():
    """Pinning WHY the guard could not live in one Kind: this helper is the
    documented convention, and Agent, Skill, Tenant and TenantMembership all
    route through it."""
    from dna.kernel.write.helpers import pop_source_files_as_entries

    spec = {"source_files": {"a.md": "x", "b/c.md": "y"}}
    entries = pop_source_files_as_entries(spec, "Agent")
    assert sorted(e["relativePath"] for e in entries) == ["a.md", "b/c.md"]
    assert "source_files" not in spec


# ── serialize_document: the escape must not move one frame up the stack ──────

def test_serialize_document_never_hands_back_a_traversing_relative_path(tmp_path):
    """``serialize_document`` writes no bytes, but the WHOLE POINT of its
    payload is that a caller writes those ``relativePath`` values out. Before
    the fix a Skill carrying ``root_files`` came back as
    ``['skills/x/SKILL.md', 'skills/x/../../../etc/cron.d/pwn']`` — the escape
    relocated, not closed."""
    from dna.kernel import Kernel
    from dna.extensions.helix import HelixExtension

    k = Kernel()
    k.load(HelixExtension())
    raw = _agent({"model": "gpt-4o",
                  "root_files": {"../../../etc/cron.d/pwn": "pwned"}})

    with pytest.raises(InvalidBundleEntry):
        k.serialize_document("test-mod", "Agent", "innocent", raw)
    del tmp_path


def test_serialize_document_still_serializes_a_legitimate_bundle(tmp_path):
    from dna.kernel import Kernel
    from dna.extensions.helix import HelixExtension

    k = Kernel()
    k.load(HelixExtension())
    raw = _agent({"model": "gpt-4o", "root_files": {"skills/foo/SKILL.md": "x"}})
    files = k.serialize_document("test-mod", "Agent", "innocent", raw)["files"]

    assert files, "the control must still serialize"
    rels = [f["relativePath"] for f in files]
    assert any("skills/foo/SKILL.md" in r for r in rels), rels
    for r in rels:
        assert ".." not in Path(r).parts, r
        assert not Path(r).is_absolute(), r
    del tmp_path
