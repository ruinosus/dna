# exp-value-comparison — DNA vs a YAML folder, measured honestly

The **same** Acme Cloud support agent built two ways, to test the founder's
critique: *does DNA pay for itself vs a folder of YAML + Pydantic + Git + a
framework?* Both compose the **byte-identical** system prompt.

- `solution-a-yaml/` — plain YAML + Pydantic (`models.py`) + a hand-rolled
  composer (`compose.py`) + a hand-rolled emitter (`emit_langgraph.py`).
- `solution-b-dna/` — the same agent as DNA Kinds (Genome + Agent + Soul +
  Guardrail + Skill), composed by `build_prompt`, emitted by `dna emit`, and
  overlaid per-tenant by the kernel (`.dna/tenants/acme-eu/...`).

Full dimension-by-dimension report with numbers and a blunt verdict:
[`docs/analysis/exp-value-comparison.md`](../../docs/analysis/exp-value-comparison.md).

TL;DR: DNA earns its keep on **per-tenant overlay** and **multi-runtime emit**;
for a single-app / single-runtime / single-tenant case a YAML folder is simply
better (terser config, smaller onboarding, deeper validation, easier debugging).
