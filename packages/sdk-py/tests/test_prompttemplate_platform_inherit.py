"""s-externalize-generator-personas — PromptTemplate é inheritable de _lib.

Os generators de llm_generators/ (lesson/teaching/intro) externalizam o corpo do
user-prompt num PromptTemplate Kind em _lib. Pra a rota resolver esse doc
de QUALQUER scope (Lumi/Pictogram, SDK teaching, etc), PromptTemplate precisa
herdar de _lib — mesma semântica de Agent/Skill/JobType. Este teste
prova a herança de fato: escreve um PromptTemplate só em _lib e resolve de
um scope filho que não tem cópia local.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from dna.kernel import Kernel
from dna.extensions.helix import HelixExtension
from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource


def test_prompttemplate_in_inheritable_sets():
    # Membership lock (Py kernel + V1 resolver mirror).
    from dna.kernel.resolver import DEFAULT_INHERITABLE_KINDS_V1

    # _INHERITABLE_KINDS is now a derived instance property
    # (s-kernel-kindport-classification-attrs).
    assert "PromptTemplate" in Kernel.auto()._INHERITABLE_KINDS
    assert "PromptTemplate" in DEFAULT_INHERITABLE_KINDS_V1


def _make_kernel(tmp: Path) -> Kernel:
    (tmp / "scope").mkdir(exist_ok=True)
    (tmp / "scope" / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
        "metadata: {name: scope}\nspec: {}\n"
    )
    (tmp / "_lib").mkdir(exist_ok=True)
    (tmp / "_lib" / "Genome.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
        "metadata: {name: _lib}\nspec: {}\n"
    )
    k = Kernel()
    k.load(HelixExtension())
    src = FilesystemWritableSource(str(tmp), writers=list(k._writers), kernel=k)
    k.source(src)
    k.cache(FilesystemCache(tmp / ".dna-cache"))
    return k


def test_child_scope_resolves_platform_prompttemplate(tmp_path: Path):
    async def _run():
        k = _make_kernel(tmp_path)
        # PromptTemplate lives ONLY in _lib.
        await k.write_document(
            "_lib", "PromptTemplate", "shared-prompt",
            {
                "apiVersion": "github.com/ruinosus/dna/v1",
                "kind": "PromptTemplate",
                "metadata": {"name": "shared-prompt"},
                "spec": {"body": "OLA {who}"},
            },
            tenant=None,
        )
        mi = await k.instance_async("scope")
        doc = await mi.one_async("PromptTemplate", "shared-prompt")
        assert doc is not None, "child scope should inherit the _lib PromptTemplate"
        assert (doc.spec or {}).get("body") == "OLA {who}"

    asyncio.run(_run())
