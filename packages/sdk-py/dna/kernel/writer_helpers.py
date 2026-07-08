"""Shared helpers for KindPort writers.

L3 (s-writer-binary-entries, 2026-05-25): user-content bundle Kinds
(HtmlArtifact, ImagePrompt, Pictogram, Asset) all share the
same convention: ``spec.source_files: dict[str, str | bytes]`` becomes
sibling bundle entries alongside the writer's primary marker (PROMPT.md,
README.md, etc.).

Centralising the pop+convert+write logic keeps the 5 writers honest
and lets adapter-level enhancements (e.g. size warnings, content-type
sniffing) land in one place.
"""
from __future__ import annotations

from typing import Any


def pop_source_files_as_entries(
    spec: dict[str, Any], kind_name: str,
) -> list[dict[str, Any]]:
    """Pop ``spec.source_files`` from spec (mutates) and convert each
    file to a bundle-entry dict.

    Returns a list with entries shaped as:
      - ``{"relativePath": str, "content": str}`` for text payloads
      - ``{"relativePath": str, "content_bytes": bytes}`` for binary

    The caller (a writer) prepends its primary marker (PROMPT.md /
    README.md / etc.) to this list. The adapter then writes each entry
    to the appropriate column via the BundleHandle's write_text /
    write_bytes — see PostgresWritableSource.save_document for the
    persistence side.

    Raises:
        TypeError: when a payload is neither str nor bytes.
    """
    extra = spec.pop("source_files", None) or {}
    if not isinstance(extra, dict):
        raise TypeError(
            f"{kind_name}.spec.source_files must be a dict[str, str|bytes], "
            f"got {type(extra).__name__}"
        )
    out: list[dict[str, Any]] = []
    for rel_path, payload in extra.items():
        if isinstance(payload, (bytes, bytearray)):
            out.append({"relativePath": rel_path, "content_bytes": bytes(payload)})
        elif isinstance(payload, str):
            out.append({"relativePath": rel_path, "content": payload})
        else:
            raise TypeError(
                f"{kind_name}.spec.source_files[{rel_path!r}] must be "
                f"str or bytes, got {type(payload).__name__}"
            )
    return out


def write_entries_to_handle(bundle: Any, entries: list[dict[str, Any]]) -> None:
    """Write a list of bundle entries (mixed text/binary) to a BundleHandle.

    Replaces the historical 1-line loop ``for f in self.serialize(raw):
    bundle.write_text(f["relativePath"], f["content"])`` that only
    handled text. Writers using ``pop_source_files_as_entries`` should
    call this in their ``.write()`` to dispatch correctly.
    """
    for f in entries:
        if "content_bytes" in f:
            bundle.write_bytes(f["relativePath"], f["content_bytes"])
        else:
            bundle.write_text(f["relativePath"], f["content"])
