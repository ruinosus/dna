"""CopilotFlow (F2 do adr-copiloto-como-dado) — o Kind pela PORTA.

O fluxo do arquétipo (medido 3× nos spikes) como documento: o runtime do
dna-cloud resolve docs deste Kind sobre o registry embutido. Aqui só o
contrato do Kind: escrita válida entra; violação estrutural é vetada na
escrita (a lição guard-na-porta)."""

from __future__ import annotations

import pytest


@pytest.fixture()
def kernel(tmp_path):
    from dna.adapters.filesystem import FilesystemCache
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.extensions.helix import HelixExtension
    from dna.kernel import Kernel

    (tmp_path / "fluxos").mkdir()
    k = Kernel()
    k.load(HelixExtension())
    k.source(FilesystemWritableSource(tmp_path, kernel=k))
    k.cache(FilesystemCache(tmp_path / ".dna-cache"))
    yield k


@pytest.mark.asyncio
async def test_um_fluxo_valido_grava_e_rele(kernel):
    doc = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "CopilotFlow",
        "metadata": {"name": "memory-composer"},
        "spec": {
            "state_key": "draft",
            "tool_name": "update_memory_draft",
            "canvas_keys": ["draft", "scope", "ui"],
            "blocked_persist_tools": ["remember", "forget", "consolidate"],
            "guidance_template": None,
            "description": "O compositor de memória.",
        },
    }
    await kernel.write_document("fluxos", "CopilotFlow", "memory-composer", doc)
    lido = await kernel.get_document("fluxos", "CopilotFlow", "memory-composer")
    assert lido["spec"]["state_key"] == "draft"
    assert lido["spec"]["canvas_keys"] == ["draft", "scope", "ui"]


@pytest.mark.asyncio
async def test_sem_state_key_o_guard_veta_na_escrita(kernel):
    from dna.kernel.protocols import SpecValidationError

    doc = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "CopilotFlow",
        "metadata": {"name": "quebrado"},
        "spec": {"tool_name": "x", "canvas_keys": ["a"]},
    }
    with pytest.raises(SpecValidationError):
        await kernel.write_document("fluxos", "CopilotFlow", "quebrado", doc)


@pytest.mark.asyncio
async def test_chave_desconhecida_e_vetada_o_schema_e_fechado(kernel):
    from dna.kernel.protocols import SpecValidationError

    doc = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "CopilotFlow",
        "metadata": {"name": "com-steps"},
        "spec": {
            "state_key": "x", "tool_name": "t", "canvas_keys": ["x"],
            # steps ainda NÃO existem no schema — data-honesty: um campo que
            # nada lê é formulário-sem-fio; ele entra quando o renderer
            # genérico que o consome shippar (registrado no ADR).
            "steps": [{"id": "um"}],
        },
    }
    with pytest.raises(SpecValidationError):
        await kernel.write_document("fluxos", "CopilotFlow", "com-steps", doc)
