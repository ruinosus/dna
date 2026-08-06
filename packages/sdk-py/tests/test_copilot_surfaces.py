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
    await kernel.write_instance("fluxos", "Copilot", "memory-copilot", doc)
    lido = await kernel.get_instance("fluxos", "Copilot", "memory-copilot")
    surface = lido["spec"]["surfaces"][0]
    assert surface["state_key"] == "draft"
    assert surface["canvas_keys"] == ["draft", "scope", "ui"]


@pytest.mark.asyncio
async def test_surface_sem_state_key_e_vetada_na_escrita(kernel):
    from dna.kernel.protocols import SpecValidationError

    doc = _copilot([{"name": "x", "tool_name": "t", "canvas_keys": ["a"]}])
    with pytest.raises(SpecValidationError):
        await kernel.write_instance("fluxos", "Copilot", "memory-copilot", doc)


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
        await kernel.write_instance("fluxos", "Copilot", "memory-copilot", doc)


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
        await kernel.write_instance("fluxos", "CopilotFlow", "qualquer", doc)
    assert "surfaces" in str(ei.value)


@pytest.mark.asyncio
async def test_surface_com_steps_declarados_grava_e_rele(kernel):
    """F4: o wizard declarado — steps com campos do Kind e gate humano."""
    doc = _copilot([
        {
            "name": "contrato-intake",
            "state_key": "document_draft",
            "tool_name": "update_instance_draft",
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
    await kernel.write_instance("fluxos", "Copilot", "memory-copilot", doc)
    lido = await kernel.get_instance("fluxos", "Copilot", "memory-copilot")
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
        await kernel.write_instance("fluxos", "Copilot", "memory-copilot", doc)


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
    await kernel.write_instance("fluxos", "Copilot", "memory-copilot", doc)
    lido = await kernel.get_instance("fluxos", "Copilot", "memory-copilot")
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
        await kernel.write_instance("fluxos", "Copilot", "memory-copilot", doc)


@pytest.mark.asyncio
async def test_interaction_presenca_liga_com_defaults_seguros(kernel):
    """F6.c: declarar o bloco É ligar a capacidade — `{}` funciona (o padrão
    voice_persona medido no spike do cardápio)."""
    doc = _copilot([])
    doc["spec"]["interaction"] = {
        "attachments": {"image": {}, "text": {"extensions": [".md"]}},
        "suggestions": {"from_steps": True, "static": [
            {"title": "Extrair", "message": "Extraia os campos do contrato anexado."}
        ]},
    }
    await kernel.write_instance("fluxos", "Copilot", "memory-copilot", doc)
    lido = await kernel.get_instance("fluxos", "Copilot", "memory-copilot")
    it = lido["spec"]["interaction"]
    assert it["attachments"]["image"] == {} or "max_per_turn" in it["attachments"]["image"]
    assert it["suggestions"]["static"][0]["title"] == "Extrair"


@pytest.mark.asyncio
async def test_interaction_sugestao_sem_message_e_vetada(kernel):
    from dna.kernel.protocols import SpecValidationError

    doc = _copilot([])
    doc["spec"]["interaction"] = {"suggestions": {"static": [{"title": "só título"}]}}
    with pytest.raises(SpecValidationError):
        await kernel.write_instance("fluxos", "Copilot", "memory-copilot", doc)


@pytest.mark.asyncio
async def test_interaction_voice_presenca_liga(kernel):
    """spec-interaction-voice: o bloco voice entra no cardápio JUNTO com o
    renderer (dna-cloud#302 — regra renderer-first cumprida). Presença liga:
    `{}` funciona; os campos são só os que o runtime shipado lê."""
    doc = _copilot([])
    doc["spec"]["interaction"] = {"voice": {}}
    await kernel.write_instance("fluxos", "Copilot", "memory-copilot", doc)
    lido = await kernel.get_instance("fluxos", "Copilot", "memory-copilot")
    assert "voice" in lido["spec"]["interaction"]

    doc["spec"]["interaction"] = {
        "voice": {
            "voice": "marin",
            "style": "calmo, pausado",
            "identity_lock": "Você é o copiloto de escrita do workspace.",
            "budget": {"max_session_seconds": 120},
        }
    }
    await kernel.write_instance("fluxos", "Copilot", "memory-copilot", doc)
    lido = await kernel.get_instance("fluxos", "Copilot", "memory-copilot")
    assert lido["spec"]["interaction"]["voice"]["budget"]["max_session_seconds"] == 120


@pytest.mark.asyncio
async def test_interaction_voice_campo_morto_e_vetado(kernel):
    """Os campos da persona de referência que NENHUM runtime lia (archetype,
    wake_word…) ficam FORA por regra F4 — declarar um deles é erro, não
    silêncio."""
    from dna.kernel.protocols import SpecValidationError

    doc = _copilot([])
    doc["spec"]["interaction"] = {"voice": {"archetype": "sábio"}}
    with pytest.raises(SpecValidationError):
        await kernel.write_instance("fluxos", "Copilot", "memory-copilot", doc)


@pytest.mark.asyncio
async def test_interaction_sandbox_presenca_liga(kernel):
    """i-097: o bloco `sandbox` entra JUNTO com o runtime que o lê (o executor
    de scripts de skill shipou em dna-cloud#319 e já faz o merge). Presença
    liga — `{}` funciona e significa "sem rebaixamento": valem os limites
    operacionais do host."""
    doc = _copilot([])
    doc["spec"]["interaction"] = {"sandbox": {}}
    await kernel.write_instance("fluxos", "Copilot", "memory-copilot", doc)
    lido = await kernel.get_instance("fluxos", "Copilot", "memory-copilot")
    assert "sandbox" in lido["spec"]["interaction"]

    doc["spec"]["interaction"] = {
        "sandbox": {
            "budget": {"max_execute_seconds": 30, "max_session_seconds": 120},
            "allow_internet": False,
        }
    }
    await kernel.write_instance("fluxos", "Copilot", "memory-copilot", doc)
    bloco = (await kernel.get_instance("fluxos", "Copilot", "memory-copilot"))[
        "spec"
    ]["interaction"]["sandbox"]
    assert bloco["budget"] == {"max_execute_seconds": 30, "max_session_seconds": 120}
    assert bloco["allow_internet"] is False


@pytest.mark.asyncio
async def test_interaction_sandbox_campo_sem_leitor_e_vetado(kernel):
    """A regra F4 aplicada ao bloco novo: o orçamento de UPLOAD é constante do
    host — o merge do runtime preserva o valor dele e nunca olha o doc. Um campo
    que ninguém lê renderiza como se funcionasse; declarar tem de ser ERRO."""
    from dna.kernel.protocols import SpecValidationError

    doc = _copilot([])
    doc["spec"]["interaction"] = {"sandbox": {"max_upload_bytes": 9_000_000}}
    with pytest.raises(SpecValidationError):
        await kernel.write_instance("fluxos", "Copilot", "memory-copilot", doc)

    doc["spec"]["interaction"] = {"sandbox": {"budget": {"max_upload_bytes": 9_000_000}}}
    with pytest.raises(SpecValidationError):
        await kernel.write_instance("fluxos", "Copilot", "memory-copilot", doc)


@pytest.mark.asyncio
async def test_interaction_sandbox_recusa_o_que_seria_grampeado_em_silencio(kernel):
    """Os tetos ABSOLUTOS estão no schema porque um número acima deles não é um
    rebaixamento — é um pedido que o runtime cortaria calado. Recusar na escrita
    é o único momento em que alguém ainda lê a mensagem."""
    from dna.kernel.protocols import SpecValidationError

    doc = _copilot([])
    for budget in (
        {"max_execute_seconds": 3600},   # acima do teto de UM comando
        {"max_execute_seconds": 0},      # nem existe execução de zero segundo
        {"max_session_seconds": 86_400}, # um dia de sandbox é um job, não um turno
    ):
        doc["spec"]["interaction"] = {"sandbox": {"budget": budget}}
        with pytest.raises(SpecValidationError):
            await kernel.write_instance("fluxos", "Copilot", "memory-copilot", doc)
