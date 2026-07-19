"""s-write-path-despecialize — the kernel write path has NO Kind-name
special-cases; extension-owned rules ride the ``pre_save`` veto channel.

Three layers of guarantees:

1. AST ratchet — no concrete Kind-name string literal ("Agent",
   "Engram", "Genome", ...) inside ``write_document`` /
   ``_write_document_inner`` / ``delete_document``. Generic dispatch by
   KindPort ATTRIBUTE (e.g. ``is_catalog_identity``) is fine; matching by
   name in the kernel is domain leakage and fails here.
2. Veto-channel mechanics — priority ordering, key-idempotent registration,
   sync+async listeners, exception propagation (the veto).
3. Write-path regressions previously only covered inline — bitemporal
   Engram preservation via ``write_document`` (SdlcExtension hook,
   Engram itself registered by HelixExtension since s-engram-rename)
   and the Genome write → catalog-cache drop keyed by
   ``is_catalog_identity``.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from dna.kernel import Kernel
from dna.kernel.hooks import HookRegistry, PreSaveContext
from tests.test_kernel_invalidate_modes import _FakeWritableSource

# ---------------------------------------------------------------------------
# 1. AST ratchet — kernel write path is Kind-name agnostic
# ---------------------------------------------------------------------------

_KERNEL_INIT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "dna" / "kernel" / "__init__.py"
)

# The write path must never branch on these concrete Kind names — the rules
# belong to the extensions that own the Kinds (helix / sdlc / ...). Extend
# the set as more Kinds earn write rules: they must arrive as pre_save veto
# hooks, never as kernel special-cases.
_FORBIDDEN_KIND_LITERALS = frozenset({
    "Agent", "Engram", "Genome",
})

_WRITE_PATH_FUNCTIONS = ("write_document", "_write_document_inner", "delete_document")


def _write_path_function_nodes() -> list[ast.AsyncFunctionDef]:
    tree = ast.parse(_KERNEL_INIT.read_text())
    found: dict[str, ast.AsyncFunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in _WRITE_PATH_FUNCTIONS:
                found[node.name] = node  # type: ignore[assignment]
    missing = set(_WRITE_PATH_FUNCTIONS) - set(found)
    assert not missing, f"write-path functions moved/renamed: {sorted(missing)}"
    return [found[n] for n in _WRITE_PATH_FUNCTIONS]


def test_write_path_has_no_hardcoded_kind_names():
    offenders: list[str] = []
    for fn in _write_path_function_nodes():
        body = list(fn.body)
        # The function docstring legitimately NARRATES Kinds (e.g. the
        # invalidate_mode bullets) — drop it; only executable code counts.
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]
        for stmt in body:
            for node in ast.walk(stmt):
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and node.value in _FORBIDDEN_KIND_LITERALS
                ):
                    offenders.append(
                        f"{fn.name}:{node.lineno} → {node.value!r}"
                    )
    assert not offenders, (
        "Kernel write path grew a hardcoded Kind-name special-case "
        "(s-write-path-despecialize). Move the rule to the owning extension "
        "as a pre_save veto hook (kernel.on_veto), or key it off a KindPort "
        "attribute:\n  " + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# 2. Veto channel mechanics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_veto_priority_order_and_async_mix():
    reg = HookRegistry()
    calls: list[str] = []

    async def late(_ctx):
        calls.append("late")

    def early(_ctx):
        calls.append("early")

    reg.on_veto("pre_save", late, priority=50)
    reg.on_veto("pre_save", early, priority=10)
    assert reg.has_veto("pre_save")
    assert reg.has("pre_save")  # veto listeners count as registered hooks
    await reg.emit_veto("pre_save", PreSaveContext(
        scope="s", kind="K", name="n", raw={},
    ))
    assert calls == ["early", "late"]


@pytest.mark.asyncio
async def test_veto_raise_propagates_and_aborts_chain():
    reg = HookRegistry()
    calls: list[str] = []

    def guard(_ctx):
        calls.append("guard")
        raise ValueError("vetoed")

    def never(_ctx):
        calls.append("never")

    reg.on_veto("pre_save", guard, priority=1)
    reg.on_veto("pre_save", never, priority=2)
    with pytest.raises(ValueError, match="vetoed"):
        await reg.emit_veto("pre_save", PreSaveContext(
            scope="s", kind="K", name="n", raw={},
        ))
    assert calls == ["guard"]  # chain aborted at the veto


@pytest.mark.asyncio
async def test_veto_key_registration_is_idempotent():
    reg = HookRegistry()
    calls: list[str] = []
    reg.on_veto("pre_save", lambda _c: calls.append("v1"), key="ext.rule")
    reg.on_veto("pre_save", lambda _c: calls.append("v2"), key="ext.rule")
    await reg.emit_veto("pre_save", PreSaveContext(
        scope="s", kind="K", name="n", raw={},
    ))
    assert calls == ["v2"]  # replaced, not stacked


@pytest.mark.asyncio
async def test_write_document_emits_pre_save_even_with_skip_hooks():
    """pre_save veto hooks are integrity gates — ``skip_hooks`` only
    silences post_save, it must NOT bypass the guards."""
    k = Kernel()
    k.source(_FakeWritableSource())
    seen: list[PreSaveContext] = []
    k.on_veto("pre_save", seen.append)
    raw = {"apiVersion": "x/v1", "kind": "Doc", "metadata": {"name": "d"},
           "spec": {"a": 1}}
    await k.write_document("scope-x", "Doc", "d", raw, skip_hooks=True)
    assert len(seen) == 1
    ctx = seen[0]
    assert (ctx.scope, ctx.kind, ctx.name) == ("scope-x", "Doc", "d")
    assert ctx.raw is raw          # live payload — mutation reaches the save
    assert ctx.kernel is k


@pytest.mark.asyncio
async def test_write_document_veto_blocks_persist():
    k = Kernel()
    src = _FakeWritableSource()
    k.source(src)

    def guard(ctx):
        if ctx.kind == "Doc":
            raise PermissionError("no Docs today")

    k.on_veto("pre_save", guard)
    raw = {"apiVersion": "x/v1", "kind": "Doc", "metadata": {"name": "d"},
           "spec": {}}
    with pytest.raises(PermissionError):
        await k.write_document("scope-x", "Doc", "d", raw)
    assert src.save_calls == []  # nothing persisted


# ---------------------------------------------------------------------------
# 3. Write-path regressions for the migrated rules
# ---------------------------------------------------------------------------

def _ll_raw(name: str, spec: dict) -> dict:
    return {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Engram",
            "metadata": {"name": name}, "spec": spec}


@pytest.mark.asyncio
async def test_bitemporal_guard_fires_through_write_document(tmp_path):
    """A maintenance re-write of a superseded Engram (no valid_to)
    must NOT resurrect it — the SdlcExtension pre_save hook preserves
    valid_to/superseded_by_memory before the save (i-046). The hook stays
    wired by SdlcExtension even though Engram itself now registers via
    HelixExtension (s-engram-rename) — both are loaded here."""
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.extensions.helix import HelixExtension
    from dna.extensions.sdlc import SdlcExtension

    k = Kernel()
    k.load(SdlcExtension())
    k.load(HelixExtension())
    src = FilesystemWritableSource(str(tmp_path / ".dna"))
    k.source(src)
    src.attach_kernel(k)

    # Full required set (area/surface_when/source_refs/affect/summary) — the
    # generic write-path validation (i-008) now vetoes the skeletal fixture
    # this test used to write.
    _ll_base = {
        "area": "Feature/despecialize",
        "surface_when": ["feature_touched"],
        "source_refs": ["s-1"],
        "affect": "triumph",
        "affect_reason": "guard preserved rem-x valid_to across maintenance write",
        "summary": "old lesson",
    }
    superseded = _ll_raw("rem-x", {
        **_ll_base,
        "valid_to": "2026-06-02T00:00:00+00:00",
        "superseded_by_memory": "sem-x",
    })
    await k.write_document("proj", "Engram", "rem-x", superseded)

    # Maintenance write drops valid_to (decay/cue hooks re-emit by name).
    maintenance = _ll_raw("rem-x", {**_ll_base, "surface_count": 3})
    await k.write_document("proj", "Engram", "rem-x", maintenance)

    stored = await k.get_document("proj", "Engram", "rem-x")
    assert stored is not None
    assert stored["spec"]["valid_to"] == "2026-06-02T00:00:00+00:00"
    assert stored["spec"]["superseded_by_memory"] == "sem-x"
    assert stored["spec"]["surface_count"] == 3  # maintenance payload kept


@pytest.mark.asyncio
async def test_package_write_drops_catalog_cache_via_attribute():
    """The catalog-cache drop is keyed by ``KindPort.is_catalog_identity``
    (GenomeKind), not a hardcoded name — a Genome write clears the cache,
    a non-catalog write leaves it alone."""
    from dna.extensions.helix import HelixExtension

    k = Kernel()
    k.load(HelixExtension())
    k.source(_FakeWritableSource())

    kp = k.kind_port_for("Genome")
    assert kp is not None and kp.is_catalog_identity is True

    k._catalog_cache["acme"] = (0.0, [("s", None)])
    await k.write_document(
        "other-scope", "Agent", "helper",
        {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
         "metadata": {"name": "helper"}, "spec": {"instruction": "hi"}},
    )
    assert "acme" in k._catalog_cache  # non-catalog Kind → cache untouched

    await k.write_document(
        "pkg-scope", "Genome", "pkg-scope",
        {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
         "metadata": {"name": "pkg-scope"}, "spec": {"default_agent": "x"}},
    )
    assert k._catalog_cache == {}  # catalog-identity write → full drop
