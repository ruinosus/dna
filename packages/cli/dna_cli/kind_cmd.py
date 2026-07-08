"""``dna kind`` — list and inspect Kinds registered on the kernel.

Migrated to dna-client (Phase F9 follow-up). Uses /kernel/kinds (global)
and /scopes/{X}/kinds/{kind}/schema (per-scope) instead of touching
the local kernel.
"""
from __future__ import annotations

import click

from dna_cli._ctx import dna_client, fail, print_json, print_table, run_async


@click.group("kind", help="List + inspect registered Kinds.")
def kind() -> None:
    """Group root."""


@kind.command("list")
@click.option("--json", "as_json", is_flag=True, help="JSON output.")
@click.option(
    "--scope",
    default="dna-development",
    show_default=True,
    help="Scope to enumerate kinds from.",
)
@click.option("--tenant", default=None, help="Route as this tenant.")
def list_kinds(as_json: bool, scope: str, tenant: str | None) -> None:
    """List all Kinds registered on the kernel (in the given scope)."""
    with dna_client(tenant=tenant) as dna:
        try:
            body = run_async(dna.scopes.kinds(scope))
        except Exception as e:  # noqa: BLE001
            raise fail(f"scopes.kinds failed: {e}") from e
    # /scopes/{X}/kinds returns {KindName: [doc names…], ...} — keys
    # are the registered kinds. Tabular view emits one row per key;
    # we don't have the per-kind metadata (alias/api_version/is_root)
    # cheaply from this endpoint (would need /scopes/{X}/kinds/{kind}/schema
    # per-kind, expensive on N=60+). For full descriptor of one kind,
    # use `dna kind describe <KindName>`.
    if isinstance(body, dict):
        kinds_list = sorted(body.keys())
    elif isinstance(body, list):
        kinds_list = [it if isinstance(it, str) else (it.get("kind") if isinstance(it, dict) else "?") for it in body]
    else:
        kinds_list = []
    rows = [
        {
            "kind": k,
            "alias": "(use describe)",
            "api_version": "(use describe)",
            "is_root": "",
            "is_prompt_target": "",
        }
        for k in kinds_list
    ]
    rows.sort(key=lambda r: r["kind"])
    if as_json:
        print_json(rows)
    else:
        print_table(rows, ["kind", "alias", "api_version", "is_root", "is_prompt_target"])


@kind.command("describe")
@click.argument("kind_name")
@click.option(
    "--scope",
    default="dna-development",
    show_default=True,
)
@click.option("--tenant", default=None, help="Route as this tenant.")
def describe(kind_name: str, scope: str, tenant: str | None) -> None:
    """Show the JSON Schema + storage descriptor for a Kind."""
    with dna_client(tenant=tenant) as dna:
        try:
            descriptor = run_async(dna.scopes.kind_schema(scope, kind_name))
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "404" in msg or "not found" in msg.lower():
                raise fail(f"Kind '{kind_name}' not registered in scope '{scope}'.") from e
            raise fail(f"kind_schema failed: {e}") from e
    # Descriptor: {kind, alias, api_version, display_label, schema,
    #              dep_filters, is_runtime_artifact, is_root, ...}
    print_json(descriptor)
