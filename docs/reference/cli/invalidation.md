# `dna invalidation`

O custo da invalidação de cache (i-123), lido do log.

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna invalidation --help`.

## `dna invalidation stats`

Os DOIS gatilhos do i-123, lidos das linhas de invalidação.

O i-123 trocou o default de ``plane`` do Kind de tenant para ``record`` — o
que tira o dado errado da gaveta cara, e **não** torna a gaveta cara barata.
Este comando é como se descobre se a gaveta cara aguenta: ele lê as linhas
que ``dna.kernel.invalidation`` emite (uma por escrita, uma por invalidação
de escopo, uma por rebuild de ManifestInstance) e imprime quanto custa
reconstruir um escopo, com que frequência isso é exigido, e se cada limiar
foi ultrapassado.


Ligar o funil:   DNA_INVALIDATION_TELEMETRY=on   (no serviço que GRAVA)
Ler na nuvem:    az containerapp logs show -n ca-dna-api-… --tail 5000 \
                   | dna invalidation stats --gate
Ler local:       dna invalidation stats /tmp/api.log

Lê de STDIN quando LOGFILE é omitido ou `-`, então qualquer coisa que cuspa
as linhas serve de fonte — nada aqui precisa de banco.

⚠️ **O `p95` do fan-out (`invalidate`) NÃO é a medida do custo.** Os holders
recarregam preguiçosamente e, dentro de um event loop, fora do relógio: o
custo real é o REBUILD que a invalidação obriga na próxima leitura daquele
escopo. É por isso que o gatilho 1 mede `rebuild` e não `invalidate`.

```text
dna invalidation stats [OPTIONS] [LOGFILE]
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

