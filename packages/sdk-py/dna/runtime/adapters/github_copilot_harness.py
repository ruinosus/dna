"""Consumer lifecycle adapter for the official GitHub Copilot agent."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from dna.definitions import ResolvedAgent
from dna.integrations.github_copilot import build_github_copilot_agent
from dna.runtime.harness import (
    HarnessConfigurationError,
    RunHandle,
    RunRequest,
    SessionResumeError,
)


def _safe_provider_event(update: Any) -> Mapping[str, Any]:
    payload: dict[str, Any] = {}
    for name in ("response_id", "message_id", "role", "finish_reason"):
        value = getattr(update, name, None)
        if value is not None and isinstance(value, (str, int, float, bool)):
            payload[name] = value
    return payload


class GitHubCopilotHarness:
    provider = "github-copilot"

    def __init__(
        self,
        *,
        agent_factory: Callable[[ResolvedAgent], Any] = build_github_copilot_agent,
    ) -> None:
        self._agent_factory = agent_factory

    async def start(
        self,
        definition: ResolvedAgent,
        request: RunRequest,
    ) -> RunHandle:
        try:
            agent = self._agent_factory(definition)
        except ImportError as error:
            raise HarnessConfigurationError(str(error)) from error
        except (TypeError, ValueError) as error:
            raise HarnessConfigurationError(str(error)) from error

        try:
            if request.service_session_id:
                session = agent.get_session(
                    request.service_session_id,
                    session_id=request.session_id,
                )
                session_event = "session.resumed"
            else:
                session = agent.create_session(session_id=request.session_id)
                session_event = "session.started"
        except Exception as error:
            if request.service_session_id:
                raise SessionResumeError(
                    f"Could not resume GitHub Copilot session: {error}"
                ) from error
            raise HarnessConfigurationError(
                f"Could not create GitHub Copilot session: {error}"
            ) from error

        session_id = str(session.session_id)
        session_data = {
            "provider": self.provider,
            "service_session_id": request.service_session_id,
        }

        async def consume(emit) -> None:
            stream = agent.run(request.prompt, stream=True, session=session)
            async for update in stream:
                text = getattr(update, "text", None)
                if text:
                    await emit(
                        "message.delta",
                        text=str(text),
                        data=_safe_provider_event(update),
                    )
            response = await stream.get_final_response()
            service_id = getattr(session, "service_session_id", None)
            await emit(
                "message.completed",
                text=str(getattr(response, "text", "") or ""),
                data={
                    "provider": self.provider,
                    "service_session_id": str(service_id) if service_id else None,
                    **_safe_provider_event(response),
                },
            )

        return RunHandle(
            session_id=session_id,
            worker=consume,
            initial_events=(
                ("run.started", None, {"provider": self.provider}),
                (session_event, None, session_data),
            ),
        )


__all__ = ["GitHubCopilotHarness"]
