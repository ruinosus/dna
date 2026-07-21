#!/usr/bin/env python3
"""Generate the CLI reference (docs/reference/cli/) from the `dna` Click tree.

Source-of-truth generator, uv/Ruff style: the reference is introspected from
the live Click command objects (``dna_cli.main``), so ``dna <cmd> --help`` and
the published docs can never disagree. One markdown page per top-level command
group; nested subgroups are rendered as sub-sections on the same page.

Determinism: commands, subcommands and options are emitted in a stable,
sorted order and the output carries no timestamps — running this twice on the
same source yields byte-identical files (guarded by ``--check``).

Usage:
    python3 scripts/gen_cli_docs.py            # (re)generate the pages
    python3 scripts/gen_cli_docs.py --check    # fail if regeneration would change anything

This script imports ``dna_cli``; the ``dna`` SDK + CLI must be installed
(``pip install -e packages/sdk-py -e packages/cli``). The docs CI job installs
them before running this generator.
"""
from __future__ import annotations

import argparse
import inspect
import io
import re
import sys
from pathlib import Path

import click

# Wrap bare `scheme://…` example URLs (file://, fs://, postgres://, …) that
# appear in help text as inline code. Rendered nicer AND keeps the offline
# link-checker (lychee) from resolving an *example* connection string as a
# real local file link (would 404 on docs-links).
_URL_RE = re.compile(r"(?<![`\w])([a-z][a-z0-9+.\-]*://[^\s`|)]+)")


def _neutralize_urls(text: str) -> str:
    return _URL_RE.sub(r"`\1`", text)

# Groups to surface as top-level pages (the task's blessed CLI surface). Any
# additional registered top-level command is still emitted, so the reference
# cannot silently omit a newly-added group.
_ORDER = ["sdlc", "research", "doc", "docs", "scope", "kind", "source"]

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OUT_DIR = _REPO_ROOT / "docs" / "reference" / "cli"


def _md_escape(text: str) -> str:
    return _neutralize_urls(text.replace("|", "\\|").replace("\n", " ").strip())


def _help_text(cmd: click.Command) -> str:
    """``cmd.help``, normalized to be Python-version-independent.

    Python 3.13 dedents docstrings at COMPILE time (``__doc__`` arrives
    already stripped of common leading whitespace); 3.12 and earlier keep the
    raw indentation. Without this, the generated pages differ by hundreds of
    reflow-only lines depending on which interpreter ran the generator — the
    exact non-reproducibility that made this guard get waved through.
    ``inspect.cleandoc`` is idempotent, so on 3.13 it is a no-op."""
    return inspect.cleandoc(cmd.help) if cmd.help else ""


def _short_help(cmd: click.Command) -> str:
    help_text = (_help_text(cmd) or cmd.short_help or "").strip()
    if not help_text:
        return ""
    # First paragraph only for the index/summary lines.
    return help_text.split("\n\n")[0].replace("\n", " ").strip()


def _usage(cmd: click.Command, path: list[str]) -> str:
    ctx = click.Context(cmd, info_name=" ".join(path))
    pieces = cmd.collect_usage_pieces(ctx)
    return " ".join(["dna", *path, *pieces])


def _options_table(cmd: click.Command, out: io.StringIO) -> None:
    ctx = click.Context(cmd)
    args: list[click.Argument] = []
    opts: list[click.Option] = []
    for param in cmd.get_params(ctx):
        if isinstance(param, click.Argument):
            args.append(param)
        elif isinstance(param, click.Option):
            opts.append(param)

    if args:
        # click.Argument carries no help text; show name, cardinality, required.
        out.write("**Arguments**\n\n")
        out.write("| Argument | Required |\n")
        out.write("| --- | --- |\n")
        for a in args:
            metavar = a.metavar or a.name.upper()
            if a.nargs == -1:
                metavar += "..."
            req = "yes" if a.required else "no"
            out.write(f"| `{metavar}` | {req} |\n")
        out.write("\n")

    if opts:
        out.write("**Options**\n\n")
        out.write("| Option | Description |\n")
        out.write("| --- | --- |\n")
        for o in sorted(opts, key=lambda p: p.opts[0]):
            decls = ", ".join(f"`{d}`" for d in o.opts + o.secondary_opts)
            desc = _md_escape(o.help or "")
            default = o.default
            # Skip sentinel / object-repr defaults (e.g. Sentinel.UNSET,
            # <object at 0x…>) — they're noise, not a user-facing value.
            show_default = (
                default is not None
                and default is not False
                and not o.is_flag
                and "UNSET" not in repr(default)
                and not repr(default).startswith("<")
            )
            if show_default:
                desc = f"{desc} _(default: `{default}`)_".strip()
            out.write(f"| {decls} | {desc} |\n")
        out.write("\n")


def _render_command(cmd: click.Command, path: list[str], level: int, out: io.StringIO) -> None:
    heading = "#" * min(level, 6)
    out.write(f"{heading} `{' '.join(['dna', *path])}`\n\n")

    help_text = _help_text(cmd).strip()
    if help_text:
        out.write(_neutralize_urls(help_text) + "\n\n")

    out.write("```text\n")
    out.write(_usage(cmd, path) + "\n")
    out.write("```\n\n")

    _options_table(cmd, out)

    if isinstance(cmd, click.Group):
        for name, sub in sorted(cmd.commands.items()):
            _render_command(sub, [*path, name], level + 1, out)


def _render_group_page(name: str, cmd: click.Command) -> str:
    out = io.StringIO()
    title = _short_help(cmd) or f"`dna {name}`"
    out.write(f"# `dna {name}`\n\n")
    if cmd.help:
        out.write(_neutralize_urls(_help_text(cmd).strip()) + "\n\n")
    out.write(
        "!!! info \"Generated from the command definitions\"\n\n"
        "    This page is introspected from the `dna` Click command tree by\n"
        "    `scripts/gen_cli_docs.py`, so it stays in lockstep with\n"
        f"    `dna {name} --help`.\n\n"
    )
    if isinstance(cmd, click.Group):
        for sub_name, sub in sorted(cmd.commands.items()):
            _render_command(sub, [name, sub_name], 2, out)
    else:
        _render_command(cmd, [name], 2, out)
    return out.getvalue()


def _build() -> dict[str, str]:
    from dna_cli import main

    pages: dict[str, str] = {}
    top = dict(main.commands)

    # index page
    idx = io.StringIO()
    idx.write("# CLI reference\n\n")
    idx.write(
        "The `dna` binary is a thin wrapper over the DNA kernel — every command\n"
        "boots a local kernel against `DNA_SOURCE_URL` / `DNA_BASE_DIR`, runs one\n"
        "command, and exits. No service is required.\n\n"
        "These pages are **generated from the Click command definitions** by\n"
        "`scripts/gen_cli_docs.py`, so `--help` and the docs can never drift.\n\n"
    )
    idx.write("| Group | What it does |\n| --- | --- |\n")
    ordered = [n for n in _ORDER if n in top] + [n for n in sorted(top) if n not in _ORDER]
    for name in ordered:
        idx.write(f"| [`dna {name}`]({name}.md) | {_md_escape(_short_help(top[name]))} |\n")
    pages["index.md"] = idx.getvalue()

    for name in ordered:
        pages[f"{name}.md"] = _render_group_page(name, top[name])

    return pages


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="fail if regeneration would change files")
    args = ap.parse_args()

    pages = _build()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    changed = []
    for rel, content in pages.items():
        path = _OUT_DIR / rel
        old = path.read_text() if path.exists() else None
        if old != content:
            changed.append(rel)
            if not args.check:
                path.write_text(content)

    if args.check and changed:
        print(f"CLI docs are stale — run scripts/gen_cli_docs.py. Drifted: {', '.join(changed)}", file=sys.stderr)
        return 1
    if not args.check:
        print(f"Wrote {len(pages)} CLI reference pages to {_OUT_DIR.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
