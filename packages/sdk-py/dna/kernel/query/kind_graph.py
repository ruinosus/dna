"""The SCHEMA graph — which Kinds may point at which, and by which field.

This module answers *one* question: given the registered Kinds, what does the
model say about how they reference each other? It is a projection of the
REGISTRY, not of stored data — no document is read, nothing is written, and
the answer is identical for every caller of a given scope.

Why it lives in the kernel
--------------------------
The projection already existed, inside ``scripts/gen_data_model_docs.py``,
where it computes ``docs/reference/data-model.md``. When a REST route needed
the same graph the honest move was to give the computation one home and two
consumers, not to write it a second time: two readings of ``x-dna-ref`` that
can disagree is exactly the defect ``references.py`` was written to end. The
generator now imports from here; its page is byte-identical, and
``scripts/data_model_guard.py`` proves it.

The declaration itself is read by :func:`dna.kernel.query.references
.declared_references` — the SAME function the write pipeline uses to validate
references at write time. The graph therefore cannot claim an edge the write
path would not enforce.

Four tiers, and the ranking is the point
----------------------------------------
A graph whose lines all looked alike would imply the model knows more than it
does:

1. ``declared`` — the field carries ``x-dna-ref``. The kernel resolves it at
   write time (``DNA_REF_VALIDATION``). **The only tier the system enforces.**
2. ``composition`` — ``dep_filters`` names the target Kind. A real
   declaration, but it exists to drive PROMPT COMPOSITION and is never checked
   against stored data, so it can dangle silently.
3. ``inferred`` — nothing declares it; the field NAME resolves to exactly one
   registered Kind. A convention, not a contract.
4. ``unresolved`` — reference-shaped field with no confident target. NOT an
   edge; returned as a gap. This tier is the honest measure of what the model
   still cannot express, and it is meant to shrink as ``x-dna-ref`` spreads.

What this projection deliberately cannot see is stated, not hidden, by
:data:`COVERAGE_LIMITS` — which travels WITH the graph so that no consumer can
render it as "all the relations". On the measurement of 06/08/2026 the model
carried 109 schema edges of which 16 were declared; a screen that dropped the
qualifier would be asserting a completeness nothing in this repo has.

Determinism is a hard requirement (the docs guard is worthless without it):
every collection is sorted and nothing embeds a timestamp, hostname or path.
"""
from __future__ import annotations

from typing import Any, Iterable

from dna.kernel.query.references import declared_references

#: Edge tiers, strongest first. Ordered — consumers rank by index.
TIERS: tuple[str, ...] = ("declared", "composition", "inferred")

#: The tiers the runtime actually ENFORCES on write. A list, not a bare
#: string: derived by the consumer instead of hardcoded, and it grows if
#: ``dep_filters`` is ever promoted to a validated declaration.
ENFORCED_TIERS: tuple[str, ...] = ("declared",)

# Suffixes that make a field "reference-shaped": it points at SOMETHING even
# when we cannot say at what. This is what makes the unresolved tier a
# meaningful gap list rather than a grep for nouns.
REF_SUFFIXES: tuple[str, ...] = ("_refs", "_ref", "_oid", "_ids", "_id", "_slug")

# --- inference denylist: (Kind, field) -> why the NAME match is WRONG --------
# The name-convention pass matches a field name against registered Kind names.
# These matches are false positives, each confirmed against the field's own
# schema description. They are NOT silently dropped: the generated data-model
# page prints this table with the justifications so the suppression is
# auditable, and the REST envelope reports how many were suppressed.
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
    ("Memory", "namespace"): (
        "MIF's hierarchical memory scope path (`_semantic/decisions`, §10) — a "
        "string axis inside the document, not the `KindNamespace` Kind, whose "
        "alias `tenant-kind-namespace` merely ends in the same token"
    ),
    ("RemoteAgent", "skills"): (
        "the A2A Card's own `skills[]` (id/name/description/tags/examples) — "
        "structured self-description of what the remote agent can do, not a "
        "reference to the `Skill` Kind (agentskills), which merely shares "
        "the singular of the field name"
    ),
}

# --- known-undeclarable references -------------------------------------------
# Real edges that ``x-dna-ref`` deliberately does NOT declare, because it
# resolves targets by DOCUMENT NAME and these are keyed by something else.
# Declaring them would produce false write-time violations on valid data.
# This is the concrete backlog for a future ``x-dna-ref-key`` (i-040 follow-up)
# and it belongs in every answer: a graph that hides these implies a
# completeness the model does not have.
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

# --- what the projection cannot see, travelling WITH the projection ----------
# Machine-readable ``code`` first, prose ``detail`` second. The code is what a
# UI switches on (its own copy, in its own catalogue, in its own language);
# the detail is documentation for whoever reads the raw answer. Neither is a
# rendered string — a screen that printed ``detail`` verbatim would be
# shipping English from a backend, which this project does not do.
#
# Enumerated here rather than assembled per-caller for the same reason the
# denylist is: a caveat that each consumer restates is a caveat one consumer
# will eventually forget.
COVERAGE_LIMITS: tuple[dict[str, str], ...] = (
    {
        "code": "schema_not_data",
        "detail": (
            "These edges say which Kinds MAY point at which, through which "
            "field. They say nothing about which DOCUMENTS point at which — "
            "that is a different graph, derived at write time, and this "
            "projection does not serve it."
        ),
    },
    {
        "code": "declared_tier_only_enforced",
        "detail": (
            "Only the `declared` tier is resolved by the kernel at write time. "
            "`composition` edges come from `dep_filters`, which drives prompt "
            "composition and is never checked against stored data; `inferred` "
            "edges are this projection matching a field NAME against the "
            "registry. Both can be wrong, and neither can dangle loudly."
        ),
    },
    {
        "code": "top_level_properties_only",
        "detail": (
            "`x-dna-ref` is read from the schema's first-level `properties` "
            "only. A reference nested under `spec.foo.bar`, inside `items`, or "
            "behind `$ref`/`oneOf`/`anyOf` is invisible to this graph — and is "
            "equally invisible to the write-time validation, so the two agree."
        ),
    },
    {
        "code": "keyed_references_undeclarable",
        "detail": (
            "`x-dna-ref` resolves a target by document NAME. Fields keyed by "
            "something else (an opaque id, a role id, a composite `Kind:name` "
            "string) are real references that cannot be declared today; they "
            "are listed under `undeclarable` instead of drawn as edges."
        ),
    },
    {
        "code": "suppressed_name_matches",
        "detail": (
            "Some name-convention matches are known false positives (a `plan` "
            "that is a billing tier, a `tool` that is a provenance enum) and "
            "are suppressed. `coverage.suppressed` counts them."
        ),
    },
)


def _attr(port: object, name: str):
    value = getattr(port, name, None)
    return value() if callable(value) else value


def kind_rows(ports: Iterable[Any]) -> list[dict]:
    """Every registered Kind as a plain sorted dict — the logical entities.

    A row carries what the graph needs and nothing else: identity
    (``kind``/``alias``/``group``/``plane``), the two declarations that can
    name a target (``refs`` from ``x-dna-ref``, ``dep_filters``), and the raw
    ``properties`` the name-convention pass reads. A Kind whose ``schema()``
    raises contributes an empty one rather than taking the caller down.
    """
    kinds: list[dict] = []
    for port in ports:
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


def target_index(kinds: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
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
    for suffix in REF_SUFFIXES:
        if token.endswith(suffix) and len(token) > len(suffix):
            token = token[: -len(suffix)]
            break
    if token.endswith("s") and not token.endswith("ss"):
        token = token[:-1]
    return token


def _cardinality(prop: dict) -> str:
    return "many" if (prop or {}).get("type") == "array" else "one"


def _md(text: str) -> str:
    """Flatten prose so it survives a Markdown table cell unbroken."""
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def build_edges(kinds: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return ``(edges, unresolved)`` for the rows from :func:`kind_rows`.

    Each edge carries a ``tier``: ``declared`` (x-dna-ref) > ``composition``
    (dep_filters) > ``inferred`` (name convention). A field declared by
    ``x-dna-ref`` is never also emitted as a lower tier — the strongest
    statement about a field wins, so no line is drawn twice.

    An ``x-dna-ref`` naming a Kind no registry provides does NOT become a
    dangling edge: it becomes an ``unresolved`` row. A graph is a set of
    relations between things that exist; an authoring typo is a gap, and
    printing it as an edge would let a screen draw a node for a Kind nobody
    registered.
    """
    by_alias, by_token = target_index(kinds)
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
            ref_shaped = field.lower().endswith(REF_SUFFIXES)

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


def undeclarable_for(kinds: list[dict]) -> list[dict]:
    """The known-undeclarable references whose Kind is in ``kinds``.

    Filtered rather than dumped whole: telling a scope about a field of a Kind
    it does not register would be describing somebody else's model.
    """
    registered = {k["kind"] for k in kinds}
    return [
        {"source": source, "field": field, "target": target, "reason": why}
        for (source, field), (target, why) in sorted(UNDECLARABLE.items())
        if source in registered
    ]


def suppressed_for(kinds: list[dict]) -> list[dict]:
    """The suppressed name matches whose Kind is in ``kinds`` — same rule."""
    registered = {k["kind"] for k in kinds}
    return [
        {"source": source, "field": field, "reason": why}
        for (source, field), why in sorted(INFERENCE_DENYLIST.items())
        if source in registered
    ]


def coverage(
    kinds: list[dict],
    edges: list[dict],
    unresolved: list[dict],
    undeclarable: list[dict],
    suppressed: list[dict],
) -> dict[str, Any]:
    """What this graph covers — the counters a screen must qualify itself with.

    Every number is DERIVED from the collections it describes; none is
    enumerated by hand. That is the lesson of ``guardas-enumeracao-vs-
    derivacao``: a hand-kept count goes stale silently and then the guard that
    reads it is green for the wrong reason.
    """
    per_tier = {tier: 0 for tier in TIERS}
    for e in edges:
        per_tier[e["tier"]] = per_tier.get(e["tier"], 0) + 1
    return {
        "kinds": len(kinds),
        "edges": len(edges),
        **per_tier,
        "unresolved": len(unresolved),
        "undeclarable": len(undeclarable),
        "suppressed": len(suppressed),
        "enforced_tiers": list(ENFORCED_TIERS),
        "limits": [dict(limit) for limit in COVERAGE_LIMITS],
    }


def build_kind_graph(ports: Iterable[Any]) -> dict[str, Any]:
    """The whole schema graph, as the wire envelope — nodes, edges, gaps, and
    the coverage statement that keeps a consumer from calling it complete.

    ``scope`` is NOT set here: this function knows Kinds, not deployments. The
    caller that resolved the registry stamps it.
    """
    rows = kind_rows(ports)
    edges, unresolved = build_edges(rows)
    undeclarable = undeclarable_for(rows)
    suppressed = suppressed_for(rows)
    return {
        "kinds": [
            {
                "kind": r["kind"],
                "alias": r["alias"],
                "group": r["group"],
                "plane": r["plane"],
            }
            for r in rows
        ],
        "edges": [
            {
                "from_kind": e["source"],
                "field": e["field"],
                "to_kind": e["target"],
                "cardinality": e["cardinality"],
                "tier": e["tier"],
                "polymorphic": e["polymorphic"],
            }
            for e in edges
        ],
        "unresolved": [
            {"kind": u["source"], "field": u["field"], "reason": u["reason"]}
            for u in unresolved
        ],
        "undeclarable": [
            {
                "kind": u["source"], "field": u["field"],
                "target": u["target"], "reason": u["reason"],
            }
            for u in undeclarable
        ],
        "coverage": coverage(rows, edges, unresolved, undeclarable, suppressed),
    }
