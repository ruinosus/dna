from __future__ import annotations

import pytest

from dna import DnaClient, RuntimeBindingNotFound
from dna.definitions import ResolvedRuntimeBinding, RuntimePolicy
from dna.kernel.kinds.registry import KindRegistry
from dna.kernel.source.descriptor_loader import load_descriptors


@pytest.fixture
def port():
    registry = KindRegistry()
    registered = [
        registry.register_from_descriptor(raw)
        for raw in load_descriptors("dna.extensions.runtime")
    ]
    return next(item for item in registered if item.kind == "RuntimeBinding")


def binding_spec(**overrides):
    spec = {
        "agent": "opentag-triage",
        "runtime": {"protocol": "ahp", "provider": "vscode-agent-host"},
        "host": {"ref": "local-vscode-agent-host"},
        "policy": {
            "sessions": "host-authoritative",
            "reconnect": "resume",
            "confirmations": "host",
        },
    }
    spec.update(overrides)
    return spec


def parse(port, spec):
    return port.parse({
        "apiVersion": "github.com/ruinosus/dna/runtime/v1alpha1",
        "kind": "RuntimeBinding",
        "metadata": {"name": "opentag-vscode-host"},
        "spec": spec,
    })


def test_runtime_binding_registers_and_parses(port):
    parsed = parse(port, binding_spec())

    assert port.api_version == "github.com/ruinosus/dna/runtime/v1alpha1"
    assert parsed["spec"]["runtime"]["protocol"] == "ahp"


@pytest.mark.parametrize("field", ["endpoint", "credentials", "token"])
def test_runtime_binding_rejects_deployment_fields(port, field):
    with pytest.raises(Exception):
        parse(port, binding_spec(**{field: "must-not-live-in-dna"}))


def test_runtime_binding_requires_named_host_reference(port):
    with pytest.raises(Exception):
        parse(port, binding_spec(host={"endpoint": "ws://127.0.0.1:8125"}))

    with pytest.raises(Exception):
        parse(port, binding_spec(host={"ref": "ws://127.0.0.1:8125"}))


def test_resolved_binding_is_runtime_neutral_data():
    binding = ResolvedRuntimeBinding.from_instance({
        "metadata": {"name": "opentag-vscode-host"},
        "spec": binding_spec(),
    }, scope="opentag")

    assert binding == ResolvedRuntimeBinding(
        name="opentag-vscode-host",
        agent="opentag-triage",
        protocol="ahp",
        provider="vscode-agent-host",
        host_ref="local-vscode-agent-host",
        policy=RuntimePolicy(
            sessions="host-authoritative",
            reconnect="resume",
            confirmations="host",
        ),
        scope="opentag",
    )


def test_projection_rejects_a_raw_host_endpoint():
    with pytest.raises(ValueError, match="raw endpoint"):
        ResolvedRuntimeBinding.from_instance({
            "metadata": {"name": "unsafe"},
            "spec": binding_spec(host={"ref": "ws://127.0.0.1:8125"}),
        })


@pytest.mark.asyncio
async def test_client_resolves_binding_by_name(tmp_path):
    scope = tmp_path / "opentag"
    bindings = scope / "runtime-bindings"
    bindings.mkdir(parents=True)
    (scope / "Genome.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\nmetadata: {name: opentag}\nspec: {}\n"
    )
    (bindings / "opentag-vscode-host.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/runtime/v1alpha1\n"
        "kind: RuntimeBinding\n"
        "metadata: {name: opentag-vscode-host}\n"
        "spec:\n"
        "  agent: opentag-triage\n"
        "  runtime: {protocol: ahp, provider: vscode-agent-host}\n"
        "  host: {ref: local-vscode-agent-host}\n"
    )

    async with await DnaClient.from_env(
        scope="opentag", base_dir=str(tmp_path),
    ) as client:
        binding = await client.resolve_runtime_binding("opentag-vscode-host")

    assert binding.host_ref == "local-vscode-agent-host"
    assert binding.scope == "opentag"


@pytest.mark.asyncio
async def test_client_fails_loud_for_missing_binding(tmp_path):
    scope = tmp_path / "opentag"
    scope.mkdir()
    (scope / "Genome.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\nmetadata: {name: opentag}\nspec: {}\n"
    )

    async with await DnaClient.from_env(
        scope="opentag", base_dir=str(tmp_path),
    ) as client:
        with pytest.raises(RuntimeBindingNotFound, match="missing"):
            await client.resolve_runtime_binding("missing")