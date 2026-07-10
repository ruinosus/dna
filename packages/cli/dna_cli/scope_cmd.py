"""``dna scope`` — list scopes + dump scope inventory."""
from __future__ import annotations

import sys

import click

from dna_cli._ctx import get_holder, print_json, print_table


@click.group("scope", help="List + inspect scopes (manifest modules).")
def scope() -> None:
    """Group root."""


@scope.command("list")
@click.option("--json", "as_json", is_flag=True)
@click.option("--tenant", default=None, help="Route as this tenant (overrides DNA_TENANT).")
def list_scopes(as_json: bool, tenant: str | None) -> None:
    """List discoverable scopes from the configured source.

    Uses dna-client (HTTP to kinds-api) instead of building a local
    kernel — avoids the asyncpg "task attached to different loop"
    error that happens when a click-sync entrypoint calls
    kernel.list_scopes_async() against a holder built in a different
    event loop.
    """
    from dna_cli._ctx import dna_client, run_async

    with dna_client(tenant=tenant) as dna:
        try:
            scopes = run_async(dna.scopes.list())
        except Exception as e:  # noqa: BLE001
            click.secho(f"scopes.list failed: {e}", err=True, fg="red")
            raise click.exceptions.Exit(1) from e
    # API normalizes shape — accept list[str] OR list[dict] OR {"scopes": [...]}
    if isinstance(scopes, dict):
        scopes = scopes.get("scopes") or list(scopes.keys())
    names = [s if isinstance(s, str) else s.get("scope") or s.get("name") for s in scopes]
    rows = [{"scope": n} for n in names if n]
    if as_json:
        print_json(rows)
    else:
        print_table(rows, ["scope"])


@scope.command("tree")
@click.argument("scope_name", required=False)
@click.option("--json", "as_json", is_flag=True)
@click.option("--tenant", default=None, help="Route as this tenant (overrides DNA_TENANT).")
def tree(scope_name: str | None, as_json: bool, tenant: str | None) -> None:
    """Inventory all documents in a scope, grouped by Kind.

    Migrated to dna-client (HTTP /scopes/{X}/tree) so it doesn't need
    DNA_SOURCE_URL set in the CLI's own env — the kinds-api already
    has the kernel and serves the snapshot.
    """
    from dna_cli._ctx import dna_client, run_async

    target = scope_name or "dna-development"
    with dna_client(tenant=tenant) as dna:
        try:
            by_kind = run_async(dna.scopes.tree(target))
        except Exception as e:  # noqa: BLE001
            click.secho(f"scopes.tree failed: {e}", err=True, fg="red")
            raise click.exceptions.Exit(1) from e

    # API returns {Kind: [{name, ...}, ...]} — normalize to {Kind: [name, ...]}
    normalized: dict[str, list[str]] = {}
    if isinstance(by_kind, dict):
        for k, v in by_kind.items():
            if isinstance(v, list):
                names = [
                    item if isinstance(item, str) else (item.get("name") or "?")
                    for item in v
                ]
                normalized[k] = sorted(names)

    if as_json:
        print_json(normalized)
        return
    for k in sorted(normalized):
        click.secho(f"\n{k}", fg="cyan", bold=True)
        for name in normalized[k]:
            click.echo(f"  • {name}")


@scope.command("detect")
@click.option("--cwd", default=None, help="Override starting directory (default: CWD).")
def detect_scope(cwd: str | None) -> None:
    """Walk upward from cwd looking for the nearest .dna/<scope>/Genome.yaml.

    Phase 14u — used by the Claude Code PreToolUse hook to auto-inject
    scope context. Prints the scope name to stdout (no decorations) so
    shell scripts can capture it via $(dna scope detect).

    Genome.yaml is the canonical scope-root marker (Phase 16); the legacy
    pre-Genome manifest.yaml is still accepted (i-007) — same dual-marker
    contract as `dna install` and the composite source.
    """
    from pathlib import Path

    def _detect(start):
        # Walk upward looking for `.dna/<scope>/Genome.yaml` (canonical)
        # or the legacy `.dna/<scope>/manifest.yaml`, max 6 levels.
        here = (start or Path.cwd()).resolve()
        for _ in range(6):
            dna = here / ".dna"
            if dna.is_dir():
                for child in sorted(dna.iterdir()):
                    if child.is_dir() and (
                        (child / "Genome.yaml").is_file()
                        or (child / "manifest.yaml").is_file()
                    ):
                        return child.name
            if here.parent == here:
                break
            here = here.parent
        return None

    name = _detect(Path(cwd).resolve() if cwd else None)
    if not name:
        click.secho("(no DNA scope found)", err=True, fg="yellow")
        raise click.exceptions.Exit(1)
    click.echo(name)


# (scope export/import/reindex — the portable scope-bundle engine —
# live in the host platform's infra package and do not ship here.)
