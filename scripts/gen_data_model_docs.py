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

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OUT = _REPO_ROOT / "docs" / "reference" / "data-model.md"

# Suffixes that make a field "reference-shaped": it points at SOMETHING even
# when we cannot say at what. This is what makes the unresolved tier a
# meaningful gap list rather than a grep for nouns.
_REF_SUFFIXES = ("_refs", "_ref", "_oid", "_ids", "_id", "_slug")

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

# --- inference denylist: (Kind, field) -> why the NAME match is WRONG --------
# The name-convention pass matches a field name against registered Kind names.
# These matches are false positives, each confirmed against the field's own
# schema description. They are NOT silently dropped: the page prints this
# table with the justifications so the suppression is auditable.
#
# Shrink-only by convention (docs_coverage_guard.py style): an entry goes away
# when the field gets a real ``x-dna-ref``, never grows to paper over a guess.
INFERENCE_DENYLIST: dict[tuple[str, str], str] = {
    ("Tenant", "plan"): (
        "billing/feature tier (a Tier `tier_id`), not the SDLC `Plan` Kind"
    ),
    ("Organization", "plan_ref"): (
        "the DNA Cloud Tier this org is on, not the SDLC `Plan` Kind"
    ),
    ("Workspace", "plan_ref"): (
        "DEPRECATED and never read — billing is per ACCOUNT (workspace → "
        "account_id → AccountPlan); also not the SDLC `Plan` Kind"
    ),
    ("AgentSession", "tool"): (
        "provenance enum of the AI coding tool that produced the session "
        "(claude-code | cursor | cline | …), not a `Tool` document"
    ),
    ("Copilot", "tenant"): (
        "inbound-tenant handling mode for the emitted serving layer, not a "
        "reference to a `Tenant` document"
    ),
    ("AuditLog", "actor"): (
        "the request identity string from claims (email/sub, or 'dev-user'), "
        "not a reference to an `Actor` document"
    ),
}

# --- known-undeclarable references -------------------------------------------
# Real edges that ``x-dna-ref`` deliberately does NOT declare, because it
# resolves targets by DOCUMENT NAME and these are keyed by something else.
# Declaring them would produce false write-time violations on valid data.
# This is the concrete backlog for a future ``x-dna-ref-key`` (i-040 follow-up)
# and it belongs on the page: a MER that hides these implies a completeness
# the model does not have.
UNDECLARABLE: dict[tuple[str, str], tuple[str, str]] = {
    ("Project", "workspace_id"): (
        "Workspace",
        "keyed by the Workspace's opaque generated `workspace_id`, not its "
        "document name",
    ),
    ("WorkspaceMembership", "workspace_id"): (
        "Workspace",
        "same opaque `workspace_id` key",
    ),
    ("WorkspaceMembership", "role"): (
        "Role",
        "keyed by `role_id` (owner/admin/member/guest), not the document name",
    ),
    ("Membership", "role"): (
        "Role",
        "keyed by `role_id`, not the document name",
    ),
    ("Organization", "plan_ref"): (
        "Tier",
        "keyed by `tier_id` (free/pro/enterprise), not the document name",
    ),
    ("Comment", "target_ref"): (
        "any",
        "a composite `Kind:name` string — needs parsing, not a name lookup",
    ),
}


def _md(text: str) -> str:
    """Flatten prose for a Markdown table cell."""
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def _attr(port: object, name: str):
    value = getattr(port, name, None)
    return value() if callable(value) else value


# --- model extraction --------------------------------------------------------


def _load_kinds() -> list[dict]:
    """Every registered Kind as a plain sorted dict — the logical entities."""
    from dna.kernel import Kernel
    from dna.kernel.references import declared_references

    kinds: list[dict] = []
    for port in Kernel.auto().kind_ports():
        name = _attr(port, "kind")
        if not name:
            continue
        try:
            schema = port.schema() or {}
        except Exception:  # pragma: no cover - defensive
            schema = {}
        alias = str(_attr(port, "alias") or "")
        kinds.append(
            {
                "kind": str(name),
                "alias": alias,
                "group": alias.split("-", 1)[0] if alias else "ungrouped",
                "plane": str(_attr(port, "plane") or ""),
                "dep_filters": {
                    str(k): str(v)
                    for k, v in dict(_attr(port, "dep_filters") or {}).items()
                },
                "refs": declared_references(port),
                "properties": dict((schema or {}).get("properties") or {}),
            }
        )
    kinds.sort(key=lambda k: k["kind"])
    return kinds


def _target_index(kinds: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """alias -> Kind, and lowercased-token -> Kind.

    A token maps only when it resolves to exactly ONE Kind; an ambiguous token
    resolves to nothing rather than to a guess.
    """
    by_alias = {k["alias"]: k["kind"] for k in kinds if k["alias"]}
    buckets: dict[str, set[str]] = {}
    for k in kinds:
        tokens = {k["kind"].lower()}
        if k["alias"]:
            tokens.add(k["alias"].lower().rsplit("-", 1)[-1])
            tokens.add(k["alias"].lower())
        for token in tokens:
            buckets.setdefault(token, set()).add(k["kind"])
    by_token = {t: sorted(v)[0] for t, v in buckets.items() if len(v) == 1}
    return by_alias, by_token


def _normalize(field: str) -> str:
    """Strip a reference suffix and a trailing plural from a field name."""
    token = field.lower()
    for suffix in _REF_SUFFIXES:
        if token.endswith(suffix) and len(token) > len(suffix):
            token = token[: -len(suffix)]
            break
    if token.endswith("s") and not token.endswith("ss"):
        token = token[:-1]
    return token


def _cardinality(prop: dict) -> str:
    return "many" if (prop or {}).get("type") == "array" else "one"


def _build_edges(kinds: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (edges, unresolved).

    Each edge carries a ``tier``: ``declared`` (x-dna-ref) > ``composition``
    (dep_filters) > ``inferred`` (name convention). A field declared by
    ``x-dna-ref`` is never also emitted as a lower tier — the strongest
    statement about a field wins, so no line is drawn twice.
    """
    by_alias, by_token = _target_index(kinds)
    by_kind = {k["kind"]: k for k in kinds}

    edges: list[dict] = []
    unresolved: list[dict] = []

    for k in kinds:
        source = k["kind"]
        props = k["properties"]
        claimed: set[str] = set()

        # -- tier 1: x-dna-ref (declared AND enforced at write) --------------
        for ref in k["refs"]:
            claimed.add(ref.field)
            for target in ref.targets:
                if target not in by_kind:
                    unresolved.append({
                        "source": source, "field": ref.field,
                        "reason": f"`x-dna-ref` names `{_md(target)}`, "
                                  "which no registered Kind provides",
                    })
                    continue
                edges.append({
                    "source": source, "field": ref.field, "target": target,
                    "cardinality": "many" if ref.is_array else "one",
                    "tier": "declared", "polymorphic": ref.polymorphic,
                })

        # -- tier 2: dep_filters (declared for composition, never checked) ---
        for field, spec in sorted(k["dep_filters"].items()):
            if field in claimed:
                continue
            targets = sorted({
                by_alias[a] for a in str(spec).split("|") if a in by_alias
            })
            if not targets:
                unresolved.append({
                    "source": source, "field": field,
                    "reason": f"`dep_filters` names alias(es) "
                              f"`{_md(str(spec))}` which no registered Kind "
                              "claims",
                })
                continue
            claimed.add(field)
            for target in targets:
                edges.append({
                    "source": source, "field": field, "target": target,
                    "cardinality": _cardinality(props.get(field, {})),
                    "tier": "composition", "polymorphic": len(targets) > 1,
                })

        # -- tiers 3 & 4: whatever nothing declared --------------------------
        for field in sorted(props):
            if field in claimed:
                continue
            token = _normalize(field)
            target = by_token.get(token)
            ref_shaped = field.lower().endswith(_REF_SUFFIXES)

            if target == source:
                # `Workspace.workspace_id`, `Tier.tier_id`: own identity.
                continue
            if target and (source, field) in INFERENCE_DENYLIST:
                continue
            if (source, field) in UNDECLARABLE:
                continue
            if target:
                edges.append({
                    "source": source, "field": field, "target": target,
                    "cardinality": _cardinality(props.get(field, {})),
                    "tier": "inferred", "polymorphic": False,
                })
            elif ref_shaped and token not in by_token:
                unresolved.append({
                    "source": source, "field": field,
                    "reason": f"reference-shaped, but `{token}` matches no "
                              "registered Kind",
                })

    edges.sort(key=lambda e: (e["tier"], e["source"], e["field"], e["target"]))
    unresolved.sort(key=lambda e: (e["source"], e["field"]))
    return edges, unresolved


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
        f"{len(UNDECLARABLE)} known-undeclarable ones.\n\n"
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
        "valid data. This is the concrete backlog for a future `x-dna-ref-key`.\n\n"
    )
    out.write("| Kind | Field | Really points at | Why undeclarable |\n")
    out.write("| --- | --- | --- | --- |\n")
    for (kind, field), (target, why) in sorted(UNDECLARABLE.items()):
        out.write(f"| `{kind}` | `{field}` | `{target}` | {_md(why)} |\n")
    out.write("\n")

    out.write("### Unresolved reference-shaped fields\n\n")
    out.write(
        "Fields that clearly point at something the model cannot name. This\n"
        "shrinks when references get declared, not when the generator gets\n"
        "cleverer.\n\n"
    )
    if unresolved:
        out.write("| Kind | Field | Why unresolved |\n| --- | --- | --- |\n")
        for e in unresolved:
            out.write(f"| `{e['source']}` | `{e['field']}` | {e['reason']} |\n")
    else:
        out.write("_None._\n")
    out.write("\n")

    out.write("### Suppressed name matches\n\n")
    out.write(
        "The name-convention pass matched these and each is wrong. Listed\n"
        "rather than silently dropped, so the suppression is auditable.\n\n"
    )
    out.write("| Kind | Field | Why the match is wrong |\n| --- | --- | --- |\n")
    for (kind, field), why in sorted(INFERENCE_DENYLIST.items()):
        out.write(f"| `{kind}` | `{field}` | {_md(why)} |\n")
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
    edges, unresolved = _build_edges(kinds)
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
