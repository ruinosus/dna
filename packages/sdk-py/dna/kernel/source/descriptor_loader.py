"""F3 (spec D3): builtin Kind descriptors as package data.

Extensions ship builtin record Kinds as ``kinds/*.kind.yaml`` files inside
their package (same KindDefinition format as per-scope KIND.yaml docs —
one format, one funnel). ``load_descriptors`` reads them via
importlib.resources (the same mechanism the doc/gaia/autoagent extensions
use for their template trees — hatchling ships non-py package files by
default, no pyproject change needed) and hands the parsed raws to
``kernel.kind_from_descriptor``.

The descriptor FILES ship as package data inside each extension.
"""
from __future__ import annotations

from importlib.resources import files as _pkg_files
from typing import Any

import yaml

_SUFFIX = ".kind.yaml"


def load_descriptors(package: str) -> list[dict[str, Any]]:
    """Parse every ``kinds/*.kind.yaml`` shipped inside ``package``.

    Parameters
    ----------
    package : str
        Importable package name, e.g. ``"dna.extensions.sdlc"``.

    Returns the raw dicts sorted by filename (deterministic registration
    order). A package without a ``kinds/`` dir returns ``[]`` — extensions
    can call this unconditionally. A descriptor that isn't a YAML mapping
    raises ``ValueError`` (a broken packaged descriptor is a packaging bug,
    never a silent skip).
    """
    kinds_dir = _pkg_files(package) / "kinds"
    try:
        entries = list(kinds_dir.iterdir())
    except (FileNotFoundError, NotADirectoryError):
        return []

    raws: list[dict[str, Any]] = []
    for entry in sorted(entries, key=lambda e: e.name):
        if not entry.name.endswith(_SUFFIX):
            continue
        raw = yaml.safe_load(entry.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(
                f"descriptor {package}/kinds/{entry.name} must be a YAML "
                f"mapping (KindDefinition), got {type(raw).__name__}"
            )
        raws.append(raw)
    return raws
