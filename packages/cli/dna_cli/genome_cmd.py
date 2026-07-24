"""``dna genome view`` — the DERIVED view of a scope's Genome.

A Genome (the scope-root manifest) is deliberately minimal: identity, version,
runtime defaults. The module's CONTENTS ("what does it ship?") are not a stored
list on the Genome — they ARE the scope itself, so the answer can never drift.
This command composes the full picture live: the Genome identity + the scope's
contents (copilots/agents/tools/federations) + the tenant LayerPolicy (the Strain
customization contract). Reads through the dna-client, so it works against any
configured source (filesystem or Postgres).
"""
from __future__ import annotations

import click

from dna_cli._ctx import dna_client, fail, print_json, run_async

# (Kind, label) for the "ships" — the module's own contents, enumerated from the
# scope. Add a kind here and it shows up automatically; nothing to keep in sync.
_SHIP_KINDS = [
    ("Copilot", "copilots"),
    ("Agent", "agents"),
    ("Tool", "tools"),
    ("MCPFederation", "federations"),
]


def _items(dna, scope: str, kind: str) -> list:
    body = run_async(dna.docs(scope).list(kind=kind))
    items = body.get("items") if isinstance(body, dict) else body
    return items if isinstance(items, list) else []


def _name_of(it) -> str | None:
    return (it.get("metadata", {}) or {}).get("name") or it.get("name")


def _names(dna, scope: str, kind: str) -> list[str]:
    return sorted(n for it in _items(dna, scope, kind) if (n := _name_of(it)))


def _spec(dna, scope: str, kind: str, name: str) -> dict:
    # `docs.list` returns a lightweight {name, kind}; the spec lives on `docs.get`,
    # which wraps the document under a `raw` key.
    body = run_async(dna.docs(scope).get(kind, name))
    if not isinstance(body, dict):
        return {}
    doc = body.get("raw", body)
    return (doc.get("spec", {}) or {}) if isinstance(doc, dict) else {}


@click.group()
def genome() -> None:
    """The Genome view — a module's identity, contents (ships), and Strain policy."""


@genome.command("view")
@click.argument("scope")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON.")
def view(scope: str, as_json: bool) -> None:
    """Derived view of SCOPE's Genome: identity + ships (the scope's contents) +
    the tenant LayerPolicy. Reads the scope live — no stored list, no drift."""
    with dna_client() as dna:
        try:
            g_items = _items(dna, scope, "Genome")
            g_name = _name_of(g_items[0]) if g_items else None
            g = _spec(dna, scope, "Genome", g_name) if g_name else {}
            ships = {label: _names(dna, scope, kind) for kind, label in _SHIP_KINDS}
            policies: dict[str, dict] = {}
            for it in _items(dna, scope, "LayerPolicy"):
                name = _name_of(it)
                spec = _spec(dna, scope, "LayerPolicy", name) if name else {}
                policies[spec.get("layer_id") or name or "?"] = spec.get("policies", {}) or {}
        except Exception as e:  # noqa: BLE001
            raise fail(f"genome view failed: {e}") from e

    if as_json:
        print_json({"scope": scope, "identity": g, "ships": ships, "policies": policies})
        return

    echo = click.echo
    bar = "═" * 60
    echo(bar)
    echo(f"  GENOME VIEW — {scope}   (derived live from the scope)")
    echo(bar)
    echo(f"  identity : {scope}   ·   v{g.get('version', '—')}   ·   {g.get('visibility', '—')}")
    echo(f"  defaults : agent = {g.get('default_agent', '—')}")
    echo(f"  tags     : {', '.join(g.get('tags') or []) or '—'}")
    echo("")
    echo("  SHIPS — the module's contents ARE the scope (no stored list = no drift)")
    for _, label in _SHIP_KINDS:
        n = ships[label]
        echo(f"    {label:12} ({len(n)})  {', '.join(n) or '—'}")
    echo("")
    echo("  STRAIN CONTRACT — the tenant LayerPolicy (what an overlay may touch)")
    any_pol = False
    for _layer, p in policies.items():
        for alias, pol in sorted(p.items(), key=lambda x: (x[1] != "open", x[0])):
            any_pol = True
            mark = "OPEN    tenant may overlay" if pol == "open" else "LOCKED  pinned (infra/identity)"
            echo(f"    {alias:16}  {mark}")
    if not any_pol:
        echo("    (no LayerPolicy in scope)")
    echo(bar)
    echo("  reading: base(Genome) + tenant overlay → composed by resolve_layers({tenant})")
