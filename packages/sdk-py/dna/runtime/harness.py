"""Consumer lifecycle contracts layered above provider-owned agent loops."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Protocol
from uuid import uuid4

from dna.definitions import ResolvedAgent


class HarnessError(Exception):
    """Base error for consumer harness lifecycle failures."""


class HarnessNotFound(HarnessError):
    """Raised when no harness is registered for a provider."""


class HarnessConfigurationError(HarnessError):
    """Raised when a harness cannot be configured."""


class HarnessExecutionError(HarnessError):
    """Raised when a provider execution fails before it can be streamed."""


class SessionResumeError(HarnessError):
    """Raised when a provider session cannot be resumed."""


@dataclass(frozen=True)
class RunRequest:
    prompt: str
    session_id: str | None = None
    service_session_id: str | None = None

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise HarnessConfigurationError("Run prompt must not be empty")


@dataclass(frozen=True)
class HarnessEvent:
    type: str
    run_id: str
    session_id: str
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    text: str | None = None
    data: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.type,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat(),
        }
        if self.text is not None:
            payload["text"] = self.text
        if self.data:
            payload["data"] = dict(self.data)
        return payload


EventEmitter = Callable[..., Awaitable[None]]
RunWorker = Callable[[EventEmitter], Awaitable[None]]
_END = object()
_TERMINAL_EVENTS = {"run.completed", "run.cancelled", "run.failed"}


class RunHandle:
    """One active run with a single-consumer event stream."""

    def __init__(
        self,
        *,
        session_id: str,
        worker: RunWorker,
        run_id: str | None = None,
        initial_events: tuple[tuple[str, str | None, Mapping[str, Any]], ...] = (),
    ) -> None:
        self.run_id = run_id or str(uuid4())
        self.session_id = session_id
        self._queue: asyncio.Queue[HarnessEvent | object] = asyncio.Queue()
        self._terminal: str | None = None
        self._events_claimed = False
        for event_type, text, data in initial_events:
            self._queue.put_nowait(self._event(event_type, text=text, data=data))
        self._task = asyncio.create_task(self._drive(worker))

    def _event(
        self,
        event_type: str,
        *,
        text: str | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> HarnessEvent:
        return HarnessEvent(
            type=event_type,
            run_id=self.run_id,
            session_id=self.session_id,
            text=text,
            data=data or {},
        )

    async def _emit(
        self,
        event_type: str,
        *,
        text: str | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> None:
        if self._terminal is not None:
            return
        if event_type in _TERMINAL_EVENTS:
            self._terminal = event_type
        await self._queue.put(self._event(event_type, text=text, data=data))

    async def _drive(self, worker: RunWorker) -> None:
        try:
            await worker(self._emit)
        except asyncio.CancelledError:
            await self._emit("run.cancelled")
        except Exception as error:  # noqa: BLE001 - provider boundary
            await self._emit(
                "run.failed",
                data={"error": type(error).__name__, "message": str(error)},
            )
        finally:
            if self._terminal is None:
                await self._emit("run.completed")
            await self._queue.put(_END)

    async def events(self) -> AsyncIterator[HarnessEvent]:
        if self._events_claimed:
            raise HarnessExecutionError("Run events may only be consumed once")
        self._events_claimed = True
        while True:
            item = await self._queue.get()
            if item is _END:
                break
            yield item  # type: ignore[misc]

    async def cancel(self) -> None:
        if self._terminal is not None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            # A task cancelled before its first scheduling point cannot emit.
            await self._emit("run.cancelled")
            await self._queue.put(_END)


class AgentHarnessPort(Protocol):
    provider: str

    async def start(
        self,
        definition: ResolvedAgent,
        request: RunRequest,
    ) -> RunHandle: ...


AgentHarness = AgentHarnessPort


__all__ = [
    "AgentHarness",
    "AgentHarnessPort",
    "HarnessConfigurationError",
    "HarnessError",
    "HarnessEvent",
    "HarnessExecutionError",
    "HarnessNotFound",
    "RunHandle",
    "RunRequest",
    "SessionResumeError",
]
