"""``dna explain`` — show WHERE each part of a composed prompt comes from.

Provenance is the DNA's most defensible differentiator: ``build_prompt``
renders a flat string, but explain mode ALSO returns the section→artifact map
the composition knows internally. ``dna explain <agent>`` prints that map as a
table — one row per composed section (the agent instruction, its Soul, each
Skill, each Guardrail) with its source file, content hash, version, and the
layer/overlay origin the section resolved from.

    dna explain <agent> [--scope S] [--tenant T] [--json]

A tenant that overlays a section is flagged ``OVERRIDDEN by tenant overlay`` —
so a per-tenant customization is visible without diffing artifacts. The
composed prompt is byte-identical to ``dna emit`` / ``build_prompt``; explain
never re-renders (see ``PromptBuilder.explain``).
"""
from __future__ import annotations

import click

from dna_cli._ctx import dna_session, fail, print_json


@click.command("explain", help="Show per-section provenance for a composed agent prompt.")
@click.argument("agent", required=False)
@click.option("--scope", default=None, help="Scope holding the agent (default: env / sole scope).")
@click.option("--tenant", default=None, help="Resolve with this tenant's overlays (marks overridden sections).")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output (prompt + provenance).")
@click.option("--show-prompt", is_flag=True, help="Also print the composed prompt below the table.")
def explain(agent, scope, tenant, as_json, show_prompt):
    """Explain how AGENT's system prompt is composed — section by section.

    \b
    Examples:
      dna explain swe-agent
      dna explain concierge --scope support --tenant acme
      dna explain triage --json
    """
    import os

    if not agent:
        raise fail("missing AGENT argument")
    effective_tenant = tenant if tenant is not None else (os.getenv("DNA_TENANT") or None)

    with dna_session(scope) as s:
        kernel = s.kernel.with_tenant(effective_tenant) if effective_tenant else s.kernel
        mi = kernel.instance(s.scope) if effective_tenant else s.mi
        try:
            explanation = mi.explain_prompt(agent, tenant=effective_tenant)
        except Exception as e:  # noqa: BLE001 — surface a clean CLI error
            raise fail(f"explain failed: {e}") from None

    if as_json:
        print_json({
            "agent": agent,
            "scope": s.scope,
            "tenant": effective_tenant,
            **explanation.serialize(),
        })
        return

    click.secho(f"Prompt provenance — {agent} (scope: {s.scope}" +
                (f", tenant: {effective_tenant}" if effective_tenant else "") + ")",
                fg="cyan", bold=True)
    rows = []
    for sec in explanation.sections:
        origin = sec.origin
        if sec.is_inherited:
            origin = f"{origin} (inherited)"
        rows.append({
            "section": sec.section,
            "source file": sec.source,
            "hash": (sec.hash or "-")[:12],
            "version": sec.version or "-",
            "origin": origin,
        })
    _print_provenance_table(rows)

    # Tenant-overlay markers — called out on their own line so they stand out.
    overridden = [sec for sec in explanation.sections if sec.overridden_by_tenant]
    if overridden:
        click.echo()
        for sec in overridden:
            click.secho(f"  ⚠ {sec.section}: OVERRIDDEN by tenant overlay", fg="yellow")

    if show_prompt:
        click.echo()
        click.secho("# composed prompt (byte-identical to build_prompt):", fg="green", err=True)
        click.echo(explanation.prompt)


def _print_provenance_table(rows: list[dict]) -> None:
    """Borderless aligned table — mirrors the prior spike's output shape."""
    columns = ["section", "source file", "hash", "version", "origin"]
    if not rows:
        click.echo("(no composed sections)", err=True)
        return
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows)) for c in columns}
    header = "  ".join(c.ljust(widths[c]) for c in columns)
    click.secho(header, bold=True)
    click.echo("  ".join("-" * widths[c] for c in columns))
    for r in rows:
        click.echo("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in columns))
