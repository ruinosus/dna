# dna-sdk (TypeScript)

TypeScript SDK for **DNA — Domain Notation of Anything**: a microkernel +
extensions runtime for declarative agent notation. 1:1 behavioral twin of
the Python SDK (`packages/sdk-py`) — same ports, same composition rules,
same outputs, parity-enforced by tests. See the
[repository README](https://github.com/ruinosus/dna#readme) for the thesis and the Kind catalog.

## Install

```bash
npm install dna-sdk        # or: bun add dna-sdk
```

Pre-release / exact-pin alternative — consume straight from the repo:

```bash
cd packages/sdk-ts
bun install
```

ESM-only, Node >= 20 or Bun. The published package ships compiled JS +
type declarations (`dist/`); inside the repo, dev and tests run the
TypeScript sources directly under Bun (no build step needed). The
publication build is `bun run build` (tsc emit + runtime-asset copy).

## Minimal example

```typescript
import { quickInstance } from "dna-sdk";

// Scan a scope (directory of YAML/Markdown manifests under .dna/)
const mi = await quickInstance("hello-genome", "examples/hello-genome/.dna");

// Every document is identified by (apiVersion, kind, name)
for (const d of mi.documents) {
  console.log(d.apiVersion, d.kind, d.name);
}

// Compose agent + soul + skills + guardrails into one system prompt
console.log(await mi.buildPrompt({ agent: "greeter" }));
```

Runnable version: [`examples/hello-genome/run.ts`](https://github.com/ruinosus/dna/blob/main/examples/hello-genome/run.ts).

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
