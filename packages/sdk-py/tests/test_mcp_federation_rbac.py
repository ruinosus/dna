"""MCPFederation read/write + min-role RBAC (absorption phase 6a, §6.4).

Extends the flat ``allowed_tools`` allowlist with read/write tool
governance + per-tool role floors (``min_role`` / ``min_role_write``),
mirroring foundry-assured's ``McpServer`` registry
(apps/backend/app/agents/mcp/registry.py) adapted to DNA's role ladder
(``guest < member < admin < owner``, highest-rank-wins).

Back-compat is SACRED: ``allowed_tools`` is unchanged. The read/write
split + role floors are ADDITIVE, OPTIONAL refinements — a legacy doc
with only ``allowed_tools`` (and no split) behaves EXACTLY as before
(RBAC off, ``allowed_tools`` governs alone).

Twin: packages/sdk-ts/tests/mcp-federation-rbac.test.ts — keep the field
lists, RBAC semantics, and the back-compat cases in sync.
"""
from __future__ import annotations

import jsonschema
import pytest

from dna.extensions.federation import (
    MCPFederationKind,
    STANDARD_ROLE_RANKS,
    classify_tool,
    resolve_tools,
    visible_tools,
)


@pytest.fixture(scope="module")
def fed_schema() -> dict:
    return MCPFederationKind().schema()


class TestRBACSchemaFields:
    def test_schema_is_still_valid_jsonschema(self, fed_schema):
        jsonschema.Draft7Validator.check_schema(fed_schema)

    def test_rbac_fields_present_with_defaults(self, fed_schema):
        props = fed_schema["properties"]
        for f in ("read_tools", "write_tools", "min_role", "min_role_write"):
            assert f in props, f"missing RBAC field: {f}"
        assert props["read_tools"]["default"] == []
        assert props["write_tools"]["default"] == []
        # DNA ladder floors: reads default to the lowest rung, writes above it.
        assert props["min_role"]["default"] == "guest"
        assert props["min_role_write"]["default"] == "member"

    def test_v2_fields_untouched(self, fed_schema):
        """The RBAC extension is additive — the v2 fields are all still here."""
        props = fed_schema["properties"]
        for f in (
            "transport", "url", "command", "args", "env", "cwd",
            "tool_prefix", "enabled", "allowed_tools", "timeout_s",
            "auth", "propagate_tenant", "health_check", "tags",
        ):
            assert f in props, f"RBAC extension dropped v2 field: {f}"


class TestStandardLadder:
    def test_standard_ranks(self):
        assert STANDARD_ROLE_RANKS == {
            "guest": 0, "member": 10, "admin": 20, "owner": 30,
        }


class TestClassifyTool:
    def test_read_tool_classifies_read(self):
        spec = {"read_tools": ["search"], "write_tools": ["deploy"]}
        assert classify_tool(spec, "search") == "read"

    def test_write_tool_classifies_write(self):
        spec = {"read_tools": ["search"], "write_tools": ["deploy"]}
        assert classify_tool(spec, "deploy") == "write"

    def test_unclassified_is_write_fail_closed(self):
        """A tool on NEITHER list is a WRITE (fail-closed) — an unclassified
        new tool can't slip through as an open read. Mirrors foundry."""
        spec = {"read_tools": ["search"], "write_tools": ["deploy"]}
        assert classify_tool(spec, "mystery_new_tool") == "write"


class TestVisibleTools:
    SPEC = {
        "read_tools": ["search", "fetch"],
        "write_tools": ["deploy"],
        "min_role": "guest",
        "min_role_write": "member",
    }

    def test_reader_sees_reads_not_writes(self):
        reads, writes = visible_tools(self.SPEC, {"guest"})
        assert reads == ["search", "fetch"]
        assert writes == []  # guest is below min_role_write=member

    def test_member_sees_reads_and_writes(self):
        reads, writes = visible_tools(self.SPEC, {"member"})
        assert reads == ["search", "fetch"]
        assert writes == ["deploy"]

    def test_below_min_role_denied_read(self):
        spec = {**self.SPEC, "min_role": "admin"}
        reads, writes = visible_tools(spec, {"member"})
        assert reads == []  # member (10) below admin (20) → no reads

    def test_below_min_role_write_denied_write(self):
        reads, writes = visible_tools(self.SPEC, {"guest"})
        assert writes == []  # guest (0) below member (10) → no writes

    def test_no_role_sees_nothing(self):
        """Fail-closed: a caller with no roles sees nothing."""
        reads, writes = visible_tools(self.SPEC, set())
        assert reads == []
        assert writes == []

    def test_highest_role_wins(self):
        """A caller with multiple roles is gated by the HIGHEST (max rank)."""
        reads, writes = visible_tools(self.SPEC, {"guest", "admin"})
        assert reads == ["search", "fetch"]
        assert writes == ["deploy"]  # admin (20) >= member (10)

    def test_unknown_floor_is_fail_closed(self):
        """An unrecognized floor role (not in the standard ladder, no rank
        override) denies — better closed than silently open."""
        spec = {**self.SPEC, "min_role": "wizard"}
        reads, _ = visible_tools(spec, {"owner"})
        assert reads == []

    def test_role_ranks_override_custom_ladder(self):
        """DNA's thesis: roles are data. A consumer can inject the tenant's
        actual ladder (custom rungs) so the pure gate honors it."""
        spec = {"read_tools": ["search"], "min_role": "auditor"}
        ranks = {"guest": 0, "auditor": 5, "member": 10}
        reads, _ = visible_tools(spec, {"auditor"}, role_ranks=ranks)
        assert reads == ["search"]


class TestResolveToolsBackCompat:
    def test_legacy_allowed_tools_behaves_exactly_as_before(self):
        """THE SACRED back-compat test. A legacy federation with only
        allowed_tools (no read/write split) → RBAC is OFF, allowed_tools is
        returned untouched, and NO role gating is applied. Behaves exactly
        as before the extension existed."""
        legacy = {"allowed_tools": ["search", "deploy"]}
        got = resolve_tools(legacy, roles=set())  # even a no-role caller
        assert got["rbac"] is False
        assert got["allowed"] == ["search", "deploy"]
        assert got["reads"] == []
        assert got["writes"] == []

    def test_legacy_empty_allowed_means_all_unchanged(self):
        """Empty allowed_tools still means 'all tools' — the v2 semantics —
        unchanged by the RBAC extension."""
        got = resolve_tools({}, roles=set())
        assert got["rbac"] is False
        assert got["allowed"] == []  # empty = all (caller keeps prior behavior)

    def test_split_declared_turns_rbac_on(self):
        spec = {
            "read_tools": ["search"],
            "write_tools": ["deploy"],
            "min_role_write": "member",
        }
        got = resolve_tools(spec, roles={"member"})
        assert got["rbac"] is True
        assert got["reads"] == ["search"]
        assert got["writes"] == ["deploy"]

    def test_allowed_tools_can_only_tighten_the_split(self):
        """When BOTH the split and allowed_tools are present, allowed_tools
        is an outer bound (stricter-of-both) — it can tighten, never loosen.
        Mirrors foundry's registry ∧ connection min-role."""
        spec = {
            "read_tools": ["search", "fetch"],
            "write_tools": ["deploy", "purge"],
            "allowed_tools": ["search", "deploy"],  # purge/fetch excluded
            "min_role_write": "member",
        }
        got = resolve_tools(spec, roles={"member"})
        assert got["reads"] == ["search"]
        assert got["writes"] == ["deploy"]


class TestLegacyDocStillValidates:
    def test_v1_and_v2_docs_still_validate_after_extension(self, fed_schema):
        # v1 stdio doc
        jsonschema.validate(
            {"command": "npx", "args": ["-y", "graphify-mcp"], "allowed_tools": ["x"]},
            fed_schema,
        )
        # v2 http doc
        jsonschema.validate(
            {"transport": "streamable_http", "url": "https://mcp.draw.io/mcp"},
            fed_schema,
        )
        # new RBAC doc
        jsonschema.validate(
            {
                "transport": "streamable_http",
                "url": "https://x/mcp",
                "read_tools": ["a"],
                "write_tools": ["b"],
                "min_role": "guest",
                "min_role_write": "admin",
            },
            fed_schema,
        )
