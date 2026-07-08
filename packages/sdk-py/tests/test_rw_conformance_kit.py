"""s-dna-rw-roundtrip-suite — the public RW kit × every registered pair.

Consumes the public kit (``dna.testing``) — the same suite an
external Reader/Writer author runs — against the FULL ``Kernel.auto()``
registration (every extension's readers/writers plus the auto-generated
generic pairs), and against the REAL market bundles in
``scopes/market-integration`` (marketplace Skills, the brad soul,
AGENTS.md) so the fixpoint invariant is exercised on artifacts we did
not author.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dna.kernel import Kernel
from dna.testing import (
    CaseNotApplicable,
    reader_writer_conformance_suite,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MARKET_SCOPE = REPO_ROOT / "scopes" / "market-integration" / ".dna" / "market-demo"

CASES = reader_writer_conformance_suite(
    Kernel.auto,
    real_bundle_roots=[MARKET_SCOPE] if MARKET_SCOPE.is_dir() else None,
)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_rw_conformance(case):
    try:
        case.run()
    except CaseNotApplicable as skip:
        pytest.skip(str(skip))
