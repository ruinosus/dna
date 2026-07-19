"""``dna memory`` — remember / recall / forget / list / consolidate, offline.

Kernel-bound, no server. Memory in DNA is the Kinds it already has
(Engram, Research, Evidence) written + recalled through the same kernel
+ ``RecordSearchProvider``. This command group drives ``dna.memory``'s verbs:

    dna memory remember "always deep-copy the L2 cache before mutating" \
        --area Feature/kernel --affect regret \
        --reason "hit live during the JARVIS audit — same dict ref across calls"
    dna memory recall "cache mutation" --json
    dna memory forget rem-abc123 --superseded-by rem-def456
    dna memory list --kind Engram
    dna memory consolidate --apply

With the ``search-sqlite`` extra present recall is hybrid (dense sqlite-vec +
lexical FTS5 + RRF, ``degraded=false``); without it, it degrades HONESTLY to the
kernel's lexical scan. Recall re-ranks memory hits by Ebbinghaus retention ×
affect, excludes bi-temporally-invalidated memories, and applies a light
reconsolidation bump (cues_history + confidence) — all fail-soft.

``--semantic/--no-semantic`` (default: auto) additionally blends embedding
similarity into the ecphory ranking and fuses it with the recall ranking via
RRF (s-memory-semantic-recall) — auto turns it on exactly when the provider is
available, so offline behavior without the extra is unchanged.
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from typing import Any

import click

from dna_cli._ctx import dna_session, print_json, print_table
from dna_cli.recall_cmd import _register_provider

_MEMORY_KINDS = ("Engram", "Research", "Evidence")


def _resolve_memory_tenant(personal: bool, tenant: str | None) -> str | None:
    """Resolve the effective ``tenant`` a ``dna memory`` command targets, honoring
    the ``--personal`` selector (ADR-personal-memory §6, CLI face).

    * ``--personal`` → the caller's OWN private partition ``personal:<oid>`` where
      ``oid`` is read SERVER-SIDE from ``DNA_PERSONAL_ID`` (the offline/stdio
      single-user identity — never a caller argument). Missing ``DNA_PERSONAL_ID``
      FAILS CLOSED with a clear message; combining ``--personal`` with an explicit
      ``--tenant`` is rejected (they name conflicting partitions).
    * otherwise → the raw ``--tenant`` overlay, but a value naming the reserved
      ``personal:`` scheme is REJECTED (INV-PERSONAL layer 4 — personal partitions
      are reachable ONLY via ``--personal``, never a raw override)."""
    from dna.memory.personal import (
        PersonalIdentityRequired,
        assert_no_personal_override,
        personal_tenant,
    )

    if personal:
        if tenant:
            raise click.ClickException(
                "--personal and --tenant are mutually exclusive: --personal targets "
                "your private per-user partition (DNA_PERSONAL_ID), --tenant names a "
                "workspace overlay."
            )
        oid = (os.environ.get("DNA_PERSONAL_ID") or "").strip()
        if not oid:
            raise click.ClickException(
                "--personal needs an identity — set DNA_PERSONAL_ID to your durable "
                "personal id (offline single-user). Personal memory never resolves to "
                "a blank partition (fail-closed)."
            )
        try:
            return personal_tenant(oid)
        except PersonalIdentityRequired as exc:  # pragma: no cover — guarded above
            raise click.ClickException(str(exc)) from None
    try:
        assert_no_personal_override(tenant)
    except PermissionError as exc:
        raise click.ClickException(str(exc)) from None
    return tenant


def _slug(text: str) -> str:
    """Derive a stable ``rem-<hash>`` name from the summary (upstream memory
    naming convention)."""
    h = hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()[:10]
    return f"rem-{h}"


def _index_memory_kinds(s: Any, scope: str, kinds, tenant) -> None:
    """Lazy-backfill: index the memory Kinds into the registered provider so
    recall finds pre-provider docs (``dna.memory.backfill_index`` — idempotent
    by text hash, unchanged docs are skipped)."""
    from dna.memory import backfill_index

    s.run(backfill_index(s.kernel, scope, kinds=tuple(kinds), tenant=tenant))


@click.group(name="memory")
def memory() -> None:
    """Declarative memory over existing Kinds (remember/recall/forget/consolidate)."""


@memory.command(name="remember")
@click.argument("summary")
@click.option("--kind", default="Engram", type=click.Choice(_MEMORY_KINDS), show_default=True)
@click.option("--name", default=None, help="Doc name (default: rem-<hash> of summary).")
@click.option("--area", default="general", show_default=True, help="Scoped target area (Feature/X, Epic/Y, …).")
@click.option("--affect", default="triumph",
              type=click.Choice(["triumph", "regret", "surprise", "wistful", "ominous"]), show_default=True)
@click.option("--reason", "affect_reason", default=None, help="Concrete justification for the affect (≥20 chars).")
@click.option("--source-ref", "source_refs", multiple=True, help="Source artifact ref (repeatable).")
@click.option("--tag", "tags", multiple=True, help="Tag (repeatable) — also seeds encoding_context co_topics.")
@click.option("--owner", default=None, help="Authoring agent (claude-code, jarvis, …).")
@click.option("--scope", default=None, help="Scope (default: first/only scope).")
@click.option("--tenant", default=None, help="Tenant overlay.")
@click.option("--personal", is_flag=True,
              help="Remember PRIVATELY — into your own per-user partition "
                   "(DNA_PERSONAL_ID), portable across workspaces, not shared.")
@click.option("--json", "as_json", is_flag=True)
def remember_cmd(
    summary: str, kind: str, name: str | None, area: str, affect: str,
    affect_reason: str | None, source_refs: tuple[str, ...], tags: tuple[str, ...],
    owner: str | None, scope: str | None, tenant: str | None, personal: bool,
    as_json: bool,
) -> None:
    """Write a memory Kind + deterministic encoding-context + index it."""
    from dna.memory import remember

    tenant = _resolve_memory_tenant(personal, tenant)
    name = name or _slug(summary)
    spec: dict[str, Any] = {"summary": summary}
    if kind == "Engram":
        spec.update({
            "area": area,
            "surface_when": ["feature_touched"],
            "source_refs": list(source_refs) or [area],
            "affect": affect,
        })
        if affect_reason:
            spec["affect_reason"] = affect_reason
        if tags:
            spec["tags"] = list(tags)
        if owner:
            spec["owner"] = owner

    with dna_session(scope) as s:
        provider = _register_provider(s)  # registered → remember indexes on write
        try:
            out = s.run(remember(
                s.kernel, s.scope, kind=kind, name=name, spec=spec, tenant=tenant,
            ))
        finally:
            if provider is not None:
                provider.close()

    if as_json:
        print_json({"kind": out["kind"], "name": out["name"], "indexed": out["indexed"]})
        return
    click.secho(f"🧠 remembered {out['kind']}/{out['name']}", fg="green", bold=True)
    click.echo(f"   {summary}")
    if not out["indexed"]:
        click.secho("   (search-sqlite extra absent — recall will be lexical)", fg="yellow")


@memory.command(name="recall")
@click.argument("query")
@click.option("--kind", "kinds", multiple=True, type=click.Choice(_MEMORY_KINDS),
              help="Restrict to memory kind(s). Default: all.")
@click.option("--scope", default=None)
@click.option("--tenant", default=None)
@click.option("--personal", is_flag=True,
              help="Recall YOUR OWN private memory (DNA_PERSONAL_ID), unioned with "
                   "the base defaults — never any workspace's memory.")
@click.option("-k", "--limit", "k", default=5, show_default=True)
@click.option("--no-reconsolidate", is_flag=True, help="Skip the cue/confidence bump side-effect.")
@click.option("--actor", default="cli", show_default=True, help="Who is recalling (stamped in cues_history).")
@click.option("--semantic/--no-semantic", "semantic", default=None,
              help="Blend embedding similarity into the ecphory ranking (RRF fusion). "
                   "Default: auto — on when the search provider is available.")
@click.option("--json", "as_json", is_flag=True)
def recall_cmd(
    query: str, kinds: tuple[str, ...], scope: str | None, tenant: str | None,
    personal: bool, k: int, no_reconsolidate: bool, actor: str,
    semantic: bool | None, as_json: bool,
) -> None:
    """Hybrid, bi-temporal, retention-re-scored recall over the memory Kinds."""
    from dna.memory import recall
    from dna.memory.verbs import MEMORY_KINDS

    tenant = _resolve_memory_tenant(personal, tenant)
    kind_list = list(kinds) or list(MEMORY_KINDS)
    with dna_session(scope) as s:
        provider = _register_provider(s)
        if provider is not None:
            try:
                _index_memory_kinds(s, s.scope, kind_list, tenant)
            except Exception as exc:  # noqa: BLE001 — indexing failure degrades to lexical
                click.secho(f"⚠ index failed ({exc}); lexical fallback", fg="yellow", err=True)
        else:
            click.secho(
                "⚠ search-sqlite extra not installed — degrading to lexical scan "
                "(pip install 'dna-sdk[search-sqlite]' for semantic recall)",
                fg="yellow", err=True,
            )
        try:
            res = s.run(recall(
                s.kernel, s.scope, query, kinds=tuple(kind_list), tenant=tenant, k=k,
                reconsolidate=not no_reconsolidate, actor=actor, semantic=semantic,
            ))
        finally:
            if provider is not None:
                provider.close()

    if as_json:
        print_json(res)
        return
    mode = "lexical (degraded)" if res["degraded"] else "hybrid (dense+lexical+RRF)"
    if res.get("semantic"):
        mode += " + semantic (ecphory×cosine)"
    click.secho(f"\n🧠 recall · {mode} · scope={res['scope']} · '{query}'", bold=True)
    hits = res["hits"]
    if not hits:
        click.echo("  (no memories)")
        return
    for i, h in enumerate(hits, 1):
        score = h.get("score", 0.0)
        ret = h.get("retention")
        tail = f"  [retention {ret:.2f}]" if ret is not None else ""
        cos = h.get("semantic")
        if cos is not None:
            tail += f"  [cos {cos:.2f}]"
        click.echo(f"  {i:>2}. {h.get('kind','?')}/{h.get('name','?')}  ({score:.4f}){tail}")
        if h.get("snippet"):
            click.secho(f"      {h['snippet']}", fg="bright_black")


@memory.command(name="forget")
@click.argument("name")
@click.option("--kind", default="Engram", type=click.Choice(_MEMORY_KINDS), show_default=True)
@click.option("--superseded-by", default=None, help="Name of the memory that supersedes this one.")
@click.option("--scope", default=None)
@click.option("--tenant", default=None)
@click.option("--json", "as_json", is_flag=True)
def forget_cmd(
    name: str, kind: str, superseded_by: str | None,
    scope: str | None, tenant: str | None, as_json: bool,
) -> None:
    """Bi-temporal DEMOTION — set valid_to (never hard-delete)."""
    from dna.memory import forget

    tenant = _resolve_memory_tenant(False, tenant)  # reject raw personal: override
    with dna_session(scope) as s:
        try:
            out = s.run(forget(
                s.kernel, s.scope, name, kind=kind, tenant=tenant, superseded_by=superseded_by,
            ))
        except KeyError as exc:
            raise click.ClickException(str(exc)) from exc

    if as_json:
        print_json(out)
        return
    verb = "already forgotten" if out["already_forgotten"] else "forgotten"
    click.secho(f"🕯  {verb}: {out['kind']}/{out['name']} (valid_to={out['valid_to']})", fg="yellow")
    click.secho("   (retained + auditable — bi-temporal invalidation, not deleted)", fg="bright_black")


@memory.command(name="list")
@click.option("--kind", default="Engram", type=click.Choice(_MEMORY_KINDS), show_default=True)
@click.option("--all", "show_all", is_flag=True, help="Include bi-temporally-invalidated (forgotten) memories.")
@click.option("--scope", default=None)
@click.option("--tenant", default=None)
@click.option("--json", "as_json", is_flag=True)
def list_cmd(kind: str, show_all: bool, scope: str | None, tenant: str | None, as_json: bool) -> None:
    """List memories in the scope (current by default; ``--all`` includes forgotten)."""
    from dna.memory.decay import currently_valid

    tenant = _resolve_memory_tenant(False, tenant)  # reject raw personal: override
    now = datetime.now(timezone.utc)
    with dna_session(scope) as s:
        rows: list[dict[str, Any]] = []

        async def _collect() -> None:
            async for raw in s.kernel.query(s.scope, kind, tenant=tenant):
                spec = raw.get("spec") or {}
                nm = (raw.get("metadata") or {}).get("name") or raw.get("name")
                valid = currently_valid(spec.get("valid_to"), now=now)
                if not show_all and not valid:
                    continue
                rows.append({
                    "name": nm,
                    "area": spec.get("area", ""),
                    "affect": spec.get("affect", ""),
                    "state": "current" if valid else "forgotten",
                    "summary": (spec.get("summary") or "")[:60],
                })

        s.run(_collect())

    rows.sort(key=lambda r: r["name"])
    if as_json:
        print_json({"kind": kind, "count": len(rows), "memories": rows})
        return
    if not rows:
        click.echo("(no memories)")
        return
    print_table(rows, ["name", "state", "affect", "area", "summary"])


@memory.command(name="consolidate")
@click.option("--kind", default="Engram", type=click.Choice(_MEMORY_KINDS), show_default=True)
@click.option("--floor", "stale_floor", default=0.15, show_default=True,
              help="Retention floor below which a memory is stale.")
@click.option("--apply", "do_apply", is_flag=True, help="Soft-forget stale memories (bi-temporal, never delete).")
@click.option("--scope", default=None)
@click.option("--tenant", default=None)
@click.option("--json", "as_json", is_flag=True)
def consolidate_cmd(
    kind: str, stale_floor: float, do_apply: bool,
    scope: str | None, tenant: str | None, as_json: bool,
) -> None:
    """Deterministic consolidation pass — recompute decay, report/soft-forget
    stale memories. NO LLM (that scribe is external + optional)."""
    from dna.memory import consolidate

    tenant = _resolve_memory_tenant(False, tenant)  # reject raw personal: override
    with dna_session(scope) as s:
        report = s.run(consolidate(
            s.kernel, s.scope, kind=kind, tenant=tenant,
            stale_retention_floor=stale_floor, apply=do_apply,
        ))

    if as_json:
        print_json(report)
        return
    click.secho(
        f"\n🌙 consolidate · evaluated {report['evaluated']} · "
        f"{len(report['stale'])} stale · archived {report['archived']}",
        bold=True,
    )
    for stl in report["stale"]:
        click.echo(f"  · {stl['name']}  retention={stl['retention']:.3f}  "
                   f"({stl['days_since']:.0f}d since recall)")
    if report["stale"] and not do_apply:
        click.secho("  (report-only — pass --apply to soft-forget)", fg="bright_black")


__all__ = ["memory"]
