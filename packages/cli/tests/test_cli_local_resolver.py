"""kz-001 — the CLI boot path must wire the LocalResolver, like ``Kernel.quick``.

Regression for the platform-consistency bug found dogfooding DNA in the
``foundry`` consumer: an eval gate declared a ``local:<lib-scope>`` dependency.
It resolved through the SDK (``Kernel.quick`` registers ``LocalResolver``) but
NOT through the CLI (``dna eval run``), because the CLI boot
(``_ctx._build_holder_async``) called ``Kernel.auto()`` with NO source and then
wired the source SEPARATELY — so ``build_auto_kernel``'s resolver-wiring branch
(guarded by ``source is not None``) never ran and the kernel had ZERO resolvers.
Same composition, two results.

These tests mount a consumer scope with a RELATIVE ``local:<lib>`` dep (the case
that actually exercises ``LocalResolver.base_dir``) and prove:

  1. the CLI boot path resolves the dep (RED before the fix, green after);
  2. ``Kernel.quick`` resolves the SAME scenario (no regression);
  3. both paths agree on the resolved Skill set.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from dna.kernel import Kernel

from dna_cli._ctx import _build_holder_async


# ---------------------------------------------------------------------------
# Fixture — a base_dir with a lib bundle + a consumer scope depending on it
# via a RELATIVE ``local:`` path (resolved against LocalResolver.base_dir).
# ---------------------------------------------------------------------------


def _make_base_dir(tmp_path: Path) -> Path:
    """Return a ``.dna`` base dir holding:

        <base>/my-lib/skills/greet/SKILL.md      (the local dep target)
        <base>/consumer/manifest.yaml            (Genome with local:my-lib dep)
        <base>/consumer/agents/main-agent.yaml
    """
    base = tmp_path / "project" / ".dna"

    # The lib bundle — resolved via the RELATIVE path ``local:my-lib``.
    skill_dir = base / "my-lib" / "skills" / "greet"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Greet Skill\nSay hello.")

    # The consumer scope.
    consumer = base / "consumer"
    (consumer / "agents").mkdir(parents=True)
    manifest = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": "consumer", "description": "consumes my-lib"},
        "spec": {
            "default_agent": "main-agent",
            "dependencies": [
                {
                    # RELATIVE local path — meaningless without a wired
                    # LocalResolver(base_dir=<base>). This is the crux of kz-001.
                    "source": "local:my-lib",
                    "items": [{"kind": "Skill", "names": ["greet"]}],
                },
            ],
        },
    }
    (consumer / "manifest.yaml").write_text(yaml.dump(manifest))
    agent = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "main-agent"},
        "spec": {"instruction": "You are the main agent.", "skills": ["greet"]},
    }
    (consumer / "agents" / "main-agent.yaml").write_text(yaml.dump(agent))

    return base


def _skill_names_via_cli(base: Path, scope: str, monkeypatch) -> tuple[list[str], Kernel]:
    """Boot the kernel via the REAL CLI path and resolve ``scope`` non-lazily.

    Points ``DNA_BASE_DIR`` at the project dir (the ``.dna`` parent) exactly like
    a user running ``dna eval run`` from a project root.
    """
    monkeypatch.setenv("DNA_BASE_DIR", str(base.parent))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)

    async def _boot() -> tuple[list[str], Kernel]:
        holder = await _build_holder_async(scope)
        mi = await holder.kernel.instance_async(scope, lazy=False)
        names = sorted(d.name for d in mi.documents if d.kind == "Skill")
        return names, holder.kernel

    return asyncio.run(_boot())


def _skill_names_via_quick(base: Path, scope: str) -> list[str]:
    mi = Kernel.quick(scope, base_dir=str(base))
    return sorted(d.name for d in mi.documents if d.kind == "Skill")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_cli_boot_wires_local_resolver(tmp_path, monkeypatch):
    """The CLI-built kernel must carry a ``local`` resolver — like ``quick``."""
    base = _make_base_dir(tmp_path)
    _names, kernel = _skill_names_via_cli(base, "consumer", monkeypatch)
    assert "local" in kernel._resolvers, (
        "CLI boot left the kernel WITHOUT a LocalResolver — a local:<scope> dep "
        "cannot resolve through the CLI (kz-001)."
    )


def test_cli_boot_resolves_local_dep(tmp_path, monkeypatch):
    """End-to-end: the consumer's ``local:my-lib`` Skill resolves via the CLI."""
    base = _make_base_dir(tmp_path)
    names, _kernel = _skill_names_via_cli(base, "consumer", monkeypatch)
    assert "greet" in names, (
        "local:my-lib -> greet did not resolve through the CLI boot path (kz-001)."
    )


def test_quick_resolves_local_dep(tmp_path):
    """Control: ``Kernel.quick`` resolves the SAME scenario (must not regress)."""
    base = _make_base_dir(tmp_path)
    assert "greet" in _skill_names_via_quick(base, "consumer")


def test_cli_and_quick_agree(tmp_path, monkeypatch):
    """Same composition, same result across the two boot paths."""
    base = _make_base_dir(tmp_path)
    cli_names, _ = _skill_names_via_cli(base, "consumer", monkeypatch)
    quick_names = _skill_names_via_quick(base, "consumer")
    assert cli_names == quick_names
