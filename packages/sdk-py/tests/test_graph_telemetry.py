"""A instrumentação da travessia — a fatia 0 de ``spec-topologia-do-grafo``.

A spec recomendou **ficar no Postgres** e nomeou dois gatilhos MEDIDOS que
invertem a recomendação. O de escala não era mensurável — "contagem hoje: não
instrumentado" — e uma recomendação cujo gatilho ninguém consegue ler é uma
opinião com data de validade indefinida. Estes testes existem para que a
instrumentação não possa ser removida, afrouxada ou vazar, em silêncio:

* **a porta emite** — uma travessia pela mesma função de caso de uso que a rota
  REST e a face MCP chamam produz UMA linha, parseável;
* **desligada não custa** — provado pelo NEGATIVO: o relógio é trocado por algo
  que levanta, e a travessia desligada segue verde. Apagar o ``if observing``
  torna este teste vermelho;
* **o rótulo não identifica ninguém** — o nome da instância e o tenant cru são
  procurados na linha e não podem estar lá;
* **os limiares são estritos** — 500,0 ms não dispara, 500,1 dispara; 1,00% não
  dispara, 1,01% dispara. Trocar ``>`` por ``>=`` fica vermelho;
* **o gatilho 1 é uma guarda de FORMA** — ele conta rotas de travessia e
  parâmetros que compõem, coisas que não aparecem em tráfego nenhum.
"""
from __future__ import annotations

import inspect
import json
import logging
import sys
from typing import Any

import pytest
import pytest_asyncio

from dna.application.instances import graph_refs_impl
from dna.application.live import LiveDna
from dna.kernel import Kernel
from dna.kernel.query import graph as g
from tests import _graph_store

_SDLC_API = "github.com/ruinosus/dna/sdlc/v1"
SCOPE = "graph-telemetry"


def _doc(kind: str, name: str, **spec: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"description": "d", "status": "todo"}
    base.update(spec)
    return {
        "apiVersion": _SDLC_API, "kind": kind,
        "metadata": {"name": name}, "spec": base,
    }


@pytest.fixture(autouse=True)
def _modes(monkeypatch):
    monkeypatch.delenv("DNA_REF_VALIDATION", raising=False)
    monkeypatch.delenv("DNA_GRAPH_MAX_DEPTH", raising=False)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")


@pytest.fixture(autouse=True)
def _isolated_funnel():
    """O logger é estado de PROCESSO, e a suíte roda em paralelo (xdist).

    Nível, handlers e ``propagate`` são restaurados ao sair para que um teste
    que liga o funil não deixe os vizinhos do mesmo worker medindo.
    """
    log = logging.getLogger(g.TRAVERSAL_LOGGER)
    before = (log.level, list(log.handlers), log.propagate)
    log.setLevel(logging.WARNING)  # DESLIGADO por default, e explicitamente
    log.propagate = True
    try:
        yield log
    finally:
        log.setLevel(before[0])
        log.handlers[:] = before[1]
        log.propagate = before[2]


@pytest_asyncio.fixture(params=_graph_store.DIALECTS)
async def live(request):
    """Um ``LiveDna`` sobre um store real, nos DOIS dialetos.

    ``LiveDna`` e não só o kernel porque é ele que a rota REST e a face MCP
    seguram: ``graph_refs_impl`` é a porta compartilhada, e é atravessando ela
    que a instrumentação precisa valer.
    """
    src, cleanup = await _graph_store.build_store(request.param, "telem")
    kernel = Kernel.auto()
    kernel.source(src)
    handle = LiveDna(base_scope=SCOPE, kernel=kernel, provider=None)
    try:
        yield handle
    finally:
        await cleanup()


async def _chain(kernel) -> None:
    """``Task/t-1 → Story/s-x → Feature/f-y → Epic/e-1`` — três saltos."""
    await kernel.write_instance(SCOPE, "Epic", "e-1", _doc("Epic", "e-1"))
    await kernel.write_instance(
        SCOPE, "Feature", "f-y", _doc("Feature", "f-y", epic="e-1"),
    )
    await kernel.write_instance(
        SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"),
    )
    await kernel.write_instance(
        SCOPE, "Task", "t-1", _doc("Task", "t-1", story_ref="s-x"),
    )


def _lines(caplog) -> list[dict[str, Any]]:
    """Os registros de travessia que saíram, já parseados pelo LEITOR real."""
    out = []
    for rec in caplog.records:
        parsed = g.parse_traversal_line(rec.getMessage())
        if parsed is not None:
            out.append(parsed)
    return out


# ───────────────────────────────────────────────────────────────────────────
# A porta emite
# ───────────────────────────────────────────────────────────────────────────


class TestAPortaEmite:
    @pytest.mark.anyio
    async def test_uma_travessia_pela_porta_emite_uma_linha(self, live, caplog):
        """A chamada REAL — ``graph_refs_impl``, a mesma que a rota REST e a
        face MCP fazem — e não a função de policy isolada."""
        await _chain(live.kernel)
        caplog.set_level(logging.INFO, logger=g.TRAVERSAL_LOGGER)

        answer = await graph_refs_impl(
            live, kind="Feature", name="f-y", scope=SCOPE,
            direction="in", depth=3,
        )

        records = _lines(caplog)
        assert len(records) == 1, "uma travessia, uma linha"
        line = records[0]
        assert line["kind"] == "Feature"
        assert line["dir"] == "in"
        assert line["depth"] == 3
        # O `stop` da linha é o MESMO que a resposta carrega — duas contas do
        # mesmo fato divergiriam, e a taxa de truncamento do relatório tem de
        # ser a do que o cliente recebeu.
        assert line["stop"] == answer["stop"]
        assert line["edges"] == len(answer["edges"])
        assert line["producer"] == answer["graph_producer"]
        assert isinstance(line["ms"], (int, float)) and line["ms"] >= 0.0

    @pytest.mark.anyio
    async def test_a_marca_sobrevive_ao_prefixo_do_coletor(self, live, caplog):
        """A linha real chega com carimbo, container e nível na frente (é o que
        ``az containerapp logs show`` cospe). O leitor tem de achá-la assim."""
        await _chain(live.kernel)
        caplog.set_level(logging.INFO, logger=g.TRAVERSAL_LOGGER)
        await graph_refs_impl(live, kind="Feature", name="f-y", scope=SCOPE)

        raw = caplog.records[-1].getMessage()
        dressed = f"2026-08-06T20:11:02.51Z ca-dna-api-4j2 stdout F INFO {raw}"
        assert g.parse_traversal_line(dressed) == g.parse_traversal_line(raw)

    @pytest.mark.anyio
    async def test_a_travessia_recusada_nao_conta_como_chamada(self, caplog):
        """``GraphUnsupported`` sai antes do relógio: um store sem arestas não
        pode inflar o denominador da taxa de truncamento com chamadas que nunca
        andaram."""
        caplog.set_level(logging.INFO, logger=g.TRAVERSAL_LOGGER)

        class _NoEdges:
            pass

        with pytest.raises(g.GraphUnsupported):
            await g.traverse(_NoEdges(), SCOPE, "Feature", "f-y")
        assert _lines(caplog) == []


# ───────────────────────────────────────────────────────────────────────────
# ⭐ Custo zero desligada — provado pelo negativo
# ───────────────────────────────────────────────────────────────────────────


class TestCustoZeroDesligada:
    """A restrição que vale mais que a métrica: uma travessia não pode ficar
    mais lenta porque alguém pode querer medir depois."""

    @pytest.mark.anyio
    async def test_desligada_o_relogio_nem_e_lido(self, live, monkeypatch):
        """⚠️ O mutante: apague o ``if observing`` (ou meça sempre) e este
        teste fica vermelho, porque o relógio LEVANTA.

        Medir a ausência de custo por cronômetro seria um teste instável; medir
        pelo lado do efeito — nenhuma chamada ao relógio, nenhum dicionário,
        nenhuma formatação — é determinístico.
        """
        await _chain(live.kernel)

        def _explode() -> float:
            raise AssertionError(
                "o caminho DESLIGADO leu o relógio — a instrumentação deixou "
                "de ser gratuita para quem não a ligou"
            )

        monkeypatch.setattr(g, "_clock", _explode)
        assert not g.traversal_logging_enabled()

        answer = await graph_refs_impl(
            live, kind="Feature", name="f-y", scope=SCOPE, depth=3,
        )
        assert answer["edges"], "a travessia continua respondendo o mesmo"

    @pytest.mark.anyio
    async def test_ligada_o_relogio_E_lido(self, live, monkeypatch, caplog):
        """A outra metade do mutante: se o teste acima passasse porque o
        relógio nunca é lido em lugar nenhum, ele não estaria provando nada."""
        await _chain(live.kernel)
        caplog.set_level(logging.INFO, logger=g.TRAVERSAL_LOGGER)
        seen: list[int] = []

        def _ticking() -> float:
            seen.append(1)
            return float(len(seen))

        monkeypatch.setattr(g, "_clock", _ticking)
        await graph_refs_impl(live, kind="Feature", name="f-y", scope=SCOPE)
        assert len(seen) == 2, "início e fim, uma vez cada"
        assert _lines(caplog)[0]["ms"] == pytest.approx(1000.0)

    def test_a_chave_liga_o_nivel_E_garante_que_a_linha_SAIA(self, monkeypatch):
        """⚠️ Ligar o nível não basta, e a diferença é a porta.

        Sob ``uvicorn`` o logger raiz não tem handler, e um record INFO sem
        handler é descartado em silêncio (``lastResort`` só atende WARNING+).
        Uma instrumentação "ligada" que não emite nada é exatamente
        "capacidade existe, porta não" — então a chave também garante o
        destino, e só quando ninguém mais está ouvindo.
        """
        log = logging.getLogger(g.TRAVERSAL_LOGGER)
        log.handlers[:] = []
        log.propagate = False  # ninguém ouvindo, como sob uvicorn
        monkeypatch.setenv("DNA_GRAPH_TELEMETRY", "on")

        g._configure_from_env()

        assert log.isEnabledFor(logging.INFO)
        assert log.hasHandlers(), "ligado e sem destino é o mesmo que desligado"
        # ⚠️ stderr, nunca stdout: `dna graph refs --json` escreve o RESULTADO
        # em stdout, e uma linha de telemetria no meio dele quebra o `| jq` de
        # quem consome. Observar não pode estragar o observado.
        assert log.handlers[0].stream is sys.stderr

    def test_sem_a_chave_nada_e_tocado(self, monkeypatch):
        """Uma biblioteca que mexe no logging de quem a importa é uma
        biblioteca mal-educada. Sem a chave, nem o nível nem os handlers."""
        log = logging.getLogger(g.TRAVERSAL_LOGGER)
        log.handlers[:] = []
        log.setLevel(logging.WARNING)
        monkeypatch.delenv("DNA_GRAPH_TELEMETRY", raising=False)

        g._configure_from_env()

        assert log.level == logging.WARNING and log.handlers == []

    def test_a_chave_nao_rouba_o_handler_de_quem_ja_escuta(self, monkeypatch):
        """Quem já configurou logging fica com o handler dele — duas emissões
        da mesma travessia contariam a mesma chamada duas vezes."""
        log = logging.getLogger(g.TRAVERSAL_LOGGER)
        log.handlers[:] = []
        log.propagate = True  # a raiz do host escuta
        logging.getLogger().addHandler(logging.NullHandler())
        monkeypatch.setenv("DNA_GRAPH_TELEMETRY", "1")
        try:
            g._configure_from_env()
            assert log.handlers == [] and log.propagate is True
        finally:
            root = logging.getLogger()
            root.handlers[:] = [
                h for h in root.handlers if not isinstance(h, logging.NullHandler)
            ]

    @pytest.mark.anyio
    async def test_desligada_nao_sai_linha_nenhuma(self, live, caplog):
        await _chain(live.kernel)
        caplog.set_level(logging.INFO)  # a raiz inteira em INFO…
        logging.getLogger(g.TRAVERSAL_LOGGER).setLevel(logging.WARNING)  # …menos nós
        await graph_refs_impl(live, kind="Feature", name="f-y", scope=SCOPE)
        assert _lines(caplog) == []


# ───────────────────────────────────────────────────────────────────────────
# O rótulo não identifica ninguém
# ───────────────────────────────────────────────────────────────────────────


class TestORotuloNaoIdentificaNinguem:
    """Isto é multi-tenant, e a linha é um artefato de OPERADOR: nome de
    instância é conteúdo do cliente e cardinalidade infinita."""

    @pytest.mark.anyio
    async def test_nem_o_nome_nem_o_tenant_cru_aparecem(self, live, caplog):
        await live.kernel.write_instance(
            SCOPE, "Epic", "e-1", _doc("Epic", "e-1"),
        )
        await live.kernel.write_instance(
            SCOPE, "Feature", "segredo-do-cliente-xyz",
            _doc("Feature", "segredo-do-cliente-xyz", epic="e-1"),
        )
        caplog.set_level(logging.INFO, logger=g.TRAVERSAL_LOGGER)

        await graph_refs_impl(
            live, kind="Feature", name="segredo-do-cliente-xyz", scope=SCOPE,
            tenant="acme-corp-9", direction="out",
        )

        raw = caplog.records[-1].getMessage()
        assert "segredo-do-cliente-xyz" not in raw
        assert "acme-corp-9" not in raw
        assert SCOPE not in raw
        line = g.parse_traversal_line(raw)
        # ``axis`` entrou na fatia 4 (``live`` / ``as_of``) e é vocabulário
        # FECHADO, como todos os outros rótulos aqui — ele diz QUAL travessia
        # rodou, nunca sobre o quê. O ``==`` continua deliberado: um campo novo
        # tem de passar por esta linha, porque é aqui que alguém percebe que
        # acabou de pôr conteúdo de cliente num log de operador.
        assert set(line) == {
            "kind", "dir", "depth", "stop", "edges", "ms", "producer", "tenant",
            "axis",
        }
        assert line["tenant"] == g.tenant_bucket("acme-corp-9")
        assert line["axis"] == "live"

    def test_o_balde_agrupa_sem_nomear(self):
        """Sem balde nenhum o gatilho "no maior tenant real" não fecha; com o
        tenant cru, o log de operador carrega o cliente. O balde faz as duas."""
        a1 = g.tenant_bucket("acme-corp-9")
        a2 = g.tenant_bucket("acme-corp-9")
        b = g.tenant_bucket("beta-ltda")
        assert a1 == a2, "estável entre chamadas, processos e réplicas"
        assert a1 != b, "tenants diferentes, baldes diferentes"
        assert "acme" not in a1 and len(a1) == 8
        assert g.tenant_bucket(None) == "-" and g.tenant_bucket("") == "-"


# ───────────────────────────────────────────────────────────────────────────
# Os dois números do GATILHO 2
# ───────────────────────────────────────────────────────────────────────────


def _line(*, ms: float, depth: int = 3, stop: str = "complete",
          tenant: str = "-", kind: str = "Feature") -> str:
    body = json.dumps({
        "kind": kind, "dir": "in", "depth": depth, "stop": stop,
        "edges": 1, "ms": ms, "producer": "warn", "tenant": tenant,
    })
    return f"2026-08-06T00:00:00Z ca-dna-api INFO {g.TRAVERSAL_MARK}{body}"


class TestOGatilho2:
    def test_o_limiar_de_p95_e_ESTRITO(self):
        """⚠️ O mutante do ``>``: 100 chamadas exatamente no limiar NÃO podem
        disparar uma migração de topologia; 0,1 ms acima, sim."""
        no = g.traversal_stats([_line(ms=500.0) for _ in range(100)])
        assert no["triggers"]["scale_p95"]["fired"] is False
        assert no["triggers"]["scale_p95"]["value_ms"] == 500.0

        yes = g.traversal_stats([_line(ms=500.1) for _ in range(100)])
        assert yes["triggers"]["scale_p95"]["fired"] is True
        assert yes["fired"] is True

    def test_o_p95_e_o_percentil_e_nao_a_media(self):
        """90 chamadas de 10 ms e 10 de 900 ms: a MÉDIA (99 ms) passaria longe
        do limiar, o p95 não. É por isso que o gatilho é p95."""
        lines = [_line(ms=10.0) for _ in range(90)]
        lines += [_line(ms=900.0) for _ in range(10)]
        report = g.traversal_stats(lines)
        assert sum(900.0 if i >= 90 else 10.0 for i in range(100)) / 100 == 99.0
        assert report["deep"]["p95_ms"] == 900.0
        assert report["triggers"]["scale_p95"]["fired"] is True

    def test_so_a_travessia_PROFUNDA_conta_para_o_p95(self):
        """O gatilho fala de ``depth=3``. Uma pilha de ``depth=1`` lentas é um
        problema, mas não É este gatilho — e contá-la aqui faria a spec ser
        invertida pelo número errado."""
        report = g.traversal_stats([_line(ms=5000.0, depth=1)] * 50)
        assert report["deep"]["calls"] == 0
        assert report["triggers"]["scale_p95"]["fired"] is False
        assert report["p95_ms"] == 5000.0, "o p95 geral ainda é reportado"

    def test_depth_acima_de_3_tambem_conta(self):
        """``depth>=3``: excluir 4 e 5 esconderia o pior caso justamente onde
        ele mora."""
        report = g.traversal_stats([_line(ms=900.0, depth=5)] * 20)
        assert report["deep"]["calls"] == 20
        assert report["triggers"]["scale_p95"]["fired"] is True

    def test_um_tenant_lento_e_pequeno_nao_some_na_media_de_todos(self):
        """"no maior tenant real" — sem agrupar por balde, 5 chamadas lentas de
        um tenant desaparecem entre 500 rápidas de outro, e o gatilho fica
        cego."""
        lines = [_line(ms=10.0, tenant="aaaaaaaa") for _ in range(500)]
        lines += [_line(ms=900.0, tenant="bbbbbbbb") for _ in range(5)]
        report = g.traversal_stats(lines)
        assert report["deep"]["p95_ms"] < g.TRIGGER_P95_MS, "o global é rápido"
        assert report["worst_tenant"]["tenant"] == "bbbbbbbb"
        assert report["triggers"]["scale_p95"]["fired"] is True

    def test_a_taxa_de_truncamento_e_ESTRITAMENTE_acima_de_1_por_cento(self):
        """⚠️ O outro mutante do ``>``: exatamente 1% não dispara."""
        one = [_line(ms=1.0, stop="truncated")] + [_line(ms=1.0)] * 99
        assert g.traversal_stats(one)["truncated_ratio"] == pytest.approx(0.01)
        assert g.traversal_stats(one)["triggers"]["scale_truncated"]["fired"] is False

        two = [_line(ms=1.0, stop="truncated")] * 2 + [_line(ms=1.0)] * 98
        assert g.traversal_stats(two)["triggers"]["scale_truncated"]["fired"] is True

    def test_truncado_e_so_somar_o_que_a_resposta_ja_devolvia(self):
        """O ``stop`` já existia na resposta; o relatório não o recalcula."""
        report = g.traversal_stats(
            [_line(ms=1.0, stop="truncated"), _line(ms=1.0, stop="depth_reached")]
        )
        assert report["truncated"] == 1 and report["calls"] == 2

    def test_zero_linha_NAO_se_lê_como_nao_disparou(self):
        """Um relatório de zeros sobre o arquivo errado é a mentira mais fácil
        aqui: ``calls`` e ``ignored`` existem para que ela seja visível."""
        report = g.traversal_stats(["log de outra coisa", "e outra"])
        assert report["calls"] == 0 and report["ignored"] == 2
        assert report["fired"] is False

    def test_o_percentil_devolve_um_valor_OBSERVADO(self):
        """Rank mais próximo, não interpolação: um p95 que nenhuma chamada
        levou é um número que ninguém consegue ir procurar no log."""
        assert g.percentile([1.0, 2.0, 3.0, 4.0], 0.95) == 4.0
        assert g.percentile([], 0.95) == 0.0
        assert g.percentile([7.0], 0.95) == 7.0

    def test_o_limiar_vem_da_spec_e_mora_num_lugar_so(self):
        assert (g.TRIGGER_DEPTH, g.TRIGGER_P95_MS, g.TRIGGER_TRUNCATED_RATIO) \
            == (3, 500.0, 0.01)


# ───────────────────────────────────────────────────────────────────────────
# ⭐ GATILHO 1 — expressividade. Uma guarda de FORMA, não de tráfego.
# ───────────────────────────────────────────────────────────────────────────


#: A contagem que a spec registrou: **uma rota, zero parâmetros que compõem.**
#: Parâmetros de COORDENADA (de onde, para que lado, até onde, **quando**) —
#: nenhum deles compõe com outro para formar uma pergunta nova. Um que filtre
#: por Kind no caminho, aplique predicado sobre a aresta ou deixe o cliente
#: escolher a projeção JÁ é uma linguagem de consulta em formação.
#:
#: ⭐ **``as_of`` entrou em 07/08/2026 (fatia 4) e o gatilho 1 foi CONTADO, não
#: contornado.** O argumento fica escrito para o próximo leitor JULGAR em vez de
#: herdar: ``as_of`` é a quarta COORDENADA da mesma pergunta, não um filtro
#: sobre a resposta. A rota continua UMA, a forma continua fixa, e o que muda é
#: o INSTANTE — as mesmas chaves, o mesmo ``stop``, o mesmo teto, o mesmo
#: anti-ciclo. Nada nele compõe com ``direction`` ou ``depth`` para formar uma
#: pergunta que a rota não fazia; ele diz QUANDO a rota está sendo feita. O
#: sinal do gatilho segue o mesmo e segue sem disparar: o primeiro parâmetro que
#: COMPÕE, ou uma segunda rota de travessia de forma diferente.
TRAVERSAL_PARAMS = {"tenant", "direction", "depth", "as_of"}

#: COLABORADORES injetados — não são a pergunta, são de QUEM a travessia
#: pergunta. Contados numa lista própria e nunca somados aos de cima, porque a
#: distinção é exatamente o que o gatilho mede: um colaborador a mais é
#: acoplamento (revisável em code review), um parâmetro de PERGUNTA a mais é
#: expressividade — que é o que inverte a recomendação da spec. Somá-los faria
#: esta guarda perder o dente sem ninguém notar.
TRAVERSAL_COLLABORATORS = {"kinds"}

_GATILHO_1 = (
    "\n\n⚠️ GATILHO 1 de spec-topologia-do-grafo §10 — EXPRESSIVIDADE.\n"
    "Esta guarda não está reclamando do seu código: ela está dizendo que a\n"
    "recomendação da spec (ficar no Postgres, grafo como índice na mesma\n"
    "transação) acabou de ser posta em dúvida pelo sinal que a própria spec\n"
    "escolheu — 'o primeiro parâmetro que COMPÕE na rota refs' ou 'duas rotas\n"
    "de travessia de forma diferente'.\n"
    "A porta já está nomeada e o custo já está medido: Apache AGE, no mesmo\n"
    "Postgres, US$ 0,00 marginal, decisão de meio dia (§5.1.1). E a regra do\n"
    "§8 manda ADOTAR GQL/openCypher, nunca inventar linguagem de consulta.\n"
    "Se a mudança é mesmo para entrar: atualize esta guarda NA MESMA PR e\n"
    "diga na descrição que o gatilho 1 foi contado."
)


class TestGatilho1Expressividade:
    """O gatilho que de fato vira um banco de grafo não aparece em tráfego
    nenhum: ele conta FORMAS de pergunta. Então ele é uma guarda de assinatura,
    e o dia em que a forma mudar a suíte fica vermelha citando a spec."""

    def test_a_travessia_tem_UMA_forma(self):
        params = {
            n for n, p in inspect.signature(g.traverse).parameters.items()
            if p.kind is inspect.Parameter.KEYWORD_ONLY
        }
        assert params == TRAVERSAL_PARAMS | TRAVERSAL_COLLABORATORS, _GATILHO_1

    def test_a_fachada_do_kernel_nao_compoe_nada_a_mais(self):
        """Um parâmetro que compõe tem de atravessar esta fachada para chegar
        na CTE — contá-la fecha o caminho por cima.

        O colaborador NÃO aparece aqui, e essa ausência é o teste: a fachada
        CONSTRÓI a lente a partir do próprio kernel. Se ``kinds`` vazasse para
        cá, um chamador de fora poderia escolher de qual registro a travessia
        deriva o passado — que é composição, não coordenada."""
        params = {
            n for n, p in inspect.signature(Kernel.graph_refs).parameters.items()
            if p.kind is inspect.Parameter.KEYWORD_ONLY
        }
        assert params == TRAVERSAL_PARAMS, _GATILHO_1

    def test_a_porta_do_caso_de_uso_nao_compoe_nada_a_mais(self):
        """``graph_refs_impl`` é o que a rota REST e a face MCP chamam.
        ``kind``, ``name``, ``scope`` e ``api_version`` são ENDEREÇO (QUAL
        instância, e onde ela mora), não forma da pergunta — por isso entram na
        lista e não contam como composição."""
        params = {
            n for n, p in inspect.signature(graph_refs_impl).parameters.items()
            if p.kind is inspect.Parameter.KEYWORD_ONLY
        }
        assert params == TRAVERSAL_PARAMS | {
            "kind", "name", "scope", "api_version",
        }, _GATILHO_1

    def test_existe_UMA_travessia_no_kernel(self):
        """"Duas rotas de travessia de forma diferente" começa aqui: uma
        segunda função de caminhada no módulo de policy é a segunda forma.

        ⚠️ ``_walk_as_of`` é privada e não conta — e a razão está escrita para
        ser contestada, não engolida: ela responde a MESMA pergunta com a
        coordenada de tempo, só é alcançável por ``traverse``, e nenhuma face
        pode chamá-la. Uma pública seria a segunda porta; um helper atrás da
        primeira não é. O teste abaixo prende essa condição — se ela virar
        pública, este teste fica vermelho citando a spec."""
        walkers = {
            n for n, fn in vars(g).items()
            if inspect.iscoroutinefunction(fn) and not n.startswith("_")
        }
        assert walkers == {"traverse"}, _GATILHO_1

    def test_a_travessia_tem_UM_eixo_de_tempo(self):
        """``as_of`` (transação) e ``valid_at`` (validade) são eixos DIFERENTES,
        e esta travessia carrega um só.

        Não é preguiça e não é acaso: a interseção bitemporal precisa da janela
        de validade nas LINHAS DE VERSÃO, e ``dna_versions`` não a tem — a mesma
        lacuna nomeada que faz ``get_instance(as_of=…, valid_at=…)`` juntos
        serem recusados com ``ValueError``. Esta guarda fica vermelha no dia em
        que alguém acrescentar o segundo eixo por conveniência, e o remédio
        certo naquele dia é fechar a lacuna, não passar a guarda."""
        for fn in (g.traverse, Kernel.graph_refs, graph_refs_impl):
            params = set(inspect.signature(fn).parameters)
            assert "as_of" in params, fn
            assert "valid_at" not in params, (
                f"{fn.__qualname__} ganhou um SEGUNDO eixo de tempo. "
                "A interseção bitemporal precisa da janela de validade em "
                "dna_versions, que não a tem — servir o eixo que por acaso "
                "for checado primeiro responde uma pergunta que ninguém fez, "
                "com a cara de uma que fizeram."
            )
