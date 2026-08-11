from __future__ import annotations

import asyncio
import json

import pytest
from click.testing import CliRunner
from dna.definitions import ResolvedAgent, ResolvedRuntimeBinding
from dna.runtime import RunHandle
from dna_cli import main, run_cmd


class _Client:
    def __init__(self):
        self.agent_names = []
        self.binding_names = []
        self.closed = False
        self.binding = ResolvedRuntimeBinding(
            name="local",
            agent="architect",
            protocol="ag-ui",
            host_ref="local-host",
            provider="fake",
        )

    async def resolve_agent(self, name):
        self.agent_names.append(name)
        return ResolvedAgent(name=name, instructions="Analyze")

    async def resolve_runtime_binding(self, name):
        self.binding_names.append(name)
        return self.binding

    async def close(self):
        self.closed = True


class _Harness:
    provider = "fake"

    def __init__(self):
        self.starts = []

    async def start(self, definition, request):
        self.starts.append((definition, request))

        async def worker(emit):
            await emit("message.delta", text="hello ")
            await emit(
                "message.completed",
                text="hello world",
                data={"service_session_id": "service-2"},
            )

        return RunHandle(
            session_id=request.session_id or "generated",
            worker=worker,
            initial_events=(("run.started", None, {"provider": "fake"}),),
        )


def _install(monkeypatch):
    client = _Client()
    harness = _Harness()

    async def client_factory(**kwargs):
        client.factory_kwargs = kwargs
        return client

    monkeypatch.setattr(run_cmd, "_client_factory", client_factory)
    monkeypatch.setattr(run_cmd, "_harness_getter", lambda provider: harness)
    return client, harness


def test_direct_agent_streams_human_output(monkeypatch):
    client, harness = _install(monkeypatch)

    result = CliRunner().invoke(
        main,
        [
            "run",
            "architect",
            "--prompt",
            "Analyze",
            "--provider",
            "fake",
            "--session-id",
            "local-1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "hello " in result.output
    assert "Session: local-1 (service: service-2)" in result.output
    assert client.agent_names == ["architect"]
    assert harness.starts[0][1].prompt == "Analyze"
    assert client.closed is True


def test_json_mode_emits_one_object_per_event(monkeypatch):
    _install(monkeypatch)

    result = CliRunner().invoke(
        main,
        ["run", "architect", "--prompt", "Analyze", "--provider", "fake", "--json"],
    )

    assert result.exit_code == 0, result.output
    events = [json.loads(line) for line in result.output.splitlines()]
    assert [event["type"] for event in events] == [
        "run.started",
        "message.delta",
        "message.completed",
        "run.completed",
    ]
    assert all(event["run_id"] for event in events)


def test_runtime_binding_selects_agent_and_provider(monkeypatch):
    client, harness = _install(monkeypatch)

    result = CliRunner().invoke(
        main,
        ["run", "--binding", "local", "--prompt", "Continue"],
    )

    assert result.exit_code == 0, result.output
    assert client.binding_names == ["local"]
    assert client.agent_names == ["architect"]
    assert harness.starts[0][1].prompt == "Continue"


def test_binding_provider_conflict_is_rejected(monkeypatch):
    client, _ = _install(monkeypatch)

    result = CliRunner().invoke(
        main,
        [
            "run",
            "--binding",
            "local",
            "--prompt",
            "Continue",
            "--provider",
            "other",
        ],
    )

    assert result.exit_code == 2
    assert "conflicts" in result.output
    assert client.closed is True


@pytest.mark.parametrize(
    "args",
    [
        ["run", "--prompt", "Analyze"],
        ["run", "architect", "--binding", "local", "--prompt", "Analyze"],
    ],
)
def test_exactly_one_target_is_required(args):
    result = CliRunner().invoke(main, args)

    assert result.exit_code == 2
    assert "exactly one" in result.output


def test_execute_cancellation_calls_handle_cancel_and_closes(monkeypatch):
    client = _Client()

    class CancellingHandle:
        cancelled = False

        async def events(self):
            raise asyncio.CancelledError
            yield

        async def cancel(self):
            self.cancelled = True

    handle = CancellingHandle()

    class CancellingHarness:
        async def start(self, definition, request):
            return handle

    async def client_factory(**kwargs):
        return client

    monkeypatch.setattr(run_cmd, "_client_factory", client_factory)
    monkeypatch.setattr(
        run_cmd, "_harness_getter", lambda provider: CancellingHarness()
    )

    async def execute():
        await run_cmd._execute(
            agent_name="architect",
            binding_name=None,
            prompt="Analyze",
            scope=None,
            base_dir=None,
            provider="fake",
            session_id=None,
            service_session_id=None,
            json_output=False,
        )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(execute())

    assert handle.cancelled is True
    assert client.closed is True
