# Feature Specification: Runtime Consumer Harness

**Feature Branch**: `feat/runtime-consumer-harness`

**Created**: 2026-08-11

**Status**: Implemented

**Target**: DNA SDK + CLI, Python reference implementation

## Current Architecture

DNA `v0.77.0` already has two complementary execution lanes:

1. `build_runtime()` composes a Copilot and dispatches to a `RuntimePort`
   (`langchain` or `maf`) that returns a servable `AGUIApp`.
2. `DnaClient.resolve_agent()` returns a runtime-neutral `ResolvedAgent`, and
   provider bindings such as `build_github_copilot_agent()` convert that data
   while leaving sessions, streaming, and lifecycle to the consumer.

`RuntimeBinding` declares a portable `(agent, protocol, provider, host.ref,
policy)` target. It never owns endpoints, credentials, transports, or sessions.

This feature adds the missing consumer lifecycle above those contracts. It does
not add another model loop, runtime framework, resource resolver, tool registry,
or session persistence model.

## Architectural Decisions

### AD-001: Harness, not framework

An `AgentHarness` starts one execution from a `ResolvedAgent`. The selected
provider continues to own model calls, tool calls, streaming details, and its
service session. DNA owns the portable request, lifecycle events, cancellation,
and typed failures.

### AD-002: Preserve existing runtime architecture

`RuntimePort`, `AGUIApp`, `build_runtime()`, `ThreadStorePort`, and framework
adapters remain unchanged. The harness is a consumer-side execution contract,
not a replacement for live AG-UI runtime construction.

### AD-003: Binding and framework are independent axes

`RuntimeBinding.runtime.provider` selects a consumer harness. It MUST NOT be
translated into `RuntimePort.target`; `serving.framework` continues to select a
servable framework adapter.

### AD-004: Minimal event normalization

The public event stream normalizes lifecycle, text deltas, completion,
cancellation, and errors. Provider payloads remain available as opaque data.
DNA does not recreate AG-UI or every provider-specific tool event.

### AD-005: Explicit cancellation

`RunHandle.cancel()` is idempotent and cancels the active execution task. A
cancelled run emits `run.cancelled` and terminates without a completion event.
Ctrl+C in the CLI invokes the same contract.

## Public Contracts

The SDK exposes:

```python
@dataclass(frozen=True)
class RunRequest:
    prompt: str
    session_id: str | None = None
    service_session_id: str | None = None

@dataclass(frozen=True)
class HarnessEvent:
    type: str
    run_id: str
    session_id: str
    timestamp: datetime
    text: str | None = None
    data: Mapping[str, Any] = field(default_factory=dict)

class RunHandle(Protocol):
    run_id: str
    session_id: str

    def events(self) -> AsyncIterator[HarnessEvent]: ...
    async def cancel(self) -> None: ...

class AgentHarness(Protocol):
    provider: str

    async def start(
        self,
        definition: ResolvedAgent,
        request: RunRequest,
    ) -> RunHandle: ...
```

The registry is keyed by provider name. Unknown providers fail explicitly and
list available providers.

## Event Contract

Events are immutable and carry UTC timestamps.

Required sequence for success:

```text
run.started
session.started | session.resumed
message.delta*
message.completed
run.completed
```

Required sequence for cancellation:

```text
run.started
session.started | session.resumed
...
run.cancelled
```

Required sequence for failure:

```text
run.started
session.started | session.resumed
...
run.failed
```

`message.delta` is optional when a provider only returns a final response.
`message.completed` contains the complete final text. Provider-native update
objects may be carried in `data["provider_event"]` when serializable; the CLI
must not depend on their shape.

## Error Model

Public errors:

```text
HarnessError
├── HarnessNotFound
├── HarnessConfigurationError
├── HarnessExecutionError
└── SessionResumeError
```

These are separate from kernel resolution errors. Invalid configuration never
silently falls back to another provider or session.

## GitHub Copilot Harness

The first implementation wraps the official Microsoft Agent Framework GitHub
Copilot agent produced by `build_github_copilot_agent()`.

- New session: `agent.create_session(session_id=...)`.
- Resume: `agent.get_session(service_session_id, session_id=...)`.
- Execution: `agent.run(prompt, stream=True, session=session)`.
- The provider updates `session.service_session_id`; completion events expose
  it for later resume.
- Provider permission and tool behavior remain in the existing integration.
- Importing DNA core or `dna.runtime.harness` must not require the provider
  extra. Registration/import is lazy.

## CLI Contract

Primary command:

```text
dna run <agent> --prompt <text> [--provider github-copilot]
```

Binding-driven command:

```text
dna run --binding <name> --prompt <text>
```

Options:

```text
--scope TEXT
--base-dir PATH
--provider TEXT
--binding TEXT
--session-id TEXT
--service-session-id TEXT
--json
```

Rules:

- Exactly one of `<agent>` or `--binding` is required.
- With `--binding`, provider and agent come from the resolved binding.
- A CLI `--provider` conflicting with the binding is rejected.
- Human output streams text deltas and prints session resume metadata.
- `--json` emits one JSON object per event (JSON Lines).
- Ctrl+C cancels the run and exits with code 130.
- Resolution/configuration failures exit non-zero with an actionable message.

## Security

- The harness receives only capabilities already present on `ResolvedAgent`.
- It does not add tools or bypass tool confirmation policy.
- Secrets remain provider/deployment inputs and never enter events or JSON.
- Provider event serialization is allowlisted; arbitrary object `repr` values
  are not emitted because they may contain credentials.
- `RuntimeBinding.host_ref` remains deployment-owned and is not resolved by
  this local CLI milestone.

## Files

### Add

```text
packages/sdk-py/dna/runtime/harness.py
packages/sdk-py/dna/runtime/harness_registry.py
packages/sdk-py/dna/runtime/adapters/github_copilot_harness.py
packages/sdk-py/tests/runtime/test_harness.py
packages/sdk-py/tests/runtime/test_github_copilot_harness.py
packages/cli/dna_cli/run_cmd.py
packages/cli/tests/test_run_cmd.py
specs/002-runtime-consumer-harness/spec.md
```

### Modify

```text
packages/sdk-py/dna/runtime/__init__.py
packages/cli/dna_cli/__init__.py
packages/cli/pyproject.toml
packages/cli/README.md
docs/reference/cli/index.md
```

## Test Matrix

Unit tests use fake agents and streams only. No external model/API is called.

- immutable event and request contracts;
- registry registration, lazy built-in loading, and unknown provider errors;
- new provider session and resumed provider session;
- text delta and final text adaptation;
- provider error mapping;
- cancellation before and during stream consumption;
- cancellation idempotence;
- event ordering and no completion after cancellation/failure;
- CLI direct-agent and binding resolution;
- CLI conflict and missing-target validation;
- human streaming output;
- JSON Lines output;
- Ctrl+C exit code 130;
- base install import isolation;
- Python 3.12 and 3.13.

A live smoke with authenticated GitHub Copilot is a delivery gate, not a unit
test.

## Acceptance Criteria

1. `dna run architect --prompt "Analyze this repository"` resolves a normal
   declarative Agent and executes it through the selected harness.
2. `dna run --binding local-copilot --prompt "..."` resolves the binding and
   executes its declared Agent/provider without inventing endpoint ownership.
3. A completed run prints and emits enough session metadata to resume it.
4. Passing that metadata resumes the provider session.
5. JSON mode emits valid JSON Lines with stable event types.
6. Ctrl+C and `RunHandle.cancel()` stop execution and produce cancellation,
   never successful completion.
7. The base SDK and CLI still import without the GitHub Copilot extra.
8. Existing runtime, kernel, definition, and integration tests remain green.
9. No code duplicates model loops, tool registries, DNA resolution, AG-UI, or
   `ThreadStorePort`.

## Non-Goals

- A new DNA-native model/tool loop.
- OpenAI or Anthropic provider abstractions.
- A new declarative `Runtime` Kind.
- AHP transport or VS Code session ownership inside DNA.
- Replacement of projection, AG-UI, `RuntimePort`, or provider SDK sessions.
- Cross-provider session migration.
- Universal normalization of provider tool-call events.
- TypeScript runtime parity in this milestone.

## Delivery

The feature is complete only when contracts, GitHub Copilot harness, CLI,
unit/integration tests, documentation, live smoke, and CI are all complete.
Public SDK changes require a release before dependent repositories are updated.
