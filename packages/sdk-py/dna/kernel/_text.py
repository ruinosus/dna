"""Internal text helpers used by the kernel parse pipeline."""
from __future__ import annotations


def strip_prompt_block(value: str) -> str:
    """Normalize trailing whitespace of a text block entering PROMPT
    COMPOSITION (i-013).

    Bundle bodies (SOUL.md, AGENTS.md, ...) are stored byte-faithfully —
    editors re-add a trailing newline, and the rw conformance kit requires
    the WRITE path to round-trip it. But at composition time the prompt
    template supplies its own joiners (``{{{soul_content}}}\\n\\n``), so a
    body's trailing newline stacked into ``\\n\\n\\n`` in the composed
    prompt. Strip ONLY here, at the consumption boundary — never at
    read/write, which must stay byte-identical to storage.
    """
    return value.rstrip()


def derive_first_line(text: str | None, max_len: int = 160) -> str | None:
    """Return the first useful line of a markdown/text blob.

    Strips leading heading markers (`#`) and surrounding whitespace, skips
    empty lines and divider-only lines (`---`, `===`, etc.). Truncates to
    ``max_len`` chars with an ellipsis suffix.

    Returns ``None`` if no meaningful line is found.
    """
    if not text:
        return None
    for raw in text.splitlines():
        line = raw.strip().lstrip("#").strip()
        if not line:
            continue
        if set(line) <= {"-", "=", "*", "_"}:
            continue
        if len(line) > max_len:
            return line[:max_len] + "..."
        return line
    return None
