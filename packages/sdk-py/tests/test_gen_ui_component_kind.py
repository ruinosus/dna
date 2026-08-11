from __future__ import annotations

import pytest

from dna import DnaClient
from dna.definitions import (
    GenUIA2UIBinding,
    GenUIGroundingPolicy,
    GenUIMcpBinding,
    ResolvedGenUIBinding,
    ResolvedGenUIComponent,
)
from dna.kernel.kinds.identifiers import identifiers_of
from dna.kernel.kinds.registry import KindRegistry
from dna.kernel.source.descriptor_loader import load_descriptors


@pytest.fixture
def port():
    registry = KindRegistry()
    registered = [
        registry.register_from_descriptor(raw)
        for raw in load_descriptors("dna.extensions.runtime")
    ]
    return next(item for item in registered if item.kind == "GenUIComponent")


@pytest.fixture
def binding_port():
    registry = KindRegistry()
    registered = [
        registry.register_from_descriptor(raw)
        for raw in load_descriptors("dna.extensions.runtime")
    ]
    return next(item for item in registered if item.kind == "GenUIBinding")


def component_spec(**overrides):
    spec = {
        "tool_name": "render_incident_brief",
        "description": "Render a visual operational incident brief.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "severity": {"enum": ["SEV-1", "SEV-2", "SEV-3"]},
            },
            "required": ["title", "severity"],
        },
        "renderer_ref": "incident-brief",
        "protocols": ["ag-ui"],
        "required_capabilities": ["frontend-tools"],
        "fallback": {"type": "markdown"},
    }
    spec.update(overrides)
    return spec


def standards_component_spec(**overrides):
    spec = {
        "description": "Render a grounded operational incident brief.",
        "mcp": {
            "tool_name": "get_incident_brief",
            "resource_uri": "ui://incident-brief/app.html",
        },
        "a2ui": {
            "catalog_id": "https://opentag.dev/a2ui/catalogs/operations/v1",
            "component": "IncidentBrief",
        },
        "grounding": {
            "source": "mcp-tool-result",
            "enforce": True,
        },
        "protocols": ["mcp-apps", "a2ui", "ag-ui"],
        "required_capabilities": ["mcp-apps", "a2ui"],
        "fallback": {"type": "markdown"},
        "contract_version": 2,
    }
    spec.update(overrides)
    return spec


def parse(port, spec):
    return port.parse({
        "apiVersion": "github.com/ruinosus/dna/runtime/v1alpha1",
        "kind": "GenUIComponent",
        "metadata": {"name": "incident-brief"},
        "spec": spec,
    })


def test_gen_ui_component_registers_and_parses(port):
    parsed = parse(port, component_spec())
    renderer_identifier = identifiers_of(port)["renderer_ref"]

    assert port.api_version == "github.com/ruinosus/dna/runtime/v1alpha1"
    assert renderer_identifier.role == "external"
    assert renderer_identifier.system == "ui-host"
    assert parsed["spec"]["renderer_ref"] == "incident-brief"
    assert parsed["spec"]["contract_version"] == 1


def test_gen_ui_component_accepts_structured_protocol_bindings(port):
    parsed = parse(port, standards_component_spec())

    assert "tool_name" not in parsed["spec"]
    assert "input_schema" not in parsed["spec"]
    assert "renderer_ref" not in parsed["spec"]
    assert parsed["spec"]["mcp"] == {
        "tool_name": "get_incident_brief",
        "resource_uri": "ui://incident-brief/app.html",
    }
    assert parsed["spec"]["a2ui"]["component"] == "IncidentBrief"
    assert parsed["spec"]["grounding"] == {
        "source": "mcp-tool-result",
        "enforce": True,
    }


@pytest.mark.parametrize("field", ["tool_name", "input_schema", "renderer_ref"])
def test_gen_ui_component_rejects_partial_legacy_bindings(port, field):
    with pytest.raises(Exception):
        parse(port, standards_component_spec(**{field: component_spec()[field]}))


def test_gen_ui_component_requires_mcp_for_tool_result_grounding(port):
    spec = standards_component_spec()
    spec.pop("mcp")

    with pytest.raises(Exception):
        parse(port, spec)


@pytest.mark.parametrize("field", ["code", "module", "url"])
def test_gen_ui_component_rejects_executable_or_remote_fields(port, field):
    with pytest.raises(Exception):
        parse(port, component_spec(**{field: "https://example.test/component.js"}))


def test_gen_ui_component_requires_a_symbolic_renderer_reference(port):
    with pytest.raises(Exception):
        parse(port, component_spec(renderer_ref="https://example.test/component.js"))


def test_gen_ui_component_requires_an_object_tool_schema(port):
    with pytest.raises(Exception):
        parse(port, component_spec(input_schema={"type": "string"}))


def test_gen_ui_binding_registers_and_parses(binding_port):
    parsed = binding_port.parse({
        "apiVersion": "github.com/ruinosus/dna/runtime/v1alpha1",
        "kind": "GenUIBinding",
        "metadata": {"name": "opentag-triage-ui"},
        "spec": {
            "agent": "opentag-triage",
            "components": ["incident-brief"],
        },
    })

    assert parsed["spec"]["agent"] == "opentag-triage"
    assert parsed["spec"]["components"] == ["incident-brief"]


@pytest.mark.parametrize("spec", [
    {"agent": "opentag-triage", "components": []},
    {"agent": "", "components": ["incident-brief"]},
    {"agent": "opentag-triage", "components": ["incident-brief", "incident-brief"]},
])
def test_gen_ui_binding_rejects_invalid_assignments(binding_port, spec):
    with pytest.raises(Exception):
        binding_port.parse({
            "apiVersion": "github.com/ruinosus/dna/runtime/v1alpha1",
            "kind": "GenUIBinding",
            "metadata": {"name": "invalid"},
            "spec": spec,
        })


def test_resolved_component_rejects_a_remote_renderer_reference():
    raw = {
        "metadata": {"name": "unsafe"},
        "spec": component_spec(renderer_ref="https://example.test/component.js"),
    }

    with pytest.raises(ValueError, match="symbolic host key"):
        ResolvedGenUIComponent.from_instance(raw)


def test_resolved_component_preserves_legacy_positional_construction():
    resolved = ResolvedGenUIComponent(
        "incident-brief",
        "render_incident_brief",
        "Render an operational incident brief.",
        {"type": "object", "properties": {}},
        "incident-brief",
        ("ag-ui",),
        frozenset({"frontend-tools"}),
        "markdown",
    )

    assert resolved.name == "incident-brief"
    assert resolved.renderer_ref == "incident-brief"
    assert resolved.mcp is None
    assert resolved.a2ui is None


def test_resolved_component_projects_structured_protocol_bindings():
    resolved = ResolvedGenUIComponent.from_instance({
        "metadata": {"name": "incident-brief"},
        "spec": standards_component_spec(),
    })

    assert resolved.tool_name is None
    assert resolved.input_schema is None
    assert resolved.renderer_ref is None
    assert resolved.mcp == GenUIMcpBinding(
        tool_name="get_incident_brief",
        resource_uri="ui://incident-brief/app.html",
    )
    assert resolved.a2ui == GenUIA2UIBinding(
        catalog_id="https://opentag.dev/a2ui/catalogs/operations/v1",
        component="IncidentBrief",
    )
    assert resolved.grounding == GenUIGroundingPolicy(
        source="mcp-tool-result",
        enforce=True,
    )
    assert resolved.contract_version == 2


def test_resolved_component_requires_a_rendering_binding():
    spec = standards_component_spec()
    spec.pop("mcp")
    spec.pop("a2ui")

    with pytest.raises(ValueError, match="legacy host binding, spec.mcp, or spec.a2ui"):
        ResolvedGenUIComponent.from_instance({
            "metadata": {"name": "invalid"},
            "spec": spec,
        })


@pytest.mark.asyncio
async def test_client_lists_gen_ui_components(tmp_path):
    scope = tmp_path / "opentag"
    components = scope / "gen-ui-components"
    bindings = scope / "gen-ui-bindings"
    components.mkdir(parents=True)
    bindings.mkdir()
    (scope / "Genome.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\nmetadata: {name: opentag}\nspec: {}\n"
    )
    spec = component_spec()
    (components / "incident-brief.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/runtime/v1alpha1\n"
        "kind: GenUIComponent\n"
        "metadata: {name: incident-brief}\n"
        "spec:\n"
        "  description: Render a grounded operational incident brief.\n"
        "  mcp:\n"
        "    tool_name: get_incident_brief\n"
        "    resource_uri: ui://incident-brief/app.html\n"
        "  a2ui:\n"
        "    catalog_id: https://opentag.dev/a2ui/catalogs/operations/v1\n"
        "    component: IncidentBrief\n"
        "  grounding: {source: mcp-tool-result, enforce: true}\n"
        "  protocols: [mcp-apps, a2ui, ag-ui]\n"
        "  required_capabilities: [mcp-apps, a2ui]\n"
        "  fallback: {type: markdown}\n"
        "  contract_version: 2\n"
    )
    (bindings / "opentag-triage-ui.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/runtime/v1alpha1\n"
        "kind: GenUIBinding\n"
        "metadata: {name: opentag-triage-ui}\n"
        "spec:\n"
        "  agent: opentag-triage\n"
        "  components: [incident-brief]\n"
    )

    async with await DnaClient.from_env(
        scope="opentag", base_dir=str(tmp_path),
    ) as client:
        resolved = await client.list_gen_ui_components()
        assigned = await client.list_gen_ui_components(agent="opentag-triage")
        unassigned = await client.list_gen_ui_components(agent="another-agent")
        binding = await client.list_gen_ui_bindings(agent="opentag-triage")

    assert len(resolved) == 1
    assert resolved[0].name == "incident-brief"
    assert resolved[0].renderer_ref is None
    assert resolved[0].mcp == GenUIMcpBinding(
        tool_name="get_incident_brief",
        resource_uri="ui://incident-brief/app.html",
    )
    assert resolved[0].a2ui == GenUIA2UIBinding(
        catalog_id="https://opentag.dev/a2ui/catalogs/operations/v1",
        component="IncidentBrief",
    )
    assert resolved[0].grounding == GenUIGroundingPolicy(
        source="mcp-tool-result",
        enforce=True,
    )
    assert resolved[0].required_capabilities == frozenset({"mcp-apps", "a2ui"})
    assert resolved[0].contract_version == 2
    assert assigned == resolved
    assert unassigned == ()
    assert binding == (
        ResolvedGenUIBinding(
            name="opentag-triage-ui",
            agent="opentag-triage",
            components=("incident-brief",),
            scope="opentag",
        ),
    )