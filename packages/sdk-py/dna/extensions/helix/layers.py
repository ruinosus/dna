"""DEPRECATED shim — DefaultLayerResolver moved into the kernel.

Layer resolution is a core kernel responsibility
(s-invert-layer-resolver-dep, 2026-07-07): the kernel must work with
zero extensions loaded, so the resolver now lives at
``dna.kernel.compose.layer_resolver``. This module reexports the old
public names for external importers and warns on import.
"""
from __future__ import annotations

import warnings

from dna.kernel.compose.layer_resolver import (  # noqa: F401
    DefaultLayerResolver,
    _merge_timeline_arrays,
    _stamp_overlay_metadata,
    deep_merge,
)

warnings.warn(
    "dna.extensions.helix.layers is deprecated — import "
    "DefaultLayerResolver/deep_merge from dna.kernel.compose.layer_resolver "
    "instead (s-invert-layer-resolver-dep).",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "DefaultLayerResolver",
    "deep_merge",
    "_merge_timeline_arrays",
    "_stamp_overlay_metadata",
]
