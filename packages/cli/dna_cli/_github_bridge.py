"""DNA ↔ GitHub Issues bridge — pure builders + ``gh`` plumbing.

The philosophy (s-github-issues-bridge)
---------------------------------------
GitHub Issues are artifacts of the github.com domain — DNA **bridges**
to them with provenance, it does not replace them. Same stance as the
PR half of the symbiosis (``pr_cmd.py``): the ``gh`` CLI is the door,
the 🧬 attribution footer is the signature, and the provenance fields
(``github_number`` / ``github_url`` / ``github_state`` /
``github_synced_at`` on the Issue Kind schema) are the machine-readable
link back.

This module is the single home for the bridge's *mechanics* so both
``issue_bridge_cmd.py`` (the ``dna sdlc issue publish|import|sync``
commands) and ``sdlc_cmd.cmd_issue_resolve`` (the fail-soft close-on-
resolve hook) share one implementation:

- **pure builders** — issue title/body assembly, ``owner/name`` repo
  parsing, ``#N``/URL reference parsing, the label→type/severity
  heuristic. All offline-testable, no subprocess.
- **gh plumbing** — a bounded ``subprocess.run`` wrapper in two
  flavors: ``run_gh`` (raises ``GhError`` with a didactic message —
  publish/import/sync want fail-loud) and ``close_issue_best_effort``
  (returns a warning string — ``issue resolve`` must NEVER fail because
  the network did).

Label → type/severity heuristic (documented contract for ``import``):

=================================  =============
GitHub label (case-insensitive)    Issue field
=================================  =============
``bug`` / ``regression``           type=bug
``enhancement`` / ``feature``      type=enhancement
``question`` / ``help wanted``     type=question
``documentation`` / ``docs`` /
``task`` / ``chore``               type=task
(none of the above)                type=task
``critical`` / ``urgent`` / ``p0``  severity=critical
``high`` / ``p1``                  severity=high
``low`` / ``minor`` / ``p3`` /
``trivial``                        severity=low
(none of the above)                severity=medium
=================================  =============

Deliberately simple: first match wins in label order; anything fancier
belongs to a human triage, not an import heuristic.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any

from dna_cli import _git_symbiosis as gs

GH_TIMEOUT = 60  # seconds — every gh call here talks to the network

#: One comment template for the close-on-resolve sync so tests + prose
#: can't drift from the implementation.
CLOSE_COMMENT_TEMPLATE = (
    "Resolved in DNA SDLC{resolution}.\n\n{footer}"
)


class GhError(Exception):
    """A ``gh`` invocation failed in a way the caller should surface.

    The message is already didactic (install/auth/network hints) — CLI
    commands wrap it in ``fail()`` verbatim.
    """


# ─── pure builders (the offline-testable surface) ─────────────────────


def parse_repo_from_remote(remote_url: str) -> str | None:
    """``owner/name`` from a git remote URL, or ``None``.

    Handles the three shapes GitHub remotes come in::

        https://github.com/owner/name.git
        git@github.com:owner/name.git
        ssh://git@github.com/owner/name

    Non-GitHub remotes → ``None`` (the bridge is a github.com bridge).
    """
    url = (remote_url or "").strip()
    m = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url)
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2)}"


def default_repo() -> str | None:
    """``owner/name`` derived from the current repo's ``origin`` remote.

    Fail-soft (``None``) — callers turn absence into a didactic error
    asking for ``--repo``.
    """
    out = gs._run_git(["remote", "get-url", "origin"])
    if not out:
        return None
    return parse_repo_from_remote(out.strip())


def parse_issue_ref(ref: str) -> tuple[int, str | None]:
    """Parse ``#N`` / ``N`` / a full GitHub issue URL → ``(number, repo)``.

    The URL form also yields the repo (``owner/name``); the numeric
    forms yield ``(N, None)`` and the caller resolves the repo. Raises
    ``ValueError`` with a didactic message on anything else.
    """
    r = (ref or "").strip()
    m = re.match(r"^https?://github\.com/([^/\s]+)/([^/\s]+)/issues/(\d+)/?$", r)
    if m:
        return int(m.group(3)), f"{m.group(1)}/{m.group(2)}"
    m = re.match(r"^#?(\d+)$", r)
    if m:
        return int(m.group(1)), None
    raise ValueError(
        f"referência de issue inválida: {ref!r} — use '#N', 'N' ou a URL "
        f"completa (https://github.com/<owner>/<repo>/issues/N)."
    )


def slug_from_title(title: str, *, max_words: int = 6) -> str:
    """Kebab-case slug from a GitHub issue title (for ``i-NNN-<slug>``)."""
    words = re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).split()
    return "-".join(words[:max_words]) or "imported"


def build_issue_title(name: str, spec: dict[str, Any]) -> str:
    """GitHub issue title: ``<title> (<i-x>)`` — pure.

    Same convention as ``build_pr_title``: the slug rides along so the
    GitHub title alone is ⌘K-pasteable back to the work item. Issues
    often have no ``title`` field — fall back to the description's
    first line, squeezed and bounded (GitHub caps titles at 256 chars).
    """
    title = str(spec.get("title") or "").strip()
    if not title:
        desc = " ".join(str(spec.get("description") or name).split())
        title = desc[:120] + ("…" if len(desc) > 120 else "")
    return f"{title} ({name})"


def doc_url(repo: str, scope: str, name: str) -> str:
    """GitHub blob URL of the Issue doc inside the repo (main branch)."""
    return f"https://github.com/{repo}/blob/main/.dna/{scope}/issues/{name}.yaml"


def build_issue_body(name: str, spec: dict[str, Any], *, scope: str, repo: str) -> str:
    """GitHub issue body: description + facts + doc link + 🧬 footer — pure.

    The footer reuses the exact PR attribution template
    (``_git_symbiosis.pr_footer_block``) with ``Issue/<i-x>`` as the
    work item — one convention, three surfaces (commits, PRs, issues).
    """
    parts: list[str] = []
    desc = str(spec.get("description") or "").strip()
    if desc:
        parts.append(desc)
    facts = [
        f"**{label}:** {spec.get(key)}"
        for label, key in (("Type", "type"), ("Severity", "severity"))
        if spec.get(key)
    ]
    if facts:
        parts.append(" · ".join(facts))
    parts.append(f"Tracked as [`{name}`]({doc_url(repo, scope, name)}) on the DNA SDLC board.")
    parts.append(gs.pr_footer_block("Issue", name))
    return "\n\n".join(parts) + "\n"


def map_labels(labels: list[str]) -> tuple[str, str]:
    """GitHub labels → ``(type, severity)`` — the documented heuristic.

    First match wins in label order; defaults ``("task", "medium")``.
    """
    type_map = {
        "bug": "bug", "regression": "bug",
        "enhancement": "enhancement", "feature": "enhancement",
        "question": "question", "help wanted": "question",
        "documentation": "task", "docs": "task", "task": "task", "chore": "task",
    }
    sev_map = {
        "critical": "critical", "urgent": "critical", "p0": "critical",
        "high": "high", "p1": "high",
        "low": "low", "minor": "low", "p3": "low", "trivial": "low",
    }
    issue_type = severity = None
    for raw in labels or []:
        lbl = str(raw).strip().lower()
        if issue_type is None and lbl in type_map:
            issue_type = type_map[lbl]
        if severity is None and lbl in sev_map:
            severity = sev_map[lbl]
    return issue_type or "task", severity or "medium"


def close_comment(name: str, resolution: str | None) -> str:
    """The comment posted when ``issue resolve`` closes the GitHub twin."""
    res = f": {resolution}" if resolution else ""
    return CLOSE_COMMENT_TEMPLATE.format(
        resolution=res, footer=gs.pr_footer("Issue", name),
    )


# ─── gh plumbing ──────────────────────────────────────────────────────


def gh_available() -> bool:
    return shutil.which("gh") is not None


def gh_missing_message(context: str) -> str:
    """The didactic no-gh error, shared by publish/import/sync."""
    return (
        f"gh (GitHub CLI) não encontrado no PATH — {context} precisa dele. "
        "Instale via https://cli.github.com e autentique com `gh auth login`."
    )


def run_gh(args: list[str], *, context: str) -> str:
    """Run ``gh`` fail-LOUD: returns stdout, raises ``GhError`` didactically.

    ``context`` names the operation for the error message ("issue
    publish", "issue import", …). Never lets a raw traceback escape.
    """
    if not gh_available():
        raise GhError(gh_missing_message(context))
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=GH_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise GhError(
            f"gh excedeu {GH_TIMEOUT}s durante {context} — rede/gateway? Tente de novo."
        ) from None
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise GhError(
            f"gh falhou durante {context}:\n{detail}\n"
            "Dicas: `gh auth status` mostra a autenticação; --repo "
            "aponta o repositório explicitamente."
        )
    return proc.stdout or ""


def fetch_issue(number: int, repo: str, *, context: str) -> dict[str, Any]:
    """``gh issue view N --json …`` → parsed dict (fail-loud via GhError)."""
    out = run_gh(
        [
            "gh", "issue", "view", str(number), "--repo", repo,
            "--json", "number,title,body,state,url,author,labels,createdAt,closedAt",
        ],
        context=context,
    )
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise GhError(
            f"gh devolveu JSON inválido durante {context} — saída: {out[:200]!r}"
        ) from None


def close_issue_best_effort(
    number: int, repo: str | None, comment: str,
) -> str | None:
    """Close the GitHub twin with a comment — NEVER raises.

    Returns ``None`` on success, else a human warning string the caller
    prints (the local resolve already happened; the sync is best-effort
    by contract).
    """
    if not gh_available():
        return (
            f"gh não encontrado — issue #{number} NÃO foi fechada no GitHub "
            f"(feche à mão ou rode `dna sdlc issue sync` depois)."
        )
    args = ["gh", "issue", "close", str(number), "--comment", comment]
    if repo:
        args += ["--repo", repo]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=GH_TIMEOUT)
    except Exception as e:  # noqa: BLE001 — best-effort by contract
        return f"não consegui fechar a issue #{number} no GitHub ({e}) — feche à mão."
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return (
            f"gh issue close #{number} falhou (non-fatal): {detail} — "
            f"o resolve local já aconteceu; feche no GitHub à mão."
        )
    return None
