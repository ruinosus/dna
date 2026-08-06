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

And ``unresolved`` itself ranks, for the same reason
----------------------------------------------------
Measured 06/08/2026: all 25 unresolved rows carried the SAME reason — a field
NAME ending in ``_id``/``_ref``/``_refs`` that matched no Kind. None was a
declaration. (Two of the 25 were not gaps at all: see ``composite_undeclarable``
below. 23 remain, still all of one origin.) Yet the wire said only ``reason``,
in English prose, so a screen
could not tell a broken DECLARATION from the projection's own guess and the
portal presented all of them as "declarations that do not resolve" — false for
every one. ``AgentCatalogEntry.client_id`` is an OAuth client id,
``PlanBinding.stripe_customer_id`` is a Stripe id; no Kind should exist for
either.

So each row carries :data:`UNRESOLVED_ORIGINS` in ``origin``:

* ``declared`` — ``x-dna-ref`` names a Kind no registry provides;
* ``composition`` — ``dep_filters`` names an alias no Kind claims;
* ``shape-inferred`` — nothing declared anything; the field NAME looked like a
  reference and resolved to nothing. Usually not a reference at all.

The first two are CLAIMS somebody made and the model cannot honour — an
authoring error worth alerting on. The third is this projection guessing.
:data:`DECLARED_ORIGINS` names the first two so a consumer DERIVES "is this an
alarm?" instead of hard-coding it, exactly as :data:`ENFORCED_TIERS` does for
the edge tiers — and it is the reason ``reason`` never needs translating: the
prose stays for whoever reads the raw answer, the enum is what a screen
switches on.

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

from dna.kernel.query.references import composite_references, declared_references

#: Edge tiers, strongest first. Ordered — consumers rank by index.
TIERS: tuple[str, ...] = ("declared", "composition", "inferred")

#: The tiers the runtime actually ENFORCES on write. A list, not a bare
#: string: derived by the consumer instead of hardcoded, and it grows if
#: ``dep_filters`` is ever promoted to a validated declaration.
ENFORCED_TIERS: tuple[str, ...] = ("declared",)

#: Why a field landed in ``unresolved`` — the machine-readable half of
#: ``reason``. Ordered strongest-claim first, like :data:`TIERS`.
UNRESOLVED_ORIGINS: tuple[str, ...] = ("declared", "composition", "shape-inferred")

#: The origins that mean somebody DECLARED a reference the model cannot
#: honour: an authoring error to fix, not noise to page through. A list, not a
#: bare string, for the same reason ``ENFORCED_TIERS`` is one — a consumer
#: derives "does this deserve alarm?" instead of hard-coding the answer.
DECLARED_ORIGINS: tuple[str, ...] = ("declared", "composition")

#: The ``target`` reported for a reference whose Kind is chosen per VALUE (a
#: composite ``Kind:name`` pointer). Not a Kind name, and deliberately not
#: mistakable for one.
POLYMORPHIC_TARGET = "any"

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
#
# ⚠️ An entry can go INERT without going away, and three have. The name pass
# only resolves a token claimed by exactly ONE Kind; the metering rename put
# ``PricingPlan`` beside ``Plan``, so ``plan`` is now ambiguous and the three
# ``plan``/``plan_ref`` entries suppress nothing — ambiguity does. They stay,
# because the day that ambiguity ends the wrong edge comes back and this is
# the only thing that would stop it. What does NOT stay is counting them:
# ``suppressed_for`` reports what the pass actually suppressed.
INFERENCE_DENYLIST: dict[tuple[str, str], str] = {
    ("Tenant", "plan"): (
        "billing/feature tier (a `PricingPlan` `tier_id`), not the SDLC "
        "`Plan` Kind"
    ),
    ("Organization", "plan_ref"): (
        "the DNA Cloud `PricingPlan` this org is on, not the SDLC `Plan` Kind"
    ),
    ("Workspace", "plan_ref"): (
        "DEPRECATED and never read — billing is per ACCOUNT (workspace → "
        "account_id → `PlanBinding`); also not the SDLC `Plan` Kind"
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

# --- known-undeclarable references: KEYED BY SOMETHING ELSE -------------------
# Real edges that ``x-dna-ref`` deliberately does NOT declare, because it
# resolves targets by DOCUMENT NAME and these are keyed by something else — an
# opaque generated id, a role id, a tier id. Declaring them would produce false
# write-time violations on valid data.
# This is the concrete backlog for a future ``x-dna-ref-key`` (i-040 follow-up)
# and it belongs in every answer: a graph that hides these implies a
# completeness the model does not have.
#
# ⚠️ Each entry repeats a Kind NAME, and a repeated name is a name that can be
# renamed elsewhere: this table went on naming `Tier` for a release after the
# metering rename made it `PricingPlan`, and `GET /v1/kinds/registry/Tier`
# answered 404 while the graph kept citing it. Nothing failed, because nothing
# checked the table against the registry. Something does now —
# ``tests/test_kind_graph_registry.py`` resolves every target here against the
# LIVE registry, so a rename that misses this table fails there instead of
# shipping a dead citation.
#
# The COMPOSITE family (`Kind:name` pointers) used to live here too and no
# longer does: it is derived from the schema — see ``composite_undeclarable``.
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
        "PricingPlan",
        "keyed by `tier_id` (free/pro/enterprise), not the document name",
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
            "are listed under `undeclarable` instead of drawn as edges. A "
            "composite one reports `target: any` — its Kind is chosen per "
            "VALUE, so the schema cannot name one."
        ),
    },
    {
        "code": "unresolved_is_not_all_broken",
        "detail": (
            "`unresolved` holds two different things and `origin` separates "
            "them. `declared` and `composition` rows are DECLARATIONS whose "
            "target does not resolve — an authoring error somebody must fix. "
            "`shape-inferred` rows are this projection guessing from a field "
            "NAME (`_id`/`_ref`/`_refs`) and are usually not references at "
            "all: an OAuth `client_id`, a Stripe customer id, an IdP subject. "
            "`coverage.declared_origins` names the ones that are claims, so a "
            "screen ranks them without reading `reason`."
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
    name a target (``refs`` from ``x-dna-ref``, ``dep_filters``), the composite
    pointers that carry their own target (``composites``), and the raw
    ``properties`` the name-convention pass reads. A Kind whose ``schema()``
    raises contributes an empty one rather than taking the caller down.

    ``composites`` is read HERE, once, so ``build_edges`` and
    ``undeclarable_for`` classify a field by the same reading. Two passes over
    the same schema are two passes that can disagree, and disagreeing about
    which bucket a field belongs in is precisely the defect this closes.
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
                "composites": composite_references(port),
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


def composite_undeclarable(kinds: list[dict]) -> dict[tuple[str, str], tuple[str, str]]:
    """The composite pointers, DERIVED from the schemas — not enumerated.

    Same shape as :data:`UNDECLARABLE` so the two merge into one index: a
    ``(Kind, field) -> (target, why)`` mapping. The target is always
    :data:`POLYMORPHIC_TARGET`, because a composite value names its own Kind.

    This is the half that no longer needs a maintainer. ``Comment.target_ref``
    was in the hand table and classified right; ``Engram.source_refs`` and
    ``SourceArtifact.derived_refs`` are the same kind of pointer, were not in
    it, and were reported as unresolved gaps — three instances of one rule,
    two of them wrong, because membership was somebody's memory. Now the field
    says it (``x-dna-ref-composite``) or its shape does (an object requiring
    ``kind`` + ``name``), and a new one classifies itself the day it is written.
    """
    out: dict[tuple[str, str], tuple[str, str]] = {}
    for k in kinds:
        for comp in k.get("composites") or ():
            plural = "pointers" if comp.is_array else "pointer"
            out[(k["kind"], comp.field)] = (
                POLYMORPHIC_TARGET,
                f"composite `{_md(comp.form)}` {plural} — the target Kind "
                "travels in the value, so it needs parsing, not a name lookup",
            )
    return out


def undeclarable_index(kinds: list[dict]) -> dict[tuple[str, str], tuple[str, str]]:
    """Every undeclarable reference of these Kinds — keyed AND composite.

    ONE index, two producers, and every consumer reads it: ``build_edges``
    decides what not to draw from the same mapping ``undeclarable_for``
    reports. When those were two membership tests, a field could be excluded
    from the edges by one and absent from the report of the other.

    The hand table is filtered to REGISTERED Kinds: telling a scope about a
    field of a Kind it does not register would be describing somebody else's
    model.
    """
    registered = {k["kind"] for k in kinds}
    index = {
        (source, field): (target, why)
        for (source, field), (target, why) in UNDECLARABLE.items()
        if source in registered
    }
    index.update(composite_undeclarable(kinds))
    return index


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

    Every unresolved row carries an ``origin`` from :data:`UNRESOLVED_ORIGINS`
    naming WHICH of the three passes produced it — the difference between a
    declaration the model cannot honour and this projection guessing at a field
    name, which ``reason`` could only state in English prose.
    """
    by_alias, by_token = target_index(kinds)
    by_kind = {k["kind"]: k for k in kinds}
    undeclarable = undeclarable_index(kinds)

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
                        "origin": "declared",
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
                    "origin": "composition",
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
            if (source, field) in undeclarable:
                # Keyed or composite: a REAL reference, stated under
                # `undeclarable` rather than drawn as an edge or reported as a
                # gap. Never both — one field, one classification.
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
                    "origin": "shape-inferred",
                    "reason": f"reference-shaped, but `{token}` matches no "
                              "registered Kind",
                })

    edges.sort(key=lambda e: (e["tier"], e["source"], e["field"], e["target"]))
    unresolved.sort(key=lambda e: (e["source"], e["field"]))
    return edges, unresolved


def undeclarable_for(kinds: list[dict]) -> list[dict]:
    """The undeclarable references of these Kinds — keyed AND composite.

    Reads :func:`undeclarable_index`, the same mapping ``build_edges`` uses to
    decide what not to draw, so the report and the drawing cannot disagree.
    """
    return [
        {"source": source, "field": field, "target": target, "reason": why}
        for (source, field), (target, why) in sorted(undeclarable_index(kinds).items())
    ]


def suppressed_for(kinds: list[dict]) -> list[dict]:
    """The name matches this projection ACTUALLY suppressed, for these Kinds.

    Membership in :data:`INFERENCE_DENYLIST` is not enough. The denylist only
    fires where the field name RESOLVES to exactly one registered Kind — so an
    entry can go inert without being touched, and three of them did: the
    metering rename added ``PricingPlan`` next to ``Plan``, which made the
    token ``plan`` ambiguous, which is now what stops those matches. Counting
    them anyway made ``coverage.suppressed`` report 8 where 5 happened.

    Reporting what the pass DID, rather than what the table says it would do,
    is the same rule every other counter here follows.
    """
    registered = {k["kind"] for k in kinds}
    props = {k["kind"]: k["properties"] for k in kinds}
    _, by_token = target_index(kinds)
    return [
        {"source": source, "field": field, "reason": why}
        for (source, field), why in sorted(INFERENCE_DENYLIST.items())
        if source in registered
        and field in props.get(source, {})
        and by_token.get(_normalize(field))
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
    per_origin = {origin: 0 for origin in UNRESOLVED_ORIGINS}
    for u in unresolved:
        origin = u.get("origin", "")
        per_origin[origin] = per_origin.get(origin, 0) + 1
    return {
        "kinds": len(kinds),
        "edges": len(edges),
        **per_tier,
        "unresolved": len(unresolved),
        # The split the single `unresolved` count could not show: 25 rows all
        # of one origin read exactly like 25 broken declarations.
        "unresolved_by_origin": per_origin,
        "undeclarable": len(undeclarable),
        "suppressed": len(suppressed),
        "enforced_tiers": list(ENFORCED_TIERS),
        "declared_origins": list(DECLARED_ORIGINS),
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
            {
                "kind": u["source"], "field": u["field"],
                "origin": u["origin"], "reason": u["reason"],
            }
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
