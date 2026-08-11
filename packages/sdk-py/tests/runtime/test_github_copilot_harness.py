from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from dna.definitions import ResolvedAgent
from dna.runtime.adapters.github_copilot_harness import GitHubCopilotHarness
from dna.runtime.harness import RunRequest, SessionResumeError


@dataclass
class _Update:
    text: str
    response_id: str = "response-1"
    raw_representation: str = "secret"


class _Response:
    text = "complete answer"
    response_id = "response-1"


class _Stream:
    def __init__(self, updates=None):
        self._updates = list(
            updates if updates is not None else (_Update("hello "), _Update("world"))
        )
        self.finalized = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._updates:
            raise StopAsyncIteration
        return self._updates.pop(0)

    async def get_final_response(self):
        self.finalized += 1
        return _Response()


class _Session:
    def __init__(self, session_id="local-1", service_session_id=None):
        self.session_id = session_id
        self.service_session_id = service_session_id


class _Agent:
    def __init__(self):
        self.stream = _Stream()
        self.created = None
        self.resumed = None
        self.run_args = None

    def create_session(self, *, session_id=None):
        self.created = session_id
        return _Session(session_id or "generated")

    def get_session(self, service_session_id, *, session_id=None):
        self.resumed = (service_session_id, session_id)
        return _Session(session_id or "generated", service_session_id)

    def run(self, prompt, *, stream, session):
        self.run_args = (prompt, stream, session)
        session.service_session_id = "service-2"
        return self.stream


def _definition():
    return ResolvedAgent(name="architect", instructions="Analyze carefully")


async def _collect(handle):
    return [event async for event in handle.events()]


@pytest.mark.asyncio
async def test_new_session_streams_normalized_events_and_resume_metadata():
    agent = _Agent()
    harness = GitHubCopilotHarness(agent_factory=lambda definition: agent)

    handle = await harness.start(
        _definition(), RunRequest(prompt="Analyze", session_id="local-1")
    )
    events = await _collect(handle)

    assert [event.type for event in events] == [
        "run.started",
        "session.started",
        "message.delta",
        "message.delta",
        "message.completed",
        "run.completed",
    ]
    assert [event.text for event in events if event.type == "message.delta"] == [
        "hello ",
        "world",
    ]
    assert events[-2].text == "complete answer"
    assert events[-2].data["service_session_id"] == "service-2"
    assert "raw_representation" not in events[2].data
    assert agent.created == "local-1"
    assert agent.stream.finalized == 1


@pytest.mark.asyncio
async def test_existing_service_session_is_resumed():
    agent = _Agent()
    harness = GitHubCopilotHarness(agent_factory=lambda definition: agent)

    events = await _collect(
        await harness.start(
            _definition(),
            RunRequest(
                prompt="Continue",
                session_id="local-1",
                service_session_id="service-1",
            ),
        )
    )

    assert events[1].type == "session.resumed"
    assert agent.resumed == ("service-1", "local-1")


@pytest.mark.asyncio
async def test_resume_failure_is_typed():
    class BrokenAgent(_Agent):
        def get_session(self, service_session_id, *, session_id=None):
            raise ValueError("unknown conversation")

    harness = GitHubCopilotHarness(agent_factory=lambda definition: BrokenAgent())

    with pytest.raises(SessionResumeError, match="unknown conversation"):
        await harness.start(
            _definition(),
            RunRequest(prompt="Continue", service_session_id="missing"),
        )


@pytest.mark.asyncio
async def test_cancel_interrupts_blocked_provider_stream():
    entered = asyncio.Event()

    class BlockingStream(_Stream):
        async def __anext__(self):
            entered.set()
            await asyncio.Event().wait()

    agent = _Agent()
    agent.stream = BlockingStream()
    handle = await GitHubCopilotHarness(agent_factory=lambda definition: agent).start(
        _definition(), RunRequest(prompt="Wait")
    )

    await entered.wait()
    await handle.cancel()
    events = await _collect(handle)

    assert events[-1].type == "run.cancelled"
    assert "run.completed" not in [event.type for event in events]
