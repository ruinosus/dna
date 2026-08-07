"""Abort the suite when ``dna`` / ``dna_cli`` come from ANOTHER checkout.

⚠️ Why this exists (i-138, measured 07/08/2026).

The venv is shared. Every agent that runs ``uv pip install -e .`` inside its own
git worktree **repoints the shared venv's editable install** at that worktree.
The last one to install wins, and nothing says so. Measured in the shared
checkout, with four agents working in parallel::

    dna_cli  -> /Users/…/dna-wt-i123/packages/cli/dna_cli
    dna      -> /private/tmp/wt-margem/packages/sdk-py/dna
    cwd      -> /Users/…/projects/dna

Three different trees, none of them the one under review.

**The suite still passes.** That is the whole problem: a green run against code
that is not the code being changed is indistinguishable from an honest one, and
this house has a standing rule that a test passing for the wrong reason is worse
than a test failing. Here the wrong reason is invisible by construction.

It first surfaced as a docs bug — regenerating reference pages emitted a CLI
page for a command that does not exist in this checkout — which is the lucky
version. The unlucky version is a review that says "suite green" about a tree
nobody read.

⚠️ **The invariant is the CHECKOUT, not pytest's rootdir.** CI's ``cli`` job runs
``uv pip install -e ../sdk-py -e ".[dev]"`` with rootdir at ``packages/cli``, so
``dna`` legitimately resolves *outside* rootdir and inside the same repo. A guard
written against rootdir would fail that job — correct-looking and wrong, which is
the failure mode it exists to prevent.

Escape hatch, for the one legitimate case (testing a published wheel rather than
the working tree)::

    DNA_ALLOW_FOREIGN_TREE=1 uv run pytest …

It is an env var and not a config flag on purpose: a per-run decision someone
takes knowingly, not a setting that quietly outlives the reason for it.
"""

from __future__ import annotations

import os
import pathlib


def _repo_root(start: pathlib.Path) -> pathlib.Path | None:
    """Walk up to the directory holding ``.git``.

    ``.git`` is a *file* inside a worktree and a *directory* in the main
    checkout — ``.exists()`` covers both, which is the point: worktrees are
    exactly the situation this guard is about.
    """
    for d in (start, *start.parents):
        if (d / ".git").exists():
            return d
    return None


def assert_same_checkout() -> None:
    if os.environ.get("DNA_ALLOW_FOREIGN_TREE"):
        return

    raiz = _repo_root(pathlib.Path(__file__).resolve())
    if raiz is None:
        # Not in a git tree (an installed sdist running its own tests, say).
        # Nothing to compare against — stay quiet rather than guess.
        return

    forasteiros: list[str] = []
    for nome in ("dna", "dna_cli"):
        try:
            mod = __import__(nome)
        except ImportError:
            continue  # dna_cli is absent from the sdk-py suite; that is fine.
        arquivo = getattr(mod, "__file__", None)
        if not arquivo:
            continue
        onde = pathlib.Path(arquivo).resolve()
        if raiz not in onde.parents:
            forasteiros.append(f"  {nome}: {onde.parent}")

    if forasteiros:
        raise RuntimeError(
            "\n\n"
            "════ A SUÍTE IA TESTAR OUTRA ÁRVORE ════════════════════════════\n"
            f"checkout sob teste : {raiz}\n"
            "resolvido de fora  :\n" + "\n".join(forasteiros) + "\n\n"
            "O venv é compartilhado, e quem rodou `uv pip install -e .` por\n"
            "último reapontou o editable. Um verde daqui não diria nada sobre\n"
            "o código em revisão (i-138).\n\n"
            "Conserte com:\n"
            f'  PYTHONPATH="{raiz}/packages/sdk-py:{raiz}/packages/cli" uv run --no-project pytest …\n'
            "ou reinstale o editable a partir DESTE checkout.\n"
            "Testando um wheel publicado de propósito? DNA_ALLOW_FOREIGN_TREE=1\n"
            "════════════════════════════════════════════════════════════════\n"
        )
