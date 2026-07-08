"""hello-genome — the minimal DNA example (Python).

Loads the scope in ./.dna, lists every document by (apiVersion, kind, name),
shows typed access to a real marketplace Skill, and composes the agent's
system prompt.

Run it with the SDK installed (from the repo root):

    cd packages/sdk-py && uv sync
    uv run python ../../examples/hello-genome/run.py
"""
from pathlib import Path

from dna import Kernel

base = Path(__file__).resolve().parent / ".dna"
mi = Kernel.quick("hello-genome", base_dir=str(base))

print(f"scope: {mi.scope}")
for d in mi.documents:
    print(f"  {d.api_version:32s} {d.kind:8s} {d.name}")

# Typed access — the Skill is a REAL marketplace bundle, consumed
# byte-faithful under its owner's namespace (agentskills.io/v1).
skill = next(d for d in mi.documents if d.kind == "Skill")
print(f"\ntyped skill: {skill.typed.metadata.name}")
print(f"  {skill.typed.metadata.description[:72]}...")

print("\n--- composed prompt (agent: greeter) ---")
print(mi.build_prompt(agent="greeter"))
