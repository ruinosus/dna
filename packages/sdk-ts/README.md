# @dna/sdk (TypeScript)

TypeScript SDK for **DNA — Domain Notation of Anything**: a microkernel +
extensions runtime for declarative agent notation. 1:1 behavioral twin of
the Python SDK (`packages/sdk-py`) — same ports, same composition rules,
same outputs, parity-enforced by tests. See the
[repository README](../../README.md) for the thesis and the Kind catalog.

## Install

Not yet on npm — use it from the repo:

```bash
cd packages/sdk-ts
bun install
```

ESM-only. Bun is the supported runtime and test runner; the package ships
TypeScript sources directly (no build step).

## Minimal example

```typescript
import { quickInstance } from "@dna/sdk";

// Scan a scope (directory of YAML/Markdown manifests under .dna/)
const mi = await quickInstance("hello-genome", "examples/hello-genome/.dna");

// Every document is identified by (apiVersion, kind, name)
for (const d of mi.documents) {
  console.log(d.apiVersion, d.kind, d.name);
}

// Compose agent + soul + skills + guardrails into one system prompt
console.log(await mi.buildPrompt({ agent: "greeter" }));
```

Runnable version: [`examples/hello-genome/run.ts`](../../examples/hello-genome/run.ts).

Prefer `createKernelWithBuiltins()` (from the same entrypoint) when you
want to wire sources, caches and resolvers yourself.

## Tests

```bash
bun test              # full suite
bun run typecheck     # tsc --noEmit
```

The suite includes the market-fidelity conformance tests
(`tests/market-conformance.test.ts`) and the Py↔TS parity fixtures shared
with the Python twin.
