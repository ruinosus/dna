#!/usr/bin/env python3
"""Brand grep-guard for the public DNA repo (s-public-ci). Pure stdlib.

DNA was extracted from an internal codebase; no internal brand token may leak
into this repository — file contents, file paths, or commit identities.

The forbidden tokens are stored BASE64-ENCODED in ``_TOKENS_B64`` and decoded
only at runtime, so this file itself carries no literal occurrence: a plain
GitHub/grep search for the tokens returns nothing, and the guard can scan
itself like any other file (no self-exclusion). To inspect the list:
``python3 -c "import base64; print(base64.b64decode('...'))"``.

Checked per tracked file: (1) the two brand words anywhere, case-insensitive;
(2) the legacy three-letter prefix at word start (which also flags e.g. the
a stock ticker — re-admitted via allowlist) and its snake/dot mid-word forms.

Allowlist is EXPLICIT and versioned here, per file + per WORD — never global.
A match is admitted only when its surrounding word (lowercased) is listed for
that exact relative path.

Usage:
    python3 scripts/brand_guard.py                  # scan the repo (exit 1 on hit)
    python3 scripts/brand_guard.py --self-test      # planted-token + commit self-tests
    python3 scripts/brand_guard.py --root DIR       # scan an arbitrary tree
    python3 scripts/brand_guard.py --commits RANGE  # validate commit identities

CI runs ``--self-test`` first, then the real scans (.github/workflows/guards.yml).
"""
from __future__ import annotations

import argparse
import base64
import os
import re
import subprocess
import sys
import tempfile

# --- patterns (tokens base64-encoded — this file must scan clean) -----------

_TOKENS_B64 = ("YXZhbmFkZQ==", "Y29ja3BpdA==", "YWFw")
_BRAND1, _BRAND2, _PFX = (base64.b64decode(t).decode() for t in _TOKENS_B64)

BRAND_RE = re.compile(f"{_BRAND1}|{_BRAND2}", re.IGNORECASE)
# word-start prefix (subsumes the exact word and catches ticker-style
# extensions, re-admitted via allowlist) + snake/dot mid-word forms.
PFX_RE = re.compile(rf"\b{_PFX}|{_PFX}_|_{_PFX}|\.{_PFX}", re.IGNORECASE)
PATTERNS = (BRAND_RE, PFX_RE)

WORD_RE = re.compile(r"[A-Za-z0-9]+")

# --- allowlist: relative path -> set of allowed WORDS (lowercase) -----------
# The "word" is the full contiguous [A-Za-z0-9]+ run containing the match, so
# the ticker allowlists as the full 4-letter word even though the regex only
# matched its 3-letter prefix.
ALLOWLIST: dict[str, frozenset[str]] = {
    # Real marketplace fixture (Anthropic xlsx skill) — cites a Bloomberg
    # source citing a stock ticker (the 4-letter extension of the prefix).
    "scopes/market-integration/.dna/market-demo/skills/xlsx/SKILL.md": frozenset(
        {_PFX + "l"}
    ),
    # Pilot story cites foundry-assured's agent block names verbatim
    # (triage/retrieve/resolve/concierge×3/<this>/selfwiki/platform) — the
    # word there is THAT repo's agent name, not an internal brand token.
    ".dna/dna-development/stories/s-pilot-foundry-assured.yaml": frozenset(
        {_BRAND2}
    ),
}

SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", "dist"}


# --- scanning ---------------------------------------------------------------


def _tracked_files(root: str) -> list[str]:
    """git-tracked files (relative paths) when available; os.walk fallback."""
    try:
        out = subprocess.run(
            ["git", "-C", root, "ls-files", "-z"],
            capture_output=True, check=True, timeout=30,
        ).stdout
        files = [p for p in out.decode("utf-8", "replace").split("\0") if p]
        if files:
            return files
    except Exception:
        pass
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            files.append(os.path.relpath(os.path.join(dirpath, name), root))
    return files


def _word_at(text: str, start: int, end: int) -> str:
    """Full contiguous alphanumeric word containing text[start:end], lowered."""
    lo = start
    while lo > 0 and text[lo - 1].isalnum():
        lo -= 1
    hi = end
    while hi < len(text) and text[hi].isalnum():
        hi += 1
    return text[lo:hi].lower()


def scan(root: str, allowlist: dict[str, frozenset[str]] | None = None) -> list[str]:
    """Return violations as 'path:line: token (word)' strings."""
    allowlist = ALLOWLIST if allowlist is None else allowlist
    violations: list[str] = []
    for rel in sorted(_tracked_files(root)):
        rel_posix = rel.replace(os.sep, "/")
        allowed = allowlist.get(rel_posix, frozenset())
        # File PATH itself must be clean too (e.g. a stray legacy directory).
        for pat in PATTERNS:
            for m in pat.finditer(rel_posix):
                word = _word_at(rel_posix, m.start(), m.end())
                if word not in allowed:
                    violations.append(f"{rel_posix}: path contains '{m.group(0)}'")
        path = os.path.join(root, rel)
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable — path already checked above
        for pat in PATTERNS:
            for m in pat.finditer(text):
                word = _word_at(text, m.start(), m.end())
                if word in allowed:
                    continue
                line = text.count("\n", 0, m.start()) + 1
                violations.append(
                    f"{rel_posix}:{line}: forbidden token '{m.group(0)}' (word: '{word}')"
                )
    return violations


# --- self-test ---------------------------------------------------------------


def self_test() -> int:
    """Plant each forbidden token in a temp tree and prove the guard fails on
    every one; prove the allowlist admits exactly its file+token pair."""
    # planted contents are BUILT from the decoded tokens so this file itself
    # never spells them
    cases_must_fail = {
        "a.md": f"Powered by {_BRAND1.title()} internally.",
        "b.py": f'PORTAL = "{_BRAND2}-portal"',
        "c.txt": f"the {_PFX} kernel",                     # word-start
        "d.py": f"{_PFX.upper()}_TENANT = 'acme'",         # snake prefix
        "e.yaml": f"path: scopes/_{_PFX}/x",               # snake suffix
        "f.md": f"stored under .{_PFX}/scope",             # dot form
        "g.md": f"ticker {_PFX.upper()}L is not allowlisted here",  # prefix ext
    }
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, content in cases_must_fail.items():
            sub = os.path.join(tmp, "case", name)
            os.makedirs(os.path.dirname(sub), exist_ok=True)
            with open(sub, "w", encoding="utf-8") as fh:
                fh.write(content)
        got = scan(tmp, allowlist={})
        hit_files = {v.split(":", 1)[0] for v in got}
        for name in cases_must_fail:
            if f"case/{name}" not in hit_files:
                failures.append(f"planted token in case/{name} NOT caught")
        # clean file must not be flagged
        with open(os.path.join(tmp, "case", "clean.md"), "w", encoding="utf-8") as fh:
            fh.write("nothing to see here")
        got = scan(tmp, allowlist={})
        if any(v.startswith("case/clean.md") for v in got):
            failures.append("clean file falsely flagged")
        # allowlist admits exactly the file+word pair, nothing more
        got = scan(tmp, allowlist={"case/g.md": frozenset({_PFX + "l"})})
        if any(v.startswith("case/g.md") for v in got):
            failures.append("allowlisted ticker in case/g.md still flagged")
        if not any(v.startswith("case/c.txt") for v in got):
            failures.append("allowlist for g.md leaked to c.txt")
    if failures:
        print("brand_guard SELF-TEST FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"brand_guard self-test OK ({len(cases_must_fail)} planted tokens caught, "
          "allowlist scoped to file+token)")
    return 0


# --- commit metadata (s-commit-email-guard) ----------------------------------
# The file scan above cannot see COMMIT metadata — that's how 27 corporate
# identities reached the history before the one-off rewrite. This closes the
# hole for good: every commit in a range must have clean author/committer
# name + email.

IDENTITY_DENY_RE = BRAND_RE  # same decoded tokens — no literals here either


def scan_commits(root: str, rev_range: str) -> list[str]:
    """Return violations 'sha: field <value>' for denied commit identities."""
    out = subprocess.run(
        ["git", "-C", root, "log", "--format=%h%x00%an%x00%ae%x00%cn%x00%ce", rev_range],
        capture_output=True, check=True, timeout=60,
    ).stdout.decode("utf-8", "replace")
    violations: list[str] = []
    for line in filter(None, out.splitlines()):
        sha, an, ae, cn, ce = line.split("\0")
        for field, value in (("author", f"{an} <{ae}>"), ("committer", f"{cn} <{ce}>")):
            if IDENTITY_DENY_RE.search(value):
                violations.append(f"{sha}: {field} identity '{value}' matches denylist")
    return violations


def self_test_commits() -> int:
    """git-init a temp repo, plant a denied identity, prove the guard fails."""
    denied = f"dev@{_BRAND1}.com"  # built from the decoded token
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ,
               "GIT_AUTHOR_NAME": "dev", "GIT_AUTHOR_EMAIL": denied,
               "GIT_COMMITTER_NAME": "dev", "GIT_COMMITTER_EMAIL": denied,
               "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
        def g(*args: str, e: dict | None = None) -> None:
            subprocess.run(["git", "-C", tmp, *args], check=True,
                           capture_output=True, env=e or env, timeout=30)
        g("init", "-q", "-b", "main")
        open(os.path.join(tmp, "f"), "w").close()
        g("add", "f")
        g("commit", "-q", "-m", "planted", "--no-verify")
        bad = scan_commits(tmp, "HEAD")
        clean_env = {**env, "GIT_AUTHOR_EMAIL": "ok@users.noreply.github.com",
                     "GIT_COMMITTER_EMAIL": "ok@users.noreply.github.com"}
        with open(os.path.join(tmp, "f"), "w") as fh:
            fh.write("x")
        g("add", "f")
        g("commit", "-q", "-m", "clean", "--no-verify", e=clean_env)
        good = scan_commits(tmp, "HEAD~1..HEAD")
    if not bad:
        print("commit self-test FAILED: planted identity not caught", file=sys.stderr)
        return 1
    if good:
        print(f"commit self-test FAILED: clean identity flagged: {good}", file=sys.stderr)
        return 1
    print("brand_guard commit self-test OK (planted identity caught, clean identity passes)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="tree to scan (default: repo root)")
    parser.add_argument("--self-test", action="store_true", help="run the planted-token self-test")
    parser.add_argument("--commits", metavar="RANGE", default=None,
                        help="validate commit author/committer identities in RANGE (e.g. BASE..HEAD)")
    args = parser.parse_args()
    if args.self_test:
        rc = self_test()
        return rc or self_test_commits()
    root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if args.commits:
        violations = scan_commits(root, args.commits)
        if violations:
            print(f"brand_guard: {len(violations)} commit identity violation(s):", file=sys.stderr)
            for v in violations:
                print(f"  {v}", file=sys.stderr)
            print("\nRewrite the offending commits (rebase -r / filter-branch) before merging.",
                  file=sys.stderr)
            return 1
        print("brand_guard: commit identities clean")
        return 0
    violations = scan(root)
    if violations:
        print(f"brand_guard: {len(violations)} violation(s):", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "\nIf a hit is legitimate (e.g. a real market fixture), add the exact"
            f" file + word to ALLOWLIST in scripts/brand_guard.py.",
            file=sys.stderr,
        )
        return 1
    print("brand_guard: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
