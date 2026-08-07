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
    default=None,
    help="Scope to enumerate kinds from (default: env / sole scope).",
)
@click.option("--tenant", default=None, help="Route as this tenant.")
def list_kinds(as_json: bool, scope: str | None, tenant: str | None) -> None:
    """List all Kinds registered on the kernel (in the given scope)."""
    with dna_client(tenant=tenant) as dna:
        scope = scope or dna.default_scope
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
    default=None,
    help="Scope to look up the Kind in (default: env / sole scope).",
)
@click.option("--tenant", default=None, help="Route as this tenant.")
def describe(kind_name: str, scope: str | None, tenant: str | None) -> None:
    """Show the JSON Schema + storage descriptor for a Kind."""
    with dna_client(tenant=tenant) as dna:
        scope = scope or dna.default_scope
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


@kind.command("traits")
@click.option("--json", "as_json", is_flag=True, help="JSON output.")
@click.option("--trait", "one", default=None,
              help="Show only which Kinds declare this trait.")
def traits(as_json: bool, one: str | None) -> None:
    """List the TRAITS Kinds declare, and which Kinds carry each.

    A trait answers "does this Kind take part in X?" for an X the kernel has no
    opinion about — ``sdlc.work-item``, ``memory.recallable``,
    ``record.append-only``. Consumers ask ``kernel.kinds_with_trait(name)``
    instead of carrying a literal Kind-name list, so adding a Kind to a family is
    a declaration rather than an edit everywhere that family is consulted.

    The vocabulary is OPEN: a trait no extension registered a description for is
    still perfectly legal and still shows up here (with an empty description),
    because an extension that ships a Kind and its one consumer must not have to
    patch a core enum. Registration buys documentation, never a veto.

    Reads the LOCAL kernel registry — traits are a property of the registered
    Kinds, not of any scope's instances.
    """
    from dna.kernel import Kernel
    from dna.kernel.kinds.traits import known_traits, port_traits

    kernel = Kernel.auto()
    declared: dict[str, list[str]] = {}
    for port in kernel.kind_ports():
        for trait in port_traits(port):
            declared.setdefault(trait, []).append(getattr(port, "kind", "?"))
    descriptions = known_traits()

    names = sorted(set(declared) | set(descriptions))
    if one:
        names = [n for n in names if n == one]
        if not names:
            raise fail(
                f"no trait named {one!r} — neither declared by a Kind nor "
                f"registered. Known: {', '.join(sorted(set(declared) | set(descriptions)))}"
            )
    rows = [
        {
            "trait": n,
            "kinds": ", ".join(sorted(declared.get(n, []))) or "(none)",
            "count": len(declared.get(n, [])),
            "description": descriptions.get(n, "(undocumented — legal, see `dna kind traits`)"),
        }
        for n in names
    ]
    if as_json:
        print_json(rows)
    else:
        print_table(rows, ["trait", "count", "kinds"])
