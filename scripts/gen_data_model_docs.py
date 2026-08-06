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
  registered ``KindPort``, its ``spec.relations`` declarations and its
  ``dep_filters``.
* **PHYSICAL — the real tables.** From ``build_metadata()``. Deliberately
  framed as the low-information diagram it is: a generic document store,
  seven tables, ZERO foreign keys. The page says so rather than faking depth.

**Two edge tiers plus a per-edge ``enforced`` flag, and the ranking is the
point.** A MER whose lines all look alike would imply the model knows more than
it does:

1. ``declared`` — the Kind's ``spec.relations`` says so. Drawn solid when the
   kernel RESOLVES it at write time (``DNA_REF_VALIDATION``) and dashed when
   the relation is declared but addressed by something the runtime does not
   follow — a domain key (``by: workspace_id``) or a Kind carried in the value
   (``to: "*"``).
2. ``composition`` — ``dep_filters`` names the target Kind. A real
   declaration, but it exists to drive PROMPT COMPOSITION and is never
   checked against stored data, so it can dangle silently. Never enforced.

``unresolved`` is not a tier: it is the gap list — a declaration the registry
cannot honour, an inverse that does not pair, or a reference-shaped field
nobody declared. NOT drawn; tabulated. It is the honest measure of what the
model still cannot express, and it shrinks as relations get declared.

**The name-convention pass is GONE.** It produced EDGES from a field-name
match, which drew ``KindDefinition.docs → Doc`` from a field of prose and
``StatusReport.insight → IntelInsight`` from a field whose own description says
the target Kind was deleted — and it needed a denylist to suppress the worst of
them. The name SHAPE survives only as an ``undeclared`` gap row, which guesses
no target and therefore needs no suppression table.

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
# ⚠️ Everything here is READ from ``build_edges``/``kind_rows``, never
# recomputed. The two hand-kept gap tables this page used to print
# (``UNDECLARABLE``, ``INFERENCE_DENYLIST``) are gone with the mechanisms that
# needed them; while they existed, reading the raw dicts instead of what the
# projection FOUND made the page list 6 undeclarable references where the route
# had 16, and 8 suppressions where 5 happened.
from dna.kernel.kinds.relations import ANY_TARGET
from dna.kernel.query.kind_graph import build_edges, kind_rows

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


#: What the ``to: "*"`` target is CALLED in a diagram. The raw token sanitizes
#: to a bare underscore, which reads as a rendering accident rather than as a
#: statement — and the statement matters: these relations really do point at a
#: document, they just choose its Kind per value.
_ANY_NODE = "ANY_KIND"


def _mm(name: str) -> str:
    """Mermaid entity ids must be bare identifiers."""
    if name == ANY_TARGET:
        return _ANY_NODE
    return re.sub(r"[^0-9A-Za-z_]", "_", name)


_TIER_LABEL = {"declared": "", "composition": " (dep)"}


def _er(nodes: list[str], edges: list[dict]) -> str:
    """One Mermaid erDiagram. Dashed line = NOT enforced at write time."""
    out = io.StringIO()
    out.write("```mermaid\nerDiagram\n")
    for kind in sorted(nodes):
        out.write(f"    {_mm(kind)}\n")
    for e in sorted(edges, key=lambda x: (x["source"], x["field"], x["target"])):
        right = "}o" if e["cardinality"] == "many" else "||"
        link = "--" if e["enforced"] else ".."
        label = e["field"] + _TIER_LABEL[e["tier"]]
        if e["by"] != "name":
            label += f" [{e['by']}]"
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
        # A ``to: "*"`` relation belongs to no group — its target Kind is
        # chosen per value. Counting it under a "?" group would invent one.
        if e["target"] == ANY_TARGET:
            continue
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
        "would be the whole problem. Two tiers, and one flag that matters more\n"
        "than either:\n\n"
        "| Tier | What it means |\n| --- | --- |\n"
        "| **Declared** | The Kind's `spec.relations` says so — name, target, "
        "cardinality, and (where there is one) the inverse. |\n"
        "| **Composition** (`dep`) | `dep_filters` names the target Kind. A "
        "real declaration, but it drives prompt composition and is never "
        "checked against stored data. |\n\n"
        "**Solid line = the kernel resolves it at write time. Dashed = it does "
        "not.** That is the `enforced` flag, and it is not the same as the "
        "tier: a relation addressed by a domain key (`by: workspace_id`) or "
        "carrying its Kind in the value (`to: *`) is fully declared and "
        "deliberately not followed — resolving by key needs an index the store "
        "does not have, and a second resolution rule beside a live one can "
        "veto data the live one accepts.\n\n"
        "`*` on a label marks a polymorphic relation (several possible target "
        "Kinds, or one chosen per value). `[key]` marks the addressing when it "
        "is not the document name.\n\n"
    )

    total = len(edges)
    d, c = (len(by_tier[t]) for t in ("declared", "composition"))
    enforced = len([e for e in edges if e["enforced"]])
    with_rel = len([k for k in kinds if k["relations"]])
    out.write(
        f"**{total} edges: {d} declared, {c} composition-only — of which "
        f"{enforced} are ENFORCED at write time.** {with_rel} of "
        f"{len(kinds)} Kinds declare at least one relation, and "
        f"{len(unresolved)} fields are listed below as gaps.\n\n"
    )
    out.write(
        "!!! warning \"Declared is not enforced\"\n\n"
        "    `dep_filters` declares a target *Kind*; nothing validates the\n"
        "    *value*. A `Feature.owner` naming an Actor that does not exist is\n"
        "    written without complaint. And a relation addressed by a key says\n"
        "    what the value MEANS without teaching the kernel to follow it. A\n"
        "    line therefore means \"the model knows what this points at\", and\n"
        "    only a SOLID one means \"the runtime checks it\".\n\n"
    )

    # ---- overview -----------------------------------------------------------
    out.write("### Overview — how the groups reference each other\n\n")
    out.write(
        "Kinds are grouped by alias prefix (`sdlc-`, `helix-`, …) — a grouping\n"
        "that comes from the data. Arrows are counts of edges between groups;\n"
        "self-references are omitted here and shown in the detail diagrams.\n\n"
        "Relations whose target is chosen per VALUE (`to: *`) are omitted from\n"
        "this view — they belong to no group, and inventing one for them would\n"
        "be the projection guessing again. They appear in the detail diagrams\n"
        f"against `{_ANY_NODE}` and in the declared-relations table.\n\n"
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
                for tier in ("declared", "composition")
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
    out.write("### Declared relations (`spec.relations`)\n\n")
    out.write(
        "What each Kind says it points at. `Enforced` is the column that\n"
        "matters: `yes` means the kernel resolves the target at write time and\n"
        "the graph gets a data edge; blank means the relation is declared and\n"
        "the runtime does not follow it — read `By` for why.\n\n"
    )
    _edge_table(out, by_tier["declared"], group_of)

    out.write("### Composition edges (`dep_filters` only)\n\n")
    out.write(
        "Declared for prompt composition, never validated against stored\n"
        "data. Each row is a candidate for promotion to a relation.\n\n"
    )
    _edge_table(out, by_tier["composition"], group_of)

    # ---- gaps ---------------------------------------------------------------
    out.write("## What this model cannot express\n\n")
    out.write(
        "A MER that implies completeness is worse than none. These are the\n"
        "known gaps, generated alongside everything else so they cannot be\n"
        "quietly dropped.\n\n"
    )

    out.write("### Gaps\n\n")
    out.write(
        "This shrinks when relations get declared, not when the generator gets\n"
        "cleverer.\n\n"
        "`Origin` is the column that keeps the list honest. **declared**,\n"
        "**composition** and **inverse** rows are declarations the model cannot\n"
        "honour — somebody wrote a target, an alias or an inverse and it does\n"
        "not resolve. **undeclared** rows are fields whose NAME looks like a\n"
        "reference and which nothing declares; they are usually not references\n"
        "at all (an OAuth `client_id`, a Stripe customer id, an IdP subject),\n"
        "and this generator no longer guesses a target for them. Reading the\n"
        "two alike is how a real broken reference arrives invisible in a list\n"
        "of false alarms.\n\n"
        "The **known-undeclarable** table that used to sit here is gone, and\n"
        "its absence is the point: those were real references the annotation\n"
        "could not express. They are declared relations now, in the table\n"
        "above, with `Enforced` blank.\n\n"
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
    out.write("| From | Field | To | Cardinality | By | Enforced | Inverse of "
              "| Cross-group |\n")
    out.write("| --- | --- | --- | --- | --- | --- | --- | --- |\n")
    for e in sorted(edges, key=lambda x: (x["source"], x["field"], x["target"])):
        # A ``*`` target belongs to no group, so it is neither cross-group
        # nor same-group. Reporting `yes` would be an answer to a question
        # that has none.
        cross = (
            e["target"] != ANY_TARGET
            and group_of.get(e["source"]) != group_of.get(e["target"])
        )
        field = f"`{e['field']}`" + (" *(poly)*" if e["polymorphic"] else "")
        inverse = f"`{e['inverse_of']}`" if e["inverse_of"] else ""
        out.write(
            f"| `{e['source']}` | {field} | `{e['target']}` | "
            f"{e['cardinality']} | `{e['by']}` | "
            f"{'yes' if e['enforced'] else ''} | {inverse} | "
            f"{'yes' if cross else ''} |\n"
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
