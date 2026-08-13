"""i-119 group C — the nine islands that "probably should not be", measured.

The issue asked for a verdict per Kind AND the reason, saying the reason is
worth as much as the declaration. Three of the nine turned out to point at
something real and now say so; six stay islands, and this module pins the
reason each one stays, because a reason that lives only in a comment is a
reason the next slice will re-litigate.

What each section defends:

1. ``Genome`` / ``MCPFederation`` — the declarations that landed, including the
   ADDRESSING (``by:``), which is the half a careless edit would "simplify"
   into ``by: name`` and thereby install a second resolution rule.
2. The fields i-119 named as references that are NOT references. This is the
   mutant-killer for the whole slice: declaring any of them would satisfy the
   island count and lie about the model, which the taxonomy spec names as THE
   error to avoid.
3. ``Hook.target`` — filed by i-119 as "names a Kind", measured as a kernel
   HOOK POINT. The test reads the same vocabulary the registry does.
4. The measurement that refused ``to: KindDefinition`` as the answer to
   "points at a Kind". Without this, the next reader re-derives the argument
   from the sentence "a Kind IS an instance" and gets it wrong.
5. The island set itself, before and after, so a removed declaration shows up
   as a Kind falling back into the list rather than as a silent count drift.
"""
from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa

from dna.kernel import Kernel
from dna.kernel.hooks import KNOWN_HOOK_NAMES
from dna.kernel.kinds.relations import relations_of
from dna.kernel.query.kind_graph import build_edges, kind_rows
from tests import _graph_store

_HELIX_API = "github.com/ruinosus/dna/v1"
SCOPE = "i119-group-c"

#: The six that stay islands after this slice, and WHY — the id is the reason,
#: so a failure names the argument rather than a number.
STILL_ISLANDS: dict[str, str] = {
    "Hook": "target is a kernel hook point, not a Kind (i-119 misfiled it)",
    "Lesson": "skill/subject are vocabulary; target_concepts names Pictogram, "
              "which no registry provides",
    "Memory": "MIF's own relationships[], foreign address space, market "
              "fidelity forbids re-modelling it",
    "RemoteAgent": "skills[] are objects; the Agent allowlist is nested one "
                   "level down",
    "Automation": "result_kind names the KIND REGISTRY — needs vocabulary the "
                  "founder has not decided",
    "KindDefinition": "meta-Kind: its relations/dep_filters are DATA about "
                      "another Kind",
}

#: Left the island list in this slice, and by which declaration.
LEFT_THE_ISLANDS: dict[str, str] = {
    "Genome": "default_agent / default_llm / owner_tenant",
    "MCPFederation": "min_role / min_role_write",
    "ModelProfile": "nothing landed ON it — Genome.default_llm points AT it",
}


@pytest.fixture(scope="module")
def kernel():
    return Kernel.auto()


# ---------------------------------------------------------------------------
# 1. The declarations that landed — and their ADDRESSING
# ---------------------------------------------------------------------------


class TestGenomeFinallyPointsSomewhere:
    def test_default_agent_is_resolved_by_name(self, kernel):
        """The one the kernel actually FOLLOWS.

        The Agent lives in the Genome's own scope and is addressed by instance
        name, which is the same address ``get_default_agent_name`` already
        hands to the agent lookup. If this ever stops being ``resolved``, the
        scope root has gone back to pointing at nothing enforceable.
        """
        rel = relations_of(kernel.kind_port_for("Genome"))["default_agent"]
        assert rel.to == ("Agent",)
        assert rel.cardinality == "one"
        assert rel.resolved is True

    @pytest.mark.parametrize(
        "field, target, by",
        [
            ("default_llm", "ModelProfile", "model_id"),
            ("owner_tenant", "Workspace", "workspace_id"),
        ],
    )
    def test_the_key_addressed_ones_are_followed_and_never_enforced(
        self, kernel, field, target, by,
    ):
        """``by:`` is load-bearing, and ``by: name`` here is still a REGRESSION.

        Both targets are looked up by a spec key rather than by instance name,
        and both live in ``_lib`` rather than in the writer's scope
        (``kernel.model_profile()`` says so for one; ``Workspace`` is GLOBAL
        for the other). Fatia 5 changed none of that — what it changed is that
        the kernel now FOLLOWS the key instead of only naming it.

        ⚠️ ``enforced is False`` is what carries this test's original intent
        forward. What it protected was a *veto* on an address the live lookup
        resolves more generously (``model_profile()`` falls through to
        ``spec.aliases[]``), and that is answered by refusing the veto — never
        by refusing to look.
        """
        rel = relations_of(kernel.kind_port_for("Genome"))[field]
        assert rel.to == (target,)
        assert rel.by == by
        assert rel.by_name is False, (
            f"Genome.{field} would resolve by NAME — right by a coincidence of "
            f"the filesystem, and wrong the day the two diverge"
        )
        assert rel.resolved is True
        assert rel.enforced is False, (
            f"Genome.{field} started vetoing — the kernel would now refuse a "
            f"value ``model_profile()``/``tier()`` accept through aliases"
        )


class TestTheRoleLadderIsDataAndTheModelSaysSo:
    @pytest.mark.parametrize("field", ["min_role", "min_role_write"])
    def test_the_floors_point_at_role_by_role_id(self, kernel, field):
        """Same declaration ``Membership.role`` already makes, deliberately.

        ``role.kind.yaml`` says the doc name only SHOULD equal ``role_id``, and
        Role is TENANTED — so ``by: role_id`` is the honest address and
        ``by: name`` would be right by coincidence.
        """
        rel = relations_of(kernel.kind_port_for("MCPFederation"))[field]
        assert rel.to == ("Role",)
        assert rel.cardinality == "one"
        assert rel.by == "role_id"
        # Followed since fatia 5, never enforced — the address is honest
        # BECAUSE the name only *should* equal the key, and the resolver is
        # allowed to look for the key without being allowed to refuse over it.
        assert rel.by_name is False
        assert rel.resolved is True
        assert rel.enforced is False

    def test_it_matches_the_membership_precedent_exactly(self, kernel):
        """Two Kinds, two mechanisms (a Python class and a descriptor), one
        contract. Divergence here would be two ways to name the same ladder."""
        federation = relations_of(
            kernel.kind_port_for("MCPFederation"),
        )["min_role"].to_declaration()
        membership = relations_of(
            kernel.kind_port_for("Membership"),
        )["role"].to_declaration()
        assert federation == membership


# ---------------------------------------------------------------------------
# 2. The fields i-119 called references, and that are not
# ---------------------------------------------------------------------------


class TestTheNonReferencesStayUndeclared:
    """THE mutant-killer for this slice.

    Every entry here is a field the issue named as pointing at a Kind. Each one
    was measured and does not. Declaring any of them would drop the island
    count and put a false edge in the graph, which is precisely the failure
    mode the taxonomy spec calls out.
    """

    @pytest.mark.parametrize(
        "kind, field, why",
        [
            # Genome
            ("Genome", "dependencies",
             "entries are objects {source, items[]}; source is an external "
             "package coordinate, not an instance name"),
            ("Genome", "parent_scope",
             "the target Genome lives in ANOTHER scope and resolution is "
             "intra-scope — by: name would dangle for 100% of declarers"),
            ("Genome", "owner",
             "free text (helix-team, dna) — not the workspace id, which is "
             "owner_tenant"),
            # MCPFederation
            ("MCPFederation", "allowed_tools",
             "remote MCP tool names minted by the foreign server, not DNA Tool "
             "instances"),
            ("MCPFederation", "read_tools", "same"),
            ("MCPFederation", "write_tools", "same"),
            # RemoteAgent
            ("RemoteAgent", "skills",
             "an array of A2A skill OBJECTS the remote writes about itself"),
            ("RemoteAgent", "delegation_target_for",
             "an object; the Agent allowlist is nested under .agents and "
             "carries the ['*'] sentinel"),
            ("RemoteAgent", "data_scope",
             "an object whose .kinds names KINDS — the same gap as "
             "AgentGrant.scope_kinds"),
            # Lesson
            ("Lesson", "skill",
             "a closed enum of PT-BR pedagogical verbs, not an agentskills.io "
             "Skill"),
            ("Lesson", "subject", "a concept-group slug, free text"),
            ("Lesson", "target_concepts",
             "names Pictogram, which no registry provides — declaring it adds "
             "a permanent false alarm, not an edge"),
            # Hook / Automation / Memory
            ("Hook", "target", "a kernel hook point"),
            ("Automation", "result_kind",
             "names the Kind REGISTRY; needs vocabulary nobody has decided"),
            ("Automation", "runner",
             "the real pointer is runner.ref, nested one level down"),
            ("Memory", "relationships",
             "MIF's own edges, in MIF's address space — market fidelity"),
        ],
    )
    def test_it_is_not_declared_a_relation(self, kernel, kind, field, why):
        assert field not in relations_of(kernel.kind_port_for(kind)), (
            f"{kind}.{field} was declared a relation. It is not one: {why}. "
            f"Zeroing the island count by inventing an edge is the error "
            f"i-119 exists to avoid."
        )

    @pytest.mark.parametrize(
        "kind, field",
        [("RemoteAgent", "skills"), ("Genome", "dependencies"),
         ("Memory", "relationships")],
    )
    def test_the_value_is_objects_so_a_relation_could_carry_nothing(
        self, kernel, kind, field,
    ):
        """Not an opinion — the mechanics refuse.

        ``relation_values`` reads STRINGS. Declaring a relation on an array of
        objects draws an edge that can never carry a value, which reads as a
        healthy link that is permanently empty.
        """
        schema = kernel.kind_port_for(kind).schema() or {}
        prop = (schema.get("properties") or {}).get(field) or {}
        assert prop.get("type") == "array"
        assert (prop.get("items") or {}).get("type") == "object", prop


class TestTheThreeThatLeftAreStillPointedAt:
    def test_model_profile_left_without_declaring_anything(self, kernel):
        """i-119 asked to confirm ModelProfile as group A. It is — and it still
        stopped being an island, because the Kind that pointed AT it got
        honest. That is what a legitimate island looks like."""
        assert relations_of(kernel.kind_port_for("ModelProfile")) == {}
        assert "model_id" in getattr(
            kernel.kind_port_for("ModelProfile"), "identifiers", {},
        )

    def test_kind_definition_declares_nothing_either(self, kernel):
        """The other "confirm group A". Its relations/dep_filters/traits are
        DATA about the Kind it defines, not pointers from this instance."""
        assert relations_of(kernel.kind_port_for("KindDefinition")) == {}


# ---------------------------------------------------------------------------
# 3. Hook.target is a hook point — read from the same vocabulary the kernel uses
# ---------------------------------------------------------------------------


class TestHookTargetIsAHookPointNotAKind:
    def test_the_default_is_a_known_hook_name(self, kernel):
        default = (
            (kernel.kind_port_for("Hook").schema() or {})
            .get("properties", {}).get("target", {})
        )
        # The model's default lives on HookSpec, not in the synthesized schema,
        # so read it where it is authored.
        from dna.extensions.hooks.models import HookSpec
        assert HookSpec().target in KNOWN_HOOK_NAMES
        assert isinstance(default, dict)  # the property exists at all

    def test_no_hook_name_is_a_registered_kind_name(self, kernel):
        """The decisive check, and it is not a matter of reading.

        If ``target`` named a Kind, at least one of the kernel's own hook
        points would collide with a registered Kind name. None does — the two
        vocabularies do not intersect anywhere.
        """
        kinds = {p.kind for p in kernel.kind_ports()}
        assert not (set(KNOWN_HOOK_NAMES) & kinds)


# ---------------------------------------------------------------------------
# 4. Why `to: KindDefinition` is NOT the answer to "points at a Kind"
# ---------------------------------------------------------------------------


class TestAKindIsAnInstanceAndThatIsNotEnough:
    """The measurement the founder's brief demanded before accepting the easy
    escape. ``KindDefinition`` really is a row in ``dna_instances`` — and
    ``to: KindDefinition`` would still be false for most of the registry."""

    def test_most_kinds_have_no_kind_definition_at_all(self, kernel):
        from dna.kernel.meta import DeclarativeKindPort

        ports = list(kernel.kind_ports())
        classy = [p.kind for p in ports if not isinstance(p, DeclarativeKindPort)]
        assert len(ports) > len(classy) > 0
        # A relation resolving for a minority of its universe is worse than
        # none: it makes the graph look answered.
        assert len(classy) / len(ports) > 0.25, (
            "if this ever drops near zero, revisit the refusal — the argument "
            "was arithmetic, not taste"
        )

    def test_one_of_automations_two_examples_has_no_descriptor_at_all(
        self, kernel,
    ):
        """``result_kind``'s description names exactly two Kinds — Research and
        Doc. ``Research`` is a Python ``KindBase`` with no descriptor anywhere,
        so a KindDefinition-addressed relation dangles on the first example the
        field itself advertises. (``Doc`` HAS a descriptor, and that half of
        the refusal is the addressing test below, not this one — the two
        reasons are independent and each is sufficient.)"""
        from dna.kernel.meta import DeclarativeKindPort

        research = kernel.kind_port_for("Research")
        assert research is not None
        assert not isinstance(research, DeclarativeKindPort)
        assert isinstance(kernel.kind_port_for("Doc"), DeclarativeKindPort)

    def test_a_descriptor_is_not_named_after_the_kind_it_defines(self, kernel):
        """And the address would be wrong even where a descriptor exists.

        A KindDefinition's ``metadata.name`` is a slug (``automation``), while
        ``result_kind`` holds the Kind NAME (``Automation``). ``by: name``
        would compare two different strings.
        """
        from dna.kernel.source.descriptor_loader import load_descriptors

        descriptors = load_descriptors("dna.extensions.automation")
        assert descriptors, "the automation descriptor went missing"
        doc = descriptors[0]
        assert doc["metadata"]["name"] == "automation"
        assert doc["spec"]["target_kind"] == "Automation"
        assert doc["metadata"]["name"] != doc["spec"]["target_kind"], (
            "if a descriptor's name ever equals the Kind name it defines, the "
            "`by: name` half of the refusal changes and the argument needs "
            "re-reading — the arithmetic half above does not"
        )


# ---------------------------------------------------------------------------
# 5. The island set, named rather than counted
# ---------------------------------------------------------------------------


def _islands(kernel) -> set[str]:
    rows = kind_rows(kernel.kind_ports())
    edges, _ = build_edges(rows)
    all_kinds = {r["kind"] for r in rows}
    touched: set[str] = set()
    for e in edges:
        touched.add(e["source"])
        if e["target"] in all_kinds:
            touched.add(e["target"])
    return all_kinds - touched


class TestTheIslandSet:
    def test_the_three_left(self, kernel):
        islands = _islands(kernel)
        for kind, how in LEFT_THE_ISLANDS.items():
            assert kind not in islands, f"{kind} is an island again ({how})"

    def test_the_six_that_stay_are_the_six_we_argued_for(self, kernel):
        """Named, not counted. A removed declaration shows up as a Kind
        RETURNING to this set, with the reason printed beside it."""
        islands = _islands(kernel)
        mine = set(STILL_ISLANDS) | set(LEFT_THE_ISLANDS)
        assert islands & mine == set(STILL_ISLANDS), {
            k: STILL_ISLANDS.get(k, "unexpected") for k in sorted(islands & mine)
        }


# ---------------------------------------------------------------------------
# 6. Through the door — the resolved declaration produces a real edge
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(params=_graph_store.DIALECTS)
async def store(request):
    src, cleanup = await _graph_store.build_store(request.param, "i119c")
    k = Kernel.auto()
    k.source(src)
    try:
        yield k, src
    finally:
        await cleanup()


@pytest.fixture(autouse=True)
def _modes(monkeypatch):
    monkeypatch.delenv("DNA_REF_VALIDATION", raising=False)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")


def _genome(name: str, **spec: Any) -> dict[str, Any]:
    return {
        "apiVersion": _HELIX_API, "kind": "Genome",
        "metadata": {"name": name}, "spec": dict(spec),
    }


async def _edges(src) -> list[dict[str, Any]]:
    async with src._engine.connect() as conn:
        result = (await conn.execute(sa.select(src.edges))).all()
    return [dict(r._mapping) for r in result]


class TestTheEdgeIsBorn:
    @pytest.mark.anyio
    async def test_a_genome_naming_its_agent_writes_the_edge(self, store):
        k, src = store
        await k.write_instance(
            SCOPE, "Agent", "swe-agent",
            {"apiVersion": _HELIX_API, "kind": "Agent",
             "metadata": {"name": "swe-agent"}, "spec": {"instruction": "hi"}},
        )
        await k.write_instance(
            SCOPE, "Genome", "g", _genome("g", default_agent="swe-agent"),
        )
        rows = [r for r in await _edges(src) if r["source_field"] == "default_agent"]
        assert len(rows) == 1, rows
        assert rows[0]["to_kind"] == "Agent"
        assert rows[0]["to_name"] == "swe-agent"

    @pytest.mark.anyio
    async def test_the_key_addressed_fields_produce_a_DANGLING_edge_and_no_veto(
        self, store,
    ):
        """⚠️ The half of this test that MUST NOT change, and the half that did.

        It used to assert "no edge and no veto". Fatia 5 keeps the second half
        exactly — a write naming a profile that does not exist still persists
        untouched, which is the restraint the ``PricingPlan`` lesson bought —
        and inverts the first: the relation is now followed, so the graph
        RECORDS that it points at nothing.

        A dangling row is the honest output here, not a failure to resolve.
        The row is the list of what is broken; omitting it would render a
        healthier graph than the data deserves, which is the reason
        ``to_kind`` is nullable in the first place."""
        k, src = store
        await k.write_instance(
            SCOPE, "Genome", "g2",
            _genome("g2", default_llm="azure/gpt-4o", owner_tenant="ws-nope"),
        )
        # The write PERSISTED — this is the assertion the slice may never break.
        assert await k.get_instance(SCOPE, "Genome", "g2") is not None
        rows = {r["source_field"]: r for r in await _edges(src)}
        for field, value in (
            ("default_llm", "azure/gpt-4o"), ("owner_tenant", "ws-nope"),
        ):
            assert field in rows, (
                f"Genome.{field} is a followed relation and produced no row — "
                f"an unwritten edge and a resolved one look identical to every "
                f"reader of this table"
            )
            assert rows[field]["to_kind"] is None, "nothing resolved: dangling"
            # What we were POINTED at, since nothing was found — the key, not a
            # name we would have had to invent.
            assert rows[field]["to_name"] == value
