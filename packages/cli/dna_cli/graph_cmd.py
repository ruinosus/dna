"""``dna graph`` — the DERIVED reference graph: backfill it, ask it.

The producer writes an edge every time an instance is saved, inside the save's
own transaction. Everything written BEFORE the producer existed therefore has
no edges, and this is the command that fixes that — explicitly, from the same
``spec.relations`` declaration the producer reads, never from a scan that guesses at
slug prefixes (the mechanism i-039 refused, and the reason ``dna_edges`` was
dropped the first time).

``backfill`` is idempotent (the same DELETE+INSERT per instance the producer
uses) and runnable COLD: nothing in it needs the write path to be warm.

⚠️ Naming: ``dna_cli.graph`` is the Microsoft Graph OBO adapter, an unrelated
package that happens to share the English word. This module is ``graph_cmd``
like every other command module, and the two never meet.
"""
from __future__ import annotations

import click

from dna_cli._ctx import fail, open_session, print_json


@click.group("graph", help="The derived reference graph (declared relations).")
def graph() -> None:
    """Group root."""


@graph.command("backfill")
@click.option("--scope", default=None,
              help="Only this scope (default: every scope in the store).")
@click.option("--dry-run", is_flag=True,
              help="Resolve everything, write nothing — same reads, real numbers.")
@click.option("--json", "as_json", is_flag=True)
def backfill(scope: str | None, dry_run: bool, as_json: bool) -> None:
    """Compute edges for instances that predate the producer.

    For each declared ``(Kind, field)`` pair, ask the store for the instances
    whose ``spec`` HAS that field — on Postgres a JSONB key-existence query the
    ``dna_insts_spec_gin_idx`` index serves directly. That is a handful of
    queries, not a walk over every instance.

    An instance whose references cannot be resolved COMPLETELY (a read failed
    part-way) is left alone and its scope is reported as pending: a partial
    edge set stored as if it were whole is a graph that lies while looking
    finished, and the screen can label an absent graph but not a lying one.
    """
    from dna.kernel.query.backfill import backfill_edges
    from dna.kernel.query.graph import GraphUnsupported

    with open_session(scope) as s:
        try:
            report = s.run(
                backfill_edges(s.kernel, scope=scope, dry_run=dry_run)
            )
        except GraphUnsupported as exc:
            fail(str(exc))
            return
    if as_json:
        print_json(report.as_dict())
        return
    verb = "would write" if dry_run else "wrote"
    click.echo(
        f"{report.pairs} declared (Kind, field) pair(s) · "
        f"{report.instances} instance(s) · {verb} {report.edges} edge(s), "
        f"{report.dangling} dangling"
    )
    if report.skipped:
        # Loud on purpose: this is the number that says the graph is INCOMPLETE,
        # and an incomplete graph reported as a finished one is the whole defect
        # this degree exists to avoid.
        click.echo(
            f"⚠ {report.skipped} instance(s) left unresolved in "
            f"{', '.join(sorted(report.pending))} — their edges were NOT "
            f"replaced. Re-run once the store is healthy."
        )


@graph.command("refs")
@click.argument("kind_name")
@click.argument("name")
@click.option("--scope", default=None)
@click.option("--tenant", default=None)
@click.option("--direction", type=click.Choice(["in", "out", "both"]),
              default="in", show_default=True,
              help="'in' = what points AT this instance (the product question).")
@click.option("--depth", default=1, show_default=True,
              help="Walk further; clamped by DNA_GRAPH_MAX_DEPTH.")
@click.option("--as-of", "as_of", default=None,
              help="O grafo COMO ELE ERA nesse instante (ISO-8601, tempo de "
                   "TRANSAÇÃO). Re-derivado das versões — não é o grafo de "
                   "hoje filtrado.")
@click.option("--json", "as_json", is_flag=True)
def refs(
    kind_name: str, name: str, scope: str | None, tenant: str | None,
    direction: str, depth: int, as_of: str | None, as_json: bool,
) -> None:
    """"What points at this instance?" — the same walk the REST face serves."""
    from dna.kernel.query.graph import GraphUnsupported
    from dna.memory.as_of import (
        AsOfTruncated,
        AsOfUnsupported,
        normalize_as_of,
    )

    with open_session(scope) as s:
        try:
            # Normalized HERE and not in the kernel, so ``--as-of 2026-08-01``
            # means the same instant on this face as on the other two. A face
            # formatting its own would be the second reading of one word.
            instant = None if as_of is None else normalize_as_of(as_of)
            result = s.run(s.kernel.graph_refs(
                s.scope, kind_name, name,
                tenant=tenant, direction=direction, depth=depth,
                as_of=instant,
            ))
        except (GraphUnsupported, AsOfUnsupported, AsOfTruncated) as exc:
            # The three refusals, BY NAME and never as an empty walk. The last
            # one above all: "the record of that era was pruned" printed as "no
            # edges recorded" is the confident lie this axis exists to refuse.
            fail(f"{type(exc).__name__}: {exc}")
            return
        except (LookupError, ValueError) as exc:
            # "It did not exist yet at that instant" (an ANSWER), or an
            # ``--as-of`` that is not an ISO-8601 instant.
            fail(str(exc))
            return
    if as_json:
        print_json({
            "direction": result.direction, "depth": result.depth,
            "stop": result.stop, "graph_producer": result.graph_producer,
            "as_of": result.as_of,
            "as_of_truncated": list(result.as_of_truncated),
            "edges": result.edges,
        })
        return
    if result.as_of_truncated:
        # BEFORE the edges, deliberately: a reader who sees this first reads
        # the list below as partial. After it, they have already read it whole.
        click.echo(
            f"⚠ {len(result.as_of_truncated)} nó(s) alcançado(s) cuja história "
            f"não chega a {result.as_of} — o que eles diziam então não é "
            f"sabível: {', '.join(result.as_of_truncated)}"
        )
    if not result.edges:
        # Never a bare "none": the reader must be able to tell "nothing points
        # at it" from "the producer is off and nothing was ever recorded".
        click.echo(
            f"no edges recorded (producer: {result.graph_producer}, "
            f"stop: {result.stop})"
        )
        return
    for e in result.edges:
        # i-131 — as duas metades de "não resolve" não são o mesmo problema
        # nem têm o mesmo dono. `dangling` acusa quem AUTOROU (um nome que
        # nunca existiu); `alvo apagado` acusa um DELETE que passou por cima
        # de uma referência viva. Imprimir a mesma palavra para as duas é como
        # "47 Stories perderam a Feature" virar "47 Stories têm erro de
        # digitação".
        if e["resolved"]:
            mark = ""
        elif e.get("to_deleted_at"):
            mark = f"  ⚠ alvo apagado em {e['to_deleted_at']}"
        else:
            mark = "  ⚠ dangling"
        click.echo(
            f"[{e['depth']}] {e['from_kind']}/{e['from_name']}"
            f" --{e['source_field']}[{e['ordinal']}]--> "
            f"{e['to_kind'] or '?'}/{e['to_name']}{mark}"
        )
    click.echo(f"({len(result.edges)} edge(s); stop: {result.stop})")


@graph.command("stats")
@click.argument("logfile", type=click.File("r", encoding="utf-8"), default="-")
@click.option("--json", "as_json", is_flag=True,
              help="O relatório inteiro, para um script.")
@click.option("--gate", is_flag=True,
              help="Sai 1 se algum gatilho disparou (para CI/cron).")
def stats(logfile, as_json: bool, gate: bool) -> None:
    """O GATILHO 2 de `spec-topologia-do-grafo`, lido das linhas de travessia.

    A spec recomendou ficar no Postgres com dois gatilhos MEDIDOS que invertem
    a decisão. Este comando é a porta por onde o de ESCALA vira número: ele lê
    as linhas que `dna.graph.traversal` emite (uma por travessia) e imprime o
    `p95` das travessias profundas, a fração truncada, e se cada limiar foi
    ultrapassado.

    \b
    Ligar o funil:   DNA_GRAPH_TELEMETRY=on   (no serviço que serve a travessia)
    Ler na nuvem:    az containerapp logs show -n ca-dna-api-… --tail 5000 \\
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
    """
    from dna.kernel.query.graph import traversal_stats

    report = traversal_stats(logfile)
    if as_json:
        print_json(report)
    else:
        deep = report["deep"]
        trig = report["triggers"]
        click.echo(
            f"{report['calls']} travessia(s) lidas "
            f"({report['ignored']} linha(s) ignoradas)"
        )
        if not report["calls"]:
            # Nunca um relatório de zeros com cara de "tudo bem": zero chamada
            # lida é o funil desligado ou o arquivo errado, e as duas coisas
            # renderizadas como "não disparou" seriam a mentira mais fácil aqui.
            click.echo(
                "⚠ nenhuma linha de travessia nesta entrada — o funil está "
                "desligado (DNA_GRAPH_TELEMETRY=on no serviço) ou a fonte "
                "está errada. NADA foi medido; isto não é 'não disparou'."
            )
            return
        click.echo(
            f"  p95 geral: {report['p95_ms']:.1f} ms · "
            f"por profundidade: {report['by_depth']}"
        )
        p95 = trig["scale_p95"]
        click.echo(
            f"  [{'DISPAROU' if p95['fired'] else 'ok'}] p95 depth>="
            f"{deep['depth_min']}: {p95['value_ms']:.1f} ms "
            f"(limiar {p95['threshold_ms']:.0f} ms, "
            f"{deep['calls']} chamada(s))"
        )
        worst = report["worst_tenant"]
        if worst:
            click.echo(
                f"      pior balde de tenant: {worst['tenant']} — "
                f"{worst['p95_ms']:.1f} ms em {worst['calls']} chamada(s)"
            )
        tr = trig["scale_truncated"]
        click.echo(
            f"  [{'DISPAROU' if tr['fired'] else 'ok'}] truncadas: "
            f"{report['truncated']}/{report['calls']} = "
            f"{tr['value'] * 100:.2f}% (limiar "
            f"{tr['threshold'] * 100:.0f}%)"
        )
        if report["fired"]:
            click.echo(
                "⚠ GATILHO 2 DISPAROU — spec-topologia-do-grafo §10 já nomeia "
                "a porta: Apache AGE, no mesmo Postgres, US$ 0,00 marginal. "
                "A fatia 6 (o SPIKE de três números) é o próximo passo."
            )
    if gate and report["fired"]:
        raise SystemExit(1)
