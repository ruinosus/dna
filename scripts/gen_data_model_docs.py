#!/usr/bin/env python3
"""Generate the DNA data model (MER) — docs/reference/data-model.md.

Source-of-truth generator, same shape as ``gen_cli_docs.py`` /
``gen_kinds_docs.py``: boot ``Kernel.auto()``, introspect, emit. Nothing on
the page is hand-written, so nothing on it can quietly stop being true.

**Why this is generated.** Two hand-written MER snapshots were published and
both aged out inside a day (a table removed, a control table swapped, a new
quota counter, plan moving from workspace to account). That is the same
failure mode an audit spent a day removing from this repo: a declaration
shipped, reality diverging in silence. ``scripts/data_model_guard.py``
regenerates this page and fails when the committed copy disagrees.

Two levels, because they answer different questions:

* **LOGICAL — Kinds and their references.** The output that matters. Every
  registered ``KindPort``, its ``x-dna-ref`` declarations (i-040), its
  ``dep_filters``, and a conservative name-convention pass for what neither
  declares.
* **PHYSICAL — the real tables.** From ``build_metadata()``. Deliberately
  framed as the low-information diagram it is: a generic document store,
  seven tables, ZERO foreign keys. The page says so rather than faking depth.

**Four edge tiers, and the ranking is the point.** A MER whose lines all look
alike would imply the model knows more than it does:

1. ``declared`` — a field carries ``x-dna-ref``. The kernel resolves it at
   write time (``DNA_REF_VALIDATION``). This is the only tier the system
   actually enforces.
2. ``composition`` — ``dep_filters`` names the target Kind. A real
   declaration, but it exists to drive PROMPT COMPOSITION and is never
   checked against stored data, so it can dangle silently.
3. ``inferred`` — nothing declares it; the field NAME resolves to a
   registered Kind. Drawn dashed. A convention, not a contract.
4. ``unresolved`` — reference-shaped field with no confident target. NOT
   drawn; tabulated. This tier is the honest measure of what the model still
   cannot express, and it is meant to shrink as ``x-dna-ref`` spreads.

**The projection itself moved into the SDK** — ``dna.kernel.query.kind_graph``
— because a REST route (``GET /v1/graph/kinds``) now serves the same graph.
This script no longer OWNS the tiering, the denylist or the undeclarable
table; it imports them and renders. One computation, two consumers: a second
reading of ``x-dna-ref`` that could disagree with this page is precisely the
failure ``references.py`` exists to end.

**Partitioning.** 76 Kinds in one ``erDiagram`` is an unreadable hairball, so
the detail diagrams are split by the Kind's own alias prefix (``sdlc-``,
``helix-``, …) — a grouping that comes from the data, not from an editorial
opinion about what belongs together. A group-level overview sits above them.

Determinism (the guard is worthless without it): every collection is sorted,
nothing embeds a timestamp, hostname, version or absolute path. Run it twice,
the bytes are identical — ``gen_cli_docs.py`` failed this and its guard became
PR noise nobody reads.

Usage:
    python3 scripts/gen_data_model_docs.py            # (re)generate
    python3 scripts/gen_data_model_docs.py --check    # fail if it would change

Requires the SDK installed (``pip install -e packages/sdk-py``).
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

# The projection this page renders — the tiers, the denylist, the
# undeclarable table and the ``x-dna-ref`` reading itself — lives in the SDK,
# so the REST route ``GET /v1/graph/kinds`` and this page cannot disagree
# about what the model says. This script owns the RENDERING and nothing else.
#
# ⚠️ The two gap tables come through ``undeclarable_for``/``suppressed_for``,
# NOT from the raw dicts. Reading the raw tables was a second computation
# wearing the first one's clothes: it printed every ROW while the route served
# what the projection FOUND, so the page went on listing 6 undeclarable
# references where the route had 16, and 8 suppressions where 5 happened.
from dna.kernel.query.kind_graph import (
    build_edges,
    kind_rows,
    suppressed_for,
    undeclarable_for,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OUT = _REPO_ROOT / "docs" / "reference" / "data-model.md"

# Minimum edges for a group to get its own diagram. Below this the group's
# edges still appear in the tables and the overview — a diagram of one box
# and one line is noise.
_MIN_EDGES_FOR_DIAGRAM = 2

# Above this, one diagram per group is still a hairball (the `sdlc` group
# alone carries most of the graph), so it is split further BY TIER. That
# split is mechanical, and it happens to put the enforced work-item spine —
# the thing worth watching — in a diagram of its own instead of burying it
# under fifty composition lines.
_MAX_EDGES_PER_DIAGRAM = 20


def _md(text: str) -> str:
    """Flatten prose for a Markdown table cell."""
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


# --- model extraction --------------------------------------------------------


def _load_kinds() -> list[dict]:
    """Every registered Kind as a row, from the live registry."""
    from dna.kernel import Kernel

    return kind_rows(Kernel.auto().kind_ports())


def _load_tables() -> dict[str, list[dict]]:
    """The physical table model, per dialect, from the Alembic target metadata."""
    from dna.adapters.sqlalchemy_.schema import build_metadata

    out: dict[str, list[dict]] = {}
    for label, is_pg in (("postgresql", True), ("sqlite", False)):
        tables = build_metadata(is_pg=is_pg)
        rows: list[dict] = []
        for name in sorted(tables.metadata.tables):
            table = tables.metadata.tables[name]
            rows.append({
                "name": name,
                "columns": [
                    {
                        "name": c.name, "type": str(c.type),
                        "pk": bool(c.primary_key), "nullable": bool(c.nullable),
                    }
                    for c in table.columns
                ],
                "foreign_keys": sorted(
                    f"{fk.parent.name} -> {fk.target_fullname}"
                    for c in table.columns for fk in c.foreign_keys
                ),
            })
        out[label] = rows
    return out


# --- Mermaid -----------------------------------------------------------------


def _mm(name: str) -> str:
    """Mermaid entity ids must be bare identifiers."""
    return re.sub(r"[^0-9A-Za-z_]", "_", name)


_TIER_LABEL = {"declared": "", "composition": " (dep)", "inferred": " (inferred)"}


def _er(nodes: list[str], edges: list[dict]) -> str:
    """One Mermaid erDiagram. Dashed line = inferred (undeclared)."""
    out = io.StringIO()
    out.write("```mermaid\nerDiagram\n")
    for kind in sorted(nodes):
        out.write(f"    {_mm(kind)}\n")
    for e in sorted(edges, key=lambda x: (x["source"], x["field"], x["target"])):
        right = "}o" if e["cardinality"] == "many" else "||"
        link = ".." if e["tier"] == "inferred" else "--"
        label = e["field"] + _TIER_LABEL[e["tier"]]
        if e["polymorphic"]:
            label += " *"
        out.write(
            f"    {_mm(e['source'])} }}o{link}{right} "
            f"{_mm(e['target'])} : \"{label}\"\n"
        )
    out.write("```\n\n")
    return out.getvalue()


def _overview(kinds: list[dict], edges: list[dict]) -> str:
    """Group-level flowchart: which parts of the model reference which."""
    group_of = {k["kind"]: k["group"] for k in kinds}
    pairs: dict[tuple[str, str], int] = {}
    for e in edges:
        a, b = group_of.get(e["source"], "?"), group_of.get(e["target"], "?")
        pairs[(a, b)] = pairs.get((a, b), 0) + 1

    out = io.StringIO()
    out.write("```mermaid\nflowchart LR\n")
    for group in sorted({g for pair in pairs for g in pair}):
        count = sum(1 for k in kinds if k["group"] == group)
        # Deliberately a single-line label: a `<br/>` here survives the
        # Markdown→HTML step only as an escaped entity, so keeping the label
        # plain avoids depending on how the renderer unescapes it.
        noun = "Kind" if count == 1 else "Kinds"
        out.write(f"    {_mm(group)}[\"{group} ({count} {noun})\"]\n")
    for (a, b), n in sorted(pairs.items()):
        if a == b:
            continue
        out.write(f"    {_mm(a)} -->|{n}| {_mm(b)}\n")
    out.write("```\n\n")
    return out.getvalue()


# --- page --------------------------------------------------------------------


def _page(kinds: list[dict], edges: list[dict], unresolved: list[dict],
          tables: dict) -> str:
    from dna.adapters.sqlalchemy_.schema import FOREIGN_TABLES

    out = io.StringIO()
    by_tier = {t: [e for e in edges if e["tier"] == t]
               for t in ("declared", "composition", "inferred")}

    out.write("# Data model (MER)\n\n")
    out.write(
        "!!! info \"Generated from source — do not edit\"\n\n"
        "    Emitted by `scripts/gen_data_model_docs.py` from the live\n"
        "    `Kernel.auto()` registry and the SQLAlchemy table model.\n"
        "    `scripts/data_model_guard.py` fails CI when this page and a\n"
        "    fresh regeneration disagree. Edit the generator, never this file.\n\n"
    )
    out.write(
        "DNA's data model has two levels. The **logical** model — Kinds and\n"
        "the references between them — carries the meaning. The **physical**\n"
        "model is a generic document store that tells you almost nothing about\n"
        "the domain, and this page says so rather than dressing it up.\n\n"
    )

    # ---- four owners --------------------------------------------------------
    out.write("## One database, four schema owners\n\n")
    out.write(
        "A MER showing only the SDK's tables and stopping there misleads by\n"
        "omission. **A single Postgres instance is shared by four independent\n"
        "schema owners**, each migrating only its own tables:\n\n"
    )
    out.write("| Owner | Migrates | On this page |\n| --- | --- | --- |\n")
    out.write(
        "| DNA SDK (this repo) | the document-store tables below, via its own "
        "Alembic tree | yes — fully |\n"
        "| dna-cloud portal | its Prisma schema (accounts, plans, billing — "
        "real relational tables with real foreign keys) | **no** — separate "
        "repo, separate migration tool |\n"
        "| Copilot service | `copilot_thread` and friends | **no** |\n"
        "| LangGraph runtime | `checkpoint*` / `store*` | **no** |\n\n"
    )
    out.write(
        "The SDK's Alembic run is explicitly told not to have opinions about\n"
        "tables it does not own — otherwise autogenerate would propose\n"
        "dropping another owner's data. That exclusion list is machine-\n"
        "readable, so it is reproduced from source rather than asserted:\n\n"
    )
    out.write("| Excluded from the SDK's autogenerate |\n| --- |\n")
    for name in sorted(FOREIGN_TABLES):
        out.write(f"| `{name}` |\n")
    out.write("\n")

    # ---- logical ------------------------------------------------------------
    out.write("## Logical model — Kinds and their references\n\n")
    out.write(
        f"{len(kinds)} Kinds are registered. Each is a document, not a table: a\n"
        "Kind costs a YAML descriptor and zero migrations, which is the point\n"
        "of an open type system. The cost is that references between Kinds are\n"
        "not database foreign keys — they are fields holding a name.\n\n"
    )

    out.write("### How to read the edges\n\n")
    out.write(
        "Not every line here is equally trustworthy, and pretending otherwise\n"
        "would be the whole problem. Four tiers, strongest first:\n\n"
        "| Tier | Drawn | What it means |\n| --- | --- | --- |\n"
        "| **Declared** | solid | The field carries `x-dna-ref`. The kernel "
        "resolves it at write time — the only tier the system enforces. |\n"
        "| **Composition** (`dep`) | solid | `dep_filters` names the target "
        "Kind. A real declaration, but it drives prompt composition and is "
        "never checked against stored data. |\n"
        "| **Inferred** | dashed | Nothing declares it; the field NAME "
        "resolves to a Kind. A convention, not a contract. |\n"
        "| **Unresolved** | not drawn | Reference-shaped, no confident target. "
        "Tabulated below. |\n\n"
        "`*` on a label marks a polymorphic reference (several possible "
        "target Kinds).\n\n"
    )

    total = len(edges)
    d, c, i = (len(by_tier[t]) for t in ("declared", "composition", "inferred"))
    out.write(
        f"**{total} edges: {d} declared, {c} composition-only, {i} inferred** "
        f"— plus {len(unresolved)} reference-shaped fields left unresolved and "
        f"{len(undeclarable_for(kinds))} known-undeclarable ones.\n\n"
    )
    out.write(
        "!!! warning \"Only the declared tier cannot dangle\"\n\n"
        "    `dep_filters` declares a target *Kind*; nothing validates the\n"
        "    *value*. A `Feature.owner` naming an Actor that does not exist is\n"
        "    written without complaint. Solid therefore means \"the model knows\n"
        "    what this points at\", not \"this resolves\". Closing that gap is\n"
        "    what `x-dna-ref` does, one field at a time.\n\n"
    )

    # ---- overview -----------------------------------------------------------
    out.write("### Overview — how the groups reference each other\n\n")
    out.write(
        "Kinds are grouped by alias prefix (`sdlc-`, `helix-`, …) — a grouping\n"
        "that comes from the data. Arrows are counts of edges between groups;\n"
        "self-references are omitted here and shown in the detail diagrams.\n\n"
    )
    out.write(_overview(kinds, edges))

    # ---- per-group ----------------------------------------------------------
    group_of = {k["kind"]: k["group"] for k in kinds}
    groups: dict[str, list[dict]] = {}
    for e in edges:
        groups.setdefault(group_of.get(e["source"], "ungrouped"), []).append(e)

    out.write("### Detail by group\n\n")
    out.write(
        f"All {len(kinds)} Kinds in one diagram is an unreadable hairball, so\n"
        f"each group with at least {_MIN_EDGES_FOR_DIAGRAM} edges gets its\n"
        f"own. A group carrying more than {_MAX_EDGES_PER_DIAGRAM} edges is\n"
        "split again by tier, which keeps the enforced edges legible instead\n"
        "of losing them among the unvalidated ones. A box from another group\n"
        "appearing here is a cross-group reference.\n\n"
    )
    for group in sorted(groups):
        group_edges = groups[group]
        if len(group_edges) < _MIN_EDGES_FOR_DIAGRAM:
            continue
        if len(group_edges) <= _MAX_EDGES_PER_DIAGRAM:
            chunks = [("", group_edges)]
        else:
            chunks = [
                (tier, [e for e in group_edges if e["tier"] == tier])
                for tier in ("declared", "composition", "inferred")
            ]
        for tier, chunk in chunks:
            if not chunk:
                continue
            nodes = sorted(
                {e["source"] for e in chunk} | {e["target"] for e in chunk}
            )
            heading = f"`{group}`" + (f" — {tier}" if tier else "")
            out.write(f"#### {heading} ({len(chunk)} edges)\n\n")
            out.write(_er(nodes, chunk))

    small = sorted(g for g, e in groups.items() if len(e) < _MIN_EDGES_FOR_DIAGRAM)
    if small:
        out.write(
            f"Groups with fewer than {_MIN_EDGES_FOR_DIAGRAM} edges "
            f"(listed, not drawn): {', '.join(f'`{g}`' for g in small)}.\n\n"
        )

    # ---- edge tables --------------------------------------------------------
    out.write("### Declared edges (`x-dna-ref`)\n\n")
    out.write(
        "Enforced at write time. This table is the part of the graph the\n"
        "system will not let you break.\n\n"
    )
    _edge_table(out, by_tier["declared"], group_of)

    out.write("### Composition edges (`dep_filters` only)\n\n")
    out.write(
        "Declared for prompt composition, never validated against stored\n"
        "data. Each row is a candidate for an `x-dna-ref` promotion.\n\n"
    )
    _edge_table(out, by_tier["composition"], group_of)

    out.write("### Inferred edges (name convention)\n\n")
    out.write(
        "Not declared anywhere. Each row is this generator matching a field\n"
        "name against the Kind registry — useful, and fallible.\n\n"
    )
    _edge_table(out, by_tier["inferred"], group_of)

    # ---- gaps ---------------------------------------------------------------
    out.write("## What this model cannot express\n\n")
    out.write(
        "A MER that implies completeness is worse than none. These are the\n"
        "known gaps, generated alongside everything else so they cannot be\n"
        "quietly dropped.\n\n"
    )

    out.write("### Known-undeclarable references\n\n")
    out.write(
        "Real edges that `x-dna-ref` deliberately does NOT declare. It resolves\n"
        "targets by **document name**, and these are keyed by something else —\n"
        "declaring them would produce false write-time violations on perfectly\n"
        "valid data.\n\n"
        "Two families. **Keyed** ones name the Kind they really point at (an\n"
        "opaque id, a role id, a tier id); they are the concrete backlog for a\n"
        "future `x-dna-ref-key`. **Composite** ones carry the Kind IN the value\n"
        "(`Story:s-thing`, `Narrative/X`, `{kind, name}`), so `Really points at`\n"
        "is `any` — there is no single target to name. The composite family is\n"
        "derived from the schemas, never enumerated: a field either declares\n"
        "`x-dna-ref-composite` or its object shape requires `kind` + `name`.\n\n"
    )
    out.write("| Kind | Field | Really points at | Why undeclarable |\n")
    out.write("| --- | --- | --- | --- |\n")
    for row in undeclarable_for(kinds):
        out.write(f"| `{row['source']}` | `{row['field']}` | "
                  f"`{row['target']}` | {_md(row['reason'])} |\n")
    out.write("\n")

    out.write("### Unresolved reference-shaped fields\n\n")
    out.write(
        "Fields that clearly point at something the model cannot name. This\n"
        "shrinks when references get declared, not when the generator gets\n"
        "cleverer.\n\n"
        "`Origin` is the column that keeps the list honest. **declared** and\n"
        "**composition** rows are declarations the model cannot honour —\n"
        "somebody wrote a target and it does not resolve. **shape-inferred**\n"
        "rows are the projection guessing from a field NAME, and are usually\n"
        "not references at all: an OAuth `client_id`, a Stripe customer id, an\n"
        "IdP subject. Reading the two alike is how a real broken reference\n"
        "arrives invisible in a list of false alarms.\n\n"
    )
    if unresolved:
        out.write("| Kind | Field | Origin | Why unresolved |\n"
                  "| --- | --- | --- | --- |\n")
        for e in unresolved:
            out.write(f"| `{e['source']}` | `{e['field']}` | "
                      f"`{e['origin']}` | {e['reason']} |\n")
    else:
        out.write("_None._\n")
    out.write("\n")

    out.write("### Suppressed name matches\n\n")
    out.write(
        "The name-convention pass matched these and each is wrong. Listed\n"
        "rather than silently dropped, so the suppression is auditable.\n\n"
        "What the pass DID, not what the denylist says it would: an entry only\n"
        "fires where the field name resolves to exactly one Kind, so an entry\n"
        "can go inert without being touched — `plan` stopped resolving when\n"
        "`PricingPlan` joined `Plan`, and ambiguity now stops those matches.\n"
        "Such entries stay in the source (the day the ambiguity ends they are\n"
        "the only thing stopping a wrong edge) and are absent here.\n\n"
    )
    out.write("| Kind | Field | Why the match is wrong |\n| --- | --- | --- |\n")
    for row in suppressed_for(kinds):
        out.write(f"| `{row['source']}` | `{row['field']}` | "
                  f"{_md(row['reason'])} |\n")
    out.write("\n")

    connected = {e["source"] for e in edges} | {e["target"] for e in edges}
    isolated = sorted({k["kind"] for k in kinds} - connected)
    out.write(f"### Kinds with no reference edge ({len(isolated)})\n\n")
    out.write(
        "Standalone documents — configuration, composition-plane behaviour, or\n"
        "record Kinds whose links are simply not modelled yet.\n\n"
    )
    out.write(", ".join(f"`{k}`" for k in isolated) + "\n\n")

    # ---- physical -----------------------------------------------------------
    pg, lite = tables["postgresql"], tables["sqlite"]
    fk_count = sum(len(t["foreign_keys"]) for t in pg)

    out.write("## Physical model — the real tables\n\n")
    out.write(
        "!!! note \"This diagram carries little information, by design\"\n\n"
        f"    {len(pg)} tables on Postgres ({len(lite)} on SQLite) and\n"
        f"    **{fk_count} foreign keys**. They are a generic document store:\n"
        "    `documents` holds every Kind, of every type, as JSON in a\n"
        "    `content` column keyed by `(scope, kind, name, tenant)`. Adding a\n"
        "    Kind adds rows, never a table — so the physical diagram cannot\n"
        "    show you the domain. The logical model above is where the domain\n"
        "    lives. This section exists to be accurate, not to look deep.\n\n"
    )

    out.write("### Postgres\n\n")
    out.write("```mermaid\nerDiagram\n")
    for table in pg:
        out.write(f"    {_mm(table['name'])} {{\n")
        for col in table["columns"]:
            typ = re.sub(r"[^0-9A-Za-z_]", "_", col["type"]) or "unknown"
            out.write(
                f"        {typ} {col['name']}{' PK' if col['pk'] else ''}\n"
            )
        out.write("    }\n")
    out.write("```\n\n")
    out.write(
        "No lines connect these boxes because there are no foreign keys to\n"
        "draw. The join key is `(scope, kind, name, tenant)`, applied in\n"
        "application code.\n\n"
    )

    out.write("### Dialect differences\n\n")
    lite_names = {t["name"] for t in lite}
    out.write(
        "The dialects are genuinely disjoint — Postgres tables carry a `dna_`\n"
        "prefix, SQLite's do not, and Postgres has tables SQLite lacks.\n\n"
    )
    out.write("| Postgres | SQLite |\n| --- | --- |\n")
    for table in pg:
        twin = table["name"][4:] if table["name"].startswith("dna_") else table["name"]
        out.write(
            f"| `{table['name']}` | "
            f"{'`' + twin + '`' if twin in lite_names else '—'} |\n"
        )
    out.write("\n")

    out.write("### Columns\n\n")
    for table in pg:
        out.write(f"#### `{table['name']}`\n\n")
        out.write("| Column | Type | Key | Nullable |\n| --- | --- | --- | --- |\n")
        for col in table["columns"]:
            out.write(
                f"| `{col['name']}` | `{col['type']}` | "
                f"{'PK' if col['pk'] else ''} | "
                f"{'yes' if col['nullable'] else ''} |\n"
            )
        out.write("\n")

    return out.getvalue()


def _edge_table(out: io.StringIO, edges: list[dict], group_of: dict) -> None:
    if not edges:
        out.write("_None._\n\n")
        return
    out.write("| From | Field | To | Cardinality | Cross-group |\n")
    out.write("| --- | --- | --- | --- | --- |\n")
    for e in sorted(edges, key=lambda x: (x["source"], x["field"], x["target"])):
        cross = group_of.get(e["source"]) != group_of.get(e["target"])
        field = f"`{e['field']}`" + (" *(poly)*" if e["polymorphic"] else "")
        out.write(
            f"| `{e['source']}` | {field} | `{e['target']}` | "
            f"{e['cardinality']} | {'yes' if cross else ''} |\n"
        )
    out.write("\n")


def _build() -> str:
    kinds = _load_kinds()
    edges, unresolved = build_edges(kinds)
    return _page(kinds, edges, unresolved, _load_tables())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="fail if regeneration would change the page")
    args = ap.parse_args()

    content = _build()
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    old = _OUT.read_text(encoding="utf-8") if _OUT.exists() else None

    if args.check:
        if old != content:
            print("data model page is stale — run "
                  "scripts/gen_data_model_docs.py", file=sys.stderr)
            return 1
        print("data model page is up to date")
        return 0

    if old != content:
        _OUT.write_text(content, encoding="utf-8")
    print(f"Wrote {_OUT.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
