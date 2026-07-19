"""s-platform-inherit-by-default — scope inheritance is DENYLIST by default.

`_lib` é o padrão/stdlib declarativo; cada scope/tenant herda TUDO dele por
default e só sobrescreve o que quiser (class B(A), override local ganha). Apenas o
ledger SDLC + os Kinds estruturais NÃO herdam.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from dna.kernel import Kernel
from dna.kernel.resolver import DEFAULT_NON_INHERITABLE_KINDS_V1
from dna.extensions.helix import HelixExtension
from dna.extensions.sdlc import SdlcExtension
from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource


_LEDGER_AND_STRUCTURAL = {
    "Story", "Issue", "Feature", "Milestone", "Roadmap",
    "Narrative", "VibeSession", "Engram", "Plan",
    "Genome", "KindDefinition", "LayerPolicy",
}


def test_ledger_and_structural_do_not_inherit():
    # _INHERITABLE_KINDS is now a derived instance property
    # (s-kernel-kindport-classification-attrs).
    inh = Kernel.auto()._INHERITABLE_KINDS
    for kind in _LEDGER_AND_STRUCTURAL:
        assert kind not in inh, kind
        assert kind in DEFAULT_NON_INHERITABLE_KINDS_V1, kind


def test_everything_else_inherits_by_default():
    inh = Kernel.auto()._INHERITABLE_KINDS
    # template-y kinds that already inherited
    for kind in ("Agent", "PromptTemplate", "Skill", "Theme",
                 "LottieAsset", "Automation", "ImagePrompt", "HtmlTemplate"):
        assert kind in inh, kind
    # arbitrary / never-allowlisted kinds now inherit by default
    for kind in ("Reference", "EvalCase", "SomeFutureKind", "ModelProfile"):
        assert kind in inh, kind


def _make_kernel(tmp: Path) -> Kernel:
    for s in ("scope", "_lib"):
        (tmp / s).mkdir(exist_ok=True)
        (tmp / s / ("manifest.yaml" if s == "scope" else "Genome.yaml")).write_text(
            "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
            f"metadata: {{name: {s}}}\nspec: {{}}\n"
        )
    k = Kernel()
    # HelixExtension registers Engram (s-engram-rename) and SdlcExtension the
    # rest of the ledger Kinds, so the kernel can read their
    # scope_inheritable=False classification (s-kernel-kindport-
    # classification-attrs — classification now comes from the registered
    # Kind, not a hardcoded name list).
    k.load(HelixExtension())
    k.load(SdlcExtension())
    k.source(FilesystemWritableSource(str(tmp), writers=list(k._writers), kernel=k))
    k.cache(FilesystemCache(tmp / ".dna-cache"))
    return k


def test_child_inherits_arbitrary_kind_but_not_ledger(tmp_path: Path):
    async def _run():
        k = _make_kernel(tmp_path)
        # A Kind that was NEVER in the old allowlist, written only to _lib.
        await k.write_document(
            "_lib", "Skill", "shared-skill",
            {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Skill",
             "metadata": {"name": "shared-skill"}, "spec": {"body": "x"}},
            tenant=None,
        )
        # A ledger doc in _lib must NOT leak into the child scope. Engram's
        # real api_version genuinely IS github.com/ruinosus/dna/v1
        # (s-engram-rename) — write-path validation (i-008) now applies, so
        # the spec must satisfy the schema's required fields.
        await k.write_document(
            "_lib", "Engram", "platform-lesson",
            {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Engram",
             "metadata": {"name": "platform-lesson"},
             "spec": {
                 "area": "Feature/inherit-by-default",
                 "surface_when": ["feature_touched"],
                 "source_refs": ["s-platform-inherit-by-default"],
                 "affect": "triumph",
                 "summary": "y",
             }},
            tenant=None,
        )
        mi = await k.instance_async("scope")
        # inherits the Skill
        assert await mi.one_async("Skill", "shared-skill") is not None
        # does NOT inherit the ledger Engram
        assert await mi.one_async("Engram", "platform-lesson") is None

    asyncio.run(_run())


def test_inheritance_failsoft_when_platform_absent(tmp_path: Path):
    """No _lib scope on the source → reads still work (no crash)."""
    async def _run():
        (tmp_path / "scope").mkdir()
        (tmp_path / "scope" / "manifest.yaml").write_text(
            "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
            "metadata: {name: scope}\nspec: {}\n"
        )
        k = Kernel()
        k.load(HelixExtension())
        k.source(FilesystemWritableSource(str(tmp_path), writers=list(k._writers), kernel=k))
        k.cache(FilesystemCache(tmp_path / ".dna-cache"))
        # Querying an inheritable Kind must not raise even though _lib is absent.
        rows = [r async for r in k.query("scope", "Skill")]
        assert rows == []
        assert await k.get_document("scope", "Skill", "nope") is None

    asyncio.run(_run())
