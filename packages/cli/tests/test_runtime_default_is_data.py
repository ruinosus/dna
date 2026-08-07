"""i-101 + i-102 — o default do runtime é DADO, e a ausência de doc não é erro.

Os dois issues são o mesmo defeito visto de dois lados, e por isso a bateria é
uma só:

* **i-101** — `get_template('memory-recall-briefing')` devolvia um ERRO para o
  estado NORMAL de qualquer scope sem override. Medido em 06/08/2026 no
  ambiente do founder, com a voz funcionando perfeitamente.
* **i-102** — a voz de maior tráfego do produto (o briefing que o recall injeta
  em todo turno) só existia como constante de código; o catálogo respondia
  "vazio" e o portal carregava uma CÓPIA hardcoded do mesmo texto.

⚠️ **A bateria ATRAVESSA A PORTA.** Chamar `get_template_impl` prova a função;
o que quebrou na tela do founder foi a TOOL MCP, e é ela que estes testes
chamam — `fastmcp.Client` sobre o servidor real, o mesmo caminho do Claude
Desktop. A lição está na memória da casa como "guard existe, porta não chama":
um conserto validado só em unit já passou verde com a porta ainda quebrada.
"""
from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("fastmcp", reason="a face MCP precisa do extra opcional 'fastmcp'")

from fastmcp import Client  # noqa: E402

from dna_cli import _mcp_server as M  # noqa: E402


@pytest.fixture
def scope_vazio(tmp_path, monkeypatch):
    """Um scope SEM nenhum PromptTemplate autorado — o estado de toda instalação
    nova, e exatamente o estado em que o founder mediu o erro."""
    base = tmp_path / ".dna"
    (base / "kit").mkdir(parents=True)
    (base / "kit" / "Package.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Package\n"
        "metadata:\n  name: kit\nspec:\n  description: kit\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DNA_BASE_DIR", str(base))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return base


def _texto(resultado) -> str:
    """O conteúdo textual de uma resposta de tool do fastmcp."""
    partes = [getattr(b, "text", "") for b in (resultado.content or [])]
    return "\n".join(p for p in partes if p)


def _payload(resultado) -> dict:
    dados = getattr(resultado, "data", None)
    if isinstance(dados, dict):
        return dados
    estruturado = getattr(resultado, "structured_content", None)
    if isinstance(estruturado, dict):
        return estruturado
    return json.loads(_texto(resultado))


# ── i-101: a porta responde, não erra ──────────────────────────────────────


def test_get_template_pela_porta_mcp_nao_erra_para_o_default_vigente(scope_vazio):
    """A reprodução literal do achado: a MESMA chamada, pela MESMA porta.

    Antes: `isError: true` com "PromptTemplate 'memory-recall-briefing' not
    found in scope". Agora: a resposta serve o corpo que ESTÁ rodando e diz de
    onde ele vem."""

    async def cenario():
        server = M.build_server(base_dir=str(scope_vazio))
        async with Client(server) as client:
            return await client.call_tool(
                "get_template", {"name": "memory-recall-briefing", "scope": "kit"}
            )

    resultado = asyncio.run(cenario())
    assert not resultado.is_error, _texto(resultado)

    dados = _payload(resultado)
    assert dados["origin"] == "runtime-default"
    assert dados["name"] == "memory-recall-briefing"
    # O corpo servido é o que o recall injeta de verdade — não um placeholder.
    from dna.runtime.middleware.recall import BRIEFING_DEFAULT

    assert dados["body"] == BRIEFING_DEFAULT
    assert "{memories}" in dados["body"]
    assert dados["variables"] == ["memories"]
    # A frase precisa dizer as três coisas que faltavam no erro: que nada
    # quebrou, quem está falando, e como passar a mandar.
    assert "normal state" in dados["note"]
    assert "dna.runtime.middleware.recall" in dados["note"]
    assert "override" in dados["note"]


def test_nome_inexistente_continua_erro_e_agora_lista_o_que_existe(scope_vazio):
    """O conserto do i-101 não pode virar "nunca erra". Um nome que não é doc
    NEM default do runtime é erro do chamador — e a mensagem agora oferece a
    saída, em vez de mandar o modelo adivinhar a grafia."""

    async def cenario():
        server = M.build_server(base_dir=str(scope_vazio))
        async with Client(server) as client:
            return await client.call_tool(
                "get_template", {"name": "voz-que-nao-existe", "scope": "kit"},
                raise_on_error=False,
            )

    resultado = asyncio.run(cenario())
    assert resultado.is_error
    texto = _texto(resultado)
    assert "not a known runtime default" in texto
    assert "memory-recall-briefing" in texto


# ── i-102: o default é catálogo, não segredo do código ─────────────────────


def test_list_templates_pela_porta_mostra_as_vozes_do_runtime(scope_vazio):
    """Um scope sem docs NÃO é um catálogo vazio. Sem esta linha o default é
    alcançável só por quem já sabe o nome — capacidade sem porta."""

    async def cenario():
        server = M.build_server(base_dir=str(scope_vazio))
        async with Client(server) as client:
            return await client.call_tool("list_templates", {"scope": "kit"})

    dados = _payload(asyncio.run(cenario()))
    por_nome = {t["name"]: t for t in dados["templates"]}
    assert {
        "memory-recall-briefing",
        "memory-extraction",
        "memory-reconciliation",
        "memory-arbitration",
    } <= set(por_nome)
    briefing = por_nome["memory-recall-briefing"]
    assert briefing["origin"] == "runtime-default"
    assert briefing["variables_count"] == 1
    assert briefing["description"]  # a tela precisa de uma frase, não só do nome


def test_o_doc_autorado_VENCE_o_default_e_a_origem_muda(scope_vazio):
    """A direção que o i-102 avisa que não pode inverter: doc vence default.

    E a origem tem de acompanhar — servir o texto certo com a origem errada
    seria trocar um defeito silencioso por outro."""
    sentinela = "VOZ DA ACME\n{memories}\nfim"

    async def cenario():
        live = await M.boot_live(base_dir=str(scope_vazio))
        await live.kernel.with_tenant("acme").write_instance(
            "kit", "PromptTemplate", "memory-recall-briefing",
            {
                "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
                "kind": "PromptTemplate",
                "metadata": {"name": "memory-recall-briefing"},
                "spec": {"body": sentinela, "variables": ["memories"]},
            },
        )
        server = M.build_server(base_dir=str(scope_vazio))
        async with Client(server) as client:
            do_tenant = await client.call_tool(
                "get_template",
                {"name": "memory-recall-briefing", "scope": "kit", "tenant": "acme"},
            )
            sem_tenant = await client.call_tool(
                "get_template", {"name": "memory-recall-briefing", "scope": "kit"}
            )
            listagem = await client.call_tool(
                "list_templates", {"scope": "kit", "tenant": "acme"}
            )
        return _payload(do_tenant), _payload(sem_tenant), _payload(listagem)

    do_tenant, sem_tenant, listagem = asyncio.run(cenario())
    assert do_tenant["body"] == sentinela
    assert do_tenant["origin"] == "instance"
    # quem não é o tenant continua com o default do runtime, e sabe disso
    assert sem_tenant["origin"] == "runtime-default"
    # e o nome NÃO aparece duas vezes na listagem do tenant
    nomes = [t["name"] for t in listagem["templates"]]
    assert nomes.count("memory-recall-briefing") == 1
    assert next(
        t for t in listagem["templates"] if t["name"] == "memory-recall-briefing"
    )["origin"] == "instance"


def test_o_corpo_servido_e_o_que_roda_de_verdade(scope_vazio):
    """⭐ O teste que mata a deriva — e o motivo de o registro guardar um
    CALLABLE em vez de uma cópia do texto.

    O defeito do i-102 no portal é uma CÓPIA do default do SDK que precisa ser
    atualizada à mão. Se o catálogo servisse outra cópia, o SDK teria adquirido
    o mesmo defeito. Aqui a asserção é de IDENTIDADE com o que o runtime
    produz: qualquer edição no default do código muda as duas pontas no mesmo
    commit, ou este teste cai."""
    from dna.memory.ingestion import extraction_prompt

    async def cenario():
        server = M.build_server(base_dir=str(scope_vazio))
        async with Client(server) as client:
            return await client.call_tool(
                "get_template", {"name": "memory-extraction", "scope": "kit"}
            )

    dados = _payload(asyncio.run(cenario()))
    assert dados["body"] == extraction_prompt("{transcript}")
    assert "{transcript}" in dados["body"]


# ── os IRMÃOS ──────────────────────────────────────────────────────────────


def test_get_skill_o_irmao_segue_o_mesmo_contrato(scope_vazio):
    """O irmão `get_skill` passou pelo mesmo caminho. Hoje o SDK não registra
    nenhuma Skill built-in, então a resposta para um nome desconhecido continua
    sendo erro — mas pela MESMA porta e com a MESMA mensagem, e um registro
    futuro é servido sem tocar nesta função. ("Capacidade existe, porta não" é
    o defeito que a casa já pagou por consertar um irmão só.)"""

    async def cenario():
        server = M.build_server(base_dir=str(scope_vazio))
        async with Client(server) as client:
            erro = await client.call_tool(
                "get_skill", {"name": "voz-que-nao-existe", "scope": "kit"},
                raise_on_error=False,
            )
            listagem = await client.call_tool("list_skills", {"scope": "kit"})
        return erro, _payload(listagem)

    erro, listagem = asyncio.run(cenario())
    assert erro.is_error
    assert "not a known runtime default" in _texto(erro)
    assert listagem["skills"] == []


def test_get_skill_serve_um_default_registrado(scope_vazio, monkeypatch):
    """O terceiro degrau do irmão está LIGADO, e não só escrito: uma Skill
    built-in registrada é servida com origem, sem tocar em `get_skill_impl`."""
    import dna.prompt_defaults as PD

    monkeypatch.setitem(
        PD._REGISTRY,
        ("Skill", "voz-de-teste"),
        PD.PromptDefault(
            name="voz-de-teste",
            description="uma skill built-in de teste",
            module="testes",
            kind="Skill",
            _body="faça assim",
        ),
    )

    async def cenario():
        server = M.build_server(base_dir=str(scope_vazio))
        async with Client(server) as client:
            um = await client.call_tool(
                "get_skill", {"name": "voz-de-teste", "scope": "kit"}
            )
            listagem = await client.call_tool("list_skills", {"scope": "kit"})
        return _payload(um), _payload(listagem)

    um, listagem = asyncio.run(cenario())
    assert um["origin"] == "runtime-default"
    # a Skill mantém o nome de campo do PRÓPRIO Kind — o chamador não aprende
    # uma segunda forma só porque a origem mudou
    assert um["instruction"] == "faça assim"
    assert "body" not in um
    assert [s["name"] for s in listagem["skills"]] == ["voz-de-teste"]


def test_get_tool_NAO_tem_o_mesmo_defeito(scope_vazio):
    """O terceiro irmão, verificado e deliberadamente NÃO alterado.

    `get_tool` lê superfícies do Kind `Tool`: não existe "Tool default do
    runtime" que um doc sobrescreva, então ausência ali é ausência de verdade —
    e a mensagem já enumerava as disponíveis. Consertar-o "por simetria" seria
    inventar um degrau que não existe. Registrado como teste para que a próxima
    leitura não confunda os dois casos."""

    async def cenario():
        server = M.build_server(base_dir=str(scope_vazio))
        async with Client(server) as client:
            return await client.call_tool(
                "get_tool", {"name": "nao-existe", "scope": "kit"},
                raise_on_error=False,
            )

    resultado = asyncio.run(cenario())
    assert resultado.is_error
    assert "available:" in _texto(resultado)
