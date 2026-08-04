"""Copilot.spec.surfaces[] — o contrato da tela co-editada como dado (F2 do
adr-copiloto-como-dado, dobrado no Kind Copilot pela crítica de nome do
founder: "flow" colidia com Copilot.workflow/WorkflowEvent e com o vocabulário
de orquestração da indústria).

Pela PORTA, como sempre: surface válida grava; violação estrutural veta na
escrita; e o tombstone do CopilotFlow aponta o caminho novo."""

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


def _copilot(surfaces) -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Copilot",
        "metadata": {"name": "memory-copilot"},
        "spec": {
            "mounts": [{"id": "principal", "agent": "memory-agent", "path": "/agui"}],
            "serving": {"transport": "ag-ui"},
            "surfaces": surfaces,
        },
    }


@pytest.mark.asyncio
async def test_um_copilot_com_surface_valida_grava_e_rele(kernel):
    doc = _copilot([
        {
            "name": "memory-composer",
            "state_key": "draft",
            "tool_name": "update_memory_draft",
            "canvas_keys": ["draft", "scope", "ui"],
            "blocked_persist_tools": ["remember", "forget", "consolidate"],
            "guidance_template": None,
            "description": "O compositor de memória.",
        }
    ])
    await kernel.write_document("fluxos", "Copilot", "memory-copilot", doc)
    lido = await kernel.get_document("fluxos", "Copilot", "memory-copilot")
    surface = lido["spec"]["surfaces"][0]
    assert surface["state_key"] == "draft"
    assert surface["canvas_keys"] == ["draft", "scope", "ui"]


@pytest.mark.asyncio
async def test_surface_sem_state_key_e_vetada_na_escrita(kernel):
    from dna.kernel.protocols import SpecValidationError

    doc = _copilot([{"name": "x", "tool_name": "t", "canvas_keys": ["a"]}])
    with pytest.raises(SpecValidationError):
        await kernel.write_document("fluxos", "Copilot", "memory-copilot", doc)


@pytest.mark.asyncio
async def test_chave_fora_do_schema_e_vetada_data_honesty(kernel):
    from dna.kernel.protocols import SpecValidationError

    # steps ainda NÃO existem — entram quando o renderer que os lê shippar.
    doc = _copilot([
        {
            "name": "x", "state_key": "x", "tool_name": "t",
            "canvas_keys": ["x"], "steps": [{"id": "um"}],
        }
    ])
    with pytest.raises(SpecValidationError):
        await kernel.write_document("fluxos", "Copilot", "memory-copilot", doc)


@pytest.mark.asyncio
async def test_o_tombstone_do_copilot_flow_aponta_o_caminho(kernel):
    from dna.kernel import KindRetiredError

    doc = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "CopilotFlow",
        "metadata": {"name": "qualquer"},
        "spec": {"state_key": "x", "tool_name": "t", "canvas_keys": ["x"]},
    }
    with pytest.raises(KindRetiredError) as ei:
        await kernel.write_document("fluxos", "CopilotFlow", "qualquer", doc)
    assert "surfaces" in str(ei.value)
