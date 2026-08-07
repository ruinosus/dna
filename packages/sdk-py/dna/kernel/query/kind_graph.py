"""The SCHEMA graph — which Kinds point at which, and through which relation.

This module answers *one* question: given the registered Kinds, what does the
model say about how they relate? It is a projection of the REGISTRY, not of
stored data — no instance is read, nothing is written, and the answer is
identical for every caller of a given scope.

Why it lives in the kernel
--------------------------
The projection already existed, inside ``scripts/gen_data_model_docs.py``,
where it computes ``docs/reference/data-model.md``. When a REST route needed
the same graph the honest move was to give the computation one home and two
consumers, not to write it a second time: two readings of a relation that can
disagree is exactly the defect this whole area was written to end. The
generator now imports from here; its page is byte-identical, and
``scripts/data_model_guard.py`` proves it.

The declaration itself is read by :func:`dna.kernel.kinds.relations
.relations_of` — the SAME function the write pipeline uses. The graph
therefore cannot claim an edge the write path would not enforce.

One mechanism, not four
-----------------------
This module used to run three passes over each Kind and rank their results:
``x-dna-ref``, then ``dep_filters``, then a NAME-SHAPE guess (a field ending in
``_id``/``_ref``/``_refs`` whose token matched exactly one registered Kind) —
plus a denylist whose only job was to shut the third one up, plus a hand-kept
table of "undeclarable" references the annotation could not express. Four
mechanisms and two hand-kept tables answering "what does this field point at?".

Only ONE of them survives as a source of edges: ``spec.relations``. What the
other three were compensating for was the declaration's poverty, and the
declaration is not poor any more:

* the ones addressed by a domain KEY (``Project.workspace_id``,
  ``WorkspaceMembership.role``) — the hand table — now say so on the Kind, as
  ``by: workspace_id``. They are declared, drawable edges that this runtime
  honestly does not enforce.
* the ones whose target travels in the VALUE (``Story.produces``,
  ``Comment.target_ref``) now say ``to: "*"`` with the parseable form in
  ``by``. Also declared, also honest about not being followed.
* the name-shape guess and its denylist are GONE. A guess that produced an
  EDGE was the problem: it drew ``KindDefinition.docs → Doc`` from a field of
  prose and ``StatusReport.insight → IntelInsight`` from a field whose own
  description says the target Kind was deleted. The denylist existed to
  suppress that class of line, and a suppression table is the shape of a
  mechanism that should not be producing the thing being suppressed.

The name SHAPE survives in one place only, and demoted: a field that looks
like a reference and declares no relation is reported as an ``undeclared``
gap. That is an invitation, not a claim, and it needs no denylist — nothing is
being asserted about it, so there is nothing to suppress. It is also the
epic's own measuring stick, so deleting it outright would have removed the
number that says how much work is left.

``dep_filters`` is NOT one of the four and stays exactly where it was. It
drives PROMPT COMPOSITION — a missing optional Skill is legitimately filtered
out there rather than being an error — and it is drawn as its own tier.

Two tiers, and the ranking is still the point
---------------------------------------------
1. ``declared`` — ``spec.relations``. Carries its own ``enforced`` flag: TRUE
   when the kernel resolves the relation at write time (concrete target,
   addressed by instance name), FALSE when the relation is declared but
   addressed by a key this runtime does not follow.
2. ``composition`` — ``dep_filters`` names the target Kind. A real
   declaration, but it exists to drive prompt composition and is never checked
   against stored data, so it can dangle silently. Never enforced.

And ``unresolved`` ranks too, by ``origin``
--------------------------------------------
* ``declared`` — a relation's ``to`` names a Kind no registry provides;
* ``composition`` — ``dep_filters`` names an alias no Kind claims;
* ``inverse`` — a declared ``inverse_of`` does not PAIR (the target declares
  no such relation, or it points elsewhere, or it names a different inverse).
  This is dor 1 made visible: two Kinds claiming to be halves of one relation
  while disagreeing about it, which nothing could say before;
* ``undeclared`` — the field NAME looks like a reference and no relation
  declares it. This projection is not guessing at a TARGET any more, so the
  row says only what it can see: somebody should look.

The first three are CLAIMS somebody made and the model cannot honour — an
authoring error worth alerting on. The fourth is an invitation.
:data:`DECLARED_ORIGINS` names the first three so a consumer DERIVES "is this
an alarm?" instead of hard-coding it.

What this projection deliberately cannot see is stated, not hidden, by
:data:`COVERAGE_LIMITS` — which travels WITH the graph so that no consumer can
render it as "all the relations".

Determinism is a hard requirement (the docs guard is worthless without it):
every collection is sorted and nothing embeds a timestamp, hostname or path.
"""
from __future__ import annotations

from typing import Any, Iterable

from dna.kernel.kinds.identifiers import identifiers_of
from dna.kernel.kinds.relations import ANY_TARGET, inverse_gaps, relations_of

#: Edge tiers, strongest first. Ordered — consumers rank by index.
TIERS: tuple[str, ...] = ("declared", "composition")

#: Why a declaration or a field landed in ``unresolved`` — the machine-readable
#: half of ``reason``. Ordered strongest-claim first, like :data:`TIERS`.
UNRESOLVED_ORIGINS: tuple[str, ...] = (
    "declared", "composition", "inverse", "undeclared",
)

#: The origins that mean somebody DECLARED something the model cannot honour:
#: an authoring error to fix, not noise to page through. A list, not a bare
#: string, so a consumer derives "does this deserve alarm?" instead of
#: hard-coding the answer.
DECLARED_ORIGINS: tuple[str, ...] = ("declared", "composition", "inverse")

#: The ``to_kind`` reported for a relation whose Kind is chosen per VALUE
#: (``to: "*"``). Not a Kind name, and deliberately not mistakable for one — it
#: is the same token the declaration uses, so a consumer that special-cases it
#: reads the identical string in both places.
POLYMORPHIC_TARGET = ANY_TARGET

#: Suffixes that make a field "reference-shaped". The ONLY thing left of the
#: name-convention pass, and it no longer resolves a target: it says a field
#: looks like it points somewhere, so that an undeclared one can be listed as
#: an invitation. Nothing is asserted, so nothing needs a denylist.
REF_SUFFIXES: tuple[str, ...] = ("_refs", "_ref", "_oid", "_ids", "_id", "_slug")

# --- what the projection cannot see, travelling WITH the projection ----------
# Machine-readable ``code`` first, prose ``detail`` second. The code is what a
# UI switches on (its own copy, in its own catalogue, in its own language);
# the detail is documentation for whoever reads the raw answer. Neither is a
# rendered string — a screen that printed ``detail`` verbatim would be
# shipping English from a backend, which this project does not do.
COVERAGE_LIMITS: tuple[dict[str, str], ...] = (
    {
        "code": "schema_not_data",
        "detail": (
            "These edges say which Kinds MAY point at which, through which "
            "relation. They say nothing about which INSTANCES point at which — "
            "that is a different graph, derived at write time, and this "
            "projection does not serve it."
        ),
    },
    {
        "code": "enforced_is_per_edge",
        "detail": (
            "An edge carries TWO flags and they are not the same question. "
            "`followed` says the kernel READS the target at write time and "
            "records this edge — TRUE for a concrete target Kind addressed "
            "either `by: name` or by a spec KEY of the target. `enforced` says "
            "an unresolvable value REFUSES the write — TRUE only for `by: "
            "name`, because the by-key resolver is deliberately poorer than "
            "the live alias-tolerant lookups (`kernel.tier()` resolves a "
            "PricingPlan by `tier_id` and THEN by `aliases[]`) and may not "
            "veto data they accept. A relation carrying its Kind in the value "
            "(`to: *` with a composite `by`) is fully DECLARED and neither "
            "followed nor enforced — nothing parses that form yet. "
            "`composition` edges come from `dep_filters`, which drives prompt "
            "composition and is never checked against stored data at all."
        ),
    },
    {
        "code": "top_level_properties_only",
        "detail": (
            "A relation is named by a FIRST-LEVEL spec field. A pointer nested "
            "under `spec.foo.bar`, inside `items`, or behind "
            "`$ref`/`oneOf`/`anyOf` cannot be declared as a relation today — "
            "and is equally invisible to the write-time validation, so the two "
            "agree."
        ),
    },
    {
        "code": "unresolved_is_not_all_broken",
        "detail": (
            "`unresolved` holds two different things and `origin` separates "
            "them. `declared`, `composition` and `inverse` rows are "
            "DECLARATIONS the model cannot honour — an authoring error "
            "somebody must fix. `undeclared` rows are fields whose NAME looks "
            "like a reference (`_id`/`_ref`/`_refs`) with no relation "
            "declaring them: often not references at all (an OAuth "
            "`client_id`, a Stripe customer id, an IdP subject), and never a "
            "claim by this projection — it no longer guesses a target. "
            "`coverage.declared_origins` names the ones that are claims, so a "
            "screen ranks them without reading `reason`."
        ),
    },
    {
        "code": "an_undeclared_gap_can_be_answered",
        "detail": (
            "An `undeclared` row is an invitation, and `spec.identifiers` is "
            "how a Kind ANSWERS it: `role: self` for a field holding the "
            "instance's own key, `role: external` plus `system` for one minted "
            "outside DNA. Answered fields leave `unresolved` and appear under "
            "`identifiers`, with the reason they are not pointers. Before that "
            "block existed the list carried rows nothing could ever clear, "
            "which made a finite backlog look like a permanent one."
        ),
    },
    {
        "code": "inverse_is_declaration_only",
        "detail": (
            "`inverse` rows compare two DECLARATIONS, not two instances. A "
            "sound pair here does not mean any stored Feature and Story agree "
            "— instance reciprocity is checked at write time and REPORTED "
            "there, never enforced."
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
    name a target (``relations``, ``dep_filters``), and the raw ``properties``
    the undeclared-gap pass reads. A Kind whose ``schema()`` raises contributes
    an empty one rather than taking the caller down.
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
                "relations": relations_of(port),
                # The other half — the fields that point NOWHERE and say so.
                # Read here so the undeclared-gap pass can be ANSWERED rather
                # than only asked.
                "identifiers": identifiers_of(port),
                "properties": dict((schema or {}).get("properties") or {}),
            }
        )
    kinds.sort(key=lambda k: k["kind"])
    return kinds


def target_index(kinds: list[dict]) -> dict[str, str]:
    """alias -> Kind.

    The lowercased-token index this used to return alongside it is GONE with
    the name-shape pass that was its only consumer. Nothing maps a field name
    to a Kind any more.
    """
    return {k["alias"]: k["kind"] for k in kinds if k["alias"]}


def _cardinality(prop: dict) -> str:
    return "many" if (prop or {}).get("type") == "array" else "one"


def _md(text: str) -> str:
    """Flatten prose so it survives a Markdown table cell unbroken."""
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def build_edges(kinds: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return ``(edges, unresolved)`` for the rows from :func:`kind_rows`.

    Each edge carries a ``tier`` — ``declared`` (``spec.relations``) or
    ``composition`` (``dep_filters``) — and an ``enforced`` flag saying whether
    the kernel resolves it on write. A field declared as a relation is never
    also emitted as a ``composition`` edge: the strongest statement about a
    field wins, so no line is drawn twice.

    A relation whose ``to`` names a Kind no registry provides does NOT become a
    dangling edge: it becomes an ``unresolved`` row. A graph is a set of
    relations between things that exist; an authoring typo is a gap, and
    printing it as an edge would let a screen draw a node for a Kind nobody
    registered.

    A ``to: "*"`` relation IS drawn, with ``to_kind`` set to
    :data:`POLYMORPHIC_TARGET`. It used to be filtered into a separate
    "undeclarable" bucket, which is how eight ``produces`` fields ended up
    described as inexpressible when they were merely undeclared. A consumer
    that draws nodes filters on the token; a consumer that LISTS a Kind's
    relations — the thing that was impossible before — gets all of them.
    """
    by_alias = target_index(kinds)
    by_kind = {k["kind"]: k for k in kinds}

    edges: list[dict] = []
    unresolved: list[dict] = []

    for k in kinds:
        source = k["kind"]
        props = k["properties"]
        claimed: set[str] = set()

        # -- tier 1: spec.relations (the ONE source of declared edges) --------
        for name, rel in sorted(k["relations"].items()):
            claimed.add(name)
            targets = list(rel.to) or [POLYMORPHIC_TARGET]
            for target in targets:
                if target != POLYMORPHIC_TARGET and target not in by_kind:
                    unresolved.append({
                        "source": source, "field": name,
                        "origin": "declared",
                        "reason": f"`relations.{_md(name)}.to` names "
                                  f"`{_md(target)}`, which no registered Kind "
                                  "provides",
                    })
                    continue
                edges.append({
                    "source": source, "field": name, "target": target,
                    "cardinality": rel.cardinality,
                    "tier": "declared", "polymorphic": rel.polymorphic,
                    # Two facts, and they were ONE field until fatia 5 split
                    # them. ``enforced`` now reads the property that actually
                    # means "an unresolvable value refuses the write";
                    # ``followed`` is the wider one — "the kernel reads the
                    # target and draws this edge". A ``by: <key>`` relation is
                    # followed and NOT enforced, and a schema graph showing
                    # only the first would report the relation as unchecked
                    # while its edges sit in the table.
                    "by": rel.by, "enforced": rel.enforced,
                    "followed": rel.resolved,
                    "inverse_of": rel.inverse_of,
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
                    # ``followed`` beside ``enforced`` and both False: a
                    # composition edge is never read against stored data at
                    # all, which is a stronger statement than "it does not
                    # veto" and the reason the two keys have to be present on
                    # EVERY edge rather than only on the tier that can differ.
                    "by": "name", "followed": False, "enforced": False,
                    "inverse_of": None,
                })

        # -- the gap: reference-shaped and undeclared --------------------------
        # No target is guessed. The row says a field LOOKS like it points
        # somewhere and nothing declares where — an invitation, not a claim,
        # which is why it needs no denylist: a suppression table exists to stop
        # a false CLAIM, and nothing here is claimed.
        #
        # ``spec.identifiers`` is how the invitation gets ANSWERED. Until
        # 06/08/2026 it could not be: a Kind could say where a field points and
        # had no way to say that it points nowhere, so two thirds of this list
        # were rows nobody could ever clear (an OAuth `client_id`, a Stripe
        # customer id, `Sprint.sprint_id` naming its own instance). That is not
        # a suppression — the answer is a DECLARATION, it lives on the Kind
        # beside the schema, and it carries a machine-readable reason.
        for field in sorted(k["identifiers"]):
            claimed.add(field)
        for field in sorted(props):
            if field in claimed:
                continue
            if field.lower().endswith(REF_SUFFIXES):
                unresolved.append({
                    "source": source, "field": field,
                    "origin": "undeclared",
                    "reason": "reference-shaped field name, and neither a "
                              "relation nor an identifier declares what it is",
                })

    # -- the inverse pairs, across Kinds ---------------------------------------
    # Computed once over the whole registry rather than per-Kind: a pair is a
    # property of TWO declarations, so no single Kind's pass can see it. This
    # is dor 1's enforced half — it reads no instances and cannot deadlock.
    for gap in inverse_gaps({k["kind"]: k["relations"] for k in kinds}):
        unresolved.append({
            "source": gap["kind"], "field": gap["relation"],
            "origin": "inverse", "code": gap["code"],
            "reason": _md(gap["reason"]),
        })

    edges.sort(key=lambda e: (e["tier"], e["source"], e["field"], e["target"]))
    unresolved.sort(key=lambda e: (e["source"], e["field"], e["origin"]))
    return edges, unresolved


def coverage(
    kinds: list[dict],
    edges: list[dict],
    unresolved: list[dict],
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
        # The number that says how much of the model the runtime actually
        # checks — derived from the edges, never from a tier name, because
        # "declared" and "enforced" stopped being the same thing the day a
        # relation could declare its own addressing.
        "enforced": sum(1 for e in edges if e["enforced"]),
        # …and how much of it the runtime READS, which since fatia 5 is a
        # strictly larger number. Reporting only `enforced` would understate
        # the derived graph by every `by: <key>` edge in the table — a screen
        # would show a model less connected than the data it is drawn from.
        # ``e["followed"]``, not ``e.get(...)``: BOTH tiers set the key, and a
        # third tier that forgot it should raise here rather than be counted as
        # zero — a missing flag read as False is how a number goes quietly
        # wrong.
        "followed": sum(1 for e in edges if e["followed"]),
        "kinds_with_relations": sum(1 for k in kinds if k["relations"]),
        # The answered half of the gap list: fields that DECLARED they point
        # nowhere. Derived from the declarations, never counted by hand — and
        # reported beside `unresolved` on purpose, because "21 gaps" and "21
        # gaps plus 14 answers" describe very different models.
        "identifiers": sum(len(k["identifiers"]) for k in kinds),
        "unresolved": len(unresolved),
        # The split the single `unresolved` count could not show: 25 rows all
        # of one origin read exactly like 25 broken declarations.
        "unresolved_by_origin": per_origin,
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
                "by": e["by"],
                # ⚠️ BOTH, and this projection is the third place a key can be
                # dropped in silence (after the FastAPI ``response_model`` and
                # the TS twin). It is hand-written and indexes by name, so a
                # key added to ``build_edges`` simply does not arrive — the
                # route would keep serving ``enforced`` alone and a screen
                # would go on calling every ``by: <key>`` relation unchecked
                # while its edges sat in ``dna_edges``. Caught by
                # ``test_kind_graph_rest.py`` asking the ROUTE rather than the
                # projection.
                "followed": e["followed"],
                "enforced": e["enforced"],
                "inverse_of": e["inverse_of"],
            }
            for e in edges
        ],
        # The fields that answered the invitation: reference-SHAPED, and
        # declared to point nowhere. On the wire beside `unresolved` so a
        # screen can render "this is an id, not a broken reference" instead of
        # leaving the reader to guess which rows are alarms.
        "identifiers": [
            {"kind": r["kind"], **ident.to_wire()}
            for r in rows
            for _, ident in sorted(r["identifiers"].items())
        ],
        "unresolved": [
            {
                "kind": u["source"], "field": u["field"],
                "origin": u["origin"], "reason": u["reason"],
                # Only ``inverse`` rows carry a machine-readable sub-code
                # today. Present as ``None`` on every row rather than absent on
                # most, so a consumer types the shape once.
                "code": u.get("code"),
            }
            for u in unresolved
        ],
        "coverage": coverage(rows, edges, unresolved),
    }
