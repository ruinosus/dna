"""Minimal provenance renderer over the DNA composition engine.

This does NOT reimplement composition. It annotates it: it reads the SAME
layout template the kernel renders, the SAME resolved documents, and the SAME
dep_filters / flatten_in_context wiring, then attributes each rendered SECTION
of the composed system prompt back to the source artifact (file) that produced
it — with that artifact's content hash, version, and layer origin.

Correctness is proven by a byte-equality assertion: the concatenation of the
attributed segments MUST equal ``mi.build_prompt(agent)`` exactly.

Run:
    python render_provenance.py           # base composition
    python render_provenance.py acme      # with the acme tenant overlay
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import chevron

from dna import Kernel

BASE = Path(__file__).resolve().parent / ".dna"
SCOPE = "provenance-demo"


# ── hashing / version / path — best-effort, reused from lock.py's scheme ──────
def doc_hash(doc: Any) -> str:
    raw = getattr(doc, "raw", None) or {
        "apiVersion": doc.api_version, "kind": doc.kind,
        "metadata": dict(doc.metadata), "spec": dict(doc.spec),
    }
    return hashlib.sha256(
        json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:12]


def doc_version(doc: Any) -> str:
    raw_meta = (getattr(doc, "raw", None) or {}).get("metadata", {}) or {}
    return (
        doc.metadata.get("version")
        or doc.spec.get("version")
        or raw_meta.get("version")
        or "—"
    )


def doc_path(doc: Any, tenant: str | None) -> str:
    """Locate the on-disk file for a doc by scanning the scope tree.

    Prefers the tenant overlay path when a tenant layer is active and the file
    exists there (that is exactly what the resolver picked)."""
    roots = []
    if tenant:
        roots.append(BASE / "tenants" / tenant / "scopes" / SCOPE)
    roots.append(BASE / SCOPE)
    for root in roots:
        if not root.exists():
            continue
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            try:
                txt = f.read_text()
            except Exception:
                continue
            # name match: frontmatter/yaml `name:` or dir name
            if re.search(rf"(?m)^\s*name:\s*{re.escape(doc.name)}\s*$", txt) or f.parent.name == doc.name:
                return str(f.relative_to(BASE))
    return "?"


# ── the renderer ──────────────────────────────────────────────────────────────
_TOKEN = re.compile(r"\{\{\{(.*?)\}\}\}|\{\{#(.*?)\}\}(.*?)\{\{/\2\}\}|\{\{(.*?)\}\}", re.DOTALL)


def segment_template(template: str):
    """Split a layout template into ordered (kind, payload) segments.

    kinds: 'literal' | 'var' (triple/double var) | 'section' (name, inner)."""
    segments = []
    pos = 0
    for m in _TOKEN.finditer(template):
        if m.start() > pos:
            segments.append(("literal", template[pos:m.start()]))
        if m.group(1) is not None:            # {{{triple}}}
            segments.append(("var", m.group(1).strip()))
        elif m.group(2) is not None:          # {{#section}}inner{{/section}}
            segments.append(("section", (m.group(2).strip(), m.group(3))))
        elif m.group(4) is not None:          # {{double}}
            segments.append(("var", m.group(4).strip()))
        pos = m.end()
    if pos < len(template):
        segments.append(("literal", template[pos:]))
    return segments


def build_index(mi, agent_doc):
    """Map context variables / aliases → the source Document(s)."""
    kinds = mi._kinds
    flatten_owner: dict[str, Any] = {}   # spec-field  -> doc
    alias_docs: dict[str, list] = {}     # kind alias  -> [docs]
    for d in mi.documents:
        kp = kinds.get((d.api_version, d.kind))
        if not kp:
            continue
        alias_docs.setdefault(kp.alias, []).append(d)
        if getattr(kp, "flatten_in_context", False):
            for k in d.spec.keys():
                flatten_owner[k] = d
    return flatten_owner, alias_docs


def resolve_layout(mi, agent_doc) -> str:
    spec = agent_doc.spec
    tmpl = spec.get("promptTemplate") or spec.get("prompt_template")
    if tmpl:
        return tmpl
    kp = mi._kinds.get((agent_doc.api_version, agent_doc.kind))
    layout = spec.get("layout")
    if layout and kp:
        return kp.layout_template(layout)
    return kp.prompt_template() if kp else "{{{agent.instruction}}}"


def render_provenance(tenant: str | None = None):
    mi0 = Kernel.quick(SCOPE, base_dir=str(BASE))
    mi = mi0.resolve({"tenant": tenant}) if tenant else mi0

    # find the default agent
    root = mi.root
    kp_root = mi._kinds.get((root.api_version, root.kind))
    agent_name = kp_root.get_default_agent_name(root)
    agent_doc = next(d for d in mi.documents if d.kind == "Agent" and d.name == agent_name)

    layout_name = agent_doc.spec.get("layout", "default")
    template = resolve_layout(mi, agent_doc)
    flatten_owner, alias_docs = build_index(mi, agent_doc)

    # rebuild the exact Mustache context via the real PromptBuilder
    from dna.kernel.prompt_builder import PromptBuilder
    pb = PromptBuilder(mi)
    slots = {
        "skills": agent_doc.spec.get("skills") or [],
        "guardrails": agent_doc.spec.get("guardrails") or [],
    }
    ctx = pb._build_context(agent_doc, None, slots)

    rows = []       # (section_label, source_desc, doc, rendered_text)
    for kind, payload in segment_template(template):
        if kind == "literal":
            rows.append(("(template joiner)", None, None, payload))
        elif kind == "var":
            var = payload
            rendered = chevron.render("{{{" + var + "}}}", ctx)
            src = None
            label = f"{{{{{var}}}}}"
            if var.startswith("agent."):
                src = agent_doc
                label = f"Agent: {var.split('.',1)[1]}"
            elif var in flatten_owner:
                src = flatten_owner[var]
                label = f"{src.kind}: {var}"
            rows.append((label, var, src, rendered))
        elif kind == "section":
            alias, inner = payload
            entries = ctx.get(alias, []) or []
            docs_by_name = {d.name: d for d in alias_docs.get(alias, [])}
            for entry in entries:
                rendered = chevron.render(inner, {**ctx, **entry})
                src = docs_by_name.get(entry.get("name"))
                kname = (src.kind if src else alias)
                rows.append((f"{kname}: {entry.get('name')}", alias, src, rendered))

    # ── correctness gate: attributed segments == real build_prompt ────────────
    composed = "".join(r[3] for r in rows).rstrip("\n")
    official = mi.build_prompt(agent=agent_name)
    assert composed == official, "ATTRIBUTION DRIFT — segments != build_prompt"

    return {
        "scope": SCOPE, "tenant": tenant, "agent": agent_name,
        "layout": layout_name, "rows": rows, "official": official,
        "agent_doc": agent_doc,
    }


def overlay_note(doc, var) -> str:
    """The kernel stamps ``has_overlay`` + ``overlay_fields`` into a resolved
    doc's raw metadata when a tenant layer touched it. Surface that signal."""
    raw_meta = (getattr(doc, "raw", None) or {}).get("metadata", {}) or {}
    if not raw_meta.get("has_overlay"):
        return ""
    fields = raw_meta.get("overlay_fields") or []
    if var in fields or (var and var.split(".")[-1] in fields):
        return f"◄ OVERRIDDEN by tenant overlay (spec.{var})"
    return "◄ base metadata; overlay touched " + ",".join(fields)


def print_report(res):
    tlabel = res["tenant"] or "(base, no tenant)"
    print(f"\n{'='*78}\nCOMPOSED AGENT: {res['agent']}   scope={res['scope']}   tenant={tlabel}   layout={res['layout']}\n{'='*78}")
    print("\nSECTION → SOURCE ARTIFACT (in composition order)\n")
    print(f"{'#':>2}  {'PROMPT SECTION':<32}{'SOURCE ARTIFACT (file)':<62}{'HASH':<14}{'VER':<12}{'ORIGIN'}")
    print("-" * 132)
    i = 0
    overlay_rows = []
    for label, var, doc, text in res["rows"]:
        if doc is None and not text.strip():
            continue  # skip pure whitespace joiners in the table
        if doc is None:
            print(f"{'':>2}  {label:<32}{'— (layout template, helix-agent)':<62}{'—':<14}{'—':<12}{'—'}")
            continue
        i += 1
        path = doc_path(doc, res["tenant"])
        note = overlay_note(doc, var)
        if note.startswith("◄ OVERRIDDEN"):
            overlay_rows.append((i, note))
        print(f"{i:>2}  {label:<32}{path:<62}{doc_hash(doc):<14}{str(doc_version(doc)):<12}{doc.origin}")
    if overlay_rows:
        print("\nOVERRIDES / CONFLICTS:")
        for n, note in overlay_rows:
            print(f"   §{n}  {note}")
    print("\nCOMPOSED PROMPT (verified byte-identical to kernel build_prompt):\n")
    for line in res["official"].splitlines():
        print(f"    {line}")


if __name__ == "__main__":
    tenant = sys.argv[1] if len(sys.argv) > 1 else None
    print_report(render_provenance(tenant))
