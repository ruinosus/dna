"""DEPRECATED shim — import from ``dna.kernel.composition_resolver``.

The CompositionProfile (V1) types moved into the unified composition
motor (s-unify-composition-subsystems); this module remains only so
external callers keep importing. It will be removed in a future major.
"""
from __future__ import annotations

import warnings

from dna.kernel.composition_resolver import (  # noqa: F401
    CompositionProfile,
    CompositionSlot,
    HealthCheckHint,
    QuadrantHint,
    TimelineHint,
    profile_for_orchestrator,
)

warnings.warn(
    "dna.kernel.composition is deprecated — import CompositionProfile "
    "et al. from dna.kernel.composition_resolver "
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
