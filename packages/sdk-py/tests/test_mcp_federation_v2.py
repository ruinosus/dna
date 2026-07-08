"""MCPFederation schema v2 + Agent.spec.mcp_servers.

Story: s-mcp-servers-on-agent (f-declarative-tools-mcp).
Spec: docs/superpowers/specs/2026-07-07-mcp-first-tools-design.md §5.1.

Twin: packages/sdk-ts/tests/mcp-federation-v2.test.ts — keep assertions
in sync (field lists, back-compat cases).
"""
from __future__ import annotations

import jsonschema
import pytest

from dna import Kernel
from dna.extensions.federation import MCPFederationKind
from dna.kernel.models import AgentSpec


@pytest.fixture(scope="module")
def fed_schema() -> dict:
    return MCPFederationKind().schema()


class TestMCPFederationSchemaV2:
    def test_schema_is_valid_jsonschema(self, fed_schema):
        jsonschema.Draft7Validator.check_schema(fed_schema)

    def test_v2_fields_present(self, fed_schema):
        props = fed_schema["properties"]
        for f in (
            "transport", "url", "command", "args", "env", "cwd",
            "tool_prefix", "enabled", "allowed_tools", "timeout_s",
            "auth", "propagate_tenant", "health_check", "tags",
        ):
            assert f in props, f"missing v2 field: {f}"
        assert props["transport"]["enum"] == ["stdio", "streamable_http"]
        assert props["transport"]["default"] == "stdio"
        assert props["timeout_s"]["default"] == 30

    def test_auth_carries_env_names_only(self, fed_schema):
        """The auth block has NO field for a secret VALUE — only the
        env-var NAME. Guard against someone adding `token`/`value`."""
        auth = fed_schema["properties"]["auth"]
        assert auth["additionalProperties"] is False
        assert set(auth["properties"]) == {"kind", "env", "header"}
        assert auth["properties"]["kind"]["enum"] == [
            "none", "bearer_env", "header_env",
        ]

    def test_v1_stdio_doc_still_valid(self, fed_schema):
        """Back-compat: every v1 doc (command, no transport) validates."""
        v1_spec = {
            "command": "npx",
            "args": ["-y", "graphify-mcp"],
            "env": {"FOO": "bar"},
            "tool_prefix": "graphify_",
            "enabled": True,
            "tags": ["code"],
        }
        jsonschema.validate(v1_spec, fed_schema)

    def test_http_doc_requires_url(self, fed_schema):
        jsonschema.validate(
            {"transport": "streamable_http", "url": "https://mcp.draw.io/mcp"},
            fed_schema,
        )
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"transport": "streamable_http"}, fed_schema)

    def test_stdio_doc_requires_command(self, fed_schema):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"transport": "stdio"}, fed_schema)
        with pytest.raises(jsonschema.ValidationError):
            # transport omitted defaults to stdio → command required
            jsonschema.validate({"url": "https://x/mcp"}, fed_schema)

    def test_describe_and_summary_http(self):
        kind = MCPFederationKind()

        class Doc:
            spec = {
                "transport": "streamable_http",
                "url": "https://mcp.draw.io/mcp",
                "tool_prefix": "drawio_",
            }

        assert kind.describe(Doc()) == "https://mcp.draw.io/mcp (drawio_)"
        s = kind.summary(Doc())
        assert s["transport"] == "streamable_http"
        assert s["url"] == "https://mcp.draw.io/mcp"

    def test_describe_and_summary_stdio_backcompat(self):
        kind = MCPFederationKind()

        class Doc:
            spec = {"command": "npx", "tool_prefix": "g_"}

        assert kind.describe(Doc()) == "npx (g_)"
        s = kind.summary(Doc())
        assert s["transport"] == "stdio"
        assert s["command"] == "npx"


class TestAgentMcpServers:
    def test_spec_parses_string_and_dict_entries(self):
        spec = AgentSpec.from_raw({
            "instruction": "x",
            "mcp_servers": [
                "web-search",
                {"ref": "drawio", "allowed_tools": ["search_shapes"], "timeout_s": 20},
            ],
        })
        assert spec.mcp_servers == [
            "web-search",
            {"ref": "drawio", "allowed_tools": ["search_shapes"], "timeout_s": 20},
        ]

    def test_spec_defaults_to_empty(self):
        assert AgentSpec.from_raw({}).mcp_servers == []

    def test_kernel_schema_exposes_field(self):
        k = Kernel.auto()
        kp = next(
            (kp for kp in k._kinds.values() if kp.kind == "Agent"), None,
        )
        assert kp is not None
        assert "mcp_servers" in kp.schema()["properties"]

    def test_ui_schema_hint(self):
        k = Kernel.auto()
        kp = next(
            (kp for kp in k._kinds.values() if kp.kind == "Agent"), None,
        )
        ui = getattr(kp, "ui_schema", {}) or {}
        assert "mcp_servers" in ui
