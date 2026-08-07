"""i-123 fatia 2 — o funil que mede o CUSTO da invalidação de cache.

O que cada asserção aqui veria mudar está escrito na sua própria mensagem. As
duas que carregam o peso:

* **o caminho DESLIGADO lendo o relógio** — provado pelo negativo, trocando
  ``invalidation_cost._clock`` por algo que levanta;
* **o relatório dizendo "não disparou" quando não mediu nada** — a mentira mais
  fácil de um relatório, e a que a fatia 0 já tinha nomeado.
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

import pytest

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.extensions.helix import HelixExtension
from dna.extensions.kinddef import KindDefinitionExtension
from dna.extensions.sdlc import SdlcExtension
from dna.kernel import Kernel
from dna.kernel import invalidation_cost as ic


@pytest.fixture
def ligado(monkeypatch, caplog):
    """O funil ligado pelo NÍVEL — o mesmo mecanismo que a chave de ambiente
    usa, sem depender de reimportar o módulo."""
    logger = logging.getLogger(ic.INVALIDATION_LOGGER)
    monkeypatch.setattr(logger, "level", logging.INFO)
    caplog.set_level(logging.INFO, logger=ic.INVALIDATION_LOGGER)
    return caplog


def _linhas(caplog, ev: str | None = None) -> list[dict[str, Any]]:
    out = []
    for r in caplog.records:
        rec = ic.parse_line(r.getMessage())
        if rec is not None and (ev is None or rec.get("ev") == ev):
            out.append(rec)
    return out


@pytest.fixture
def kernel_com_escopo(tmp_path):
    scope = "test-scope"
    d = tmp_path / scope
    d.mkdir(parents=True)
    (d / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
        f"metadata:\n  name: {scope}\nspec: {{}}\n"
    )
    k = Kernel()
    k.load(HelixExtension())
    k.load(KindDefinitionExtension())
    # ⚠️ A SDLC entra porque os testes abaixo escrevem `Story`, e o plano de um
    # Kind NÃO REGISTRADO é o fail-safe `composition`: sem esta linha as
    # asserções sobre rebaixamento passariam a medir a ausência do Kind.
    k.load(SdlcExtension())
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))
    k.cache(FilesystemCache(str(tmp_path)))
    return k, scope


class TestCustoZeroDesligada:
    """⭐ O mutante nomeado no despacho: a instrumentação lendo o relógio com a
    chave desligada."""

    @pytest.mark.asyncio
    async def test_o_caminho_desligado_NAO_LE_o_relogio(
        self, kernel_com_escopo, monkeypatch,
    ):
        """Provado PELO NEGATIVO. Um teste que só afirmasse "está desligado"
        não veria o `now()` que alguém tirou de dentro do `if`."""
        k, scope = kernel_com_escopo

        def _explode() -> float:
            raise AssertionError(
                "o caminho DESLIGADO leu o relógio — a instrumentação deixou "
                "de ser gratuita para quem não a ligou"
            )

        monkeypatch.setattr(ic, "_clock", _explode)
        assert not ic.invalidation_logging_enabled()

        await k.write_instance(
            scope, "Genome", scope,
            {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
             "metadata": {"name": scope}, "spec": {"x": 1}},
        )
        mi = await k.instance_async(scope)
        assert mi is not None, "o caminho continua respondendo o mesmo"

    @pytest.mark.asyncio
    async def test_LIGADA_o_relogio_E_lido(
        self, kernel_com_escopo, monkeypatch, ligado,
    ):
        """A outra metade do mutante: se o teste acima passasse porque o
        relógio nunca é lido em lugar nenhum, ele não provaria nada."""
        k, scope = kernel_com_escopo
        vistos: list[int] = []

        def _tic() -> float:
            vistos.append(1)
            return float(len(vistos))

        monkeypatch.setattr(ic, "_clock", _tic)
        await k.instance_async(scope)
        assert vistos, "ligada, o relógio TEM de ser lido"
        assert _linhas(ligado, "rebuild"), "…e a linha tem de sair"

    def test_a_indirecao_do_relogio_alcanca_os_TRES_modulos(self):
        """A razão de ``now()`` existir em vez de um ``_clock`` importado.

        Os pontos de medição estão em três módulos. Um ``from … import _clock``
        em cada um copiaria a REFERÊNCIA, e o teste do custo-zero passaria a
        provar nada — ele trocaria um ``_clock`` que aquele módulo não lê mais.
        A guarda é que ninguém importe o nome DESTE módulo.

        ⚠️ Ela olha as importações, não a string: ``query/graph.py`` tem um
        ``_clock`` próprio, do funil da travessia, e uma busca textual o
        acusaria — uma guarda que grita por um arquivo inocente é desligada, e
        aí não guarda nada.
        """
        import ast
        import pathlib
        raiz = pathlib.Path(ic.__file__).resolve().parent
        culpados = []
        for p in raiz.rglob("*.py"):
            if p.name == "invalidation_cost.py":
                continue
            try:
                arvore = ast.parse(p.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover — defensivo
                continue
            for no in ast.walk(arvore):
                if (
                    isinstance(no, ast.ImportFrom)
                    and (no.module or "").endswith("invalidation_cost")
                    and any(a.name == "_clock" for a in no.names)
                ):
                    culpados.append(p.relative_to(raiz))
        assert not culpados, (
            f"{culpados} importam `_clock` do módulo emissor — use `now()`, ou "
            f"o teste do custo-zero deixa de alcançar esse ponto de medição"
        )


class TestAChave:

    def test_a_chave_liga_o_nivel_E_garante_que_a_linha_SAIA(self, monkeypatch):
        """⚠️ Ligar o nível não basta. Sob ``uvicorn`` o logger raiz não tem
        handler, e um record INFO sem handler morre em silêncio
        (``lastResort`` só atende WARNING+): instrumentação "ligada" e nenhum
        número em lugar nenhum — capacidade existe, porta não."""
        logger = logging.getLogger(ic.INVALIDATION_LOGGER)
        monkeypatch.setattr(logger, "level", logging.NOTSET)
        monkeypatch.setattr(logger, "handlers", [])
        monkeypatch.setattr(logger, "propagate", False)  # ninguém ouvindo
        monkeypatch.setenv("DNA_INVALIDATION_TELEMETRY", "on")

        ic._configure_from_env()

        assert logger.isEnabledFor(logging.INFO)
        assert logger.hasHandlers(), "ligado e sem destino é o mesmo que desligado"
        assert logger.handlers[0].stream is sys.stderr, (
            "stderr e NÃO stdout: uma linha de telemetria no meio de um "
            "`--json` quebra o `| jq` de quem consome a saída"
        )

    def test_a_chave_nao_rouba_o_handler_de_quem_ja_escuta(self, monkeypatch):
        """Duas emissões da mesma escrita a contariam duas vezes."""
        logger = logging.getLogger(ic.INVALIDATION_LOGGER)
        monkeypatch.setattr(logger, "handlers", [])
        monkeypatch.setattr(logger, "propagate", True)  # a raiz do host escuta
        raiz = logging.getLogger()
        nulo = logging.NullHandler()
        raiz.addHandler(nulo)
        monkeypatch.setenv("DNA_INVALIDATION_TELEMETRY", "1")
        try:
            ic._configure_from_env()
            assert logger.handlers == [] and logger.propagate is True
        finally:
            raiz.removeHandler(nulo)

    @pytest.mark.parametrize("valor", ["", "off", "0", "no", "talvez"])
    def test_qualquer_outro_valor_NAO_liga(self, monkeypatch, valor):
        """Uma biblioteca que mexe no logging de quem a importa é mal-educada:
        sem a chave, nem o nível nem os handlers."""
        logger = logging.getLogger(ic.INVALIDATION_LOGGER)
        monkeypatch.setattr(logger, "level", logging.NOTSET)
        monkeypatch.setattr(logger, "handlers", [])
        monkeypatch.setenv("DNA_INVALIDATION_TELEMETRY", valor)
        ic._configure_from_env()
        assert logger.level == logging.NOTSET and logger.handlers == []


class TestOsRotulos:
    """Cardinalidade fechada, e nada de conteúdo do cliente."""

    def test_o_nome_de_um_kind_de_TENANT_nao_sai_no_log(self):
        tenant = type("P", (), {
            "__declarative__": True, "__builtin_descriptor__": False,
        })()
        assert ic.kind_label("ContratoDePrestacaoDeServicos", tenant) == (
            ic.TENANT_KIND
        ), (
            "o nome de um Kind autorado por tenant é conteúdo do cliente e de "
            "cardinalidade aberta — um log de operador não o carrega"
        )

    @pytest.mark.parametrize("port", [
        None,
        type("Classe", (), {})(),
        type("Descritor", (), {
            "__declarative__": True, "__builtin_descriptor__": True,
        })(),
    ])
    def test_o_nome_de_um_kind_NOSSO_sai(self, port):
        assert ic.kind_label("Story", port) == "Story", (
            "os nossos são um vocabulário fechado que já está no GitHub, e é "
            "o eixo que decide o gatilho 2 — perdê-lo custaria a decisão"
        )

    def test_o_tenant_vira_balde_e_nunca_valor_cru(self, ligado):
        ic.emit_write(
            kind="Story", port=None, plane="record", mode="doc", op="write",
            tenant="ws-acme-corporation",
        )
        linha, = _linhas(ligado, "write")
        assert "acme" not in json.dumps(linha)
        assert linha["tenant"] == ic.tenant_bucket("ws-acme-corporation")

    @pytest.mark.parametrize("docs,esperado", [
        (0, "<100"), (99, "<100"), (100, "<1k"), (999, "<1k"),
        (1_000, "<10k"), (9_999, "<10k"), (10_000, "10k+"), (150_000, "10k+"),
    ])
    def test_os_baldes_de_tamanho_sao_fechados(self, docs, esperado):
        assert ic.doc_bucket(docs) == esperado


class TestOsTresEventos:

    @pytest.mark.asyncio
    async def test_uma_escrita_emite_o_contador_com_o_modo_JA_REBAIXADO(
        self, kernel_com_escopo, ligado,
    ):
        """O `mode` da linha é o EFETIVO, depois do rebaixamento record→doc.

        Se ele fosse o pedido, o gatilho 2 contaria como "gaveta cara aberta"
        justamente as escritas que o plano `record` já tinha barateado — e o
        número diria o contrário do que acontece.
        """
        k, scope = kernel_com_escopo
        await k.write_instance(
            scope, "Story", "s1",
            {"apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Story",
             "metadata": {"name": "s1"},
             "spec": {"title": "t", "description": "d", "status": "todo"}},
            invalidate_mode="scope",
        )
        escritas = _linhas(ligado, "write")
        assert escritas, "toda escrita emite o contador"
        assert escritas[-1]["kind"] == "Story"
        assert escritas[-1]["plane"] == "record"
        assert escritas[-1]["mode"] == "doc", (
            "Story está no plano record: o `scope` pedido foi rebaixado para "
            "`doc`, e é o rebaixado que a linha carrega"
        )
        assert escritas[-1]["op"] == "write"

    @pytest.mark.asyncio
    async def test_o_rebuild_carrega_docs_E_ms_NA_MESMA_LINHA(
        self, kernel_com_escopo, ligado,
    ):
        """É a regressão de um contra o outro que responde "é O(escopo)?".
        Em duas linhas separadas a pergunta não fecha."""
        k, scope = kernel_com_escopo
        await k.instance_async(scope)
        reb = _linhas(ligado, "rebuild")
        assert reb, "todo build de MI emite um rebuild"
        assert {"docs", "materialized", "skipped", "ms"} <= set(reb[-1])

    @pytest.mark.asyncio
    async def test_o_rebuild_conta_o_que_o_plano_record_POUPOU(
        self, kernel_com_escopo, ligado,
    ):
        """`skipped` é o que a decisão do i-123 compra, somado — sem ele o
        relatório mostraria o custo e não o que foi evitado."""
        k, scope = kernel_com_escopo
        for i in range(3):
            await k.write_instance(
                scope, "Story", f"s{i}",
                {"apiVersion": "github.com/ruinosus/dna/sdlc/v1",
                 "kind": "Story", "metadata": {"name": f"s{i}"},
                 "spec": {"title": "t", "description": "d", "status": "todo"}},
            )
        k._kcache.base_drop(scope)
        ligado.clear()
        await k.instance_async(scope)
        reb = _linhas(ligado, "rebuild")
        assert reb and reb[-1]["skipped"] >= 3, (
            "as três Story são plano record e têm de aparecer como POUPADAS do "
            "_parse_doc, não como materializadas"
        )

    def test_a_valvula_batch_writes_aparece_como_bufferizada(self, ligado):
        """`batch=True` com `holders=0`: contar holders num evento que só foi
        bufferizado faria a válvula aparecer custando o que ela evita."""
        ic.emit_invalidate(
            kind="Genome", port=None, op="write", holders=0, ms=0.0,
            batch=True, tenant=None,
        )
        linha, = _linhas(ligado, "invalidate")
        assert linha["batch"] is True and linha["holders"] == 0


class TestOLeitor:

    def _linha(self, **campos) -> str:
        # Com o prefixo que `az containerapp logs show` de fato põe.
        return (
            "2026-08-07T00:00:00Z ca-dna-api INFO "
            + ic.INVALIDATION_MARK + json.dumps(campos)
        )

    def test_zero_linha_NAO_se_le_como_nao_disparou(self):
        r = ic.invalidation_stats(["log de outra coisa", "e outra"])
        assert r["ignored"] == 2
        assert r["writes"]["calls"] == r["rebuild"]["calls"] == 0
        assert r["fired"] is False
        # …e o comando é obrigado a dizer isso com todas as letras; a guarda da
        # frase vive no teste do CLI, que é onde ela é impressa.

    def test_uma_linha_nossa_com_evento_DESCONHECIDO_e_contada_a_parte(self):
        r = ic.invalidation_stats([self._linha(ev="futuro", x=1)])
        assert r["unknown_events"] == 1 and r["ignored"] == 0, (
            "um emissor mais novo que o leitor tem de APARECER; somado aos "
            "ignorados ele viraria 'não aconteceu'"
        )

    def test_o_gatilho_do_rebuild_e_ESTRITAMENTE_maior(self):
        limiar = ic.TRIGGER_REBUILD_P95_MS
        no_limiar = [self._linha(ev="rebuild", docs=10, ms=limiar)] * 100
        acima = [self._linha(ev="rebuild", docs=10, ms=limiar + 0.1)] * 100
        assert ic.invalidation_stats(no_limiar)["fired"] is False, (
            "um `>=` faria o rebuild que bate EXATAMENTE no limiar disparar "
            "uma mudança de arquitetura"
        )
        assert ic.invalidation_stats(acima)["fired"] is True

    def test_o_gatilho_da_razao_e_ESTRITAMENTE_maior(self):
        # 20 escritas: 4/20 = 0,20 (no limiar) e 5/20 = 0,25 (acima).
        def _lote(scope_mode: int) -> list[str]:
            return (
                [self._linha(ev="write", mode="scope", plane="composition",
                             kind="Genome")] * scope_mode
                + [self._linha(ev="write", mode="doc", plane="record",
                               kind="Story")] * (20 - scope_mode)
            )
        no_limiar = ic.invalidation_stats(_lote(4))
        assert no_limiar["writes"]["scope_ratio"] == pytest.approx(0.20)
        assert no_limiar["triggers"]["scope_write_ratio"]["fired"] is False
        assert ic.invalidation_stats(_lote(5))[
            "triggers"]["scope_write_ratio"]["fired"] is True

    def test_o_relatorio_NOMEIA_os_kinds_que_derrubam_escopo(self):
        r = ic.invalidation_stats(
            [self._linha(ev="write", mode="scope", plane="composition",
                         kind="Genome")] * 3
            + [self._linha(ev="write", mode="scope", plane="composition",
                           kind=ic.TENANT_KIND)]
        )
        assert r["writes"]["scope_by_kind"][0] == {"kind": "Genome", "calls": 3}, (
            "sem o nome no topo, o gatilho 2 disparado manda alguém caçar; "
            "com ele, o passo seguinte é uma consulta"
        )

    def test_os_baldes_de_rebuild_saem_em_ordem_de_grandeza(self):
        r = ic.invalidation_stats([
            self._linha(ev="rebuild", docs=50_000, ms=900.0),
            self._linha(ev="rebuild", docs=10, ms=1.0),
            self._linha(ev="rebuild", docs=5_000, ms=90.0),
        ])
        assert [b["docs"] for b in r["rebuild"]["by_docs"]] == [
            "<100", "<10k", "10k+",
        ], (
            "a evidência de linearidade só se lê se os baldes vierem em ordem; "
            "fora de ordem, ninguém enxerga o `p95` decuplicando"
        )

    def test_o_fan_out_carrega_a_ressalva_DENTRO_do_relatorio(self):
        """A leitura errada que este módulo existe para impedir: `invalidate`
        sair barato NÃO significa que `composition` é barato."""
        r = ic.invalidation_stats([self._linha(ev="invalidate", ms=0.2)])
        assert "rebuild" in r["invalidate"]["note"]

    def test_o_percentil_devolve_um_valor_OBSERVADO(self):
        r = ic.invalidation_stats(
            [self._linha(ev="rebuild", docs=1, ms=float(v)) for v in range(1, 101)]
        )
        assert r["rebuild"]["p95_ms"] == 95.0
