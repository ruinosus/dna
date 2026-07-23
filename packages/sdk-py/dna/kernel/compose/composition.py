"""DEPRECATED shim — import from ``dna.kernel.compose.resolver``.

The CompositionProfile (V1) types moved into the unified composition
motor (s-unify-composition-subsystems); this module remains only so
external callers keep importing. It will be removed in a future major.
"""
from __future__ import annotations

import warnings

from dna.kernel.compose.resolver import (  # noqa: F401
    CompositionProfile,
    CompositionSlot,
    HealthCheckHint,
    QuadrantHint,
    TimelineHint,
    profile_for_orchestrator,
)

warnings.warn(
    "dna.kernel.compose.composition is deprecated — import CompositionProfile "
    "et al. from dna.kernel.compose.resolver "
    "(s-unify-composition-subsystems).",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "CompositionProfile",
    "CompositionSlot",
    "HealthCheckHint",
    "QuadrantHint",
    "TimelineHint",
    "profile_for_orchestrator",
]
