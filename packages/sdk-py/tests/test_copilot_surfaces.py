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

    # F4 criou steps[] (o renderer nasceu junto); uma chave que o schema
    # NÃO declara segue vetada — a honestidade continua na porta.
    doc = _copilot([
        {
            "name": "x", "state_key": "x", "tool_name": "t",
            "canvas_keys": ["x"], "invalidacoes": [{"quandoMuda": "x"}],
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


@pytest.mark.asyncio
async def test_surface_com_steps_declarados_grava_e_rele(kernel):
    """F4: o wizard declarado — steps com campos do Kind e gate humano."""
    doc = _copilot([
        {
            "name": "contrato-intake",
            "state_key": "document_draft",
            "tool_name": "update_document_draft",
            "canvas_keys": ["document_draft"],
            "kind": "ContratoDeServico",
            "steps": [
                {"id": "identificacao", "title": "Identificação",
                 "fields": ["titulo", "contratante"]},
                {"id": "condicoes", "title": "Condições",
                 "fields": ["valor_mensal"], "gate": True},
            ],
        }
    ])
    await kernel.write_document("fluxos", "Copilot", "memory-copilot", doc)
    lido = await kernel.get_document("fluxos", "Copilot", "memory-copilot")
    steps = lido["spec"]["surfaces"][0]["steps"]
    assert [s["id"] for s in steps] == ["identificacao", "condicoes"]
    assert steps[1]["gate"] is True


@pytest.mark.asyncio
async def test_step_sem_titulo_e_vetado(kernel):
    from dna.kernel.protocols import SpecValidationError

    doc = _copilot([
        {
            "name": "x", "state_key": "x", "tool_name": "t",
            "canvas_keys": ["x"], "steps": [{"id": "um"}],
        }
    ])
    with pytest.raises(SpecValidationError):
        await kernel.write_document("fluxos", "Copilot", "memory-copilot", doc)


@pytest.mark.asyncio
async def test_mcp_servers_extras_gravam_e_releem(kernel):
    """F6.a: o doc declara MCPs extras com o DE-PARA no vocabulário fastmcp
    (bloco de transform permissivo — a autoridade é o Pydantic oficial)."""
    doc = _copilot([])
    doc["spec"]["mcp_servers"] = [{
        "name": "meu-crm",
        "url": "https://crm.example/mcp",
        "transport": "streamable_http",
        "headers_env": {"X-Api-Key": "CRM_KEY"},
        "include_tags": ["leitura"],
        "tools": {
            "buscar_registro": {
                "name": "buscar_cliente",
                "description": "Busca um cliente pelo nome.",
                "arguments": {"q": {"name": "nome_do_cliente"}},
            }
        },
    }]
    await kernel.write_document("fluxos", "Copilot", "memory-copilot", doc)
    lido = await kernel.get_document("fluxos", "Copilot", "memory-copilot")
    srv = lido["spec"]["mcp_servers"][0]
    assert srv["url"] == "https://crm.example/mcp"
    assert srv["tools"]["buscar_registro"]["name"] == "buscar_cliente"
    # credencial NUNCA no doc — só o NOME da env var viaja
    assert srv["headers_env"] == {"X-Api-Key": "CRM_KEY"}


@pytest.mark.asyncio
async def test_mcp_server_sem_url_e_vetado(kernel):
    from dna.kernel.protocols import SpecValidationError

    doc = _copilot([])
    doc["spec"]["mcp_servers"] = [{"name": "quebrado"}]
    with pytest.raises(SpecValidationError):
        await kernel.write_document("fluxos", "Copilot", "memory-copilot", doc)
