"""``dna source`` — declarative source replicas + introspection.

Operates on ``<repo>/.dna-replicas.yaml`` (auto-discovered via upward
walk from cwd, just like git locates ``.gitignore``). The CLI never
touches the kernel directly: it only edits the YAML file. The harness
reads the file at boot and registers the post_save/post_delete
subscribers (host platforms wire the replica engine at boot).

Subcommands::

    dna source replica add <id> --replica fs://./examples \\
        --scopes dna-development [--kinds Story,Feature]
    dna source replica list
    dna source replica show <id>
    dna source replica drop <id>
    dna source replica enable <id>
    dna source replica disable <id>

Phase 1 only supports ``fs://`` / ``file://`` replica URLs. ``sqlite://``
and ``postgres://`` destinations are roadmapped (the engine already
accepts any WritableSourcePort; the CLI just gates the URL until the
async-init plumbing for non-FS schemes lands).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import click

from dna_cli._ctx import fail, print_json, print_table

CONFIG_FILENAME = ".dna-replicas.yaml"


# ─── Config rw helpers ────────────────────────────────────────────────


def _find_config(start: Path | None = None) -> Path | None:
    """Walk upward from cwd looking for ``.dna-replicas.yaml``."""
    cur = (start or Path.cwd()).resolve()
    for _ in range(20):
        candidate = cur / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        if cur.parent == cur:
            return None
        cur = cur.parent
    return None


def _default_config_path() -> Path:
    """Where ``add`` writes when no config exists yet — at cwd."""
    return Path.cwd() / CONFIG_FILENAME


def _load_or_init(path: Path) -> dict[str, Any]:
    import yaml
    if not path.exists():
        return {
            "apiVersion": "dna.io/v1",
            "kind": "ReplicaConfig",
            "replicas": [],
        }
    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise click.ClickException(f"{path}: top-level must be a mapping")
    raw.setdefault("apiVersion", "dna.io/v1")
    raw.setdefault("kind", "ReplicaConfig")
    raw.setdefault("replicas", [])
    if not isinstance(raw["replicas"], list):
        raise click.ClickException(f"{path}: 'replicas' must be a list")
    return raw


def _save(path: Path, cfg: dict[str, Any]) -> None:
    import yaml
    path.write_text(yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False))


def _entry_index(cfg: dict[str, Any], replica_id: str) -> int:
    for i, e in enumerate(cfg["replicas"]):
        if isinstance(e, dict) and e.get("id") == replica_id:
            return i
    return -1


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    scheme = parsed.scheme or "file"
    if scheme not in ("file", "fs"):
        raise click.ClickException(
            f"unsupported replica scheme '{scheme}://' — Phase 1 supports "
            f"fs:// or file:// only. (sqlite:// / postgres:// are roadmapped.)"
        )


def _resolve_url_to_path(url: str, cfg_dir: Path) -> Path:
    parsed = urlparse(url)
    raw = parsed.netloc + parsed.path if parsed.netloc else parsed.path
    p = Path(raw)
    return p if p.is_absolute() else (cfg_dir / p).resolve()


# ─── Click group ──────────────────────────────────────────────────────


@click.group(help="Source-level operations: declarative replicas, introspection.")
def source() -> None:
    """Top-level ``dna source`` group."""


@source.command("diff")
@click.argument("other_url")
@click.option("--scope", required=True, help="Scope to compare.")
@click.option("--tenant", default=None, help="Tenant layer (default: base).")
@click.option(
    "--authored-only", is_flag=True,
    help="Skip runtime-generated Kinds (EvalRun, Narrative, …) — compare only "
    "authored docs (the FS git source-of-truth class).",
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
def diff(
    other_url: str, scope: str, tenant: str | None,
    authored_only: bool, as_json: bool,
) -> None:
    """s-sync-s4 — semantic diff of a scope between the CURRENT source
    (DNA_SOURCE_URL) and OTHER_URL (e.g. file://./scopes or a postgres URL).

    Compares Kind-aware content digests (not raw text), so formatting,
    frontmatter re-serialization and volatile stamps never show as drift.
    Reports added (in current, missing in other), removed (in other only),
    and changed (digest drifted).
    """
    from dna_cli._ctx import dna_session
    from dna.kernel import Kernel
    from dna_cli._ctx import build_source_from_env

    with dna_session(scope) as s:
        kernel = s.kernel
        # authored-only → drop docs whose Kind is a runtime artifact.
        include = None
        if authored_only:
            artifact_kinds = {
                kp.kind for kp in kernel._kinds.values()
                if getattr(kp, "is_runtime_artifact", False)
            }
            include = lambda raw: raw.get("kind") not in artifact_kinds  # noqa: E731

        async def _run() -> dict:
            current = await kernel.digest_manifest(
                scope, tenant=tenant, include=include,
            )
            other_src = await build_source_from_env(
                Kernel.auto(), _source_url=other_url,
            )
            other = await kernel.digest_manifest(
                scope, tenant=tenant, include=include, source=other_src,
            )
            return Kernel.diff_manifests(current, other)

        d = s.run(_run())

    if as_json:
        print_json({k: [f"{kind}/{name}" for kind, name in v] for k, v in d.items()})
        return

    total = sum(len(v) for v in d.values())
    if total == 0:
        click.secho(f"✔ in sync — {scope} matches {other_url} (0 diffs)", fg="green")
        return
    click.secho(
        f"{scope}: {len(d['added'])} added · {len(d['changed'])} changed · "
        f"{len(d['removed'])} removed  (current ↔ {other_url})",
        fg="yellow", bold=True,
    )
    for label, color in (("added", "green"), ("changed", "cyan"), ("removed", "red")):
        for kind, name in d[label]:
            click.secho(f"  {label[0].upper()} {kind}/{name}", fg=color)


@source.command("push")
@click.argument("to_url")
@click.option("--scope", required=True, help="Scope to reconcile.")
@click.option("--tenant", default=None, help="Tenant layer (default: base).")
@click.option(
    "--authored-only", is_flag=True,
    help="Skip runtime-generated Kinds — push only authored docs.",
)
@click.option(
    "--apply", "do_apply", is_flag=True,
    help="Actually write to the target (default: dry-run preview only).",
)
@click.option(
    "--prune", is_flag=True,
    help="Delete docs that exist ONLY in the target (off by default).",
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
def push(
    to_url: str, scope: str, tenant: str | None,
    authored_only: bool, do_apply: bool, prune: bool, as_json: bool,
) -> None:
    """s-sync-s5 — reconcile TO_URL to match the CURRENT source (DNA_SOURCE_URL,
    the source-of-truth) for a scope. Writes added/changed docs atomically
    (doc + bundle via the s-sync-s3 net). Dry-run by default — pass --apply to
    write. --prune also removes docs that exist only in the target.
    """
    from dna_cli._ctx import dna_session
    from dna.kernel import Kernel
    from dna_cli._ctx import build_source_from_env

    with dna_session(scope) as s:
        kernel = s.kernel
        include = None
        if authored_only:
            artifact_kinds = {
                kp.kind for kp in kernel._kinds.values()
                if getattr(kp, "is_runtime_artifact", False)
            }
            include = lambda raw: raw.get("kind") not in artifact_kinds  # noqa: E731

        async def _run() -> dict:
            to_src = await build_source_from_env(
                Kernel.auto(), _source_url=to_url,
            )
            return await kernel.push_scope(
                scope, to_src, tenant=tenant, include=include,
                dry_run=not do_apply, prune=prune,
            )

        out = s.run(_run())

    if as_json:
        print_json({
            k: [f"{kind}/{name}" for kind, name in v] if k != "applied"
            else [f"{op}:{kind}/{name}" for op, kind, name in v]
            for k, v in out.items()
        })
        return

    n_writes = len(out["added"]) + len(out["changed"])
    verb = "would write" if not do_apply else "wrote"
    if n_writes == 0 and (not prune or not out["removed"]):
        click.secho(f"✔ {scope} already in sync with {to_url} (nothing to push)", fg="green")
        return
    head = "DRY-RUN" if not do_apply else "APPLIED"
    click.secho(
        f"[{head}] {scope} → {to_url}: {verb} {n_writes} "
        f"({len(out['added'])} added, {len(out['changed'])} changed)"
        + (f"; prune {len(out['removed'])} removed" if prune else ""),
        fg="yellow", bold=True,
    )
    for kind, name in out["added"]:
        click.secho(f"  + {kind}/{name}", fg="green")
    for kind, name in out["changed"]:
        click.secho(f"  ~ {kind}/{name}", fg="cyan")
    if prune:
        for kind, name in out["removed"]:
            click.secho(f"  - {kind}/{name}", fg="red")
    if not do_apply:
        click.secho("  (dry-run — re-run with --apply to write)", fg="white")


@source.group(help="Manage source replicas (.dna-replicas.yaml).")
def replica() -> None:
    """Replica subgroup."""


# ─── add ──────────────────────────────────────────────────────────────


@replica.command("add")
@click.argument("replica_id")
@click.option("--replica", "replica_url", required=True,
              help="Destination URL (fs://path or file://path).")
@click.option("--scopes", required=True,
              help="Comma-separated scope allowlist (e.g. dna-development).")
@click.option("--kinds", default=None,
              help="Comma-separated Kind allowlist. Omit = all kinds.")
@click.option("--config", "config_path", default=None, type=click.Path(),
              help="Path to .dna-replicas.yaml (default: walk up from cwd, then cwd).")
def add(
    replica_id: str,
    replica_url: str,
    scopes: str,
    kinds: str | None,
    config_path: str | None,
) -> None:
    """Add a new replica entry. Errors on duplicate id."""
    _validate_url(replica_url)
    scope_list = [s.strip() for s in scopes.split(",") if s.strip()]
    if not scope_list:
        raise click.ClickException("--scopes must contain at least one scope")
    kind_list: list[str] | None
    if kinds is None:
        kind_list = None
    else:
        kind_list = [k.strip() for k in kinds.split(",") if k.strip()] or None

    cfg_path = Path(config_path) if config_path else (_find_config() or _default_config_path())
    cfg = _load_or_init(cfg_path)
    if _entry_index(cfg, replica_id) >= 0:
        raise click.ClickException(
            f"replica id '{replica_id}' already exists in {cfg_path}; "
            f"use 'drop' first or pick a different id"
        )

    # Sanity-check the resolved destination dir exists. This mirrors the
    # harness check that warns + skips at boot — surfacing it earlier
    # avoids declaring a replica that silently never fires.
    dest = _resolve_url_to_path(replica_url, cfg_path.parent)
    if not dest.exists():
        click.echo(
            f"warning: replica destination {dest} does not exist; "
            f"create it before booting harness or it will be skipped",
            err=True,
        )

    entry: dict[str, Any] = {
        "id": replica_id,
        "replica": replica_url,
        "scopes": scope_list,
        "kinds": kind_list,
        "enabled": True,
    }
    cfg["replicas"].append(entry)
    _save(cfg_path, cfg)
    click.echo(f"ADDED replica/{replica_id} -> {cfg_path}")


# ─── list ─────────────────────────────────────────────────────────────


@replica.command("list")
@click.option("--config", "config_path", default=None, type=click.Path())
@click.option("--json", "as_json", is_flag=True)
def list_replicas(config_path: str | None, as_json: bool) -> None:
    """List replicas declared in the config file."""
    cfg_path = Path(config_path) if config_path else _find_config()
    if cfg_path is None:
        if as_json:
            print_json([])
        else:
            click.echo("(no .dna-replicas.yaml found)")
        return
    cfg = _load_or_init(cfg_path)
    rows = []
    for e in cfg.get("replicas", []):
        if not isinstance(e, dict):
            continue
        rows.append({
            "id": e.get("id", ""),
            "replica": e.get("replica", ""),
            "scopes": ",".join(e.get("scopes", []) or []),
            "kinds": "all" if not e.get("kinds") else ",".join(e.get("kinds") or []),
            "enabled": "yes" if e.get("enabled", True) else "NO",
        })
    if as_json:
        print_json(rows)
    elif not rows:
        click.echo(f"{cfg_path}: 0 replicas declared")
    else:
        print_table(rows, ["id", "replica", "scopes", "kinds", "enabled"])


# ─── show ─────────────────────────────────────────────────────────────


@replica.command("show")
@click.argument("replica_id")
@click.option("--config", "config_path", default=None, type=click.Path())
def show(replica_id: str, config_path: str | None) -> None:
    """Show full entry for one replica id."""
    cfg_path = Path(config_path) if config_path else _find_config()
    if cfg_path is None:
        raise fail("no .dna-replicas.yaml found in cwd or any parent")
    cfg = _load_or_init(cfg_path)
    idx = _entry_index(cfg, replica_id)
    if idx < 0:
        raise fail(f"replica id '{replica_id}' not found in {cfg_path}")
    entry = cfg["replicas"][idx]
    print_json({"config": str(cfg_path), "entry": entry})


# ─── drop ─────────────────────────────────────────────────────────────


@replica.command("drop")
@click.argument("replica_id")
@click.option("--config", "config_path", default=None, type=click.Path())
def drop(replica_id: str, config_path: str | None) -> None:
    """Remove a replica entry."""
    cfg_path = Path(config_path) if config_path else _find_config()
    if cfg_path is None:
        raise fail("no .dna-replicas.yaml found in cwd or any parent")
    cfg = _load_or_init(cfg_path)
    idx = _entry_index(cfg, replica_id)
    if idx < 0:
        raise fail(f"replica id '{replica_id}' not found in {cfg_path}")
    cfg["replicas"].pop(idx)
    _save(cfg_path, cfg)
    click.echo(f"DROPPED replica/{replica_id} from {cfg_path}")


# ─── enable / disable ─────────────────────────────────────────────────


@replica.command("enable")
@click.argument("replica_id")
@click.option("--config", "config_path", default=None, type=click.Path())
def enable(replica_id: str, config_path: str | None) -> None:
    """Set enabled=true for a replica."""
    _toggle_enabled(replica_id, True, config_path)


@replica.command("disable")
@click.argument("replica_id")
@click.option("--config", "config_path", default=None, type=click.Path())
def disable(replica_id: str, config_path: str | None) -> None:
    """Set enabled=false for a replica (soft-mute without losing config)."""
    _toggle_enabled(replica_id, False, config_path)


def _toggle_enabled(replica_id: str, value: bool, config_path: str | None) -> None:
    cfg_path = Path(config_path) if config_path else _find_config()
    if cfg_path is None:
        raise fail("no .dna-replicas.yaml found in cwd or any parent")
    cfg = _load_or_init(cfg_path)
    idx = _entry_index(cfg, replica_id)
    if idx < 0:
        raise fail(f"replica id '{replica_id}' not found in {cfg_path}")
    cfg["replicas"][idx]["enabled"] = value
    _save(cfg_path, cfg)
    click.echo(
        f"{'ENABLED' if value else 'DISABLED'} replica/{replica_id} in {cfg_path}"
    )
