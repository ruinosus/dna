"""Registry for consumer harness providers."""

from __future__ import annotations

from collections.abc import Callable

from dna.runtime.harness import AgentHarnessPort, HarnessNotFound

HarnessFactory = Callable[[], AgentHarnessPort]
_REGISTRY: dict[str, HarnessFactory] = {}
_BUILTINS_LOADED = False


def register_harness(
    provider: str,
    factory: HarnessFactory,
    *,
    replace: bool = False,
) -> None:
    name = provider.strip().lower()
    if not name:
        raise ValueError("Harness provider must not be empty")
    if name in _REGISTRY and not replace:
        raise ValueError(f"Harness already registered for provider {name!r}")
    _REGISTRY[name] = factory


def _load_builtins() -> None:
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return
    from dna.runtime.adapters.github_copilot_harness import GitHubCopilotHarness

    register_harness(
        GitHubCopilotHarness.provider,
        GitHubCopilotHarness,
        replace=True,
    )
    _BUILTINS_LOADED = True


def available_harnesses() -> tuple[str, ...]:
    _load_builtins()
    return tuple(sorted(_REGISTRY))


def get_harness(provider: str) -> AgentHarnessPort:
    _load_builtins()
    name = provider.strip().lower()
    try:
        return _REGISTRY[name]()
    except KeyError as error:
        available = ", ".join(sorted(_REGISTRY)) or "none"
        raise HarnessNotFound(
            f"Unknown harness provider {provider!r}; available: {available}"
        ) from error


__all__ = ["available_harnesses", "get_harness", "register_harness"]
