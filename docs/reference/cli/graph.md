# `dna graph`

The derived reference graph (declared relations).

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna graph --help`.

## `dna graph backfill`

Compute edges for instances that predate the producer.

For each declared ``(Kind, field)`` pair, ask the store for the instances
whose ``spec`` HAS that field — on Postgres a JSONB key-existence query the
``dna_insts_spec_gin_idx`` index serves directly. That is a handful of
queries, not a walk over every instance.

An instance whose references cannot be resolved COMPLETELY (a read failed
part-way) is left alone and its scope is reported as pending: a partial
edge set stored as if it were whole is a graph that lies while looking
finished, and the screen can label an absent graph but not a lying one.

```text
dna graph backfill [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--dry-run` | Resolve everything, write nothing — same reads, real numbers. |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--scope` | Only this scope (default: every scope in the store). |

## `dna graph refs`

"What points at this instance?" — the same walk the REST face serves.

```text
dna graph refs [OPTIONS] KIND_NAME NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND_NAME` | yes |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--as-of` | O grafo COMO ELE ERA nesse instante (ISO-8601, tempo de TRANSAÇÃO). Re-derivado das versões — não é o grafo de hoje filtrado. |
| `--depth` | Walk further; clamped by DNA_GRAPH_MAX_DEPTH. _(default: `1`)_ |
| `--direction` | 'in' = what points AT this instance (the product question). _(default: `in`)_ |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--scope` |  |
| `--tenant` |  |

## `dna graph stats`

O GATILHO 2 de `spec-topologia-do-grafo`, lido das linhas de travessia.

A spec recomendou ficar no Postgres com dois gatilhos MEDIDOS que invertem
a decisão. Este comando é a porta por onde o de ESCALA vira número: ele lê
as linhas que `dna.graph.traversal` emite (uma por travessia) e imprime o
`p95` das travessias profundas, a fração truncada, e se cada limiar foi
ultrapassado.


Ligar o funil:   DNA_GRAPH_TELEMETRY=on   (no serviço que serve a travessia)
Ler na nuvem:    az containerapp logs show -n ca-dna-api-… --tail 5000 \
                   | dna graph stats --gate
Ler local:       dna graph stats /tmp/api.log

Lê de STDIN quando LOGFILE é omitido ou `-`, então qualquer coisa que
cuspa as linhas serve de fonte — nada aqui precisa de banco.

⚠️ O gatilho 1 (EXPRESSIVIDADE), que é o que de fato vira um banco de
grafo, NÃO é medido aqui: ele conta FORMAS de pergunta, não chamadas. Quem
o guarda é o teste
`tests/test_graph_telemetry.py::TestGatilho1Expressividade`, que fica
vermelho no dia em que uma segunda forma de travessia ou o primeiro
parâmetro que compõe entrar na rota.

```text
dna graph stats [OPTIONS] [LOGFILE]
```

**Arguments**

| Argument | Required |
| --- | --- |
| `LOGFILE` | no |

**Options**

| Option | Description |
| --- | --- |
| `--gate` | Sai 1 se algum gatilho disparou (para CI/cron). |
| `--help` | Show this message and exit. |
| `--json` | O relatório inteiro, para um script. |

