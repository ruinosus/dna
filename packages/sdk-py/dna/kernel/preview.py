"""Document preview API.

The Studio's "preview" pane consumes structured ``PreviewBlock``s instead
of raw markdown so each kind can render however makes sense (markdown,
code, tabular fields). The polymorphism lives inside each KindPort
(``KindPort.preview``); this module is only the type definition,
generic fallback, and a cross-document consumer scan.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .instance import ManifestInstance


PreviewBlockKind = Literal["markdown", "code", "fields", "empty"]


@dataclass
class PreviewBlock:
    """A single renderable section of a document preview.

    Documents can produce multiple blocks (e.g. a Soul has SOUL.md +
    STYLE.md + soul.json), which the Studio renders stacked.

    ``kind`` is the renderer hint:
      - ``"markdown"`` → MarkdownBlock (prose, headings, lists)
      - ``"code"``     → CodeBlock (yaml, json, plain text in monospace)
      - ``"fields"``   → FieldsBlock (key/value pairs)
      - ``"empty"``    → no body, just the title (used for empty states)
    """

    kind: PreviewBlockKind
    title: str
    body: str | None = None
    language: str | None = None
    fields: list[dict[str, str]] = field(default_factory=list)


def generic_spec_dump(doc: Any) -> list[PreviewBlock]:
    """Last-resort renderer used by ``ManifestInstance.render_doc`` when
    the KindPort doesn't implement ``preview()``. Always returns
    SOMETHING so the Studio never has a blank pane.
    """
    spec = getattr(doc, "spec", None) or {}
    if hasattr(spec, "items"):
        spec_dict = dict(spec)
    else:
        spec_dict = spec if isinstance(spec, dict) else {}
    if not spec_dict:
        return [PreviewBlock(kind="empty", title=f"{doc.kind} (empty spec)")]
    return [
        PreviewBlock(
            kind="code",
            title=f"{doc.kind} spec",
            body=json.dumps(spec_dict, indent=2, default=str),
            language="json",
        )
    ]


def find_consumers(
    instance: "ManifestInstance",
    target: dict[str, str],
) -> list[dict[str, str]]:
    """Walk every document in the manifest and return those that
    reference the given target via a ``KindPort.dep_filters()``
    declaration.

    Uses ``instance.iter_doc_deps(doc)`` — the kernel method that
    dynamically walks ``KindPort.dep_filters()`` for each doc. No
    hardcoded field-to-kind map needed; any extension that declares its
    deps via ``dep_filters`` participates automatically.

    ``target`` is ``{"kind": str, "name": str}``. The return list contains
    dicts of the same shape — one per consumer doc.
    """
    target_kind = target["kind"]
    target_name = target["name"]
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    iter_fn = getattr(instance, "iter_doc_deps", None)
    for doc in instance.documents:
        if doc.kind == target_kind and doc.name == target_name:
            continue
        deps: list[dict[str, Any]] = []
        if callable(iter_fn):
            try:
                deps = iter_fn(doc) or []
            except Exception as e:  # noqa: BLE001
                # fail-soft: read path — a doc whose deps can't be iterated
                # contributes no consumer edges (logged).
                logging.getLogger(__name__).debug(
                    "find_consumers: iter_doc_deps failed for %s/%s: %s",
                    doc.kind, doc.name, e,
                )
                deps = []
        hit = False
        for dep in deps:
            if dep.get("target_kind") != target_kind:
                continue
            if target_name in (dep.get("names") or []):
                hit = True
                break
        key = f"{doc.kind}/{doc.name}"
        if hit and key not in seen:
            seen.add(key)
            out.append({"kind": doc.kind, "name": doc.name})
    return out
