"""examples/hello-genome must RUN — the README quick start is this example.

Executes ``examples/hello-genome/run.py`` as a subprocess (exactly what a
user copy-pastes) and asserts the three demonstrated behaviors: scope scan,
market-Skill load under the owner's namespace, and prompt composition.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "hello-genome"


def test_hello_genome_run_py() -> None:
    res = subprocess.run(
        [sys.executable, str(EXAMPLE / "run.py")],
        capture_output=True,
        text=True,
        cwd=EXAMPLE,
        timeout=120,
    )
    assert res.returncode == 0, f"run.py failed:\n{res.stderr}"
    out = res.stdout
    # 1. scope scan — every document identified by (apiVersion, kind, name)
    assert "scope: hello-genome" in out
    assert "github.com/ruinosus/dna/v1" in out
    assert "Genome" in out and "Agent" in out
    # 2. the REAL marketplace skill loads under its owner's namespace
    assert "agentskills.io/v1" in out
    assert "verification-before-completion" in out
    # 3. prompt composition
    assert "You are Helio, a friendly assistant." in out
    # the example must stay warning-free (no deprecated API usage)
    assert "DeprecationWarning" not in res.stderr
