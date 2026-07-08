"""CollabExtension — collaboration primitives (Comment Kind).

Comments can be attached to any target document via `target_ref`.
They enable audit trails, discussions, and status-change history.
"""
from __future__ import annotations
from typing import Any
from dna.kernel.protocols import ExtensionHost, StorageDescriptor
from dna.kernel.kind_base import KindBase


class CommentKind(KindBase):
    """Comment — a remark or status change attached to any document."""

    api_version = "github.com/ruinosus/dna/collab/v1"
    kind = "Comment"
    alias = "collab-comment"
    model = dict
    origin = "github.com/ruinosus/dna/collab"
    storage = StorageDescriptor.yaml("comments")
    graph_style = {"fill": "#F59E0B", "stroke": "#D97706", "text_color": "#fff"}
    ascii_icon = "💬"
    display_label = "Comments"
    is_prompt_target = False
    flatten_in_context = False
    prompt_target_priority = 0
    docs = ""

    def dep_filters(self) -> dict[str, str]:
        # Comment can point to ANY kind via target_ref — no typed dep filter
        # because target can be Finding, EvalCase, Agent, etc.
        return {}

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["target_ref", "author", "body", "type", "created_at"],
            "properties": {
                "target_ref": {"type": "string", "description": "Kind:name of the target document"},
                "author": {"type": "string"},
                "body": {"type": "string"},
                "type": {
                    "type": "string",
                    "enum": ["note", "status_change", "assignment", "system"],
                    "default": "note",
                },
                "created_at": {"type": "string", "format": "date-time"},
                # Fields when type=status_change:
                "from_status": {"type": "string"},
                "to_status": {"type": "string"},
                # Fields when type=assignment:
                "assignee": {"type": "string"},
                # Edits/attachments (future):
                "edited_at": {"type": "string"},
                "attachments": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": True,
        }

    def summary(self, doc: Any) -> dict[str, Any]:
        spec = doc.spec if hasattr(doc, "spec") else doc
        s = spec if isinstance(spec, dict) else {}
        body = s.get("body", "")
        return {
            "target_ref": s.get("target_ref", ""),
            "author": s.get("author", ""),
            "type": s.get("type", "note"),
            "body_preview": body[:80] if body else "",
        }


class CollabExtension:
    """Collaboration primitives — comments, assignments, discussions."""

    name = "collab"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        kernel.kind(CommentKind())
