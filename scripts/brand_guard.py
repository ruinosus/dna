#!/usr/bin/env python3
"""Brand grep-guard for the public DNA repo (s-public-ci). Pure stdlib.

DNA was extracted from an internal codebase; no internal brand token may leak
into this repository. The guard fails (exit 1) when any tracked text file — or
any tracked file PATH — matches:

  1. ``avanade`` or ``cockpit``      (case-insensitive, anywhere)
  2. ``\\baap`` / ``aap_`` / ``_aap`` / ``.aap``   (case-insensitive)
     — word-start ``aap`` (subsumes ``\\baap\\b`` and catches ``aapN``-style
     prefixes such as the AAPL ticker, which the allowlist then re-admits
     explicitly), plus the snake/dot forms used by the old internal naming.

Allowlist is EXPLICIT and versioned here, per file + per token — never global.
A match is admitted only when its surrounding word (lowercased) is listed for
that exact relative path. Anything else fails, including new occurrences of an
allowlisted token in a non-allowlisted file.

Usage:
    python3 scripts/brand_guard.py               # scan the repo (exit 1 on hit)
    python3 scripts/brand_guard.py --self-test   # prove the guard catches tokens
    python3 scripts/brand_guard.py --root DIR    # scan an arbitrary tree

CI runs ``--self-test`` first, then the real scan (.github/workflows/guards.yml).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile

# --- patterns ---------------------------------------------------------------

BRAND_RE = re.compile(r"avanade|cockpit", re.IGNORECASE)
# \baap subsumes \baap\b and additionally flags word-start prefixes (AAPL);
# aap_/_aap/.aap catch the old internal snake/dot naming mid-word.
AAP_RE = re.compile(r"\baap|aap_|_aap|\.aap", re.IGNORECASE)
PATTERNS = (BRAND_RE, AAP_RE)

WORD_RE = re.compile(r"[A-Za-z0-9]+")

# --- allowlist: relative path -> set of allowed WORDS (lowercase) -----------
# The "word" is the full contiguous [A-Za-z0-9]+ run containing the match, so
# "AAPL" allowlists as "aapl" even though the regex only matched "AAP".
ALLOWLIST: dict[str, frozenset[str]] = {
    # Real marketplace fixture (Anthropic xlsx skill) — line 63 cites a
    # Bloomberg source: "AAPL US Equity". Ticker, not a brand leak.
    "scopes/market-integration/.dna/market-demo/skills/xlsx/SKILL.md": frozenset(
        {"aapl"}
    ),
    # The SDLC story that SPECIFIES this guard — its description necessarily
    # names the forbidden tokens and the AAPL allowlist. (The repo's own SDLC
    # scope lives at .dna/dna-development since s-sdlc-git-symbiosis.)
    ".dna/dna-development/stories/s-public-ci.yaml": frozenset(
        {"avanade", "cockpit", "aap", "aapl"}
    ),
}

# The guard itself contains the patterns + allowlist literals by construction.
SELF_PATH = "scripts/brand_guard.py"

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
        if rel_posix == SELF_PATH:
            continue  # the guard necessarily spells its own patterns
        allowed = allowlist.get(rel_posix, frozenset())
        # File PATH itself must be clean too (e.g. a stray `.aap/` directory).
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
    cases_must_fail = {
        "a.md": "Powered by Avanade internally.",
        "b.py": 'PORTAL = "cockpit-portal"',
        "c.txt": "the aap kernel",          # \baap\b
        "d.py": "AAP_TENANT = 'acme'",       # aap_
        "e.yaml": "path: scopes/_aap/x",     # _aap
        "f.md": "stored under .aap/scope",   # .aap
        "g.md": "ticker AAPL is not allowlisted here",  # \baap prefix
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
        got = scan(tmp, allowlist={"case/g.md": frozenset({"aapl"})})
        if any(v.startswith("case/g.md") for v in got):
            failures.append("allowlisted AAPL in case/g.md still flagged")
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="tree to scan (default: repo root)")
    parser.add_argument("--self-test", action="store_true", help="run the planted-token self-test")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    violations = scan(root)
    if violations:
        print(f"brand_guard: {len(violations)} violation(s):", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "\nIf a hit is legitimate (e.g. a real market fixture), add the exact"
            f" file + word to ALLOWLIST in {SELF_PATH}.",
            file=sys.stderr,
        )
        return 1
    print("brand_guard: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
