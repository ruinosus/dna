"""Tests for ``Kernel._REMOVED_KINDS`` write guard.

Phase 1B (squishy-jumping-nebula) — verifies that Kinds retired by past
refactors raise ``KindRetiredError`` on write attempts, with a message
pointing at the migration notes. Reads of legacy docs (if any survived)
remain readable via the graceful ``_parse_doc`` fallback (returns
``typed=None``); they're only blocked on write.

Covers: OracleVerdict + Oracle (the 2 entries as of 2026-05-16).
"""
from __future__ import annotations

from unittest.mock import MagicMock, AsyncMock

import pytest

from dna.kernel import Kernel, KindRetiredError


def _bare_kernel() -> Kernel:
    src = MagicMock()
    src.write_doc = AsyncMock(return_value=[])
    src.delete_doc = AsyncMock()
    k = Kernel()
    k.source(src)
    return k


@pytest.mark.asyncio
async def test_write_oracle_verdict_raises_kind_retired():
    k = _bare_kernel()
    raw = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
        "kind": "OracleVerdict",
        "metadata": {"name": "verdict-smoke"},
        "spec": {"oracle": "tactical"},
    }
    with pytest.raises(KindRetiredError) as exc:
        await k.write_document("scope-x", "OracleVerdict", "verdict-smoke", raw)
    assert "OracleVerdict" in str(exc.value)
    assert "_REMOVED_KINDS" in str(exc.value)


@pytest.mark.asyncio
async def test_write_oracle_kind_raises_kind_retired():
    k = _bare_kernel()
    raw = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
        "kind": "Oracle",
        "metadata": {"name": "tactical"},
        "spec": {},
    }
    with pytest.raises(KindRetiredError):
        await k.write_document("scope-x", "Oracle", "tactical", raw)


def test_removed_kinds_set_is_frozenset():
    # Tamper-resistant — frozenset blocks mutation at runtime.
    assert isinstance(Kernel._REMOVED_KINDS, frozenset)
    assert "OracleVerdict" in Kernel._REMOVED_KINDS
    assert "Oracle" in Kernel._REMOVED_KINDS


@pytest.mark.asyncio
async def test_live_kind_still_writable():
    """Guard is targeted — non-retired Kinds untouched."""
    k = _bare_kernel()
    raw = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
        "kind": "LessonLearned",
        "metadata": {"name": "rem-smoke"},
        "spec": {"area": "x", "summary": "y"},
    }
    # Should NOT raise KindRetiredError. (Other errors may fire — we
    # don't care here; just asserting the retirement guard skips this.)
    try:
        await k.write_document("scope-x", "LessonLearned", "rem-smoke", raw)
    except KindRetiredError:
        pytest.fail("LessonLearned is live; must not trip _REMOVED_KINDS guard")
    except Exception:
        pass  # any other failure is unrelated to the guard
