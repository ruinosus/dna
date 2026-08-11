from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import FrozenInstanceError

import pytest
from dna.runtime.harness import HarnessEvent, HarnessExecutionError, RunHandle
from dna.runtime.harness_registry import get_harness


async def _collect(handle: RunHandle):
    return [event async for event in handle.events()]


@pytest.mark.asyncio
async def test_handle_emits_one_success_terminal():
    async def worker(emit):
        await emit("message.completed", text="done")

    handle = RunHandle(session_id="session-1", worker=worker)
    events = await _collect(handle)

    assert [event.type for event in events] == [
        "message.completed",
        "run.completed",
    ]


def test_event_and_data_are_immutable():
    source = {"provider": "fake"}
    event = HarnessEvent(
        type="run.started", run_id="run-1", session_id="session-1", data=source
    )
    source["provider"] = "changed"

    assert event.data["provider"] == "fake"
    with pytest.raises(TypeError):
        event.data["provider"] = "changed"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        event.text = "changed"  # type: ignore[misc]


@pytest.mark.asyncio
async def test_handle_maps_worker_failure_and_stops():
    async def worker(emit):
        raise ValueError("provider unavailable")

    events = await _collect(RunHandle(session_id="session-1", worker=worker))

    assert [event.type for event in events] == ["run.failed"]
    assert events[0].data == {
        "error": "ValueError",
        "message": "provider unavailable",
    }


@pytest.mark.asyncio
async def test_handle_cancellation_is_idempotent_and_never_completes():
    started = asyncio.Event()

    async def worker(emit):
        started.set()
        await asyncio.Event().wait()

    handle = RunHandle(session_id="session-1", worker=worker)
    await started.wait()
    await handle.cancel()
    await handle.cancel()
    events = await _collect(handle)

    assert [event.type for event in events] == ["run.cancelled"]


@pytest.mark.asyncio
async def test_handle_events_are_single_consumer():
    handle = RunHandle(
        session_id="session-1", worker=lambda emit: emit("run.completed")
    )
    await _collect(handle)

    with pytest.raises(HarnessExecutionError, match="only be consumed once"):
        await _collect(handle)


def test_builtin_registry_is_lazy_and_actionable():
    assert get_harness("github-copilot").provider == "github-copilot"

    with pytest.raises(Exception, match="available: github-copilot"):
        get_harness("missing")


def test_runtime_import_does_not_load_github_copilot_provider():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import dna.runtime; "
                "assert 'agent_framework' not in sys.modules; "
                "assert 'agent_framework.github' not in sys.modules"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
