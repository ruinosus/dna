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
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import click

from dna_cli._ctx import dna_session, print_json, print_table
from dna_cli.recall_cmd import _register_provider

_MEMORY_KINDS = ("Engram", "Research", "Evidence")

#: The mif-memory passthrough Kind's own schema property vocabulary
#: (packages/sdk-py/dna/extensions/mif/kinds/memory.kind.yaml) — the
#: passthrough Kind is STRICT (additionalProperties: false), so a foreign
#: MIF file's frontmatter is filtered to this set before being stored
#: verbatim; anything outside it (a stray custom top-level key a producer
#: added) is dropped rather than tripping schema validation on write. A
#: doc built by THIS module's own export path never carries anything
#: outside this set, so the DNA->MIF->DNA (Circle A) path is never
#: affected by the filter.
_KNOWN_MIF_FIELDS = frozenset({
    "id", "type", "content", "created", "title", "modified", "ontology",
    "namespace", "tags", "aliases", "entities", "relationships", "temporal",
    "provenance", "embedding", "citations", "summary", "compressed_at",
    "extensions",
})


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


def _engram_doc_name(mif_id: str) -> str:
    """Deterministic Engram doc name for an IMPORTED MIF memory — keyed by the
    MIF id, exactly like ``_mif_doc_name`` keys the passthrough copy.

    NOT ``_slug(summary)``: two distinct MIF docs can derive the same summary
    (both untitled, or simply sharing a title), and ``write_document`` is a
    full replace at a name — so a summary-keyed projection silently overwrote
    an unrelated, previously-imported memory. The id is the identity
    (``interchange.py`` §6); the projection must be named off it."""
    h = hashlib.sha256((mif_id or "unknown").strip().encode("utf-8")).hexdigest()[:10]
    return f"rem-{h}"


def _coerce_timestamps(value: Any) -> Any:
    """Recursively turn ``date``/``datetime`` back into ISO-8601 STRINGS.

    MIF's own examples write dates unquoted, and YAML's SafeLoader implicitly
    resolves those to ``datetime`` objects. MIF declares every temporal field
    as ``type: string``, so the parsed objects fail schema validation on the
    passthrough leg (the doc is silently dropped into ``failed``), sail
    unchecked into the native leg, and later crash ``--bundle`` export on
    ``json.dumps``. Foreign files written to spec are exactly the case this
    has to survive."""
    if isinstance(value, datetime):
        iso = value.isoformat()
        # Keep UTC as the `Z` form MIF's own examples use, not `+00:00`.
        return iso[:-6] + "Z" if iso.endswith("+00:00") else iso
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _coerce_timestamps(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_coerce_timestamps(v) for v in value]
    return value


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


# ─────────────────────────── export / import (s-memory-interchange-verbs) ──


def _api_version_for(kernel: Any, kind: str) -> str | None:
    """Best-effort api_version for a Kind from the kernel registry (mirrors
    the equivalent private helper in ``dna.memory.verbs``; kept as a small
    local copy rather than importing a leading-underscore cross-module name)."""
    for kp in (getattr(kernel, "_kinds", {}) or {}).values():
        if getattr(kp, "kind", None) == kind:
            return getattr(kp, "api_version", None)
    return None


def _write_kernel_for(s: Any, tenant: str | None) -> Any:
    from dna.memory.personal import is_personal_tenant

    return s.kernel.with_tenant(tenant, allow_personal=is_personal_tenant(tenant)) if tenant else s.kernel


def _mif_doc_name(mif_id: str) -> str:
    """Deterministic DNA doc name for a MIF id — same ``<prefix>-<hash>``
    convention ``_slug`` uses for Engram names, so a re-import of the SAME
    id always targets the SAME storage slot (the id, not a random suffix, is
    the identity — see ``interchange.py``'s §6 module docstring)."""
    h = hashlib.sha256((mif_id or "unknown").strip().encode("utf-8")).hexdigest()[:12]
    return f"mif-{h}"


def _safe_filename(mif_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", mif_id or "memory").strip("-")
    return (safe or "memory")[:80]


def _to_json_ld(doc: dict[str, Any]) -> dict[str, Any]:
    """Render a Markdown-profile MIF doc (``id`` a plain string) as its
    JSON-LD projection (``@id`` a ``urn:mif:`` URN) — the two representations
    the real MIF spec keeps separate (interchange.py module docstring point
    1). Used only by ``--bundle``."""
    entry = dict(doc)
    doc_id = entry.pop("id", None)
    if doc_id is None:
        return entry
    return {"@id": f"urn:mif:{doc_id}", **entry}


def _from_json_ld(entry: dict[str, Any]) -> dict[str, Any]:
    """Inverse of :func:`_to_json_ld` — used when importing a ``--bundle``
    JSON-LD file (or any JSON-LD-shaped doc): ``@id`` -> ``id``, stripping
    the ``urn:mif:`` prefix if present (the plain form is what the Markdown
    profile — and this module's own ``id`` field — carries). Delegates to the
    SHARED core normalizer (``dna.memory.interchange.from_json_ld``)."""
    from dna.memory.interchange import from_json_ld

    return from_json_ld(entry)


def _render_mif_markdown(doc: dict[str, Any]) -> str:
    """Serialize a MIF doc to its Markdown frontmatter profile — the real
    MIF file shape (frontmatter + body), reusing the SDK's own safe YAML
    dumper (``dna.kernel.source.generic_rw.safe_yaml_dump``) for the same
    round-trip-robust scalar styling every DNA bundle marker gets."""
    from dna.kernel.source.generic_rw import safe_yaml_dump

    fm = {k: v for k, v in doc.items() if k != "content"}
    content = doc.get("content") or ""
    return f"---\n{safe_yaml_dump(fm)}---\n\n{content}\n"


def _validate_mif_doc(doc: dict[str, Any], source: str) -> None:
    """CLI channel for the SHARED core validator — same fields, same message,
    surfaced as a ``ClickException`` (the REST face maps it to a 400)."""
    from dna.memory.interchange import MifFormatError, validate_mif_doc

    try:
        validate_mif_doc(doc, source)
    except MifFormatError as exc:
        raise click.ClickException(str(exc)) from None


def _read_mif_md(md_path: Path) -> dict[str, Any]:
    from dna.kernel.source.generic_rw import _parse_frontmatter

    text = md_path.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter(text, source=str(md_path))
    # YAML implicitly resolves UNQUOTED ISO dates to datetime objects; MIF
    # declares every temporal field as a string, so coerce before validating.
    doc = _coerce_timestamps(dict(fm))
    doc["content"] = body.strip()
    _validate_mif_doc(doc, str(md_path))
    return doc


def _read_mif_json(json_path: Path) -> list[dict[str, Any]]:
    """Read a MIF JSON file (JSON-LD ``@graph`` bundle, bare list, or a single
    doc) — the SHARED core parser does the shape work; this only supplies the
    bytes and maps the format error onto the CLI's channel."""
    from dna.memory.interchange import MifFormatError, parse_mif_bundle

    raw = json.loads(json_path.read_text(encoding="utf-8"))
    try:
        return parse_mif_bundle(raw, source=str(json_path))
    except MifFormatError as exc:
        raise click.ClickException(str(exc)) from None


def _read_mif_docs(path: Path) -> list[dict[str, Any]]:
    """Read one or more MIF Memory Units from PATH — a single ``.md``/
    ``.json`` file, or a directory of them (any filename; real MIF v1.0 file
    naming is plain ``{id}.md``, not ``.memory.md`` — see the passthrough
    Kind descriptor's storage note)."""
    if path.is_dir():
        docs: list[dict[str, Any]] = []
        for md in sorted(path.glob("*.md")):
            docs.append(_read_mif_md(md))
        for jf in sorted(path.glob("*.json")):
            docs.extend(_read_mif_json(jf))
        if not docs:
            raise click.ClickException(f"no MIF .md/.json files found under {path}")
        return docs
    if path.suffix == ".json":
        return _read_mif_json(path)
    return [_read_mif_md(path)]


@memory.command(name="export")
@click.option("--format", "fmt", default="mif", type=click.Choice(["mif"]), show_default=True,
              help="Interchange format. Only 'mif' is implemented; --format omp/pam are a "
                   "documented future switch (design §2/§9).")
@click.option("--out", "out_path", type=click.Path(path_type=Path), default=None,
              help="Output path — a directory (one <id>.md per memory) or, with --bundle, a "
                   "single JSON-LD file. Default: ./mif-export/ (or ./mif-export.json with --bundle).")
@click.option("--bundle", is_flag=True, help="Emit a single JSON-LD file instead of N .md files.")
@click.option("--kind", default="Engram", type=click.Choice(_MEMORY_KINDS), show_default=True,
              help="Source memory kind. Only Engram has a MIF field mapping today.")
@click.option("--personal", is_flag=True,
              help="Export YOUR OWN private partition (DNA_PERSONAL_ID) — never workspace memory "
                   "(INV-PERSONAL).")
@click.option("--include-forgotten", is_flag=True,
              help="Include bi-temporally invalidated memories (valid_to<now), temporal preserved "
                   "— otherwise supersession looks like a silent delete on export.")
@click.option("--scope", default=None)
@click.option("--tenant", default=None)
@click.option("--json", "as_json", is_flag=True)
def export_cmd(
    fmt: str, out_path: Path | None, bundle: bool, kind: str, personal: bool,
    include_forgotten: bool, scope: str | None, tenant: str | None, as_json: bool,
) -> None:
    """Project Engrams to a portable MIF bundle. Deterministic, no LLM, no network."""
    from dna.memory.decay import currently_valid
    from dna.memory.interchange import resolve_or_mint_mif_id, to_mif

    if kind != "Engram":
        raise click.ClickException(
            "dna memory export currently only projects Engram to MIF — Research/Evidence "
            "have no field mapping defined yet."
        )
    tenant = _resolve_memory_tenant(personal, tenant)
    now = datetime.now(timezone.utc)

    with dna_session(scope) as s:
        rows: list[tuple[str, dict[str, Any]]] = []

        async def _collect() -> None:
            async for raw in s.kernel.query(s.scope, "Engram", tenant=tenant):
                spec = raw.get("spec") or {}
                name = (raw.get("metadata") or {}).get("name") or raw.get("name")
                if not name:
                    continue
                if not include_forgotten and not currently_valid(spec.get("valid_to"), now=now):
                    continue
                rows.append((str(name), spec))

        s.run(_collect())

        # §6: mint-once. Resolve every doc's id up front so a batch export
        # can resolve CROSS-references (superseded_by/homophonic targets
        # pointing at another doc IN THIS BATCH) to real MIF ids via
        # id_lookup, and so newly-minted ids get pinned back exactly once.
        id_lookup: dict[str, str] = {}
        minted: dict[str, dict[str, Any]] = {}
        for name, spec in rows:
            mif_id, was_minted = resolve_or_mint_mif_id(spec)
            id_lookup[name] = mif_id
            if was_minted:
                minted[name] = spec

        if minted:
            write_kernel = _write_kernel_for(s, tenant)
            api_version = _api_version_for(s.kernel, "Engram")

            async def _pin() -> None:
                for name, spec in minted.items():
                    ec = dict(spec.get("encoding_context") or {})
                    ec["mif_id"] = id_lookup[name]
                    spec["encoding_context"] = ec
                    raw: dict[str, Any] = {"kind": "Engram", "metadata": {"name": name}, "spec": spec}
                    if api_version:
                        raw["apiVersion"] = api_version
                    await write_kernel.write_document(s.scope, "Engram", name, raw, invalidate_mode="doc")

            s.run(_pin())

        mif_docs = [to_mif(spec, mif_id=id_lookup[name], id_lookup=id_lookup) for name, spec in rows]

    out_target = out_path or Path("mif-export.json" if bundle else "mif-export")
    written: list[str] = []
    if bundle:
        out_target.parent.mkdir(parents=True, exist_ok=True)
        bundle_doc = {
            "@context": "https://mif-spec.dev/context/v1.0.0",
            "@graph": [_to_json_ld(d) for d in mif_docs],
        }
        out_target.write_text(json.dumps(bundle_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written = [str(out_target)]
    else:
        out_target.mkdir(parents=True, exist_ok=True)
        for d in mif_docs:
            file_path = out_target / f"{_safe_filename(str(d['id']))}.md"
            file_path.write_text(_render_mif_markdown(d), encoding="utf-8")
            written.append(str(file_path))

    result = {
        "format": "mif", "kind": kind, "count": len(mif_docs), "bundle": bundle,
        "out": str(out_target), "files": written, "minted_ids": len(minted),
    }
    if as_json:
        print_json(result)
        return
    click.secho(f"\n📤 exported {len(mif_docs)} {kind} -> {out_target}", fg="green", bold=True)
    if minted:
        click.secho(
            f"   minted {len(minted)} new MIF id(s) (pinned back onto the Engram for a stable re-export)",
            fg="bright_black",
        )


@memory.command(name="import")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--as", "as_mode", default="both", type=click.Choice(["passthrough", "native", "both"]),
              show_default=True,
              help="passthrough = store the MIF doc verbatim only; native = project to Engram only; "
                   "both = store verbatim AND project (default — auditable + recallable).")
@click.option("--dedupe", default="id", type=click.Choice(["id", "content-hash", "off"]), show_default=True,
              help="id = skip a doc whose MIF id was already imported (idempotent re-import, the "
                   "§6 contract); content-hash = skip by exact content match; off = no pre-check.")
@click.option("--personal", is_flag=True,
              help="Import into YOUR OWN private partition (DNA_PERSONAL_ID) — never a shared "
                   "partition (INV-PERSONAL).")
@click.option("--scope", default=None)
@click.option("--tenant", default=None)
@click.option("--json", "as_json", is_flag=True)
def import_cmd(
    path: Path, as_mode: str, dedupe: str, personal: bool,
    scope: str | None, tenant: str | None, as_json: bool,
) -> None:
    """Ingest a MIF bundle (PATH: a .md/.json file or a directory of them).

    ``--as both`` (default) stores the original MIF doc byte-for-byte as
    ``mif-spec.dev/v1 · Memory`` (passthrough — auditable, stable re-export)
    AND projects an ``Engram`` (indexable/recallable by ``dna memory
    recall``). Deterministic, no LLM, no network.
    """
    from dna.memory.verbs import import_mif_docs

    tenant = _resolve_memory_tenant(personal, tenant)
    docs = _read_mif_docs(path)

    with dna_session(scope) as s:
        # ONE write pipeline, shared with the REST face (POST /v1/memories/import)
        # so the two can never drift — see dna.memory.verbs.import_mif_docs.
        outcome = s.run(
            import_mif_docs(
                s.kernel, s.scope, docs, as_mode=as_mode, dedupe=dedupe, tenant=tenant
            )
        )

    imported_ids = outcome["ids"]
    failed = outcome["errors"]
    skipped_n = outcome["skipped"]

    result = {
        "as": as_mode, "dedupe": dedupe, "path": str(path),
        "imported": len(imported_ids), "skipped": skipped_n, "failed": len(failed),
        "ids": imported_ids, "errors": failed,
    }
    if as_json:
        print_json(result)
        return
    click.secho(f"\n📥 imported {len(imported_ids)} memories from {path} (--as {as_mode})", fg="green", bold=True)
    if skipped_n:
        click.secho(f"   skipped {skipped_n} already-imported (--dedupe {dedupe})", fg="bright_black")
    if failed:
        click.secho(f"   {len(failed)} failed:", fg="red")
        for f in failed:
            click.secho(f"     · {f['id']}: {f['error']}", fg="red")


__all__ = ["memory"]
