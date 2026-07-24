"""``dna definition`` — read/customize a tenant's definition override.

A tenant overlays an inherited definition (agent/copilot/tool/...) by writing a
copy-on-write override into its workspace scope — the Strain mutation. `get`
shows the effective (composed) spec vs the base; `set` writes the override
(vetoed by LayerPolicy for locked Kinds / non-overlayable fields — the veto
propagates as an error, not a silent no-op); `revert` removes it. Reads through
the dna-client, so it works against any configured source (filesystem or
Postgres).
"""
from __future__ import annotations

import json

import click
import yaml

from dna_cli._ctx import dna_client, fail, print_json, run_async


@click.group()
def definition() -> None:
    """Read and customize a tenant's definition overrides (the Strain)."""


@definition.command("get")
@click.argument("kind")
@click.argument("name")
@click.option("--scope", default=None, help="Scope to read KIND/NAME from.")
@click.option("--tenant", default=None, help="Read as this tenant's overlay (overrides DNA_TENANT).")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON.")
def get(kind: str, name: str, scope: str | None, tenant: str | None, as_json: bool) -> None:
    """Show KIND/NAME as the tenant sees it: effective vs base + overridden flag."""
    with dna_client() as dna:
        try:
            body = run_async(dna.read_definition(kind, name, scope=scope, tenant=tenant))
        except Exception as exc:  # noqa: BLE001 — surface a clean message, not a traceback
            raise fail(f"read failed: {exc}") from exc
    if as_json:
        print_json(body)
        return
    click.echo(f"{kind}/{name}  overridden={body.get('overridden')}")
    click.echo(f"  effective: {json.dumps(body.get('effective', {}), ensure_ascii=False)}")
    click.echo(f"  base:      {json.dumps(body.get('base'), ensure_ascii=False)}")


@definition.command("set")
@click.argument("kind")
@click.argument("name")
@click.option("--file", "spec_file", required=True, type=click.File("r"),
              help="YAML/JSON file whose top-level `spec:` (or the whole doc) is the override spec.")
@click.option("--scope", default=None, help="Scope to write the override into.")
@click.option("--tenant", required=True, help="Write as this tenant's overlay.")
def set_(kind: str, name: str, spec_file, scope: str | None, tenant: str) -> None:
    """Write the tenant override for KIND/NAME from a spec file."""
    loaded = yaml.safe_load(spec_file.read()) or {}
    spec = loaded.get("spec", loaded) if isinstance(loaded, dict) else loaded
    with dna_client() as dna:
        try:
            body = run_async(dna.apply_definition(kind, name, spec, scope=scope, tenant=tenant))
        except Exception as exc:  # noqa: BLE001 — surface the LayerPolicy veto verbatim
            raise fail(f"write rejected: {exc}") from exc
    print_json(body)


@definition.command("revert")
@click.argument("kind")
@click.argument("name")
@click.option("--scope", default=None, help="Scope to remove the override from.")
@click.option("--tenant", required=True, help="Revert this tenant's overlay.")
def revert(kind: str, name: str, scope: str | None, tenant: str) -> None:
    """Remove the tenant override for KIND/NAME → reads fall back to the base."""
    with dna_client() as dna:
        try:
            body = run_async(dna.revert_definition(kind, name, scope=scope, tenant=tenant))
        except Exception as exc:  # noqa: BLE001 — surface a clean message, not a traceback
            raise fail(f"revert failed: {exc}") from exc
    print_json(body)
