# hello-genome

The minimal DNA scope: one `Genome` (the scope root), one `Agent`, and one
**real marketplace Skill** (`verification-before-completion`, from the
Superpowers collection — copied verbatim, consumed byte-faithful under its
owner's namespace `agentskills.io/v1`).

```
.dna/
├── _lib/                      # shared-library scope every scope inherits
│                              # from (empty here — kept so the example is
│                              # self-contained)
└── hello-genome/
    ├── Genome.yaml            # scope root: identity + default_agent
    ├── agents/
    │   └── greeter.yaml       # kind: Agent — instruction + skill wiring
    └── skills/
        └── verification-before-completion/
            └── SKILL.md       # kind: Skill — real market bundle, unmodified
```

## Run it

Python:

```bash
cd packages/sdk-py && uv sync
uv run python ../../examples/hello-genome/run.py
```

It does three things:

1. **Scan** the scope: every document comes back identified by
   `(apiVersion, kind, name)`.
2. **Typed access**: the Skill's frontmatter is parsed into a typed model.
3. **Compose**: `build_prompt(agent="greeter")` renders the agent's
   instruction through the template cascade into a single system prompt.

Change `agents/greeter.yaml` or the skill wiring and re-run — behavior
changes with **no rebuild and no redeploy**. That is the DNA thesis in
one file edit.

The example is exercised by the test suite
(`packages/sdk-py/tests/test_hello_genome_example.py`), so it can never
silently rot.
