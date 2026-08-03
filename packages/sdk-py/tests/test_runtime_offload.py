"""Saída grande de tool sai do contexto — e o corte é ANUNCIADO."""
from __future__ import annotations

import asyncio

# `sdk-py` roda o arquivo inteiro.
# subconjunto sem langchain; skipar la nao perde cobertura, porque o job
# middleware nao — e estes testes a exercitam. O job `postgres` do CI roda um
# O modulo e importavel sem langchain (a REGRA e pura), mas a CLASSE de

import pytest

pytest.importorskip("langchain")

from dna.runtime.middleware.offload import (
    HEAD_CHARS,
    TAIL_CHARS,
    THRESHOLD,
    DnaToolOffloadMiddleware,
    preview,
)

GRANDE = "INICIO " + ("x" * 20_000) + " TOTAL=12345"


class _Msg:
    def __init__(self, content):
        self.content = content

    def model_copy(self, update):
        return _Msg(update["content"])


class _Req:
    tool_call = {"name": "analyze_spreadsheet"}


def _rodar(saida, store=None):
    async def _handler(_req):
        return _Msg(saida)

    return asyncio.run(
        DnaToolOffloadMiddleware(store).awrap_tool_call(_Req(), _handler)
    ).content


# ── o defeito ───────────────────────────────────────────────────────────────


def test_saida_GRANDE_nao_fica_inteira_no_estado():
    """⚠️ O mesmo defeito do base64, fechado duas vezes neste produto, agora em
    JSON: o que a tool devolve fica no estado PARA SEMPRE, reenviado a cada
    turno seguinte. Não quebra nada — só encarece tudo, em silêncio."""
    saida = _rodar(GRANDE)
    assert len(saida) < len(GRANDE) / 5


def test_saida_PEQUENA_passa_intacta():
    """A maioria das tools devolve pouco. Mexer nelas seria custo sem ganho."""
    assert _rodar("12345 linhas") == "12345 linhas"


# ── a forma do corte ────────────────────────────────────────────────────────


def test_o_corte_guarda_a_CAUDA_e_nao_so_a_cabeca():
    """⚠️ Numa saída estruturada o FIM carrega o total, a conclusão ou o erro.
    Cortar só a cauda joga fora justamente o que responde a pergunta."""
    saida = _rodar(GRANDE)
    assert saida.startswith("INICIO")
    assert "TOTAL=12345" in saida


def test_o_corte_e_ANUNCIADO():
    """Um corte silencioso faria o modelo concluir a partir de um recorte
    acreditando ser o todo — o mesmo modo de falha da planilha truncada em 1.000
    linhas, que é o motivo de este produto ter começado a olhar para isto."""
    saida = _rodar(GRANDE)
    assert "omitidos" in saida
    assert "NÃO conclua a partir deste recorte" in saida


def test_o_endereco_do_conteudo_completo_aparece():
    async def _store(conteudo, nome):
        return "/api/artifacts/abc123"

    saida = _rodar(GRANDE, _store)
    assert "/api/artifacts/abc123" in saida


def test_o_que_foi_guardado_e_o_ORIGINAL_e_nao_a_janela():
    """Guardar o recorte tornaria o endereço inútil: quem clicasse encontraria
    exatamente o que já estava na tela."""
    visto = {}

    async def _store(conteudo, nome):
        visto["conteudo"] = conteudo
        visto["tool"] = nome
        return "/x"

    _rodar(GRANDE, _store)
    assert visto["conteudo"] == GRANDE
    assert visto["tool"] == "analyze_spreadsheet"


# ── quando não há onde guardar ──────────────────────────────────────────────


def test_SEM_storage_corta_mesmo_assim_e_diz_que_nao_guardou():
    """Um deployment sem storage prefere uma janela honesta a um contexto que
    cresce sem fim. Mas não pode fingir que há onde ler o resto."""
    saida = _rodar(GRANDE)
    assert "NÃO foi guardado" in saida
    assert "/api/artifacts" not in saida


def test_um_store_que_ESTOURA_nao_derruba_a_tool():
    """A tool já rodou e já respondeu. Falhar em ARQUIVAR a resposta não pode
    apagar o trabalho que ela deu."""
    async def _explode(conteudo, nome):
        raise RuntimeError("blob fora")

    saida = _rodar(GRANDE, _explode)
    assert "TOTAL=12345" in saida
    assert "NÃO foi guardado" in saida


def test_o_preview_e_publico_e_testavel_sozinho():
    assert preview("curto") == "curto"
    grande = preview("A" * (THRESHOLD * 3))
    assert len(grande) < THRESHOLD * 3
    assert grande.startswith("A" * HEAD_CHARS)
    assert grande.endswith("A" * TAIL_CHARS)
