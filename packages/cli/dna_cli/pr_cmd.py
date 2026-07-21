"""``dna sdlc story pr`` + ``dna sdlc pr-footer`` — PR attribution.

The PR-side half of the git↔SDLC symbiosis (s-sdlc-pr-attribution): the
same way Claude Code signs the PRs it generates, DNA signs the PRs born
from its Stories. ``dna sdlc story pr <s-x>`` assembles ``gh pr create``
entirely from the Story document — the PR is born FROM the story, not
the other way around:

- **title** — ``feat(<label-hint>): <story title> (<s-x>)``. Conventional-
  commit shaped: Stories ship features by convention (bugs are Issues),
  the scope hint is the story's first label (fallback ``sdlc``), and the
  slug rides along so the PR title alone is ⌘K-pasteable back to the
  work item.
- **body** — the story description, the acceptance criteria as a GitHub
  task-list checklist (``- [ ] …``, pre-checked when the AC item carries
  ``done: true``), and the attribution footer after a ``---`` rule::

      ---
      🧬 Tracked with [DNA SDLC](https://github.com/ruinosus/dna) — Work-Item: Story/<s-x>

  Footer template + ``$DNA_SDLC_PR_FOOTER`` override live in
  ``_git_symbiosis.py`` next to the commit-trailer constants — one home
  for the whole attribution convention.

``--dry-run`` prints the exact title + body and never touches ``gh`` —
that's the testable (and offline) surface. ``dna sdlc pr-footer <s-x>``
emits just the footer block for hand-made PRs; it is a pure formatter
(no kernel session, no validation) so it works instantly from anywhere.

On success the PR URL is stamped onto the Story timeline (``pr_opened``
event, fail-soft) — commit carimbado (hook) + PR assinado (este) + the
timeline materializes both.

Deliberately NOT here — listing PRs back in ``story show`` via ``gh pr
list --search "Work-Item: Story/<x>"``: the GitHub *search* API is
rate-limited (~30 req/min), its body indexing is eventually consistent
(a fresh PR doesn't show up), and this codebase already documents the
gateway intermittently blocking api.github.com (i-133) — adding that to
``story show``, a hot fully-local command, would make it slow and flaky.
The way back already closes deterministically with zero network: a
squash-merged PR lands a commit whose message carries the ``Work-Item:``
trailer, so ``story show`` / ``story commits`` surface merged PRs via
``git log --grep``.

Registered onto the ``sdlc`` / ``sdlc story`` groups at import time
(same pattern as ``hooks_cmd``) — see ``dna_cli/__init__.py``.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import click

from dna_cli import _git_symbiosis as gs
from dna_cli._ctx import fail, open_session
from dna_cli.sdlc_cmd import (
    _append_timeline,
    _build_raw,
    _scope_option,
    sdlc,
    story_group,
)

_GH_TIMEOUT = 60  # seconds — pr create talks to the network


# ─── pure builders (the --dry-run-testable surface) ───────────────────


def _label_hint(spec: dict[str, Any]) -> str:
    """Scope hint for the conventional title: first label, else ``sdlc``."""
    labels = spec.get("labels") or []
    for lbl in labels:
        if isinstance(lbl, str) and lbl.strip():
            return lbl.strip()
    return "sdlc"


def build_pr_title(name: str, spec: dict[str, Any]) -> str:
    """``feat(<label-hint>): <story title> (<s-x>)`` — pure."""
    title = " ".join(str(spec.get("title") or name).split())
    return f"feat({_label_hint(spec)}): {title} ({name})"


def _ac_items(raw: Any) -> list[tuple[str, bool]]:
    """Normalize acceptance_criteria items (strings or ``{text, done}``
    dicts — same shapes ``story show`` renders) to ``(text, done)``."""
    out: list[tuple[str, bool]] = []
    for it in raw or []:
        if isinstance(it, str):
            if it.strip():
                out.append((it.strip(), False))
        elif isinstance(it, dict):
            text = it.get("text") or it.get("criterion") or it.get("item") or it.get("desc") or ""
            if str(text).strip():
                out.append((str(text).strip(), bool(it.get("done") or it.get("checked"))))
    return out


def build_pr_body(name: str, spec: dict[str, Any]) -> str:
    """PR body from a Story spec: description + AC checklist + footer — pure."""
    parts: list[str] = []
    desc = str(spec.get("description") or "").strip()
    if desc:
        parts.append(desc)
    ac = _ac_items(spec.get("acceptance_criteria"))
    if ac:
        lines = "\n".join(f"- [{'x' if done else ' '}] {text}" for text, done in ac)
        parts.append(f"## Acceptance criteria\n\n{lines}")
    parts.append(gs.pr_footer_block("Story", name))
    return "\n\n".join(parts) + "\n"


def build_gh_args(
    title: str, body: str, *,
    base: str | None, head: str | None, draft: bool,
) -> list[str]:
    """The exact ``gh`` argv — pure. ``--head`` is only passed when given
    (gh's own default is the current branch)."""
    args = ["gh", "pr", "create", "--title", title, "--body", body]
    if base:
        args += ["--base", base]
    if head:
        args += ["--head", head]
    if draft:
        args.append("--draft")
    return args


# ─── plumbing ─────────────────────────────────────────────────────────


def _anchor_source_to_repo_root() -> None:
    """Make the default ``./.dna`` source discovery work from ANY cwd of
    the repo: when no explicit source is configured and cwd has no
    ``.dna/``, point ``DNA_BASE_DIR`` at the enclosing repo root (where
    the scope lives by convention). Process-local — the CLI is one
    command per process."""
    if os.getenv("DNA_SOURCE_URL") or os.getenv("DNA_BASE_DIR"):
        return
    if Path(".dna").is_dir():
        return
    root = gs.repo_root()
    if root is not None and (root / ".dna").is_dir():
        os.environ["DNA_BASE_DIR"] = str(root)


def _stamp_pr_on_timeline(scope: str, name: str, url: str) -> None:
    """Append a ``pr_opened`` event carrying the PR URL. Fail-soft — the
    PR already exists; a timeline hiccup must not fail the command."""
    try:
        with open_session(scope) as s:
            existing = s.get_doc("Story", name)
            if existing is None:
                return
            spec = dict(existing.spec) if isinstance(existing.spec, dict) else {}
            _append_timeline(spec, "pr_opened", summary=f"PR aberto: {url}", pr_url=url)
            raw = _build_raw("Story", name, spec)
            s.run(s.kernel.write_document(scope, "Story", name, raw))
    except Exception as e:  # noqa: BLE001 — fail-soft by contract
        click.secho(f"⚠ não consegui carimbar o PR na timeline (non-fatal): {e}",
                    fg="yellow", err=True)


# ─── commands ─────────────────────────────────────────────────────────


@story_group.command("pr")
@click.argument("name")
@click.option("--base", default=None,
              help="Base branch do PR (passthrough pro gh; default: o do repo).")
@click.option("--head", default=None,
              help="Head branch (default: a branch corrente — default do próprio gh).")
@click.option("--draft", is_flag=True, help="Abre como draft.")
@click.option("--dry-run", "dry_run", is_flag=True,
              help="Só imprime title + body montados; não chama gh.")
@_scope_option
def cmd_story_pr(
    name: str, base: str | None, head: str | None,
    draft: bool, dry_run: bool, scope: str,
) -> None:
    """Open the Story's PR — ``gh pr create`` pre-filled FROM the story.

    Title ``feat(<label>): <título> (<s-x>)``; body = description + AC
    como checklist + footer de atribuição (``dna sdlc pr-footer``). O PR
    nasce da story, não o contrário — e a URL volta pra timeline.
    """
    _anchor_source_to_repo_root()
    with open_session(scope) as s:
        story = s.get_doc("Story", name)
        if story is None:
            raise fail(f"Story '{name}' not found in scope {scope!r}")
        spec = dict(story.spec) if isinstance(story.spec, dict) else {}

    title = build_pr_title(name, spec)
    body = build_pr_body(name, spec)

    if dry_run:
        click.secho("── title ──", fg="cyan")
        click.echo(title)
        click.secho("── body ──", fg="cyan")
        click.echo(body, nl=False)
        click.secho("(dry-run — gh pr create NÃO foi chamado)", fg="yellow", err=True)
        return

    if shutil.which("gh") is None:
        raise fail(
            "gh (GitHub CLI) não encontrado no PATH — instale via "
            "https://cli.github.com e autentique com `gh auth login`. "
            "Sem gh você ainda pode abrir o PR à mão e colar o footer: "
            f"`dna sdlc pr-footer {name}`."
        )

    args = build_gh_args(title, body, base=base, head=head, draft=draft)
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=_GH_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise fail(f"gh pr create excedeu {_GH_TIMEOUT}s — rede/gateway? "
                   f"Tente de novo ou abra à mão (dna sdlc pr-footer {name}).")
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise fail(
            "gh pr create falhou:\n"
            f"{detail}\n"
            "Dicas: a branch precisa estar publicada (git push -u origin <branch>); "
            "`gh auth status` mostra a autenticação; use --base/--head pra "
            "apontar branches explicitamente."
        )
    url = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
    click.secho(f"PR CREATED from Story/{name}", fg="green")
    if url:
        click.echo(url)
        _stamp_pr_on_timeline(scope, name, url)


@sdlc.command("pr-footer")
@click.argument("name")
def cmd_pr_footer(name: str) -> None:
    """Print the attribution footer block for a hand-made PR body.

    Pure formatter (no kernel session, no gh): paste the output at the
    end of the PR body você abriu à mão. Template + override
    (``$DNA_SDLC_PR_FOOTER``) em ``_git_symbiosis.py``.
    """
    click.echo(gs.pr_footer_block("Story", name))
