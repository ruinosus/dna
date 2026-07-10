"""``dna sdlc issue publish|import|sync`` — the GitHub Issues bridge.

The third side of the git↔SDLC symbiosis triangle (s-github-issues-
bridge): commits carry the ``Work-Item:`` trailer, PRs carry the 🧬
footer, and now GitHub issues do too. GitHub Issues are artifacts of
the github.com domain — DNA **bridges** with provenance, it does not
replace them:

- ``issue publish <i-x>`` — creates the GitHub twin via ``gh issue
  create`` (title from the doc + ``(i-x)`` suffix, body = description
  + facts + doc link + 🧬 footer) and stamps ``github_number`` /
  ``github_url`` / ``github_state`` / ``github_synced_at`` back onto
  the doc through the kernel (the write path validates — the fields
  live on the Issue Kind schema). Idempotent: an already-published doc
  just prints its link.
- ``issue import <#N | url>`` — creates an Issue doc FROM a GitHub
  issue (``gh issue view --json``), board-convention name
  (``i-NNN-<slug>`` via the next free number), labels mapped to
  type/severity by the documented heuristic in ``_github_bridge``,
  reporter = the GitHub author, provenance filled. Idempotent: a doc
  already bridged to ``#N`` on that repo wins.
- ``issue sync <i-x>`` — refreshes ``github_state`` from the remote;
  a remotely-closed issue leaves a note on the local timeline.

``--repo`` defaults to the ``origin`` remote of the enclosing repo
(``owner/name``); pass it explicitly to bridge across repos. Honest
degradation: no ``gh`` / auth / network → a didactic error, never a
traceback (the fail-SOFT half — closing the twin on ``issue resolve``
— lives in ``sdlc_cmd.cmd_issue_resolve``).

Mechanics (pure builders + gh plumbing) live in ``_github_bridge.py``;
this module is only the click surface. Registered onto the ``sdlc
issue`` group at import time (same pattern as ``pr_cmd``) — see
``dna_cli/__init__.py``.
"""
from __future__ import annotations

import re
from typing import Any

import click

from dna_cli import _github_bridge as gb
from dna_cli._ctx import dna_session, fail
from dna_cli.pr_cmd import _anchor_source_to_repo_root
from dna_cli.sdlc_cmd import (
    _append_timeline,
    _build_raw,
    _next_issue_number,
    _now_iso,
    _scope_option,
    issue_group,
)


def _repo_option(f):
    return click.option(
        "--repo", default=None,
        help="GitHub repo 'owner/name' (default: derivado do remote origin).",
    )(f)


def _resolve_repo(repo: str | None, *, context: str) -> str:
    """Explicit ``--repo`` wins; else derive from origin; else didactic fail."""
    if repo:
        return repo
    derived = gb.default_repo()
    if derived:
        return derived
    raise fail(
        f"não consegui derivar o repositório GitHub do remote origin — "
        f"passe --repo owner/name pro {context}."
    )


def _issue_number_from_url(url: str) -> int | None:
    m = re.search(r"/issues/(\d+)/?$", url.strip())
    return int(m.group(1)) if m else None


# ─── publish ──────────────────────────────────────────────────────────


@issue_group.command("publish")
@click.argument("name")
@_repo_option
@click.option("--dry-run", "dry_run", is_flag=True,
              help="Só imprime title + body montados; não chama gh.")
@_scope_option
def cmd_issue_publish(
    name: str, repo: str | None, dry_run: bool, scope: str,
) -> None:
    """Publish the Issue to GitHub — ``gh issue create`` born FROM the doc.

    Title ``<título> (<i-x>)``; body = description + type/severity + link
    pro doc no repo + footer 🧬 de atribuição. Grava github_number/url/
    state/synced_at de volta no doc (proveniência). Idempotente: doc já
    publicado só mostra o link.
    """
    _anchor_source_to_repo_root()
    with dna_session(scope) as s:
        doc = s.get_doc("Issue", name)
        if doc is None:
            raise fail(f"Issue '{name}' not found in scope {scope!r}")
        spec = dict(doc.spec) if isinstance(doc.spec, dict) else {}

        if spec.get("github_number"):
            click.secho(
                f"Issue/{name} já publicada — GitHub #{spec['github_number']}",
                fg="yellow",
            )
            if spec.get("github_url"):
                click.echo(spec["github_url"])
            return

        repo_full = _resolve_repo(repo, context="publish")
        title = gb.build_issue_title(name, spec)
        body = gb.build_issue_body(name, spec, scope=s.scope, repo=repo_full)

        if dry_run:
            click.secho("── title ──", fg="cyan")
            click.echo(title)
            click.secho("── body ──", fg="cyan")
            click.echo(body, nl=False)
            click.secho("(dry-run — gh issue create NÃO foi chamado)",
                        fg="yellow", err=True)
            return

        try:
            out = gb.run_gh(
                ["gh", "issue", "create", "--repo", repo_full,
                 "--title", title, "--body", body],
                context="issue publish",
            )
        except gb.GhError as e:
            raise fail(str(e))
        url = out.strip().splitlines()[-1] if out.strip() else ""
        number = _issue_number_from_url(url) if url else None
        if not number:
            raise fail(
                f"gh issue create não devolveu uma URL de issue reconhecível "
                f"(saída: {out.strip()[:200]!r}) — confira no GitHub antes de repetir."
            )

        spec["github_number"] = number
        spec["github_url"] = url
        spec["github_state"] = "open"
        spec["github_synced_at"] = _now_iso()
        spec["updated_at"] = _now_iso()
        _append_timeline(
            spec, "github_published",
            summary=f"Publicada no GitHub: #{number}", github_url=url,
        )
        raw = _build_raw("Issue", name, spec)
        s.run(s.kernel.write_document(scope, "Issue", name, raw))

    click.secho(f"PUBLISHED Issue/{name} → {repo_full}#{number}", fg="green")
    click.echo(url)


# ─── import ───────────────────────────────────────────────────────────


def _spec_from_github(gh_issue: dict[str, Any]) -> dict[str, Any]:
    """Build the Issue spec from a ``gh issue view --json`` payload — pure.

    Heuristics (documented in ``_github_bridge``): labels →
    type/severity; GitHub state → status (OPEN→open, CLOSED→resolved
    with ``closed_at`` from the GitHub close time); reporter = author.
    """
    labels = [
        lbl.get("name", "") for lbl in gh_issue.get("labels") or []
        if isinstance(lbl, dict)
    ]
    issue_type, severity = gb.map_labels(labels)
    title = str(gh_issue.get("title") or "").strip()
    body = str(gh_issue.get("body") or "").strip()
    state = str(gh_issue.get("state") or "open").lower()
    spec: dict[str, Any] = {
        "title": title,
        "description": body or title,
        "type": issue_type,
        "severity": severity,
        "status": "open" if state == "open" else "resolved",
        "reporter": str((gh_issue.get("author") or {}).get("login") or "github"),
        "github_number": int(gh_issue["number"]),
        "github_url": str(gh_issue.get("url") or ""),
        "github_state": "open" if state == "open" else "closed",
        "github_synced_at": _now_iso(),
    }
    if labels:
        spec["labels"] = labels
    if spec["status"] == "resolved":
        spec["closed_at"] = str(gh_issue.get("closedAt") or _now_iso())
    if gh_issue.get("createdAt"):
        spec["created_at"] = str(gh_issue["createdAt"])
    return spec


@issue_group.command("import")
@click.argument("ref")
@_repo_option
@_scope_option
def cmd_issue_import(ref: str, repo: str | None, scope: str) -> None:
    """Import a GitHub issue as an Issue doc (``#N``, ``N`` or the URL).

    Nome segue a convenção do board (``i-NNN-<slug-do-título>`` no
    próximo número livre). Labels→type/severity por heurística simples
    (documentada em ``_github_bridge``); reporter = autor GitHub;
    proveniência (github_number/url/state/synced_at) preenchida.
    Idempotente: um doc já bridged pra essa issue vence.
    """
    _anchor_source_to_repo_root()
    try:
        number, repo_from_url = gb.parse_issue_ref(ref)
    except ValueError as e:
        raise fail(str(e))
    repo_full = repo_from_url or _resolve_repo(repo, context="import")

    try:
        gh_issue = gb.fetch_issue(number, repo_full, context="issue import")
    except gb.GhError as e:
        raise fail(str(e))

    spec = _spec_from_github(gh_issue)
    _append_timeline(
        spec, "github_imported",
        summary=f"Importada do GitHub: {repo_full}#{number}",
        github_url=spec.get("github_url"),
    )

    with dna_session(scope) as s:
        for existing in s.query_list("Issue"):
            espec = existing.spec if isinstance(existing.spec, dict) else {}
            if espec.get("github_number") == number:
                click.secho(
                    f"GitHub #{number} já importada como Issue/{existing.name} "
                    f"— nada a fazer.", fg="yellow",
                )
                return
        name = f"i-{_next_issue_number(scope):03d}-gh{number}-{gb.slug_from_title(spec['title'])}"
        raw = _build_raw("Issue", name, spec)
        s.run(s.kernel.write_document(scope, "Issue", name, raw))

    click.secho(
        f"IMPORTED {repo_full}#{number} → Issue/{name} "
        f"({spec['type']}/{spec['severity']}, status={spec['status']})",
        fg="green",
    )
    if spec.get("github_url"):
        click.echo(spec["github_url"])


# ─── sync ─────────────────────────────────────────────────────────────


@issue_group.command("sync")
@click.argument("name")
@_repo_option
@_scope_option
def cmd_issue_sync(name: str, repo: str | None, scope: str) -> None:
    """Refresh ``github_state`` from the remote twin.

    Fechada lá → além do refresh, deixa uma nota na timeline local (o
    board fica sabendo sem ninguém vigiar o GitHub). Não mexe no status
    local — decidir se "closed no GitHub" vira "resolved" é triage humana.
    """
    _anchor_source_to_repo_root()
    with dna_session(scope) as s:
        doc = s.get_doc("Issue", name)
        if doc is None:
            raise fail(f"Issue '{name}' not found in scope {scope!r}")
        spec = dict(doc.spec) if isinstance(doc.spec, dict) else {}
        number = spec.get("github_number")
        if not number:
            raise fail(
                f"Issue/{name} não tem github_number — publique primeiro "
                f"(dna sdlc issue publish {name}) ou importe do GitHub."
            )
        repo_full = _resolve_repo(repo, context="sync")

        try:
            gh_issue = gb.fetch_issue(int(number), repo_full, context="issue sync")
        except gb.GhError as e:
            raise fail(str(e))

        prev_state = spec.get("github_state")
        new_state = "open" if str(gh_issue.get("state") or "").lower() == "open" else "closed"
        spec["github_state"] = new_state
        spec["github_synced_at"] = _now_iso()
        spec["updated_at"] = _now_iso()
        if new_state == "closed" and prev_state != "closed":
            _append_timeline(
                spec, "comment",
                summary=(
                    f"GitHub #{number} foi fechada no remoto "
                    f"({repo_full}) — avaliar resolve local."
                ),
            )
        raw = _build_raw("Issue", name, spec)
        s.run(s.kernel.write_document(scope, "Issue", name, raw))

    flip = f" ({prev_state} → {new_state})" if prev_state != new_state else ""
    click.secho(f"SYNCED Issue/{name} — GitHub #{number} is {new_state}{flip}",
                fg="green")
