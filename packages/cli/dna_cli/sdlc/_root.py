"""Root of the ``dna sdlc`` group.

Lives in the decomposed package so group modules (``reference``, ``journey``,
...) can attach to it without importing ``sdlc_cmd`` — which imports them for
registration, and would otherwise be a cycle. ``sdlc_cmd`` re-exports ``sdlc``
so ``from dna_cli.sdlc_cmd import sdlc`` (hooks_cmd, pr_cmd, testkit_cmd, the
tests) keeps resolving.

The group body is deliberately empty: session resolution is LAZY, per command
(``dna_cli._ctx.open_session``) — the root cannot resolve a session because
``--scope`` is parsed at the leaf, and an eager root callback would boot a
kernel just to print ``dna sdlc <group> --help``.
"""
from __future__ import annotations

import click


@click.group(name="sdlc", help="Declarative lifecycle tracking (Roadmap/Epic/Feature/Story/Issue).")
def sdlc() -> None:
    """Group root — Phase 16 SdlcExtension surface."""
