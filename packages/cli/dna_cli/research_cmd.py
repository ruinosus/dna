"""``dna research`` — manage Research synthesis docs (kernel-bound).

A Research is a curated synthesis of N Reference docs with objective,
methodology, evidence-rated findings, and priority recommendations —
agent-facing knowledge WITH provenance.

Commands:
    dna research list [--status S] [--methodology M]  — tabular listing
    dna research show <name> [--full]                 — full doc render
    dna research create <path>                         — upsert from YAML/JSON

Kernel-bound: boots a local kernel against ``DNA_SOURCE_URL`` /
``DNA_BASE_DIR`` (filesystem source, default ``./.dna``). No service.

Tenancy is PERMISSIVE — ``--tenant`` is OPTIONAL (Research is
repo-authored knowledge, not per-client data). Omit it to write/read the
base doc.

Semantic recall (``recall_research``) has no embeddings server in this
distribution; a future ``search`` sub-command would degrade to lexical
``kernel.query`` over the Research catalog. Not shipped here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click

import yaml as _yaml

from dna_cli._ctx import dna_session, fail, print_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _spec_of(doc: Any) -> dict:
    spec = getattr(doc, "spec", None)
    if spec is None and isinstance(doc, dict):
        spec = doc.get("spec")
    if not isinstance(spec, dict):
        spec = dict(spec) if spec else {}
    return spec


def _name_of(doc: Any, fallback: str = "?") -> str:
    name = getattr(doc, "name", None)
    if not name and isinstance(doc, dict):
        name = (doc.get("metadata") or {}).get("name")
    return name or fallback


@click.group(name="research")
def research() -> None:
    """Manage Research synthesis documents (curated syntheses of References)."""


@research.command("list")
@click.option("--status", type=click.Choice(list(("brief", "ready", "draft", "published", "superseded", "retracted"))))
@click.option("--methodology", default=None)
@click.option("--scope", default="dna-development")
@click.option("--tenant", default=None, help="Optional tenant (Research is PERMISSIVE — omit for base docs).")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def cmd_list(
    status: str | None, methodology: str | None, scope: str, tenant: str | None,
    as_json: bool,
) -> None:
    """List Research docs in the scope, with key metadata."""
    with dna_session(scope) as s:
        docs = s.query_list("Research", tenant=tenant) or []
        rows = []
        for d in docs:
            spec = _spec_of(d)
            if status and spec.get("status") != status:
                continue
            if methodology and spec.get("methodology") != methodology:
                continue
            findings = spec.get("findings") or []
            rows.append({
                "name": _name_of(d),
                "title": (spec.get("title") or "")[:50],
                "status": spec.get("status", "draft"),
                "method": spec.get("methodology", ""),
                "findings": len(findings),
                "sources": len(spec.get("sources") or []),
                "conducted": (spec.get("conducted_at") or "")[:10],
            })
    rows.sort(key=lambda r: r["name"])
    if as_json:
        print_json(rows)
        return
    if not rows:
        click.echo("(no Research docs)")
        return
    click.echo(f"{'name':30s} {'status':10s} {'method':20s} {'#F':>3s} {'#S':>3s} {'when':10s}  title")
    click.echo("-" * 110)
    for r in rows:
        click.echo(
            f"{r['name']:30s} {r['status']:10s} {r['method']:20s} "
            f"{r['findings']:3d} {r['sources']:3d} {r['conducted']:10s}  {r['title']}"
        )


@research.command("show")
@click.argument("name")
@click.option("--scope", default="dna-development")
@click.option("--tenant", default=None, help="Optional tenant (Research is PERMISSIVE).")
@click.option("--full", is_flag=True, help="Print all findings + recommendations.")
def cmd_show(name: str, scope: str, tenant: str | None, full: bool) -> None:
    """Show a Research doc + its citation graph."""
    with dna_session(scope) as s:
        doc = s.get_doc("Research", name, tenant=tenant)
        if not doc:
            raise fail(f"Not found: Research/{name}")
        spec = _spec_of(doc)
    click.secho(f"\n🔬 Research/{name}", bold=True)
    click.echo(f"  title:        {spec.get('title', '?')}")
    click.echo(f"  status:       {spec.get('status', 'draft')}")
    click.echo(f"  methodology:  {spec.get('methodology', '')}")
    click.echo(f"  confidence:   {spec.get('overall_confidence', '?')}")
    click.echo(f"  conducted_by: {spec.get('conducted_by', '?')}")
    click.echo(f"  conducted_at: {spec.get('conducted_at', '?')}")
    click.echo(f"  scope_ref:    {spec.get('scope_ref', '?')}")
    click.echo(f"  visibility:   {spec.get('visibility', 'scope-private')}")
    sup = spec.get("superseded_by")
    if sup:
        click.secho(f"  ⚠ superseded_by: {sup}", fg="yellow")
    obj = spec.get("objective", "")
    if obj:
        click.echo(f"\n  objective:\n    {obj}")
    takeaways = spec.get("key_takeaways") or []
    if takeaways:
        click.echo("\n  key_takeaways:")
        for t in takeaways:
            click.echo(f"    • {t}")
    srcs = spec.get("sources", []) or []
    click.echo(f"\n  sources: {len(srcs)} Reference docs")
    for ref_name in (srcs if full else srcs[:10]):
        click.echo(f"    • {ref_name}")
    if not full and len(srcs) > 10:
        click.echo(f"    … and {len(srcs) - 10} more (use --full)")
    findings = spec.get("findings", []) or []
    ev_count = sum(1 for f in findings if f.get("evidence_rating") == "evidence-based")
    click.echo(f"\n  findings: {len(findings)} ({ev_count} evidence-based)")
    for f in (findings if full else findings[:5]):
        rating = f.get("evidence_rating", "?")
        color = "green" if rating == "evidence-based" else "yellow"
        click.echo(f"    {f.get('id', '?'):34s}  [", nl=False)
        click.secho(rating, fg=color, nl=False)
        click.echo(f"]  {f.get('title', '?')}")
        if full and f.get("summary"):
            click.echo(f"        {f['summary']}")
    if not full and len(findings) > 5:
        click.echo(f"    … and {len(findings) - 5} more (use --full)")
    recs = spec.get("recommendations", []) or []
    click.echo(f"\n  recommendations: {len(recs)}")
    for r in (recs if full else recs[:5]):
        pri = r.get("priority", "?")
        color = "red" if pri == "high" else "yellow" if pri == "medium" else "white"
        click.echo(f"    {r.get('id', '?'):34s}  [", nl=False)
        click.secho(pri, fg=color, nl=False)
        click.echo(f"]  {(r.get('summary', '?') or '')[:70]}")
        if r.get("clinical_decision"):
            click.secho("       ⚠ clinical_decision — requires human approval", fg="yellow")
    if not full and len(recs) > 5:
        click.echo(f"    … and {len(recs) - 5} more (use --full)")


def _validate_spec_or_die(path: str, spec: dict[str, Any]) -> None:
    """Validate a Research spec against the Kind's own JSON schema.

    ResearchKind may opt out of validate_on_parse, so ``write_document``
    could persist a malformed spec silently. We validate here, at the
    authoring boundary, using the live Kind schema as the single source
    of truth — collecting ALL errors — and exit non-zero on any violation.
    """
    try:
        import jsonschema
        from dna.extensions.research import ResearchKind
    except ImportError:  # pragma: no cover — kernel always ships jsonschema
        return
    schema = ResearchKind().schema()
    if not schema:
        return
    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(spec),
        key=lambda e: list(e.absolute_path),
    )
    if not errors:
        return
    click.secho(
        f"{path}: Research spec failed schema validation "
        f"({len(errors)} error{'s' if len(errors) != 1 else ''}):",
        fg="red", bold=True,
    )
    for e in errors:
        loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
        click.secho(f"  • spec/{loc}: {e.message}", fg="red")
    click.secho(
        "\nHint: findings[] need {id, title, evidence_rating}; "
        "recommendations[] need {id, priority, summary}. "
        "See the Kind schema via `dna kind show Research`.",
        fg="yellow",
    )
    raise SystemExit(1)


@research.command("create")
@click.argument("path")
@click.option("--scope", default="dna-development")
@click.option("--tenant", default=None, help="Optional tenant (Research is PERMISSIVE — omit for base docs).")
@click.option("--status", default=None, help="Override spec.status (else the file's value, else 'draft').")
def cmd_create(path: str, scope: str, tenant: str | None, status: str | None) -> None:
    """Create/upsert a Research doc from a YAML/JSON file.

    First-class research authoring (no ``dna doc apply`` needed). Validates
    kind == Research and the spec schema BEFORE writing. Tenancy is
    permissive: ``--tenant`` optional.
    """
    p = Path(path)
    if not p.exists():
        raise fail(f"File not found: {path}")
    try:
        raw = _yaml.safe_load(p.read_text(encoding="utf-8"))
    except _yaml.YAMLError as e:
        raise fail(f"Invalid YAML/JSON in {path}: {e}")
    if not isinstance(raw, dict):
        raise fail(f"{path}: top-level must be a mapping (apiVersion/kind/metadata/spec).")
    if raw.get("kind") != "Research":
        raise fail(f"{path}: kind must be 'Research' (got {raw.get('kind')!r}).")
    name = (raw.get("metadata") or {}).get("name")
    if not name:
        raise fail(f"{path}: missing metadata.name.")

    raw.setdefault("apiVersion", "github.com/ruinosus/dna/research/v1")
    spec = raw.setdefault("spec", {})
    if status:
        spec["status"] = status
    spec.setdefault("status", "draft")
    spec.setdefault("created_at", _now())
    spec["updated_at"] = _now()

    _validate_spec_or_die(path, spec)

    with dna_session(scope) as s:
        existing = s.get_doc("Research", name, tenant=tenant)
        action = "UPDATED" if existing else "CREATED"
        s.run(s.kernel.write_document(scope, "Research", name, raw, tenant=tenant))
    suffix = f" (tenant={tenant})" if tenant else ""
    click.secho(f"{action} Research/{name}{suffix}", fg="green")
