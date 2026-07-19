"""``claude-export → MIF`` — the thin adapter (Círculo B of the portable
memory design).

Reads the ``memories.json`` of an official Claude account data export and
projects it to MIF v1.0 Memory Units, ready for ``dna memory import``.

WHAT THE EXPORT ACTUALLY IS (checked against a real export, not inferred):
the file is a JSON list with ONE entry holding ``account_uuid``,
``conversations_memory`` (a single markdown STRING) and ``project_memories``
(a dict of ``project_uuid -> markdown string``). It is **not** a list of
discrete memory records. Each markdown blob is a flat sequence of
``**Section heading**`` lines followed by prose paragraphs.

Three consequences, stated plainly because they bound what a round-trip
through this adapter can honestly claim:

1. **Segmentation is inferred, not given.** This adapter emits one Memory
   Unit per prose paragraph, carrying its section heading as the title. That
   boundary is the adapter's judgement; the export contains no unit
   delimiters. A different segmentation would be equally faithful to the
   source.
2. **There are no per-memory timestamps.** MIF requires ``created``, so the
   caller must supply one (``created``). It describes when the memory was
   IMPORTED, not when it was formed — that information does not exist in the
   export and is not reconstructible.
3. **There are no ids.** Ids are minted deterministically (uuid5 over the
   account, source and content), so re-running the adapter on the same
   export yields the same ids and a re-import is idempotent rather than
   duplicating.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

#: Stable namespace for minted ids — fixed forever, so the same export always
#: produces the same MIF ids across machines and runs.
CLAUDE_EXPORT_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

_HEADING = re.compile(r"^\*\*(.+?)\*\*\s*$", re.M)


def _sections(markdown: str) -> list[tuple[str, str]]:
    """Split a memory blob into ``(heading, body)`` pairs.

    Text appearing before the first heading is kept under an empty heading
    rather than dropped — silently losing it would be the easy bug here.
    """
    out: list[tuple[str, str]] = []
    marks = list(_HEADING.finditer(markdown))
    if not marks:
        return [("", markdown.strip())] if markdown.strip() else []
    if markdown[: marks[0].start()].strip():
        out.append(("", markdown[: marks[0].start()].strip()))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(markdown)
        body = markdown[m.end():end].strip()
        if body:
            out.append((m.group(1).strip(), body))
    return out


def _paragraphs(body: str) -> list[str]:
    """One unit per paragraph (blank-line separated); bullet runs stay whole."""
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]


def _unit(
    *, account: str, source: str, heading: str, text: str, created: str,
) -> dict[str, Any]:
    seed = f"{account}\x00{source}\x00{heading}\x00{text}"
    tags = ["claude-export"]
    if heading:
        tags.append(re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-"))
    doc: dict[str, Any] = {
        "id": str(uuid.uuid5(CLAUDE_EXPORT_NAMESPACE, seed)),
        "type": "semantic",
        "created": created,
        "content": text,
        "tags": tags,
        "source": {"producer": "claude-export", "ref": source},
    }
    if heading:
        doc["title"] = heading
    return doc


def from_claude_export(payload: list[dict[str, Any]], *, created: str) -> list[dict[str, Any]]:
    """Project a parsed ``memories.json`` payload to MIF Memory Unit dicts.

    Pure and deterministic — no clock, no randomness, no I/O. ``created`` is
    REQUIRED and stamped on every unit (see the module docstring: the export
    carries no timestamps, so this is import time, not formation time).
    """
    units: list[dict[str, Any]] = []
    for entry in payload:
        account = str(entry.get("account_uuid") or "unknown")
        blobs: list[tuple[str, str]] = []
        conv = entry.get("conversations_memory")
        if isinstance(conv, str) and conv.strip():
            blobs.append(("conversations_memory", conv))
        projects = entry.get("project_memories")
        if isinstance(projects, dict):
            for project_id, blob in sorted(projects.items()):
                if isinstance(blob, str) and blob.strip():
                    blobs.append((f"project:{project_id}", blob))
        for source, blob in blobs:
            for heading, body in _sections(blob):
                for text in _paragraphs(body):
                    units.append(_unit(account=account, source=source,
                                       heading=heading, text=text, created=created))
    return units


def read_claude_export(path: Path, *, created: str) -> list[dict[str, Any]]:
    """Read ``memories.json`` (or an export DIRECTORY containing it)."""
    target = path / "memories.json" if path.is_dir() else path
    payload = json.loads(target.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = [payload]
    return from_claude_export(payload, created=created)


def write_mif_dir(units: list[dict[str, Any]], out_dir: Path) -> list[Path]:
    """Write one ``<id>.md`` MIF file per unit — the shape ``dna memory
    import`` reads. Dates are QUOTED so YAML keeps them strings."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for u in units:
        fm = [f"id: {u['id']}", f"type: {u['type']}", f"created: \"{u['created']}\""]
        if u.get("title"):
            fm.append(f"title: {json.dumps(u['title'], ensure_ascii=False)}")
        if u.get("tags"):
            fm.append("tags: " + json.dumps(u["tags"], ensure_ascii=False))
        p = out_dir / f"{u['id']}.md"
        p.write_text("---\n" + "\n".join(fm) + "\n---\n\n" + u["content"] + "\n",
                     encoding="utf-8")
        written.append(p)
    return written
