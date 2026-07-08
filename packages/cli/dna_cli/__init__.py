"""``dna`` — user-facing CLI for the DNA kernel.

Boots a local Kernel against ``DNA_SOURCE_URL`` / ``DNA_BASE_DIR``
(filesystem source) and runs one command per invocation. No service
required — the kernel IS the backend.

Output formatting:
  - ``--json`` for machine-readable (default for CRUD writes).
  - rich tables for ``list`` / ``show`` (default).
"""
from __future__ import annotations

import os


import click

from dna_cli import (
    doc_cmd,
    docs_cmd,
    kind_cmd,
    scope_cmd,
    sdlc_cmd,
    source_cmd,
)


class _BannerGroup(click.Group):
    """Click Group that prints the gradient banner before ``--help`` output."""

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        from dna_cli._banner import render_banner
        banner = render_banner()
        if banner:
            formatter.write(banner)
            formatter.write_paragraph()
        super().format_help(ctx, formatter)


@click.group(
    cls=_BannerGroup,
    help=(
        "DNA — declarative lifecycle + document CLI.\n\n"
        "Boots a local kernel via DNA_SOURCE_URL / DNA_BASE_DIR "
        "(filesystem source). Run `dna kind list` to start exploring, "
        "`dna sdlc --help` for the lifecycle verbs."
    ),
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(version="0.1.0", prog_name="dna")
def main() -> None:
    """Top-level group — subcommands attached below."""


main.add_command(kind_cmd.kind)
main.add_command(doc_cmd.doc)
main.add_command(scope_cmd.scope)
main.add_command(docs_cmd.docs_)
main.add_command(sdlc_cmd.sdlc)
# Importing testkit_cmd registers `sdlc test-guide` + `sdlc test-run` on the
# sdlc group via its decorators (TESTS as first-class SDLC).
from dna_cli import testkit_cmd as _testkit_cmd  # noqa: E402,F401
# Importing hooks_cmd registers `sdlc hooks install|uninstall|status` — the
# git↔SDLC symbiosis wiring (Work-Item trailers via prepare-commit-msg).
from dna_cli import hooks_cmd as _hooks_cmd  # noqa: E402,F401
main.add_command(source_cmd.source)


if __name__ == "__main__":
    main()
