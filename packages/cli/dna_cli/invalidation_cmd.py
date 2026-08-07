"""``dna invalidation`` — o CUSTO da invalidação de cache, lido do log.

A porta por onde os gatilhos do i-123 viram número. O emissor, os limiares e o
leitor moram todos em ``dna.kernel.invalidation_cost``; este arquivo é só a
apresentação — nenhum limiar aqui, nenhuma conta aqui. Se um número aparecer
neste módulo, ele já divergiu do emissor.

Espelha ``dna graph stats`` de propósito, inclusive na leitura de STDIN: o
operador que já sabe rodar um vira o outro sem aprender nada novo.
"""
from __future__ import annotations

import click

from dna_cli._ctx import print_json


@click.group("invalidation",
             help="O custo da invalidação de cache (i-123), lido do log.")
def invalidation() -> None:
    """Group root."""


@invalidation.command("stats")
@click.argument("logfile", type=click.File("r", encoding="utf-8"), default="-")
@click.option("--json", "as_json", is_flag=True,
              help="O relatório inteiro, para um script.")
@click.option("--gate", is_flag=True,
              help="Sai 1 se algum gatilho disparou (para CI/cron).")
def stats(logfile, as_json: bool, gate: bool) -> None:
    """Os DOIS gatilhos do i-123, lidos das linhas de invalidação.

    O i-123 trocou o default de ``plane`` do Kind de tenant para ``record`` — o
    que tira o dado errado da gaveta cara, e **não** torna a gaveta cara barata.
    Este comando é como se descobre se a gaveta cara aguenta: ele lê as linhas
    que ``dna.kernel.invalidation`` emite (uma por escrita, uma por invalidação
    de escopo, uma por rebuild de ManifestInstance) e imprime quanto custa
    reconstruir um escopo, com que frequência isso é exigido, e se cada limiar
    foi ultrapassado.

    \b
    Ligar o funil:   DNA_INVALIDATION_TELEMETRY=on   (no serviço que GRAVA)
    Ler na nuvem:    az containerapp logs show -n ca-dna-api-… --tail 5000 \\
                       | dna invalidation stats --gate
    Ler local:       dna invalidation stats /tmp/api.log

    Lê de STDIN quando LOGFILE é omitido ou `-`, então qualquer coisa que cuspa
    as linhas serve de fonte — nada aqui precisa de banco.

    ⚠️ **O `p95` do fan-out (`invalidate`) NÃO é a medida do custo.** Os holders
    recarregam preguiçosamente e, dentro de um event loop, fora do relógio: o
    custo real é o REBUILD que a invalidação obriga na próxima leitura daquele
    escopo. É por isso que o gatilho 1 mede `rebuild` e não `invalidate`.
    """
    from dna.kernel.invalidation_cost import invalidation_stats

    report = invalidation_stats(logfile)
    if as_json:
        print_json(report)
        if gate and report["fired"]:
            raise SystemExit(1)
        return

    w = report["writes"]
    inv = report["invalidate"]
    reb = report["rebuild"]
    trig = report["triggers"]
    total = w["calls"] + inv["calls"] + reb["calls"]
    click.echo(
        f"{total} linha(s) de invalidação lidas "
        f"({report['ignored']} ignorada(s)) — "
        f"{w['calls']} escrita(s), {inv['calls']} invalidação(ões), "
        f"{reb['calls']} rebuild(s)"
    )
    if not total:
        # Nunca um relatório de zeros com cara de "tudo bem": zero linha lida é
        # o funil desligado ou o arquivo errado, e as duas coisas renderizadas
        # como "não disparou" seriam a mentira mais fácil aqui.
        click.echo(
            "⚠ nenhuma linha de invalidação nesta entrada — o funil está "
            "desligado (DNA_INVALIDATION_TELEMETRY=on no serviço que GRAVA) "
            "ou a fonte está errada. NADA foi medido; isto não é "
            "'não disparou'."
        )
        return
    if report["unknown_events"]:
        click.echo(
            f"⚠ {report['unknown_events']} linha(s) com a nossa marca e um "
            f"evento que este leitor não conhece — o emissor do serviço é mais "
            f"novo que este `dna`. Elas NÃO entraram em nenhuma conta abaixo."
        )

    rp = trig["rebuild_p95"]
    click.echo(
        f"  [{'DISPAROU' if rp['fired'] else 'ok'}] p95 do rebuild de escopo: "
        f"{rp['value_ms']:.1f} ms (limiar {rp['threshold_ms']:.0f} ms, "
        f"{reb['calls']} rebuild(s))"
    )
    for b in reb["by_docs"]:
        click.echo(
            f"      {b['docs']:>5} docs: {b['p95_ms']:.1f} ms "
            f"em {b['calls']} rebuild(s)"
        )
    if reb["calls"]:
        click.echo(
            f"      {reb['skipped_by_plane']} instância(s) poupadas do "
            f"_parse_doc pelo plano `record` "
            f"(vs {reb['materialized']} materializada(s))"
        )

    sw = trig["scope_write_ratio"]
    click.echo(
        f"  [{'DISPAROU' if sw['fired'] else 'ok'}] escritas que derrubam o "
        f"escopo: {w['scope_mode']}/{w['calls']} = {sw['value'] * 100:.1f}% "
        f"(limiar {sw['threshold'] * 100:.0f}%)"
    )
    if w["calls"]:
        click.echo(f"      por plano: {w['by_plane']}")
    for row in w["scope_by_kind"]:
        click.echo(f"      {row['kind']}: {row['calls']} escrita(s) de escopo")

    click.echo(
        f"  (fan-out: p95 {inv['p95_ms']:.1f} ms em {inv['calls']} "
        f"invalidação(ões), {inv['batched']} bufferizada(s) por batch_writes)"
    )
    click.echo(f"      ⚠ {inv['note']}")

    if report["fired"]:
        click.echo(
            "⚠ GATILHO DISPAROU — e a decisão que ele destrava NÃO é 'trocar o "
            "default' (i-123 já fez isso). Se foi o `rebuild_p95`: o push-down "
            "do filtro de plane para o `load_all`, já nomeado como follow-up em "
            "`instance_builder.py`. Se foi o `scope_write_ratio`: os Kinds "
            "listados acima ou declaram `plane: record`, ou a porta que os "
            "grava passa a usar `kernel.batch_writes()`."
        )
    if gate and report["fired"]:
        raise SystemExit(1)
