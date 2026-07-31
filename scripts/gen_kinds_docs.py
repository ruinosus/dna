#!/usr/bin/env python3
"""Generate the Kinds reference (docs/reference/kinds/) from the live kernel.

Source-of-truth generator: boots ``Kernel.auto()``, walks every registered
``KindPort``, and emits the Kind catalogue from each Kind's own metadata
(``kind``/``alias``/``api_version``/``plane``/flags), prose (``docs``) and
JSON ``schema()``. The KindDefinition meta-schema
(``docs/schemas/kind-definition.schema.json``) is summarised on the index —
it is the format of the ``*.kind.yaml`` descriptors that declare these Kinds.

Kinds are grouped by **plane**: *composition* Kinds compose into prompts;
*record* Kinds are queryable data rows. One page per plane, plus an index
table. Output is sorted and timestamp-free → deterministic (``--check``).

Usage:
    python3 scripts/gen_kinds_docs.py            # (re)generate the pages
    python3 scripts/gen_kinds_docs.py --check    # fail if regeneration would change anything

Requires the ``dna`` SDK installed (``pip install -e packages/sdk-py``).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OUT_DIR = _REPO_ROOT / "docs" / "reference" / "kinds"
_SCHEMA = _REPO_ROOT / "docs" / "schemas" / "kind-definition.schema.json"

_PLANE_BLURB = {
    "composition": (
        "**Composition-plane** Kinds are behaviour that composes into an "
        "agent's prompt (skills, souls, guardrails, …) — resolved through the "
        "layer/tenant overlay engine."
    ),
    "record": (
        "**Record-plane** Kinds are queryable data rows (SDLC work items, "
        "research, evidence, audit log, …) — first-class documents you "
        "`query`/`count` rather than fold into a prompt."
    ),
}


def _md(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def _first_para(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    return text.split("\n\n")[0].replace("\n", " ").strip()


#: Até onde a tabela desce dentro de um schema aninhado.
#:
#: Três níveis cobrem tudo que os Kinds registrados declaram hoje, com folga. O
#: limite não é economia — é o que garante que a geração TERMINA: um schema que
#: se referencie (por `$ref` resolvido ou por engano de construção) penduraria o
#: gerador, e uma referência que nunca termina de ser gerada é pior que uma
#: incompleta.
_MAX_DEPTH = 3


def _type_of(spec: dict) -> str:
    typ = spec.get("type")
    if isinstance(typ, list):
        typ = " \\| ".join(typ)
    return typ or (
        "enum" if "enum" in spec else spec.get("$ref", "").rsplit("/", 1)[-1] or "any"
    )


def _describe(spec: dict) -> str:
    """A descrição do campo, mais os valores que ele aceita.

    O enum entra na descrição porque saber o NOME de um campo sem saber o valor
    deixa quem lê a um passo do erro: `protocol_binding` aceita `JSONRPC`, em
    maiúsculas, e um `jsonrpc` minúsculo é recusado silenciosamente pelo
    cliente A2A oficial (que filtra as interfaces por esse valor exato).
    """
    desc = _md(spec.get("description", ""))
    enum = spec.get("enum")
    if enum:
        valores = ", ".join(f"`{_md(str(v))}`" for v in enum)
        desc = f"{desc} Um de: {valores}." if desc else f"Um de: {valores}."
    return desc.strip()


def _rows(schema: dict, out: io.StringIO, prefix: str = "", depth: int = 0) -> None:
    """Uma linha por campo, descendo nos aninhados.

    Objeto → `pai.filho`; array de objetos → `pai[].filho`. É notação de
    CAMINHO, e não de indentação, porque uma tabela markdown não tem hierarquia
    visual: o caminho é o que diz onde o campo mora, e é copiável.

    `required` é lido do nível DE CADA campo, nunca herdado do pai — herdar
    marcaria como obrigatório um campo que só o é dentro do seu próprio objeto,
    o que é pior que não marcar nada.
    """
    if depth > _MAX_DEPTH:
        return
    props = (schema or {}).get("properties") or {}
    required = set((schema or {}).get("required") or [])
    for name in sorted(props):
        spec = props[name] or {}
        caminho = f"{prefix}{name}"
        req = "yes" if name in required else ""
        out.write(f"| `{caminho}` | {_type_of(spec)} | {req} | {_describe(spec)} |\n")

        if spec.get("properties"):
            _rows(spec, out, prefix=f"{caminho}.", depth=depth + 1)
            continue
        itens = spec.get("items")
        if isinstance(itens, dict) and itens.get("properties"):
            _rows(itens, out, prefix=f"{caminho}[].", depth=depth + 1)


def _schema_table(schema: dict, out: io.StringIO) -> None:
    if not ((schema or {}).get("properties") or {}):
        out.write("_No structured spec fields (free-form or body-only Kind)._\n\n")
        return
    out.write("| Field | Type | Required | Description |\n")
    out.write("| --- | --- | --- | --- |\n")
    _rows(schema, out)
    out.write("\n")


def _kind_meta(port) -> dict:
    def g(attr, default=None):
        v = getattr(port, attr, default)
        return v() if callable(v) else v

    try:
        schema = port.schema() or {}
    except Exception:  # pragma: no cover - defensive
        schema = {}
    return {
        "kind": g("kind"),
        "alias": g("alias"),
        "api_version": g("api_version"),
        "plane": str(g("plane", "") or ""),
        "origin": g("origin"),
        "is_root": bool(g("is_root", False)),
        "is_prompt_target": bool(g("is_prompt_target", False)),
        "display_label": g("display_label"),
        "docs": g("docs", "") or "",
        "schema": schema,
    }


def _plane_page(plane: str, kinds: list[dict]) -> str:
    out = io.StringIO()
    title = plane.capitalize()
    out.write(f"# {title}-plane Kinds\n\n")
    out.write(_PLANE_BLURB.get(plane, "") + "\n\n")
    out.write(
        "!!! info \"Generated from the registered Kinds\"\n\n"
        "    Introspected from `Kernel.auto()` by `scripts/gen_kinds_docs.py`.\n"
        "    Each Kind's spec fields come from its own `schema()`.\n\n"
    )
    for k in kinds:
        out.write(f"## {k['kind']}\n\n")
        out.write(
            f"- **Alias:** `{k['alias']}`\n"
            f"- **apiVersion:** `{k['api_version']}`\n"
            f"- **Plane:** {k['plane']}\n"
        )
        flags = []
        if k["is_root"]:
            flags.append("root")
        if k["is_prompt_target"]:
            flags.append("prompt-target")
        if flags:
            out.write(f"- **Flags:** {', '.join(flags)}\n")
        out.write("\n")
        if k["docs"].strip():
            out.write(k["docs"].strip() + "\n\n")
        out.write("**Spec fields**\n\n")
        _schema_table(k["schema"], out)
    return out.getvalue()


def _index_page(by_plane: dict[str, list[dict]]) -> str:
    out = io.StringIO()
    out.write("# Kinds reference\n\n")
    out.write(
        "A **Kind** is DNA's unit of identity + composition — the equivalent of "
        "a Kubernetes CRD, but for agent behaviour. Every Kind is declared by a "
        "`*.kind.yaml` **KindDefinition** descriptor; the descriptor format is "
        "pinned by [`kind-definition.schema.json`](../../schemas/kind-definition.schema.json)"
        " and summarised below. The catalogue on this page is generated from the "
        "**live registered Kinds** (`Kernel.auto()`), so it cannot drift from the "
        "code.\n\n"
    )

    # KindDefinition meta-schema summary
    try:
        meta = json.loads(_SCHEMA.read_text())
        spec = ((meta.get("properties") or {}).get("spec") or {})
        req = set(spec.get("required") or [])
        props = spec.get("properties") or {}
        out.write("## The KindDefinition descriptor\n\n")
        desc = _first_para(meta.get("description", ""))
        if desc:
            out.write(desc + "\n\n")
        out.write("`spec` fields of a KindDefinition:\n\n")
        out.write("| Field | Required | Description |\n| --- | --- | --- |\n")
        for name in sorted(props):
            p = props[name] or {}
            out.write(f"| `{name}` | {'yes' if name in req else ''} | {_md(p.get('description',''))} |\n")
        out.write("\n")
    except Exception:  # pragma: no cover
        pass

    total = sum(len(v) for v in by_plane.values())
    out.write(f"## Registered Kinds ({total})\n\n")
    for plane in sorted(by_plane):
        out.write(f"### {plane.capitalize()} plane\n\n")
        out.write(_PLANE_BLURB.get(plane, "") + "\n\n")
        out.write("| Kind | Alias | apiVersion |\n| --- | --- | --- |\n")
        for k in by_plane[plane]:
            anchor = k["kind"].lower()
            out.write(f"| [{k['kind']}]({plane}.md#{anchor}) | `{k['alias']}` | `{k['api_version']}` |\n")
        out.write("\n")
    return out.getvalue()


def _build() -> dict[str, str]:
    from dna.kernel import Kernel

    kernel = Kernel.auto()
    metas = [_kind_meta(p) for p in kernel.kind_ports()]
    metas = [m for m in metas if m["kind"]]

    by_plane: dict[str, list[dict]] = {}
    for m in metas:
        by_plane.setdefault(m["plane"] or "other", []).append(m)
    for plane in by_plane:
        by_plane[plane].sort(key=lambda m: m["kind"])

    pages: dict[str, str] = {"index.md": _index_page(by_plane)}
    for plane, kinds in by_plane.items():
        pages[f"{plane}.md"] = _plane_page(plane, kinds)

    return pages


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="fail if regeneration would change files")
    args = ap.parse_args()

    pages = _build()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    changed = []
    for rel, content in pages.items():
        path = _OUT_DIR / rel
        old = path.read_text() if path.exists() else None
        if old != content:
            changed.append(rel)
            if not args.check:
                path.write_text(content)

    if args.check and changed:
        print(f"Kinds docs are stale — run scripts/gen_kinds_docs.py. Drifted: {', '.join(changed)}", file=sys.stderr)
        return 1
    if not args.check:
        print(f"Wrote {len(pages)} Kinds reference pages to {_OUT_DIR.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
