"""Internal text helpers used by the kernel parse pipeline."""
from __future__ import annotations


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
