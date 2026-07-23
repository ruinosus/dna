"""``dna doc`` — CRUD on documents within a scope.

Migrated to dna-client for read/write CRUD (no local kernel needed
for the common path). `apply` is the lone exception: it walks a
bundle directory or markdown marker file and needs the kernel's
registered Kinds to resolve marker→kind — that read happens in-process
via open_session. Migration of `apply` requires a server-side endpoint
that accepts the bundle+marker and resolves kind itself (TODO).
"""
from __future__ import annotations

import json as _json
import sys
from pathlib import Path  # noqa: F401 — used in deferred-eval annotations

import click

from dna_cli._ctx import (
    dna_client,
    fail,
    open_session,
    print_json,
    print_table,
    run_async,
)


def _tenant_write_note(tenant: str | None) -> tuple[str | None, str | None]:
    """Resolve the EFFECTIVE write tenant (``--tenant`` > ``DNA_TENANT`` >
    unbound) and a warning (i-020).

    Returns ``(effective, warning)``. ``warning`` is set when the effective
    tenant is non-null but absent from ``DNA_DEV_ALLOWED_TENANTS`` — the silent
    trap where a write lands in a tenant the Studio never browses (e.g. the old
    ``dev-tenant`` default while Studio browses ``acme``)."""
    import os
    effective = tenant if tenant is not None else os.getenv("DNA_TENANT")
    warning: str | None = None
    allowed_env = os.getenv("DNA_DEV_ALLOWED_TENANTS")
    if effective and allowed_env:
        allowed = [t.strip() for t in allowed_env.split(",") if t.strip()]
        if allowed and effective not in allowed:
            warning = (
                f"tenant '{effective}' não está em DNA_DEV_ALLOWED_TENANTS "
                f"({', '.join(allowed)}) — o doc pode ficar invisível no Studio"
            )
    return effective, warning


@click.group("doc", help="List, show, create, edit, delete documents.")
def doc() -> None:
    """Group root."""


@doc.command("list")
@click.argument("kind_name")
@click.option("--scope", default="dna-development")
@click.option("--tenant", default=None, help="Bind to this tenant (overrides DNA_TENANT).")
@click.option("--json", "as_json", is_flag=True)
def list_docs(
    kind_name: str, scope: str, tenant: str | None, as_json: bool,
) -> None:
    """List documents of a Kind in the scope."""
    with dna_client(tenant=tenant) as dna:
        try:
            body = run_async(dna.docs(scope).list(kind=kind_name))
        except Exception as e:  # noqa: BLE001
            raise fail(f"docs.list failed: {e}") from e
    items = body.get("items") if isinstance(body, dict) else body
    if not isinstance(items, list):
        items = []
    rows = [
        {
            "name": (it.get("metadata", {}) or {}).get("name") or it.get("name") or "?",
            "kind": it.get("kind") or kind_name,
        }
        for it in items
    ]
    rows.sort(key=lambda r: r["name"])
    if as_json:
        print_json(rows)
    else:
        print_table(rows, ["name", "kind"])


@doc.command("show")
@click.argument("kind_name")
@click.argument("doc_name")
@click.option("--scope", default="dna-development")
@click.option("--tenant", default=None, help="Bind to this tenant (overrides DNA_TENANT).")
def show(
    kind_name: str, doc_name: str, scope: str, tenant: str | None,
) -> None:
    """Print the full document (raw frontmatter + spec) as JSON."""
    with dna_client(tenant=tenant) as dna:
        try:
            doc_body = run_async(dna.docs(scope).get(kind_name, doc_name))
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "404" in msg or "not found" in msg.lower() or "not_found" in msg.lower():
                raise fail(f"{kind_name}/{doc_name} not found in scope.") from e
            raise fail(f"docs.get failed: {e}") from e
    raw = doc_body.get("raw") if isinstance(doc_body, dict) else None
    if raw is None and isinstance(doc_body, dict):
        raw = doc_body
    print_json(
        {
            "kind": raw.get("kind") if isinstance(raw, dict) else kind_name,
            "name": (raw.get("metadata") or {}).get("name") or doc_name if isinstance(raw, dict) else doc_name,
            "metadata": (raw.get("metadata") if isinstance(raw, dict) else None) or {},
            "spec": (raw.get("spec") if isinstance(raw, dict) else None) or {},
        }
    )


def _read_spec(spec_arg: str | None) -> dict:
    """Read spec JSON from a file path or `-` for stdin."""
    if spec_arg is None:
        raise fail("Missing --spec=PATH (or `-` for stdin).")
    if spec_arg == "-":
        body = sys.stdin.read()
    else:
        with open(spec_arg, encoding="utf-8") as f:
            body = f.read()
    try:
        return _json.loads(body)
    except _json.JSONDecodeError as e:
        raise fail(f"Invalid JSON in spec: {e}")


def _fetch_kind_descriptor(dna, scope: str, kind_name: str) -> dict:
    """Fetch a kind descriptor via dna-client. Returns {schema, api_version, ...}.

    Raises fail() if the kind isn't registered in the scope.
    """
    try:
        return run_async(dna.scopes.kind_schema(scope, kind_name))
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "404" in msg or "not found" in msg.lower():
            raise fail(f"Kind '{kind_name}' not registered in scope '{scope}'.") from e
        raise fail(f"kind_schema fetch failed: {e}") from e


def _coerce_value(value: str, schema_type: str | None) -> object:
    """Coerce a CLI string value to the JSON Schema type the field declares.

    integer → int, number → float, boolean → bool from truthy strings,
    array → split on ';' (with optional `[]` wrapping). Everything else → str.
    """
    if schema_type == "integer":
        try:
            return int(value)
        except ValueError:
            return value
    if schema_type == "number":
        try:
            return float(value)
        except ValueError:
            return value
    if schema_type == "boolean":
        return value.lower() in ("true", "1", "yes", "y")
    if schema_type == "array":
        v = value.strip()
        if v.startswith("[") and v.endswith("]"):
            v = v[1:-1]
        return [item.strip() for item in v.split(";") if item.strip()]
    return value


@doc.command("make")
@click.argument("kind_name")
@click.argument("doc_name")
@click.argument("fields", nargs=-1)
@click.option("--scope", default="dna-development")
@click.option("--tenant", default=None, help="Bind the write to this tenant.")
@click.option("--dry-run", is_flag=True, help="Validate without writing.")
def make_doc(
    kind_name: str,
    doc_name: str,
    fields: tuple,
    scope: str,
    tenant: str | None,
    dry_run: bool,
) -> None:
    """Create a doc via schema-driven flags (no JSON file needed).

    Syntax: dna doc make <Kind> <name> field1=value1 field2=value2 ...

    Field types are coerced from the Kind's JSON Schema:
      severity=high                  → "high" (string)
      time_box_hours=8               → 8 (integer)
      repro_steps="step1;step2"      → ["step1", "step2"] (array)
      labels=                        → [] (empty array on empty value)
    """
    with dna_client(tenant=tenant) as dna:
        descriptor = _fetch_kind_descriptor(dna, scope, kind_name)
        schema = descriptor.get("schema") or {}
        schema_props = (schema.get("properties") or {}) if isinstance(schema, dict) else {}
        api_version = descriptor.get("api_version") or "github.com/ruinosus/dna/v1"

        spec: dict[str, object] = {}
        for field in fields:
            if "=" not in field:
                raise fail(f"Field arg '{field}' must be 'key=value' (got no '=').")
            key, _, raw_value = field.partition("=")
            key = key.strip()
            prop = schema_props.get(key) if isinstance(schema_props, dict) else None
            schema_type = prop.get("type") if isinstance(prop, dict) else None
            spec[key] = _coerce_value(raw_value, schema_type)

        if "created_at" in schema_props and "created_at" not in spec:
            from datetime import datetime, timezone
            spec["created_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

        raw = {
            "apiVersion": api_version,
            "kind": kind_name,
            "metadata": {"name": doc_name},
            "spec": spec,
        }
        if dry_run:
            print_json({"dry_run": True, "would_write": raw, "tenant": tenant})
            return
        try:
            run_async(dna.docs(scope).put(kind_name, doc_name, raw))
        except Exception as e:  # noqa: BLE001
            raise fail(f"write failed: {e}") from e
        click.secho(
            f"Created {kind_name}/{doc_name} in scope {scope} "
            f"({len(spec)} fields){' (tenant=' + tenant + ')' if tenant else ''}",
            fg="green",
        )


@doc.command("transition")
@click.argument("kind_name")
@click.argument("doc_name")
@click.argument("new_status")
@click.option("--scope", default="dna-development")
@click.option("--tenant", default=None)
@click.option("--commit-ref", default=None, help="Git SHA to stamp on transition.")
@click.option("--reason", default=None, help="Optional reason string.")
def transition(
    kind_name: str,
    doc_name: str,
    new_status: str,
    scope: str,
    tenant: str | None,
    commit_ref: str | None,
    reason: str | None,
) -> None:
    """Generic status transition for any Kind that declares ``status`` in schema.

    Validates new_status against the Kind's status enum. Stamps updated_at,
    optionally closed_at (if new_status is terminal — heuristic), commit_ref,
    and a timeline entry.
    """
    with dna_client(tenant=tenant) as dna:
        descriptor = _fetch_kind_descriptor(dna, scope, kind_name)
        schema = descriptor.get("schema") or {}
        schema_props = (schema.get("properties") or {}) if isinstance(schema, dict) else {}
        api_version = descriptor.get("api_version") or "github.com/ruinosus/dna/v1"

        try:
            current = run_async(dna.docs(scope).get(kind_name, doc_name))
        except Exception as e:  # noqa: BLE001
            raise fail(f"{kind_name}/{doc_name} not found in scope: {e}") from e
        current_raw = current.get("raw") if isinstance(current, dict) else current
        current_spec = (current_raw or {}).get("spec") if isinstance(current_raw, dict) else None
        if not isinstance(current_spec, dict):
            current_spec = {}

        status_prop = schema_props.get("status") if isinstance(schema_props, dict) else None
        if isinstance(status_prop, dict) and "enum" in status_prop:
            if new_status not in status_prop["enum"]:
                raise fail(
                    f"Status '{new_status}' not in {kind_name}.status enum: "
                    f"{status_prop['enum']}"
                )

        from datetime import datetime, timezone
        prev_status = current_spec.get("status")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        spec = dict(current_spec)
        spec["status"] = new_status
        spec["updated_at"] = now
        if new_status in ("done", "resolved", "wont-fix", "duplicate", "cancelled", "reported", "executed"):
            spec.setdefault("closed_at", now)
        if commit_ref:
            commit_refs = list(spec.get("commit_refs") or [])
            if commit_ref not in commit_refs:
                commit_refs.append(commit_ref)
            spec["commit_refs"] = commit_refs
        timeline_entry: dict[str, object] = {
            "at": now,
            "actor": "cli",
            "type": "status_change",
            "from": prev_status,
            "to": new_status,
        }
        if commit_ref:
            timeline_entry["commit_ref"] = commit_ref
        if reason:
            timeline_entry["reason"] = reason
        spec.setdefault("timeline", []).append(timeline_entry)
        raw = {
            "apiVersion": api_version,
            "kind": kind_name,
            "metadata": {"name": doc_name},
            "spec": spec,
        }
        try:
            run_async(dna.docs(scope).put(kind_name, doc_name, raw))
        except Exception as e:  # noqa: BLE001
            raise fail(f"write failed: {e}") from e
    click.secho(
        f"Transitioned {kind_name}/{doc_name}: {prev_status} → {new_status}",
        fg="green",
    )


@doc.command("fields")
@click.argument("kind_name")
@click.option("--scope", default="dna-development")
@click.option("--tenant", default=None)
def fields_help(kind_name: str, scope: str, tenant: str | None) -> None:
    """List the fields a Kind accepts (with type + enum + required marker)."""
    with dna_client(tenant=tenant) as dna:
        descriptor = _fetch_kind_descriptor(dna, scope, kind_name)
    schema = descriptor.get("schema") or {}
    if not isinstance(schema, dict):
        click.secho(f"Kind '{kind_name}' has no schema()", fg="yellow")
        return
    required = set(schema.get("required") or [])
    props = schema.get("properties") or {}
    click.secho(f"Fields for {kind_name}", bold=True)
    click.echo(f"  required: {sorted(required)}")
    click.echo("")
    for name in sorted(props.keys()):
        p = props[name]
        if not isinstance(p, dict):
            continue
        t = p.get("type", "?")
        enum = p.get("enum")
        desc = (p.get("description") or "")[:60]
        marker = " *" if name in required else ""
        enum_str = f" enum={enum}" if enum else ""
        click.echo(f"  {name:<24} ({t}){enum_str}{marker}   {desc}")


@doc.command("create")
@click.argument("kind_name")
@click.argument("doc_name")
@click.option("--spec", "spec_path", default=None, help="Path to JSON file (or `-` for stdin).")
@click.option("--scope", default="dna-development")
@click.option("--tenant", default=None, help="Bind the write to this tenant (overrides DNA_TENANT).")
@click.option("--dry-run", is_flag=True, help="Validate without writing.")
def create(
    kind_name: str,
    doc_name: str,
    spec_path: str | None,
    scope: str,
    tenant: str | None,
    dry_run: bool,
) -> None:
    """Create a new document via the kernel WriterPort."""
    spec = _read_spec(spec_path)
    with dna_client(tenant=tenant) as dna:
        descriptor = _fetch_kind_descriptor(dna, scope, kind_name)
        api_version = descriptor.get("api_version") or "github.com/ruinosus/dna/v1"

        raw = {
            "apiVersion": api_version,
            "kind": kind_name,
            "metadata": {"name": doc_name},
            "spec": spec,
        }
        if dry_run:
            print_json({"dry_run": True, "would_write": raw, "tenant": tenant})
            return
        try:
            run_async(dna.docs(scope).put(kind_name, doc_name, raw))
        except Exception as e:  # noqa: BLE001
            raise fail(f"write failed: {e}") from e
        _eff, _warn = _tenant_write_note(tenant)  # i-020
        if _warn:
            click.secho(f"  ⚠ {_warn}", fg="yellow", err=True)
        suffix = f" (tenant={_eff})" if _eff else " (tenant=unbound/global)"
        click.secho(f"Created {kind_name}/{doc_name} in scope {scope}{suffix}.", fg="green")


@doc.command("delete")
@click.argument("kind_name")
@click.argument("doc_name")
@click.option("--scope", default="dna-development")
@click.option("--tenant", default=None, help="Bind the delete to this tenant (overrides DNA_TENANT).")
@click.option("--yes", is_flag=True, help="Skip confirmation.")
def delete(
    kind_name: str, doc_name: str, scope: str, tenant: str | None, yes: bool,
) -> None:
    """Delete a document from the scope. Asks for confirmation unless --yes."""
    _eff, _warn = _tenant_write_note(tenant)  # i-020: show effective tenant
    if _warn:
        click.secho(f"  ⚠ {_warn}", fg="yellow", err=True)
    suffix = f" (tenant={_eff})" if _eff else " (tenant=unbound/global)"
    if not yes:
        click.confirm(
            f"Delete {kind_name}/{doc_name} from scope {scope}{suffix}?",
            abort=True,
        )
    with dna_client(tenant=tenant) as dna:
        try:
            run_async(dna.docs(scope).delete(kind_name, doc_name))
        except Exception as e:  # noqa: BLE001
            raise fail(f"delete failed: {e}") from e
    click.secho(f"Deleted {kind_name}/{doc_name}{suffix}.", fg="green")


# ---------------------------------------------------------------------------
# `apply` — bundle / marker handling still needs local kernel for
# marker→kind resolution. TODO: add a server-side endpoint that takes
# (bundle_bytes, marker_name) and returns the canonical raw doc, so
# this can also migrate to dna-client. Until then, `dna doc apply`
# requires DNA_SOURCE_URL to be set.
# ---------------------------------------------------------------------------


_BUNDLE_TEXT_EXTS = {
    ".py", ".md", ".markdown", ".txt", ".yaml", ".yml", ".json",
    ".toml", ".cfg", ".ini", ".sh", ".html", ".css", ".js", ".ts",
    ".tsx", ".jsx", ".vue", ".sql",
}
_BUNDLE_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "dist", "build",
    "target", ".pytest_cache", ".ruff_cache", ".mypy_cache", "tasks",
}
_BUNDLE_DOCKERFILE_PREFIXES = ("Dockerfile",)


def _is_bundle_text_file(rel_path: "Path", marker_filename: str) -> bool:
    if rel_path.name == marker_filename:
        return False
    if any(part in _BUNDLE_SKIP_DIRS for part in rel_path.parts):
        return False
    if rel_path.suffix in _BUNDLE_TEXT_EXTS:
        return True
    if any(rel_path.name.startswith(p) for p in _BUNDLE_DOCKERFILE_PREFIXES):
        return True
    return False


def _collect_bundle_files(
    root: "Path", marker_filename: str,
) -> "dict[str, str | bytes]":
    """All bundle entries under ``root`` (excluding the marker + skip dirs):
    text files as ``str``, everything else (fonts, images, audio, archives)
    as ``bytes``. i-062 — the text-only collection dropped binary assets, so
    `dna doc apply` never synced fonts/images to the target source.

    The downstream apply pops these from spec.source_files and writes each via
    ``kernel.write_bundle_entry_async`` (which takes ``str | bytes``).
    """
    out: "dict[str, str | bytes]" = {}
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(root)
        if rel.name == marker_filename:
            continue
        # Skip junk: skip-dirs (.git, __pycache__, …) and dotfiles (.DS_Store).
        if any(part in _BUNDLE_SKIP_DIRS for part in rel.parts):
            continue
        if rel.name.startswith("."):
            continue
        if _is_bundle_text_file(rel, marker_filename):
            try:
                out[str(rel)] = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
        else:
            try:
                out[str(rel)] = f.read_bytes()
            except OSError:
                continue
    return out


def _load_apply_input(path: str, kernel) -> dict:
    """Load `dna doc apply` input — bundle dir, marker file, or YAML/JSON."""
    import yaml as _yaml
    from pathlib import Path as _Path
    from dna.kernel.source.generic_rw import _parse_frontmatter, _parse_body  # noqa: F401
    p = _Path(path)

    if p.is_dir():
        marker_path: _Path | None = None
        kind_name_from_marker: str | None = None
        registered_markers = {}
        for kp in kernel._kinds.values():
            sd = getattr(kp, "storage", None)
            marker = getattr(sd, "marker", None) if sd else None
            if marker:
                registered_markers[marker] = kp.kind
        for child in p.iterdir():
            if child.is_file() and child.name in registered_markers:
                marker_path = child
                kind_name_from_marker = registered_markers[child.name]
                break
        if marker_path is None:
            raise fail(
                f"{path}: directory does not contain a recognized bundle marker. "
                f"Looked for {sorted(registered_markers.keys())}."
            )
        raw_text = marker_path.read_text(encoding="utf-8")
        fm, body = _parse_frontmatter(raw_text, source=str(marker_path))
        if "kind" not in fm:
            fm["kind"] = kind_name_from_marker

        # i-062 — collect text AND binary bundle entries (fonts, images, …).
        source_files = _collect_bundle_files(p, marker_path.name)

        return _build_raw_from_marker(
            marker_path, fm, body, kernel,
            extra_source_files=source_files or None,
        )

    suffix = p.suffix.lower()
    if suffix not in (".md", ".markdown"):
        with open(path, encoding="utf-8") as f:
            raw_text = f.read()
        try:
            raw = _yaml.safe_load(raw_text)
        except _yaml.YAMLError as e:
            raise fail(f"Invalid YAML/JSON in {path}: {e}")
        if not isinstance(raw, dict):
            raise fail(
                f"{path} top-level must be a mapping (apiVersion/kind/metadata/spec)."
            )
        return raw

    raw_text = p.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter(raw_text, source=str(p))
    # i-061 — a single marker file (e.g. AGENT.md) is still a bundle: collect
    # its sibling entries (instruction.md, scripts/, references/) from the
    # parent directory so `dna doc apply path/to/AGENT.md` is equivalent to
    # `dna doc apply path/to/`. Without this, applying the marker alone dropped
    # the instruction_file fragment, zeroing the agent's instruction.
    # i-062 — collect text AND binary siblings (fonts, images, …).
    sibling_files = _collect_bundle_files(p.parent, p.name)
    return _build_raw_from_marker(
        p, fm, body, kernel, extra_source_files=sibling_files or None,
    )


def _build_raw_from_marker(
    marker_path: "Path",
    fm: dict,
    body: str,
    kernel,
    extra_source_files: "dict[str, str] | None" = None,
) -> dict:
    """Build the canonical raw doc dict from a parsed marker file."""
    from dna.kernel.source.generic_rw import _parse_body

    kind_name: str | None = fm.get("kind")
    if not kind_name:
        marker_name = marker_path.name
        for kp in kernel._kinds.values():
            sd = getattr(kp, "storage", None)
            if sd and getattr(sd, "marker", None) == marker_name:
                kind_name = kp.kind
                break
    if not kind_name:
        raise fail(
            f"{marker_path}: cannot infer kind. Add `kind: <KindName>` to the "
            f"frontmatter or use a recognized marker filename."
        )

    sd = kernel.storage_for_kind(kind_name)
    if sd is None:
        raise fail(f"{marker_path}: kind {kind_name!r} is not registered in the kernel.")

    api_version = fm.get("apiVersion") or getattr(
        kernel._kinds.get(kind_name.lower(), object()), "api_version", None,
    )
    if not api_version:
        for kp in kernel._kinds.values():
            if kp.kind == kind_name:
                api_version = getattr(kp, "api_version", None)
                if api_version:
                    break
    if not api_version:
        api_version = "github.com/ruinosus/dna/helix/v1"

    _meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
    name_val = fm.get("name") or _meta.get("name")
    if not name_val:
        if marker_path.parent and marker_path.parent.name:
            name_val = marker_path.parent.name
    if not name_val:
        raise fail(
            f"{marker_path}: missing 'name' in frontmatter (or 'metadata.name')."
        )

    metadata_keys = {"name", "apiVersion", "kind", "description", "labels", "metadata"}
    nested_spec = fm.get("spec") if isinstance(fm.get("spec"), dict) else None
    spec: dict = {
        k: v for k, v in fm.items()
        if k not in metadata_keys and k != "spec"
    }
    if nested_spec:
        spec.update(nested_spec)
    body_field = getattr(sd, "body_field", None)
    body_as = getattr(sd, "body_as", None)
    if body_field and body_as is not None:
        spec[body_field] = _parse_body(body, body_as)
    elif body.strip():
        spec.setdefault("body", body.strip())

    if extra_source_files:
        spec["source_files"] = extra_source_files

    raw = {
        "apiVersion": api_version,
        "kind": kind_name,
        "metadata": {
            "name": name_val,
            **({"description": fm["description"]} if fm.get("description") else {}),
        },
        "spec": spec,
    }
    return raw


def _stamp_created_at_if_in_schema(s, kind_name: str, raw: dict) -> None:
    """Stamp spec.created_at if Kind's schema declares it. Fail-soft."""
    spec = raw.get("spec")
    if not isinstance(spec, dict):
        return
    if spec.get("created_at"):
        return
    try:
        kind_port = next(
            (kp for kp in s.kernel._kinds.values() if getattr(kp, "kind", None) == kind_name),
            None,
        )
        if kind_port is None:
            return
        schema = kind_port.schema() or {}
        props = schema.get("properties") or {}
        if "created_at" not in props:
            return
    except Exception:  # noqa: BLE001
        return

    from datetime import datetime, timezone
    spec["created_at"] = datetime.now(timezone.utc).isoformat()


def _load_apply_inputs(path: str, kernel) -> list[dict]:
    """Load `dna doc apply` input as a LIST of raw docs.

    YAML/JSON files may contain MULTIPLE documents separated by ``---``
    (a YAML stream); each is applied independently. Bundle directories
    and markdown marker files stay single-doc (markers have one body).

    Single-doc files still return a one-element list, so the apply loop
    behaves identically to the legacy single-doc path.
    """
    from pathlib import Path as _Path

    p = _Path(path)
    suffix = p.suffix.lower()
    # Multi-doc only makes sense for plain YAML/JSON streams. Bundle dirs
    # and markdown markers carry exactly one document by construction.
    if p.is_dir() or suffix in (".md", ".markdown"):
        return [_load_apply_input(path, kernel)]

    import yaml as _yaml

    with open(path, encoding="utf-8") as f:
        raw_text = f.read()
    try:
        docs = [d for d in _yaml.safe_load_all(raw_text) if d is not None]
    except _yaml.YAMLError as e:
        raise fail(f"Invalid YAML/JSON in {path}: {e}")
    if not docs:
        raise fail(f"{path} contains no documents.")
    # Single-doc YAML: defer to _load_apply_input so its validation +
    # behavior (and any test monkeypatch of it) stays the single source of
    # truth for the common case. Multi-doc only kicks in for `---` streams.
    if len(docs) == 1:
        return [_load_apply_input(path, kernel)]
    for idx, d in enumerate(docs):
        if not isinstance(d, dict):
            raise fail(
                f"{path} document #{idx} top-level must be a mapping "
                f"(apiVersion/kind/metadata/spec)."
            )
    return docs


def _apply_one(s, raw: dict, *, path: str, doc_index: int | None,
               tenant: str | None, dry_run: bool) -> None:
    """Validate + upsert a single raw doc. Shared by single- and multi-doc apply."""
    label = f"{path}" if doc_index is None else f"{path} document #{doc_index}"
    if not isinstance(raw, dict):
        raise fail(
            f"{label} top-level must be a mapping (apiVersion/kind/metadata/spec)."
        )
    for key in ("apiVersion", "kind", "metadata"):
        if key not in raw:
            raise fail(f"{label} missing required field: {key}")
    name = (raw.get("metadata") or {}).get("name")
    if not name:
        raise fail(f"{label} missing metadata.name")
    kind_name = raw["kind"]

    # i-061 — bundle entries (e.g. the `instruction_file` fragment, scripts/,
    # references/) ride in `spec.source_files` from the loader. Pop them BEFORE
    # the doc write so they don't bloat the stored spec, then persist each as a
    # bundle entry AFTER the doc exists. Source-agnostic (FS / SQLite / Postgres)
    # via kernel.write_bundle_entry_async. Without this, applying an
    # instruction_file Agent to a fresh bundle leaves no instruction
    # fragment → resolve_document re-resolves it to empty → broken agent.
    _bundle_entries: dict = {}
    _spec_for_entries = raw.get("spec")
    if isinstance(_spec_for_entries, dict):
        _src = _spec_for_entries.pop("source_files", None)
        if isinstance(_src, dict):
            _bundle_entries = _src

    current = s.get_doc(kind_name, name)
    if current is None:
        action = "CREATED"
    else:
        # Compare RAW against RAW (i-059). `current.spec` is the PARSED spec —
        # the Kind's schema defaults are injected at parse time — while the
        # file's spec is raw, so a resolved-vs-raw compare NEVER converges for
        # a Kind with defaults: re-applying an identical file was UPDATED (and
        # a version bump) forever. `write_document` persists the RAW doc, so
        # the write is a true no-op exactly when the STORED raw spec equals
        # the incoming one — that is the pair that decides UNCHANGED/UPDATED.
        # (Raw-raw also stays honest the other way: a file that drops a key
        # whose value equalled the default DOES change the stored doc — and
        # would silently track future default changes — so it must stay
        # UPDATED, which resolved-vs-resolved would miss.)
        current_raw = current.raw if isinstance(getattr(current, "raw", None), dict) else {}
        current_spec = current_raw.get("spec")
        if not isinstance(current_spec, dict):
            # Legacy/synthetic doc with no raw round-trip — fall back to the
            # parsed spec rather than mis-reporting every apply as UPDATED.
            current_spec = dict(current.spec) if current.spec else {}
        new_spec = raw.get("spec") or {}
        if _json.dumps(current_spec, sort_keys=True, default=str) == _json.dumps(
            new_spec, sort_keys=True, default=str
        ):
            action = "UNCHANGED"
        else:
            action = "UPDATED"

    if dry_run:
        # --dry-run must actually VALIDATE (its help says "Validate without
        # writing"), not just report the CREATE/UPDATE verb. Run the SAME
        # spec↔schema check the write path enforces so a schema-violating doc
        # (e.g. a Guardrail `severity: critical`) is rejected here too, instead
        # of silently passing dry-run and only failing on the real write
        # (i-validation-shallow).
        try:
            s.kernel.validate_document(s.scope, kind_name, name, raw)
        except Exception as e:  # noqa: BLE001
            raise fail(f"{label} failed schema validation: {e}")
        print_json(
            {
                "dry_run": True,
                "action": action,
                "kind": kind_name,
                "name": name,
                "scope": s.scope,
                "tenant": tenant,
            }
        )
        return

    if action == "UNCHANGED":
        click.secho(f"UNCHANGED {kind_name}/{name}", fg="yellow")
        return

    _stamp_created_at_if_in_schema(s, kind_name, raw)

    # Tenant binding: explicit --tenant > DNA_TENANT > unbound (legacy/global).
    # i-020: surface the EFFECTIVE tenant + warn on allow-list mismatch.
    effective, _tenant_warn = _tenant_write_note(tenant)
    if _tenant_warn:
        click.secho(f"  ⚠ {_tenant_warn}", fg="yellow", err=True)
    kernel = s.kernel.with_tenant(effective) if effective else s.kernel
    try:
        s.run(kernel.write_document(s.scope, kind_name, name, raw))
    except Exception as e:  # noqa: BLE001
        # Surface prompt-budget errors with a clear message instead of the
        # generic "write failed:" wrapper. The error message from
        # PromptBudgetExceededError already includes model, cap, and
        # actionable advice — prepending "write failed:" would obscure it.
        try:
            from dna.kernel.prompt.budget import PromptBudgetExceededError
            if isinstance(e, PromptBudgetExceededError):
                click.secho(str(e), fg="red", err=True)
                raise SystemExit(1)
        except ImportError:
            pass
        raise fail(f"write failed: {e}")
    # i-061 — persist bundle entries now that the parent doc exists. These were
    # popped from spec.source_files above; the marker file (AGENT.md) is already
    # written by write_document, and source_files excludes it by construction.
    for _entry_path, _content in _bundle_entries.items():
        try:
            # i-083 — pass text entries as str and binary entries as bytes so
            # the adapter routes them to the right column (content vs
            # content_binary). Force-encoding str→bytes here buried every text
            # payload (instruction fragments, asset.json, scripts) in the
            # binary column. _collect_bundle_files already returns str for text
            # extensions and bytes for binary.
            _data = (
                _content if isinstance(_content, (str, bytes, bytearray))
                else str(_content)
            )
            s.run(kernel.write_bundle_entry_async(
                s.scope, kind_name, name, _entry_path, _data, tenant=effective,
            ))
        except Exception as _be:  # noqa: BLE001
            click.secho(
                f"  ⚠ bundle entry {_entry_path!r} not persisted: {_be}",
                fg="yellow", err=True,
            )
    s.holder.reload()
    fg = "green" if action == "CREATED" else "cyan"
    suffix = f" (tenant={effective})" if effective else " (tenant=unbound/global)"
    click.secho(f"{action} {kind_name}/{name} in scope {s.scope}{suffix}.", fg=fg)


@doc.command("apply")
@click.argument("path", type=click.Path(exists=True, dir_okay=True, readable=True))
@click.option("--scope", default=None, help="Override scope (default from env or doc).")
@click.option("--tenant", default=None, help="Bind the apply to this tenant (overrides DNA_TENANT).")
@click.option("--dry-run", is_flag=True, help="Validate without writing.")
def apply(path: str, scope: str | None, tenant: str | None, dry_run: bool) -> None:
    """Upsert document(s) from a YAML/JSON file, a bundle marker, or a bundle directory.

    YAML/JSON files may hold MULTIPLE documents separated by ``---`` (a YAML
    stream); each is applied independently in order. Single-doc files behave
    exactly as before.

    NOTE: this command still uses the local kernel (via dna_session) because
    bundle/marker → kind resolution requires walking registered Kinds. Other
    `dna doc` commands run via dna-client and don't need DNA_SOURCE_URL set.
    """
    with open_session(scope) as s:
        raws = _load_apply_inputs(path, s.kernel)
        multi = len(raws) > 1
        for idx, raw in enumerate(raws):
            _apply_one(
                s, raw,
                path=path,
                doc_index=idx if multi else None,
                tenant=tenant,
                dry_run=dry_run,
            )
