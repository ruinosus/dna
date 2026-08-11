"""Execute a resolved DNA Agent through a provider-owned consumer harness."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import click
from dna import DnaClient
from dna.runtime import (
    HarnessError,
    HarnessEvent,
    RunRequest,
    get_harness,
)

_client_factory: Callable[..., Any] = DnaClient.from_env
_harness_getter: Callable[[str], Any] = get_harness


def _print_event(
    event: HarnessEvent, *, json_output: bool, state: dict[str, Any]
) -> None:
    if json_output:
        click.echo(json.dumps(event.to_dict(), separators=(",", ":")))
        return
    if event.type == "message.delta" and event.text:
        click.echo(event.text, nl=False)
        state["streamed"] = True
    elif event.type == "message.completed":
        if not state.get("streamed") and event.text:
            click.echo(event.text, nl=False)
        if event.text or state.get("streamed"):
            click.echo()
        service_id = event.data.get("service_session_id")
        if service_id:
            click.echo(
                f"Session: {event.session_id} (service: {service_id})",
                err=True,
            )


async def _execute(
    *,
    agent_name: str | None,
    binding_name: str | None,
    prompt: str,
    scope: str | None,
    base_dir: str | None,
    provider: str | None,
    session_id: str | None,
    service_session_id: str | None,
    json_output: bool,
) -> None:
    client = await _client_factory(scope=scope, base_dir=base_dir)
    handle = None
    try:
        if binding_name:
            binding = await client.resolve_runtime_binding(binding_name)
            if provider and binding.provider and provider != binding.provider:
                raise click.UsageError(
                    f"--provider {provider!r} conflicts with RuntimeBinding "
                    f"provider {binding.provider!r}"
                )
            agent_name = binding.agent
            provider = provider or binding.provider
        if not provider:
            provider = "github-copilot"
        definition = await client.resolve_agent(agent_name)
        handle = await _harness_getter(provider).start(
            definition,
            RunRequest(
                prompt=prompt,
                session_id=session_id,
                service_session_id=service_session_id,
            ),
        )
        state: dict[str, Any] = {}
        failure: str | None = None
        async for event in handle.events():
            _print_event(event, json_output=json_output, state=state)
            if event.type == "run.failed":
                failure = str(event.data.get("message") or "Provider execution failed")
        if failure:
            raise HarnessError(failure)
    except asyncio.CancelledError:
        if handle is not None:
            await handle.cancel()
        raise
    finally:
        await client.close()


@click.command("run")
@click.argument("agent_name", required=False)
@click.option("--binding", "binding_name", help="RuntimeBinding to resolve.")
@click.option("--prompt", required=True, help="Prompt sent to the resolved Agent.")
@click.option("--scope", help="DNA scope (auto-detected when omitted).")
@click.option(
    "--base-dir",
    type=click.Path(file_okay=False, path_type=str),
    envvar="DNA_BASE_DIR",
    help="DNA source directory.",
)
@click.option("--provider", help="Harness provider (default: github-copilot).")
@click.option("--session-id", help="Stable local session identifier.")
@click.option("--service-session-id", help="Provider session identifier to resume.")
@click.option("--json", "json_output", is_flag=True, help="Emit JSON Lines events.")
def run(
    agent_name: str | None,
    binding_name: str | None,
    prompt: str,
    scope: str | None,
    base_dir: str | None,
    provider: str | None,
    session_id: str | None,
    service_session_id: str | None,
    json_output: bool,
) -> None:
    """Run AGENT_NAME or a RuntimeBinding through a consumer harness."""
    if bool(agent_name) == bool(binding_name):
        raise click.UsageError("Provide exactly one AGENT_NAME or --binding")
    try:
        asyncio.run(
            _execute(
                agent_name=agent_name,
                binding_name=binding_name,
                prompt=prompt,
                scope=scope,
                base_dir=base_dir,
                provider=provider,
                session_id=session_id,
                service_session_id=service_session_id,
                json_output=json_output,
            )
        )
    except KeyboardInterrupt as error:
        raise click.exceptions.Exit(130) from error
    except HarnessError as error:
        raise click.ClickException(str(error)) from error
    except (LookupError, ValueError) as error:
        raise click.ClickException(str(error)) from error


__all__ = ["run"]
