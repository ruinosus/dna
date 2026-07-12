"""``dna intel`` — run the intelligence pipeline + inspect its output.

A THIN face (adr-faces-reorg: logic in the CORE, faces thin). Every command
parses args, opens a kernel session, DELEGATES to the transport-agnostic core
engine (``dna.extensions.intel.engine``), and formats the result. No business
logic lives here.

    dna intel sources                 # list watched IntelSource docs
    dna intel run copiloto-medico     # pass → rank → suppress → deliver
    dna intel list [--state new]      # list produced IntelInsight docs
    dna intel metrics                 # feedback KPIs (precision / noise rate)

The intel Kinds are TENANTED (per-tenant watchlist + insight stream), so a
tenant is required. ``--tenant`` defaults to ``DNA_TENANT`` env, else the
example tenant ``demo`` (the seeded source lives there) — so
``dna intel run copiloto-medico`` works out of the box.
"""
from __future__ import annotations

import os

import click

from dna.extensions.intel import engine
from dna.extensions.intel.analyzer import select_analyzer
from dna_cli._ctx import dna_session, fail, print_json

DEFAULT_TENANT = "demo"


def _tenant(opt: str | None) -> str:
    return opt or os.getenv("DNA_TENANT") or DEFAULT_TENANT


@click.group(name="intel")
def intel() -> None:
    """Portfolio intelligence — run passes, inspect sources + insights."""


@intel.command("sources")
@click.option("--scope", default=engine.DEFAULT_SCOPE, show_default=True)
@click.option("--tenant", default=None, help=f"Tenant (default: $DNA_TENANT or {DEFAULT_TENANT!r}).")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def cmd_sources(scope: str, tenant: str | None, as_json: bool) -> None:
    """List the watched IntelSource docs (the Direction stage)."""
    t = _tenant(tenant)
    with dna_session(scope) as s:
        rows = s.run(engine.list_sources(s.kernel, scope=s.scope, tenant=t))
    if as_json:
        print_json(rows)
        return
    if not rows:
        click.echo(f"(no IntelSource docs in {scope} for tenant={t})")
        return
    click.echo(f"{'name':24s} {'type':8s} {'cadence':8s} {'thr':>4s}  pirs")
    click.echo("-" * 72)
    for r in rows:
        muted = "  🔇" if r["muted"] else ""
        click.echo(
            f"{r['name']:24s} {(r['type'] or ''):8s} {r['cadence']:8s} "
            f"{r['threshold']:4.2f}  {', '.join(r['pirs'])}{muted}"
        )


@intel.command("run")
@click.argument("source")
@click.option("--scope", default=engine.DEFAULT_SCOPE, show_default=True)
@click.option("--tenant", default=None, help=f"Tenant (default: $DNA_TENANT or {DEFAULT_TENANT!r}).")
@click.option(
    "--analyzer",
    type=click.Choice(["auto", "llm", "seed"]),
    default="auto",
    show_default=True,
    help=(
        "Which analyzer runs the pass: 'llm' researches the source live via the "
        "LLM, 'seed' uses the offline curated insights, 'auto' picks the LLM when "
        "OPENAI_API_KEY is set (else seed)."
    ),
)
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def cmd_run(
    source: str, scope: str, tenant: str | None, analyzer: str, as_json: bool,
) -> None:
    """Run one intel pass over SOURCE: pass → rank → suppress → deliver.

    Writes the surviving insights as IntelInsight docs (state=new) and prints
    what was KEPT vs SUPPRESSED (below the source threshold — the anti-noise
    core). ``--analyzer auto`` (default) researches the source live via the LLM
    when OPENAI_API_KEY is set and falls back to the offline SeedAnalyzer (real
    experiment insights, no creds) otherwise; force either with ``llm``/``seed``.
    """
    t = _tenant(tenant)
    chosen = select_analyzer(analyzer)
    with dna_session(scope) as s:
        try:
            result = s.run(engine.run_pass(
                s.kernel, source, scope=s.scope, tenant=t, analyzer=chosen,
            ))
        except LookupError as exc:
            raise fail(str(exc))
    if as_json:
        print_json(result.to_dict())
        return
    click.secho(
        f"\n📡 intel pass — {source} (scope={result.scope}, tenant={t}, "
        f"analyzer={result.analyzer})",
        bold=True,
    )
    click.secho(
        f"\n  ✅ delivered {result.kept_count} · 🔇 suppressed {result.suppressed_count}"
        f" · ♻️  deduped {result.deduped_count}",
        bold=True,
    )
    if result.deduped:
        click.secho("\n  Deduped (already surfaced — not re-delivered):", fg="cyan")
        for d in result.deduped:
            click.echo(f"    [{d['score']:.2f}] {d['title']}  ({d['reason']}, cos {d['cosine']:.2f})")
    if result.kept:
        click.secho("\n  Delivered insights:", fg="green")
        for k in result.kept:
            click.echo(f"    [{k['score']:.2f}] {k['title']}")
            if k.get("action"):
                click.echo(f"           → {k['action']}")
            click.echo(f"           {k['name']}")
    if result.suppressed:
        click.secho("\n  Suppressed (below threshold — not delivered):", fg="yellow")
        for sup in result.suppressed:
            click.echo(f"    [{sup['score']:.2f}] {sup['title']}")
            click.echo(f"           {sup['rationale']}")
    click.echo()


@intel.command("list")
@click.option("--scope", default=engine.DEFAULT_SCOPE, show_default=True)
@click.option("--tenant", default=None, help=f"Tenant (default: $DNA_TENANT or {DEFAULT_TENANT!r}).")
@click.option("--state", type=click.Choice(list(engine.VALID_STATES)), default=None)
@click.option("--source", "source_ref", default=None, help="Filter by originating IntelSource.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def cmd_list(
    scope: str, tenant: str | None, state: str | None, source_ref: str | None,
    as_json: bool,
) -> None:
    """List produced IntelInsight docs (ranked, feedback state)."""
    t = _tenant(tenant)
    with dna_session(scope) as s:
        rows = s.run(engine.list_insights(
            s.kernel, scope=s.scope, tenant=t, state=state, source_ref=source_ref,
        ))
    if as_json:
        print_json(rows)
        return
    if not rows:
        click.echo(f"(no IntelInsight docs in {scope} for tenant={t})")
        return
    click.echo(f"{'score':>5s} {'state':10s} {'source':18s}  title")
    click.echo("-" * 90)
    for r in rows:
        click.echo(
            f"{r['score']:5.2f} {r['state']:10s} {(r['source_ref'] or ''):18s}  "
            f"{(r['title'] or '')[:48]}"
        )


@intel.command("metrics")
@click.option("--scope", default=engine.DEFAULT_SCOPE, show_default=True)
@click.option("--tenant", default=None, help=f"Tenant (default: $DNA_TENANT or {DEFAULT_TENANT!r}).")
@click.option("--source", "source_ref", default=None, help="Restrict to one originating IntelSource.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def cmd_metrics(scope: str, tenant: str | None, source_ref: str | None, as_json: bool) -> None:
    """Feedback KPIs — precision (actioned ÷ actioned+dismissed) + noise rate.

    Read-only; delegates the arithmetic to the core ``feedback_metrics``. The
    noise rate is the intel layer's product KPI (it should fall over time as the
    feedback loop tunes the ranker)."""
    t = _tenant(tenant)
    with dna_session(scope) as s:
        m = s.run(engine.feedback_metrics(
            s.kernel, scope=s.scope, tenant=t, source_ref=source_ref,
        ))
    if as_json:
        print_json(m)
        return
    counts = m["counts"]
    click.secho(
        f"\n📊 intel feedback — scope={scope}, tenant={t}"
        + (f", source={source_ref}" if source_ref else ""),
        bold=True,
    )
    click.echo(
        "  delivered: "
        + " · ".join(f"{k}={counts.get(k, 0)}" for k in ("new", "actioned", "dismissed", "snoozed"))
    )
    prec = m["precision"]
    noise = m["noise_rate"]
    click.echo(
        f"  precision: {prec:.2%}" if prec is not None else "  precision: — (no feedback yet)"
    )
    click.echo(
        f"  noise rate: {noise:.2%}  (the product KPI — should fall over time)"
        if noise is not None else "  noise rate: — (no feedback yet)"
    )
    click.echo()
