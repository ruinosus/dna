# How to evaluate agents

Evaluation in DNA is authored as data — four record Kinds ([EvalCase,
EvalSuite, EvalRun, EvalBaseline](../concepts/builtin-kinds.md#evaluation))
— and executed by a **local, synchronous, offline runner**. No worker, no
service, no LLM: the default evaluable system is the kernel itself.
Composing a prompt is a deterministic function of your declared documents,
so *"does my agent compose the prompt I expect?"* is a real evaluation of
declarative config — the exact thing DNA externalizes. A prompt refactor,
a skill rename, an overlay change: the suite catches the regression in CI,
in seconds.

This guide uses the [hello-genome
example](https://github.com/ruinosus/dna/tree/main/examples/hello-genome),
which ships a working suite.

## 1. Write cases and a suite

A case names a target and deterministic checks. The built-in target type
is `prompt` — the composed system prompt of an agent:

```yaml
# .dna/hello-genome/eval-cases/greeter-identity.yaml
apiVersion: github.com/ruinosus/dna/eval/v1
kind: EvalCase
metadata:
  name: greeter-identity
spec:
  description: The greeter composes its declared identity into the prompt
  target: { type: prompt, agent: greeter }
  checks:
  - { type: contains, value: Helio }
  - { type: regex, value: 'friendly assistant' }
  - { type: min_length, value: 50 }
```

Check types: `contains`, `not_contains`, `regex`, `not_regex`, `equals`,
`min_length`, `max_length` (string checks accept `case_sensitive: false`).
All checks must pass for the case to pass.

The suite groups cases and carries the default target (cases without
their own `target` inherit it; an empty `cases` list runs every EvalCase
in the scope):

```yaml
# .dna/hello-genome/eval-suites/greeter-suite.yaml
apiVersion: github.com/ruinosus/dna/eval/v1
kind: EvalSuite
metadata:
  name: greeter-suite
spec:
  description: Does the greeter compose the prompt we expect?
  cases: [greeter-identity, greeter-tone]
  target: { type: prompt, agent: greeter }
```

## 2. Run it — offline

```console
$ dna eval run greeter-suite --scope hello-genome
suite: greeter-suite (scope hello-genome)
  ✓ greeter-identity  [passed]
  ✓ greeter-tone  [passed]
2 passed · 0 failed · 0 errored · 0 skipped (total 2)
```

The exit code is 1 when any case fails or errors — `dna eval run` in a CI
step is already a prompt-regression gate. `--save` persists the result as
an EvalRun document under `<scope>/eval-runs/`; `dna eval list` and
`dna eval show <run>` read the ledger back.

## 3. Pin a baseline, gate on regressions

A known-good run becomes the reference:

```console
$ dna eval run greeter-suite --save --json | jq -r .run.metadata.name
run-greeter-suite-20260710-120000
$ dna eval pin run-greeter-suite-20260710-120000
pinned: EvalBaseline/baseline-greeter-suite → EvalRun/run-greeter-suite-20260710-120000
```

Future runs compare against it:

```console
$ dna eval run greeter-suite --baseline baseline-greeter-suite
...
vs baseline baseline-greeter-suite (run-greeter-suite-20260710-120000): 0 regression(s) · 0 improvement(s) · 2 unchanged
```

With `--baseline`, the exit code reflects the **diff**, not the run: only
a regression (a case the baseline passed, now failing) exits 1. A
pre-existing failure doesn't re-fail your CI; a fresh improvement is
reported, never punished. Deliberately-skipped cases (`skip: true`) count
as absent, not as regressions.

## 4. The LLM extension point

The SDK never calls a model — live targets are the **host's**, the same
declare-here/execute-in-the-host split as
[Automation](../concepts/builtin-kinds.md#the-execution-extension-point)
runners. A target is anything with a `run(target, case, *, kernel, scope)
-> str` method (`EvalTargetPort`); register it under a type name and
cases declare `target: {type: llm, ...}`:

```python
# host_eval.py — a minimal LLM target (~15 lines)
from dna.extensions.eval import run_suite

class LlmTarget:
    """Sends the case input to the host's model, returns the reply."""

    def run(self, target, case, *, kernel, scope):
        prompt = kernel.instance(scope).build_prompt(agent=target.get("agent"))
        return my_llm(                       # your client (OpenAI, local, …)
            system=prompt,
            user=case.get("input", ""),
            model=target.get("model", "gpt-5-mini"),
        )

raw = run_suite(kernel, "my-scope", "my-suite", targets={"llm": LlmTarget()})
```

The runner dispatches per case by `target.type`, applies the same checks
to whatever text comes back, and produces the same EvalRun shape — so
deterministic prompt cases and host-run LLM cases live in one suite, one
ledger, one baseline. A case whose target type has no registered port
becomes `status: error`, never a silent pass.

## What travels from upstream, honestly

These Kinds are a port of a production eval system whose runner was a
Temporal worker driving live agents through LLM judges. The **authoring
vocabulary** travels (case/suite/run/baseline, target + checks, baseline
comparison semantics); the runtime does not — trajectory matching, HITL
policies, judge engines and red-team orchestration are host concerns, out
of scope for a notation library. If you need them, they are exactly what
the `EvalTargetPort` extension point is for.
