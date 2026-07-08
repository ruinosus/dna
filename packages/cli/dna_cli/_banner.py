"""ASCII banner with cobre/orange gradient, shown on ``dna --help``.

Inspired by ``claude-code-templates`` ``cct`` banner. Renders only when
stdout is a TTY (skip in pipes / CI). Set ``DNA_NO_BANNER=1`` to disable.
"""
from __future__ import annotations

import os
import sys

import click
from rich.console import Console
from rich.text import Text

# Cobre → laranja → pêssego gradient (same palette aitmpl.com uses).
_GRADIENT = ["#EA580C", "#F97316", "#FB923C", "#FDBA74", "#FED7AA", "#FFE7CC"]

# Compact 5-line block. Stencil-ish (block characters) for a "Claude Code SDK"
# feel without being noisy. Width ~50 cols → fits any terminal.
_LOGO = r"""
  █████   █████  ██████
 ██   ██ ██   ██ ██   ██
 ███████ ███████ ██████
 ██   ██ ██   ██ ██
 ██   ██ ██   ██ ██     declarative agent platform
"""


def _gradient_text(line: str) -> Text:
    """Apply per-character color gradient across visible glyphs."""
    t = Text()
    n = len(_GRADIENT)
    for i, ch in enumerate(line):
        if ch in (" ", "\n", "\t"):
            t.append(ch)
        else:
            t.append(ch, style=_GRADIENT[i % n])
    return t


def render_banner() -> str:
    """Return colorized banner string, or empty if banner suppressed."""
    if os.environ.get("DNA_NO_BANNER") == "1":
        return ""
    if not sys.stdout.isatty():
        return ""
    lines = _LOGO.strip("\n").splitlines()
    console = Console(file=sys.stdout, force_terminal=True)
    # Build the colored block via Rich's capture so we can return it as a string
    # (Click's HelpFormatter writes strings, not Rich objects).
    with console.capture() as cap:
        for line in lines:
            console.print(_gradient_text(line))
    return cap.get()


def print_banner() -> None:
    """Print banner to stdout when appropriate."""
    out = render_banner()
    if out:
        click.echo(out)
