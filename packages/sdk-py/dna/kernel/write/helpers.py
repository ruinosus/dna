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
    write_bytes — see PostgresWritableSource.save_instance for the
    persistence side.

    EVERY KEY IS VALIDATED HERE, and this is the layer that closes the SQL
    lane. The obvious place to guard a content-derived entry is the handle
    (``FilesystemBundleHandle._entry_path``) or ``DictBundleHandle._validate``,
    and for the filesystem lane that is true. It is NOT true for the SQL lane:
    ``SqlAlchemySource.save_instance`` calls this function to pop
    ``spec.source_files`` BEFORE any writer runs and merges the returned keys
    straight into its ``bundle_text`` / ``bundle_bin`` dicts — no handle is
    ever constructed for them, so no handle can refuse them. Measured before
    this check existed: ``save_instance`` on a SQLite-backed source returned
    ``version='1'`` and the ``bundle_entries`` table held the rows
    ``'../../../../etc/cron.d/pwn'`` and ``'/tmp/dna-ABSOLUTE-STORED.md'``
    verbatim. That directly contradicts the property the previous wave claimed
    — "refusing at the write keeps the escape from being STORED" — because on
    a Postgres-backed deployment nothing else in the chain looks at the key.

    So the guard goes HERE, not at the two adapters: this is the
    kind-AGNOSTIC ``spec.source_files`` convention and the ONE place the FS
    lane and the SQL lane both pass through. Guarding the adapters instead
    would be the enumeration mistake again, one lane at a time.

    A stored row is not a harmless row. ``dna_bundle_entries`` is what
    materialises a bundle onto a filesystem later (sync, export, a cache
    warm), so a traversing key is the same escape merely DEFERRED until
    something writes it down.

    Raises:
        InvalidBundleEntry: when a key is not a safe relative bundle path.
        TypeError: when ``source_files`` or a payload has the wrong type.
    """
    from dna.kernel.errors import validate_bundle_entry

    # Read BEFORE popping, so a refusal does not leave the caller's ``spec``
    # stripped of the field it was refused for.
    extra = spec.get("source_files") or {}
    if not isinstance(extra, dict):
        raise TypeError(
            f"{kind_name}.spec.source_files must be a dict[str, str|bytes], "
            f"got {type(extra).__name__}"
        )
    # ALL keys first, before any conversion — same all-or-nothing property as
    # ``write_entries_to_handle``: a half-converted batch is a state no caller
    # asked for.
    for rel_path in extra:
        validate_bundle_entry(
            rel_path, where=f"{kind_name}.spec.source_files key",
        )
    spec.pop("source_files", None)
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

    Every ``relativePath`` is validated FIRST, for the whole batch, before a
    single byte is dispatched. Two deliberate properties:

    - ALL-OR-NOTHING. A per-entry check that refused halfway would leave the
      bundle carrying whichever entries happened to come first — a state no
      caller asked for and no reader can interpret.
    - THIS IS THE EARLY LAYER, NOT THE CLOSING ONE. It runs before the handle,
      so it can fail in the writer's own vocabulary; but it does NOT close the
      class on its own, because eight in-repo writers call
      ``bundle.write_text(f["relativePath"], …)`` directly rather than coming
      through here. The class closes at ``BundleHandle`` itself — see
      ``FilesystemBundleHandle._entry_path``. Keep both: guarding only this
      sink is precisely the enumeration mistake that let the content-derived
      escape through in the first place.
    """
    from dna.kernel.errors import validate_bundle_entry

    for f in entries:
        validate_bundle_entry(
            f["relativePath"], where="bundle entry relativePath",
        )
    for f in entries:
        if "content_bytes" in f:
            bundle.write_bytes(f["relativePath"], f["content_bytes"])
        else:
            bundle.write_text(f["relativePath"], f["content"])
