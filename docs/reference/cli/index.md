# CLI reference

The `dna` binary is a thin wrapper over the DNA kernel — every command
boots a local kernel against `DNA_SOURCE_URL` / `DNA_BASE_DIR`, runs one
command, and exits. No service is required.

These pages are **generated from the Click command definitions** by
`scripts/gen_cli_docs.py`, so `--help` and the docs can never drift.

| Group | What it does |
| --- | --- |
| [`dna sdlc`](sdlc.md) | Declarative lifecycle tracking (Roadmap/Epic/Feature/Story/Issue). |
| [`dna research`](research.md) | Manage Research synthesis documents (curated syntheses of References). |
| [`dna doc`](doc.md) | List, show, create, edit, delete documents. |
| [`dna docs`](docs.md) | Browse the in-product Doc corpus. |
| [`dna scope`](scope.md) | List + inspect scopes (manifest modules). |
| [`dna kind`](kind.md) | List + inspect registered Kinds. |
| [`dna source`](source.md) | Source-level operations: declarative replicas, introspection. |
| [`dna eval`](eval.md) | Run EvalSuites locally (offline, deterministic) and compare runs against a pinned EvalBaseline. |
| [`dna init`](init.md) | Make a project agent-ready: board + skill + AGENTS.md + git hooks. |
| [`dna install`](install.md) | Install bundles/Kinds from a repository into the local source. |
| [`dna memory`](memory.md) | Declarative memory over existing Kinds (remember/recall/forget/consolidate). |
| [`dna new`](new.md) | Scaffold a valid Kind skeleton into a scope (agent \| soul \| guardrail \| tool). |
| [`dna recall`](recall.md) | Hybrid semantic search (dense + lexical + RRF) over the scope's records. |
| [`dna search`](search.md) | Alias of ``dna recall`` (neutral naming). |
