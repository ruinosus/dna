"""Template contract — file-tree scaffolds shipped by Extensions.

Templates let an Extension declare reusable scaffolds for its Kinds.
Files live inside the Extension's Python package (resource-safe), so
they survive pip-install and editable-install equally. Kernel exposes
`list_templates()` + `scaffold()` to discover and materialize them.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

OnConflict = Literal["error", "skip", "overwrite"]


@dataclass(frozen=True)
class Template:
    """A scaffoldable file tree declared by an Extension.

    id               Namespaced identifier: "<extension>/<name>".
    label            Human-friendly name shown in UIs.
    kind             Primary Kind this template scaffolds (may span
                     multiple kinds in the file tree, but this is the
                     headline one for filtering/grouping).
    description      One-line description.
    files_root       Absolute Path to the root of the template tree on
                     disk (resolved via importlib.resources by the
                     Extension).
    owner_extension  Name of the Extension that owns this template.
    post_init_hint   Optional shell/cli snippet shown after scaffold
                     (e.g. "cd .dna/<scope>/programs/research && uv sync").
    upstream_ref     Optional upstream pin (e.g. a git sha of the
                     source repo the template was cloned from).
    """

    id: str
    label: str
    kind: str
    description: str
    files_root: Path
    owner_extension: str
    post_init_hint: str | None = None
    upstream_ref: str | None = None


def materialize(
    template: Template,
    target_root: Path,
    on_conflict: OnConflict = "error",
) -> list[Path]:
    """Copy every file under ``template.files_root`` into ``target_root``.

    Returns the list of written absolute paths. Binary-safe (uses byte
    copy). Preserves relative directory structure.

    on_conflict:
      - ``"error"`` (default): raise ``FileExistsError`` on any existing dest
      - ``"skip"``: leave existing dest files untouched
      - ``"overwrite"``: replace existing dest files
    """
    if on_conflict not in ("error", "skip", "overwrite"):
        raise ValueError(f"unknown on_conflict: {on_conflict!r}")

    if not template.files_root.is_dir():
        raise FileNotFoundError(
            f"template files_root does not exist: {template.files_root}"
        )

    target_root = Path(target_root)
    target_root.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for src in sorted(template.files_root.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(template.files_root)
        dst = target_root / rel
        if dst.exists():
            if on_conflict == "error":
                raise FileExistsError(f"destination exists: {dst}")
            if on_conflict == "skip":
                continue
            # "overwrite" → fall through
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        written.append(dst)
    return written
