"""O agente lembra sem decidir lembrar — e não paga por isso em todo turno."""
from __future__ import annotations

import asyncio

from dna.runtime.middleware.recall import (
    MAX_CHARS,
    MAX_MEMORIES,
    DnaRecallMiddleware,
    briefing,
    worth_recalling,
)


class _Msg:
    def __init__(self, texto, tipo="human"):
        self.content = texto
        self.type = tipo


class _Req:
    def __init__(self, msgs, sistema=""):
        self.messages = msgs
        self.system_message = sistema
        self.alterado = {}

    def override(self, **kw):
        self.alterado = kw
        return self


def _rodar(msgs, recall=None, sistema="INSTRUCAO BASE"):
    req = _Req(msgs, sistema)
    visto = {}

    async def _handler(r):
        visto["prompt"] = getattr(r, "alterado", {}).get("system_prompt")
        return "ok"

    asyncio.run(DnaRecallMiddleware(recall).awrap_model_call(req, _handler))
    return visto.get("prompt")


def _memorias(*textos):
    async def _r(consulta, limite):
        return [{"summary": t} for t in textos]
    return _r


# ── o defeito que o módulo fecha ────────────────────────────────────────────


def test_a_memoria_entra_SEM_o_modelo_precisar_pedir():
    """⚠️ O defeito: `recall` é uma tool, e o modelo esquece de chamá-la.

    Não há erro quando isso acontece — a conversa segue, a resposta sai
    plausível, e a memória que estava no banco não participou. Nada denuncia.
    """
    prompt = _rodar(
        [_Msg("quando vence o contrato da ACME?")],
        _memorias("O contrato da ACME vence em março de 2027."),
    )
    assert "março de 2027" in prompt
    assert "INSTRUCAO BASE" in prompt, "apagou a instrução do agente"


def test_a_memoria_vai_para_o_SISTEMA_e_nao_para_a_conversa():
    """Uma parte `text` numa mensagem CHEGA À TELA — foi assim que a instrução
    da planilha apareceu na bolha do usuário como se ele a tivesse escrito."""
    req = _Req([_Msg("quando vence o contrato da ACME?")], "BASE")

    async def _handler(r):
        return "ok"

    asyncio.run(
        DnaRecallMiddleware(_memorias("vence em março")).awrap_model_call(req, _handler)
    )
    assert set(req.alterado) == {"system_prompt"}, "mexeu nas mensagens"


# ── e não paga em todo turno ────────────────────────────────────────────────


def test_um_turno_TRIVIAL_nao_gasta_busca():
    """⚠️ A maioria dos turnos de uma conversa real é `ok` / `obrigado`.

    Buscar para eles gasta tokens em toda conversa sem chance de acertar — e o
    custo é assimétrico: não buscar num turno trivial não perde nada, porque a
    tool `recall` continua montada.
    """
    async def _nunca(consulta, limite):
        raise AssertionError("buscou memória num turno trivial")

    for trivial in ("ok", "obrigado!", "pode seguir", "sim", "   "):
        assert _rodar([_Msg(trivial)], _nunca) is None


def test_uma_mensagem_LONGA_mas_vazia_tambem_nao_busca():
    """Passar do tamanho mínimo não basta: `"ok, obrigado, perfeito"` é longo e
    não discrimina nada."""
    async def _nunca(consulta, limite):
        raise AssertionError("buscou memória sem sinal")

    assert _rodar([_Msg("ok, obrigado, perfeito, valeu")], _nunca) is None


def test_sem_recall_injetado_e_um_NO_OP():
    """Um deployment sem memória continua servindo."""
    assert _rodar([_Msg("quando vence o contrato da ACME?")], None) is None


def test_recall_que_FALHA_nao_derruba_o_turno():
    """Memória indisponível é problema de operação — não motivo para o agente
    parar de responder."""
    async def _explode(consulta, limite):
        raise RuntimeError("MCP fora")

    assert _rodar([_Msg("quando vence o contrato da ACME?")], _explode) is None


def test_nenhuma_memoria_encontrada_nao_injeta_bloco_vazio():
    """Um cabeçalho "Memórias:" sem memória nenhuma diria ao modelo que ele
    procurou e não achou — quando ele nem procurou direito."""
    async def _vazio(consulta, limite):
        return []

    assert _rodar([_Msg("quando vence o contrato da ACME?")], _vazio) is None


# ── os tetos ────────────────────────────────────────────────────────────────


def test_o_teto_de_QUANTIDADE_e_duro():
    texto = briefing([{"summary": f"memoria {i}"} for i in range(20)])
    assert len([l for l in texto.splitlines() if l.startswith("- ")]) == MAX_MEMORIES


def test_o_teto_de_TAMANHO_corta_antes_de_estourar():
    """Um Engram longo sozinho não pode comer a janela."""
    texto = briefing([{"summary": "x" * 5000}, {"summary": "cabe"}])
    assert len(texto) < MAX_CHARS + 500


def test_o_bloco_diz_que_e_RESUMO_e_aponta_a_tool():
    """Este middleware é o PISO, não o teto — uma pergunta explícita sobre
    memória deve poder buscar mais fundo."""
    texto = briefing([{"summary": "algo"}])
    assert "recall" in texto
    assert "resumo" in texto


def test_a_origem_e_declarada_ao_modelo():
    """Sem isso o agente "sabe" coisas e o usuário não tem como perguntar de
    onde veio."""
    assert "memória" in briefing([{"summary": "algo"}]).lower()


# ── tolerância de formato ───────────────────────────────────────────────────


def test_memoria_em_QUALQUER_forma_razoavel_e_lida():
    """A forma vem do host (MCP, banco, dublê). Uma diferença de formato não
    pode custar o turno — no pior caso não injeta nada."""
    assert "direto" in briefing(["direto"])
    assert "no spec" in briefing([{"spec": {"summary": "no spec"}}])
    assert briefing([{"sem": "texto"}]) == ""
    assert briefing([None, 42]) == ""


def test_o_cue_e_uma_JANELA_e_nao_so_a_ultima_fala():
    """⚠️ Reescrito: antes este teste afirmava "só a última mensagem", e a
    afirmação é que estava errada.

    Numa conversa real a última fala é curta e dependente — `"e o prazo?"` —, e
    o que lhe dá sentido está duas mensagens atrás. Buscar memória com `"e o
    prazo?"` não recupera nada.

    Vem do desenho do JARVIS (`aap-sdk-v3`): cues são o transcript recente, não
    o último turno.
    """
    vistas = []

    async def _r(consulta, limite):
        vistas.append(consulta)
        return [{"summary": "achou"}]

    _rodar(
        [_Msg("preciso revisar o contrato da ACME"), _Msg("qual deles?", "ai"),
         _Msg("e o prazo de renovacao?")],
        _r,
    )
    assert "ACME" in vistas[0], "perdeu o assunto que dá sentido à pergunta"
    # A mais RECENTE vem primeiro: se o corte por tamanho acontecer, ele tira o
    # contexto antigo, nunca a pergunta.
    assert vistas[0].startswith("e o prazo de renovacao?")


def test_a_janela_NAO_arrasta_a_conversa_inteira():
    """Uma consulta gigante não discrimina melhor — só custa mais."""
    from dna.runtime.middleware.recall import CUE_WINDOW, cues

    msgs = [_Msg(f"assunto numero {i}") for i in range(20)]
    texto = cues(msgs)
    assert texto.count("assunto numero") == CUE_WINDOW


def test_worth_recalling_e_publico_e_testavel_sozinho():
    assert worth_recalling("quando vence o contrato?") is True
    assert worth_recalling("ok") is False
    assert worth_recalling(None) is False


# ── a taxonomia é DADO, não constante de código ─────────────────────────────


def test_um_tipo_DESCONHECIDO_aparece_com_o_proprio_nome():
    """⚠️ A objeção do fundador: "os memory_type tão FIXOS, não gosto".

    Ela tem alvo real. Uma tabela fechada num middleware transforma vocabulário
    do DOMÍNIO em constante de CÓDIGO — e o sintoma é um tipo novo sumir do
    prompt sem erro nenhum, que é o pior modo de falha deste produto.

    O nome é a informação: `[preferencia]` diz mais ao modelo do que `[fato]`, e
    muito mais do que não aparecer.
    """
    from dna.runtime.middleware.recall import type_label

    assert type_label("preferencia") == "preferencia"
    assert type_label("restricao_do_cliente") == "restricao_do_cliente"
    assert "[preferencia] gosta de resumo curto" in briefing(
        [{"summary": "gosta de resumo curto", "memory_type": "preferencia"}]
    )


def test_uma_REGRA_e_o_unico_tipo_com_tratamento_IMPERATIVO():
    """E por um motivo: uma regra que o modelo leia como anedota é uma regra que
    ele ignora — e ignorar anedota é o comportamento razoável."""
    texto = briefing([
        {"summary": "sempre confirme o CNPJ", "memory_type": "procedural"},
        {"summary": "o contrato venceu em março", "memory_type": "episodic"},
    ])
    assert "[REGRA (siga)] sempre confirme o CNPJ" in texto
    assert "[fato ocorrido] o contrato venceu" in texto
    assert "DEVE seguir" in texto


def test_memoria_SEM_tipo_cai_no_mais_fraco():
    """Promover algo a REGRA sem alguém ter dito que é regra colocaria na boca do
    agente uma obrigação que ninguém escreveu."""
    assert "[fato]" in briefing([{"summary": "algo"}])
    assert "[fato]" in briefing([{"summary": "algo", "memory_type": "  "}])


def test_o_briefing_NAO_reordena_o_que_o_recall_ja_pontuou():
    """`dna.memory.verbs.recall` já aplica Ebbinghaus, validade bitemporal e
    peso de afeto (`dna.memory.decay`). Repontuar aqui seria uma segunda opinião
    sobre a mesma coisa, e a que perde é sempre a que tem menos informação."""
    texto = briefing([
        {"summary": "primeira"}, {"summary": "segunda"}, {"summary": "terceira"},
    ])
    linhas = [l for l in texto.splitlines() if l.startswith("- ")]
    assert [l.split("] ", 1)[1] for l in linhas] == ["primeira", "segunda", "terceira"]


def test_um_tipo_DECLARADO_pelo_workspace_vence_a_heuristica():
    """⚠️ O classificador comparava contra a tripla fechada.

    Um workspace que declarasse `preferencia` tinha o proprio valor
    SILENCIOSAMENTE substituido por `semantic` — o classificador reescrevia a
    decisao de quem sabia mais que ele, e nada avisava.

    A heuristica so opina quando NINGUEM opinou.
    """
    from dna.memory.memory_type import classify_memory_type

    assert classify_memory_type({"memory_type": "preferencia"}) == "preferencia"
    assert classify_memory_type({"memory_type": "  restricao  "}) == "restricao"
    # sem declaracao, a heuristica continua valendo
    assert classify_memory_type({"summary": "sempre confirme o CNPJ"}) == "procedural"
    assert classify_memory_type({"summary": "o cliente e a ACME"}) == "semantic"


# ── histerese: o prompt precisa ficar ESTÁVEL ───────────────────────────────


class _ReqThread(_Req):
    def __init__(self, msgs, thread="th-1"):
        super().__init__(msgs, "BASE")
        self.runtime = type("_R", (), {"config": {"configurable": {"thread_id": thread}}})()


def _injetar(mid, req):
    visto = {}

    async def _handler(r):
        visto["p"] = getattr(r, "alterado", {}).get("system_prompt")
        return "ok"

    asyncio.run(mid.awrap_model_call(req, _handler))
    return visto.get("p")


def test_um_conjunto_QUASE_igual_mantem_o_bloco_ANTERIOR():
    """⚠️ O ponto NÃO é economizar busca — é manter o prompt ESTÁVEL.

    Um bloco que muda a cada turno muda o prefixo do prompt a cada turno, e isso
    invalida o cache do provider: custo real, medível, e invisível até chegar na
    fatura.

    Vem do JARVIS (`aap-sdk-v3`): "re-injeta só quando o set muda + histerese".
    """
    chamadas = [
        [{"name": "m1", "summary": "alfa"}, {"name": "m2", "summary": "beta"}],
        # segunda busca: uma trocou, uma ficou → 50% de sobreposição
        [{"name": "m1", "summary": "alfa"}, {"name": "m9", "summary": "gama"}],
    ]

    async def _r(consulta, limite):
        return chamadas.pop(0)

    mid = DnaRecallMiddleware(_r)
    primeiro = _injetar(mid, _ReqThread([_Msg("fale do contrato da ACME")]))
    segundo = _injetar(mid, _ReqThread([_Msg("e sobre o prazo dele?")]))
    assert primeiro == segundo, "o prompt mudou por uma troca marginal"
    assert "gama" not in segundo


def test_um_conjunto_DIFERENTE_troca_o_bloco():
    """Histerese não é congelamento: quando o assunto muda de verdade, a memória
    tem de acompanhar — senão o middleware vira uma memória presa no passado."""
    chamadas = [
        [{"name": "m1", "summary": "alfa"}, {"name": "m2", "summary": "beta"}],
        [{"name": "m8", "summary": "delta"}, {"name": "m9", "summary": "gama"}],
    ]

    async def _r(consulta, limite):
        return chamadas.pop(0)

    mid = DnaRecallMiddleware(_r)
    _injetar(mid, _ReqThread([_Msg("fale do contrato da ACME")]))
    segundo = _injetar(mid, _ReqThread([_Msg("agora fale da folha de pagamento")]))
    assert "delta" in segundo and "alfa" not in segundo


def test_threads_DIFERENTES_nao_compartilham_histerese():
    """Duas conversas do mesmo processo são independentes. Sem isto, a memória
    de uma vazaria para o prompt da outra — e num servidor com concorrência isso
    é o caso NORMAL, não a exceção."""
    chamadas = [
        [{"name": "m1", "summary": "da conversa A"}],
        [{"name": "m2", "summary": "da conversa B"}],
    ]

    async def _r(consulta, limite):
        return chamadas.pop(0)

    mid = DnaRecallMiddleware(_r)
    a = _injetar(mid, _ReqThread([_Msg("fale do contrato da ACME")], "th-A"))
    b = _injetar(mid, _ReqThread([_Msg("fale da folha de pagamento")], "th-B"))
    assert "conversa A" in a and "conversa B" in b


def test_a_histerese_devolve_o_bloco_ANTIGO_e_nao_NADA():
    """Pular a injeção quando o set não muda tiraria a memória do prompt
    exatamente nos turnos em que ela CONTINUA valendo — o oposto do que a
    histerese quer."""
    async def _r(consulta, limite):
        return [{"name": "m1", "summary": "o contrato vence em marco"}]

    mid = DnaRecallMiddleware(_r)
    req = _ReqThread([_Msg("fale do contrato da ACME")])
    _injetar(mid, req)
    segundo = _injetar(mid, _ReqThread([_Msg("e o prazo de renovacao?")]))
    assert "o contrato vence em marco" in segundo
