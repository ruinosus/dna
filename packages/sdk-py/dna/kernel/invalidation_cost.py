"""O CUSTO da invalidação de cache — o funil que transforma a forma em número.

A pergunta do fundador (i-123, 07/08/2026) foi *"se não estiver bem feito não
vai funcionar nunca em ambiente enterprise"*, e a resposta honesta era:
**sabemos a forma, não o número.** A forma está no código e é boa — três níveis
de invalidação, o barato (``doc``) automático para o plano ``record``, e até uma
válvula de lote (``Kernel.batch_writes``) que pula o reload e consolida. O que
ninguém tinha era **quanto custa**, com dado real, e se esse custo cresce com o
tamanho do escopo.

Este módulo é o equivalente, para a invalidação, do que a fatia 0 de
``spec-topologia-do-grafo`` fez para a travessia (``dna/kernel/query/graph.py``):
uma linha de log por evento, custo ZERO desligado, rótulos de cardinalidade
fechada, e **gatilhos nomeados** — um número que, ultrapassado, diz o que fazer.

## ⚠️ A leitura errada que este arquivo existe para impedir

**`invalidate` sair barato NÃO significa que ``composition`` é barato.**

``InvalidationController.invalidate_internal`` faz três coisas: derruba o cache
base do escopo (``base_drop`` — O(1)), recarrega os *holders*, e dispara os
observadores. Só que o reload de um holder é, nos dois holders que existem hoje,
**preguiçoso**: o da CLI (``dna_cli._ctx._Holder.reload``) apenas anula a MI em
cache, e dentro de um event loop o reload async vira ``loop.create_task`` — ou
seja, sai do relógio. **O custo real não está onde a invalidação acontece; está
no PRÓXIMO build do escopo**, que agora tem de refazer o ``load_all`` e o
``_parse_doc`` que o próprio ``instance_builder`` chama de *"the dominant cost"*.

Por isso o funil emite **três eventos**, e não um. Medir só o primeiro
imprimiria "p95 = 0,3 ms" e todo mundo concluiria que a gaveta cara é barata —
que é exatamente o erro que este módulo existe para não deixar acontecer.

| evento | onde | responde |
|---|---|---|
| ``write`` | ``WritePipeline.write``/``delete`` | com que FREQUÊNCIA a gaveta cara é aberta, e por qual plano |
| ``invalidate`` | ``InvalidationController.invalidate`` | quanto custa o fan-out em si (holders + observadores) |
| ``rebuild`` | ``InstanceBuilder.build`` | quanto custa RECONSTRUIR o escopo, e se isso é O(tamanho do escopo) |

O ``rebuild`` carrega ``docs`` e ``ms`` na MESMA linha de propósito: é a
regressão de um contra o outro que responde "é linear?", e duas linhas separadas
não fecham.

## Como ligar e como ler

```bash
DNA_INVALIDATION_TELEMETRY=on          # no serviço que grava
az containerapp logs show -n ca-dna-api-… --tail 5000 | dna invalidation stats --gate
dna invalidation stats /tmp/api.log    # local
```

## As regras que a fatia 0 provou e esta repete

* **Custo zero desligada.** Uma comparação de nível (``isEnabledFor``, com o
  cache que o stdlib já mantém) e mais nada: o relógio não é lido, o dicionário
  não é montado, a string não é formatada. Provado **pelo negativo** —
  ``tests/test_invalidation_telemetry.py`` troca :data:`_clock` por uma função
  que levanta ``AssertionError`` e exige que o caminho desligado siga verde.
* **A chave de ambiente é lida UMA vez, no import.** Um ``os.environ`` por
  escrita não é zero.
* **Rótulos de cardinalidade fechada.** Nada de nome de instância. E o nome do
  Kind sai só quando ele é NOSSO: um Kind autorado por tenant vira o token
  :data:`TENANT_KIND` — o nome dele é conteúdo do cliente, e um log de operador
  não o carrega. O tenant vira balde de hash, nunca valor cru.
* **Emissor e leitor no mesmo arquivo.** Os três emissores e o
  :func:`invalidation_stats` moram aqui; os pontos de chamada só chamam. Dois
  que possam divergir divergem.
* **``stderr``, não ``stdout``** — pelo mesmo motivo medido na fatia 0: uma
  linha de telemetria no meio de um ``--json`` quebra o ``| jq`` de quem
  consome.
* **Zero linha lida NÃO se lê como "não disparou".** O relatório diz, com essas
  palavras, que **NADA foi medido**.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from collections.abc import Iterable, Mapping
from typing import Any

# Reaproveitados do funil da travessia DE PROPÓSITO, e não copiados: o mesmo
# tenant tem de cair no MESMO balde nos dois relatórios, senão ninguém consegue
# cruzar "a travessia deste tenant está lenta" com "as escritas dele derrubam o
# escopo inteiro" — que é a correlação que mais importa quando os dois
# dispararem juntos. E o percentil por rank mais próximo devolve sempre um valor
# OBSERVADO, pela razão escrita lá.
from dna.kernel.query.graph import percentile, tenant_bucket

# ── os LIMIARES dos gatilhos, escritos uma vez ──────────────────────────────
#
# Ficam aqui, e não num ``if`` do comando que imprime, porque o número que
# decide uma arquitetura não pode morar na apresentação: quem lê o emissor tem
# de ver o limiar.

#: `p95` do rebuild de escopo (ms) acima do qual o GATILHO 1 dispara.
#:
#: **Mil milissegundos**, e o motivo é o lugar onde esse tempo cai: o rebuild
#: fica ENTRE uma escrita e a próxima leitura daquele escopo. Um segundo é onde
#: uma tela de portal deixa de parecer viva e passa a parecer quebrada — e ela é
#: o consumidor real deste caminho, não um job de fundo.
#:
#: ⚠️ Comparação ESTRITA. Um `>=` faria o rebuild que bate exatamente no limiar
#: disparar uma mudança de arquitetura.
TRIGGER_REBUILD_P95_MS = 1000.0

#: Fração das escritas que abre a gaveta cara (``mode="scope"``) acima da qual
#: o GATILHO 2 dispara.
#:
#: **20%.** Com o default do i-123 em ``record``, uma invalidação de escopo
#: deveria vir SÓ das escritas que mudam o esquema — Genome, KindDefinition,
#: LayerPolicy — que são raras por construção. Se mais de uma escrita em cinco
#: ainda derruba um escopo, a troca do default não alcançou o tráfego real, e a
#: gaveta cara continua sendo a comum. O relatório nomeia os Kinds do topo para
#: que o passo seguinte seja uma consulta, não uma caçada.
TRIGGER_SCOPE_WRITE_RATIO = 0.20

# ── o funil ─────────────────────────────────────────────────────────────────

#: O logger. O NÍVEL DELE é a chave liga/desliga — nenhum mecanismo novo.
INVALIDATION_LOGGER = "dna.kernel.invalidation"

#: A marca no início da mensagem. Existe porque o formato de log do host é dele,
#: não nosso: o nome do logger pode não sair na linha, e sem uma marca estável
#: no TEXTO não há como pescar estas linhas de um ``az containerapp logs show``.
INVALIDATION_MARK = "dna.kernel.invalidation "

#: O que sai no lugar do nome de um Kind autorado por tenant. Ver
#: :func:`kind_label`.
TENANT_KIND = "~tenant"

_LOG = logging.getLogger(INVALIDATION_LOGGER)

#: Indireção do relógio para que o teste do custo-zero possa provar, PELO
#: NEGATIVO, que o caminho desligado não o toca (ele o troca por algo que
#: levanta). Não é um ponto de extensão.
_clock = time.perf_counter


def now() -> float:
    """O relógio, lido através de :data:`_clock`.

    Os pontos de medição estão em TRÊS módulos (pipeline, invalidation,
    instance_builder), e um ``from … import _clock`` em cada um copiaria a
    referência: trocar ``_clock`` aqui não alcançaria nenhum deles, e o teste
    do custo-zero — que prova pelo negativo, substituindo o relógio por algo que
    LEVANTA — passaria sem provar nada. Esta função é a única leitura de
    ``_clock``, então trocá-lo alcança os três.
    """
    return _clock()


def _configure_from_env() -> None:
    """``DNA_INVALIDATION_TELEMETRY=on`` liga o funil — e garante que ele SAIA.

    Ligar o nível não basta, e a diferença já custou caro nesta casa: sob
    ``uvicorn`` o logger raiz não tem handler, e um record INFO sem handler é
    descartado em silêncio (``logging.lastResort`` só atende WARNING+). O
    resultado seria a instrumentação "ligada" e nenhum número em lugar nenhum.
    Então, e SÓ quando ninguém mais está ouvindo, este funil ganha o seu próprio
    handler para ``stderr``, que é o que o container coleta.

    Lido uma vez, no import: o custo por escrita tem de ser zero, e um
    ``os.environ`` por escrita não é zero. Quem quiser mexer ao vivo mexe pelo
    caminho normal do stdlib (``logging.getLogger(INVALIDATION_LOGGER)
    .setLevel``), que continua valendo e é por isso que não há chave própria.
    """
    raw = os.environ.get("DNA_INVALIDATION_TELEMETRY", "").strip().lower()
    if raw not in ("1", "on", "true", "yes"):
        return
    _LOG.setLevel(logging.INFO)
    if not _LOG.hasHandlers():
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        _LOG.addHandler(handler)
        # Nós passamos a ser o emissor desta linha; propagar para uma raiz que
        # ganhe handlers depois duplicaria a mesma escrita no relatório.
        _LOG.propagate = False


_configure_from_env()


def invalidation_logging_enabled() -> bool:
    """O funil está ligado? Uma comparação de inteiro, com cache do stdlib."""
    return _LOG.isEnabledFor(logging.INFO)


def kind_label(kind: str, port: Any) -> str:
    """O nome do Kind que PODE sair num log de operador — ou :data:`TENANT_KIND`.

    O nome de um Kind autorado por tenant é conteúdo do cliente e de
    cardinalidade aberta: ``ContratoDePrestacaoDeServicos`` diz o que aquele
    cliente faz. Os nossos (classe ou descritor de pacote) são um vocabulário
    fechado de ~75 palavras que já estão no GitHub.

    O discriminante é o que o ``KindRegistry`` já usa em dois lugares
    (``_prefer_system_ports``, ``validate_dep_filters``): declarativo E não
    marcado como descritor builtin ⇒ veio do store de um tenant.

    ⚠️ Distinguir "veio de tenant" de "é nosso" é EXATAMENTE o eixo que decide o
    gatilho 2 depois desta mudança — então o rótulo não perde a informação que
    importa; só perde a que não pode sair.
    """
    declarative = bool(getattr(port, "__declarative__", False))
    builtin = bool(getattr(port, "__builtin_descriptor__", False))
    return TENANT_KIND if (declarative and not builtin) else kind


def _emit(record: dict[str, Any]) -> None:
    """Uma linha, marcada e em JSON. Só chamada com o funil ligado.

    O mesmo objeto viaja em ``extra["dna_invalidation"]``, para que um handler
    que já emita JSON estruturado leia os campos sem re-parsear o texto.
    """
    _LOG.info(
        "%s%s", INVALIDATION_MARK,
        json.dumps(record, sort_keys=True, separators=(",", ":")),
        extra={"dna_invalidation": record},
    )


def emit_write(
    *, kind: str, port: Any, plane: str, mode: str, op: str, tenant: str | None,
) -> None:
    """O CONTADOR: uma linha por escrita/delete, com o modo já REBAIXADO.

    Sem relógio — este evento é o denominador do gatilho 2 e nada mais. Timing
    aqui seria medir a escrita inteira (I/O do adapter incluído), que não é o
    que está em questão.

    ``plane`` e ``mode`` juntos já dizem se houve rebaixamento
    (``record``+``doc``) sem um terceiro campo que possa discordar deles.
    """
    _emit({
        "ev": "write", "kind": kind_label(kind, port), "plane": plane,
        "mode": mode, "op": op, "tenant": tenant_bucket(tenant),
    })


def emit_invalidate(
    *, kind: str, port: Any, op: str, holders: int, ms: float, batch: bool,
    tenant: str | None,
) -> None:
    """O FAN-OUT: quanto custou derrubar o cache base + recarregar os holders.

    ⚠️ Leia junto com ``rebuild``. Ver o aviso no topo do módulo: com holders
    preguiçosos este número é pequeno POR DESENHO, e sozinho ele mente.

    ``batch`` é ``True`` quando o evento foi só BUFFERIZADO por um
    ``batch_writes()`` — a válvula. Separá-lo é o que permite ver se a válvula
    está sendo usada onde deveria.
    """
    _emit({
        "ev": "invalidate", "kind": kind_label(kind, port), "op": op,
        "holders": holders, "ms": round(ms, 1), "batch": batch,
        "tenant": tenant_bucket(tenant),
    })


def emit_rebuild(
    *, docs: int, materialized: int, skipped: int, ms: float,
) -> None:
    """O REBUILD: o custo que a invalidação de escopo DESLOCA para a frente.

    ``docs`` é o tamanho do escopo lido, ``materialized`` quantas instâncias
    entraram na MI, ``skipped`` quantas o filtro de plano poupou do
    ``_parse_doc``. Os três na mesma linha do ``ms`` porque é a razão entre eles
    que responde às duas perguntas do fundador — quanto custa, e se é
    O(tamanho do escopo).

    Sem ``tenant``: um build de escopo não é por tenant (a MI é do escopo; o
    tenant só carimba a leitura), então um balde aqui seria um campo sempre
    ``-`` fingindo ser um eixo.
    """
    _emit({
        "ev": "rebuild", "docs": docs, "materialized": materialized,
        "skipped": skipped, "ms": round(ms, 1),
    })


# ── o leitor ────────────────────────────────────────────────────────────────

#: Os baldes de tamanho de escopo, para a evidência de linearidade. Fechados e
#: por ordem de grandeza: se o `p95` dobra quando o balde multiplica por dez, o
#: rebuild é SUB-linear; se decuplica, é linear; ver :func:`invalidation_stats`.
_DOC_BUCKETS: tuple[tuple[int, str], ...] = (
    (100, "<100"), (1_000, "<1k"), (10_000, "<10k"),
)
_DOC_BUCKET_TOP = "10k+"


def doc_bucket(docs: int) -> str:
    """O balde de tamanho de escopo de um rebuild. Cardinalidade fechada: 4."""
    for ceiling, label in _DOC_BUCKETS:
        if docs < ceiling:
            return label
    return _DOC_BUCKET_TOP


def parse_line(line: str) -> dict[str, Any] | None:
    """Uma linha de log → o registro, ou ``None`` se ela não for nossa.

    Tolerante por desenho: a entrada real é a saída de ``az containerapp logs
    show``/``docker logs``, onde cada linha vem prefixada por carimbo de tempo,
    nome de container e nível. Achamos a marca, e o JSON começa na primeira
    ``{`` depois dela.
    """
    at = line.find(INVALIDATION_MARK)
    if at < 0:
        return None
    brace = line.find("{", at + len(INVALIDATION_MARK) - 1)
    if brace < 0:
        return None
    try:
        record = json.loads(line[brace:])
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def _top(counter: Mapping[str, int], n: int = 5) -> list[dict[str, Any]]:
    """Os ``n`` maiores, ordem estável (contagem desc, depois nome)."""
    return [
        {"kind": k, "calls": v}
        for k, v in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
    ]


def invalidation_stats(lines: Iterable[str]) -> dict[str, Any]:
    """As linhas → os dois números dos gatilhos, e o veredicto de cada um.

    Não filtra nada em silêncio: ``ignored`` conta as linhas que não eram
    nossas, e cada evento reporta a sua própria contagem — um relatório feito
    sobre o arquivo errado se denuncia em vez de imprimir zeros com cara de
    "tudo bem".

    ⚠️ **``rebuild.by_docs`` é EVIDÊNCIA, não gatilho.** Ele existe para
    responder "é O(tamanho do escopo)?" olhando o `p95` de cada balde: um
    rebuild linear multiplica o `p95` por ~10 a cada balde. Linearidade não é
    defeito — é a forma esperada; o que decide é o VALOR, e esse é o gatilho 1.
    """
    writes: list[Mapping[str, Any]] = []
    invalidations: list[Mapping[str, Any]] = []
    rebuilds: list[Mapping[str, Any]] = []
    ignored = 0
    unknown_ev = 0
    for line in lines:
        record = parse_line(line)
        if record is None:
            ignored += 1
            continue
        ev = record.get("ev")
        if ev == "write":
            writes.append(record)
        elif ev == "invalidate":
            invalidations.append(record)
        elif ev == "rebuild":
            rebuilds.append(record)
        else:
            # Nossa marca, evento que este leitor não conhece — uma versão mais
            # nova do emissor contra um leitor velho. Contado à parte para que
            # a diferença apareça em vez de ser lida como "não aconteceu".
            unknown_ev += 1

    # ── gatilho 2: a gaveta cara continua sendo a comum? ──
    scope_writes = [w for w in writes if w.get("mode") == "scope"]
    ratio = (len(scope_writes) / len(writes)) if writes else 0.0
    by_plane: dict[str, int] = {}
    for w in writes:
        key = str(w.get("plane", "?"))
        by_plane[key] = by_plane.get(key, 0) + 1
    scope_by_kind: dict[str, int] = {}
    for w in scope_writes:
        key = str(w.get("kind", "?"))
        scope_by_kind[key] = scope_by_kind.get(key, 0) + 1

    # ── o fan-out ──
    inv_ms = [float(r.get("ms", 0.0)) for r in invalidations]
    batched = sum(1 for r in invalidations if r.get("batch"))

    # ── gatilho 1: o rebuild ──
    reb_ms = [float(r.get("ms", 0.0)) for r in rebuilds]
    reb_p95 = percentile(reb_ms, 0.95)
    buckets: dict[str, list[float]] = {}
    saved = 0
    parsed = 0
    for r in rebuilds:
        buckets.setdefault(
            doc_bucket(int(r.get("docs", 0) or 0)), [],
        ).append(float(r.get("ms", 0.0)))
        saved += int(r.get("skipped", 0) or 0)
        parsed += int(r.get("materialized", 0) or 0)
    by_docs = [
        {"docs": label, "calls": len(v), "p95_ms": percentile(v, 0.95)}
        for label, v in sorted(
            buckets.items(),
            key=lambda kv: [b[1] for b in _DOC_BUCKETS].index(kv[0])
            if kv[0] != _DOC_BUCKET_TOP else len(_DOC_BUCKETS),
        )
    ]

    # ⚠️ ESTRITAMENTE maior, nos dois — ver os limiares.
    rebuild_fired = reb_p95 > TRIGGER_REBUILD_P95_MS
    ratio_fired = ratio > TRIGGER_SCOPE_WRITE_RATIO

    return {
        "ignored": ignored,
        "unknown_events": unknown_ev,
        "writes": {
            "calls": len(writes),
            "scope_mode": len(scope_writes),
            "scope_ratio": ratio,
            "by_plane": by_plane,
            "scope_by_kind": _top(scope_by_kind),
        },
        "invalidate": {
            "calls": len(invalidations),
            "p95_ms": percentile(inv_ms, 0.95),
            "batched": batched,
            # A frase, no relatório, para que ninguém a reconstrua errado.
            "note": (
                "o fan-out é pequeno POR DESENHO — os holders recarregam "
                "preguiçosamente e, dentro de um event loop, fora do relógio. "
                "O custo está em `rebuild`."
            ),
        },
        "rebuild": {
            "calls": len(rebuilds),
            "p95_ms": reb_p95,
            "by_docs": by_docs,
            "materialized": parsed,
            # Quantas instâncias o filtro de plano poupou do `_parse_doc` — o
            # que a decisão do i-123 compra, somado.
            "skipped_by_plane": saved,
        },
        "triggers": {
            "rebuild_p95": {
                "fired": rebuild_fired,
                "value_ms": reb_p95,
                "threshold_ms": TRIGGER_REBUILD_P95_MS,
                "basis": "p95 do tempo de build da ManifestInstance de um escopo",
            },
            "scope_write_ratio": {
                "fired": ratio_fired,
                "value": ratio,
                "threshold": TRIGGER_SCOPE_WRITE_RATIO,
                "basis": "fração das escritas com invalidate_mode='scope'",
            },
        },
        "fired": rebuild_fired or ratio_fired,
    }
