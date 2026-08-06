"""CollabExtension — collaboration primitives (Comment Kind).

Comments can be attached to any target instance via `target_ref`.
They enable audit trails, discussions, and status-change history.

The Comment Kind itself is a descriptor: the hand-written ``CommentKind``
class was DELETED — ``kinds/comment.kind.yaml`` is the single source,
registered through the same ``load_descriptors`` funnel every other
extension uses. Equivalence with the extinct class is frozen in
``tests/test_descriptor_pattern_equivalence.py`` (goldens under
``tests/goldens/descriptor_pattern/Comment.golden.json``).
"""
from __future__ import annotations

from dna.kernel.protocols import ExtensionHost
from dna.kernel.source.descriptor_loader import load_descriptors


class CollabExtension:
    """Collaboration primitives — comments, assignments, discussions."""

    name = "collab"
    version = "1.1.0"

    def register(self, kernel: ExtensionHost) -> None:
        for raw in load_descriptors("dna.extensions.collab"):
            kernel.kind_from_descriptor(raw)
