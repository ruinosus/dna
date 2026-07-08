"""Kind-Writer contract validation at ``Kernel.write_document`` (Task 2 of
the Kind-Writer pilot, feat/kind-writer-pilot).

A Agent that declares ``writes_kind`` is a "Kind-Writer" — it emits a
structured document of the target Kind. The contract is validated at write
time (fail early) rather than at runtime:

- ``writes_kind`` must point at a Kind that HAS a schema (registered KindPort
  whose ``.schema()`` returns a dict). Schema-less / unknown → reject.
- every ``creative_slots`` name must be a property in the schema.
- every ``required`` schema field must be covered by
  ``creative_slots ∪ system_slots.keys()`` — an uncovered required field is
  rejected with an "unmapped" message.

StatusReport (sdlc extension) is the schema-bearing fixture Kind:
required = [insight, verdict, confidence].
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel
from dna.extensions.helix import HelixExtension
from dna.extensions.sdlc import SdlcExtension
from tests.test_kernel_invalidate_modes import _FakeWritableSource


def _kernel() -> Kernel:
    """Kernel with the sdlc extension loaded (registers StatusReport) and a
    duck-typed writable source so the write reaches the validation hook and,
    on the positive path, completes. s-write-path-despecialize — the
    Kind-Writer contract is a pre_save veto hook registered by the Helix
    extension (the Agent owner), so it is loaded too."""
    k = Kernel()
    k.load(HelixExtension())
    k.load(SdlcExtension())
    k.source(_FakeWritableSource())
    return k


def _ua_raw(spec: dict) -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "kw-smoke"},
        "spec": {"instruction": "do the thing", **spec},
    }


@pytest.mark.asyncio
async def test_writes_kind_unknown_or_schemaless_raises():
    """writes_kind pointing at a Kind without a schema (here: unregistered)
    → reject, message mentions schema."""
    k = _kernel()
    raw = _ua_raw({"writes_kind": "NoSuchKind", "creative_slots": ["x"]})
    with pytest.raises(ValueError) as exc:
        await k.write_document("scope-x", "Agent", "kw-smoke", raw)
    assert "schema" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_creative_slot_not_a_property_raises():
    """A creative_slots name absent from schema.properties → reject."""
    k = _kernel()
    raw = _ua_raw({
        "writes_kind": "StatusReport",
        "creative_slots": ["not_a_real_field"],
        "system_slots": {"insight": "input.x", "confidence": "input.y"},
    })
    with pytest.raises(ValueError) as exc:
        await k.write_document("scope-x", "Agent", "kw-smoke", raw)
    assert "not_a_real_field" in str(exc.value)


@pytest.mark.asyncio
async def test_required_field_unmapped_raises():
    """A required StatusReport field (verdict) covered by neither
    creative_slots nor system_slots → reject with 'unmapped'."""
    k = _kernel()
    raw = _ua_raw({
        "writes_kind": "StatusReport",
        # verdict is required but mapped nowhere; insight+confidence covered.
        "creative_slots": [],
        "system_slots": {"insight": "input.x", "confidence": "input.y"},
    })
    with pytest.raises(ValueError) as exc:
        await k.write_document("scope-x", "Agent", "kw-smoke", raw)
    msg = str(exc.value).lower()
    assert "unmapped" in msg
    assert "verdict" in msg


@pytest.mark.asyncio
async def test_valid_kind_writer_does_not_raise():
    """All required fields covered (verdict via creative_slots, insight +
    confidence via system_slots) and every creative slot is a real property
    → write proceeds (no validation error)."""
    k = _kernel()
    raw = _ua_raw({
        "writes_kind": "StatusReport",
        "creative_slots": ["verdict"],
        "system_slots": {"insight": "input.oracle_id", "confidence": "input.conf"},
    })
    # Must NOT raise the Kind-Writer ValueError. Other downstream errors are
    # unrelated; the contract validation is what we assert here.
    await k.write_document("scope-x", "Agent", "kw-smoke", raw)


@pytest.mark.asyncio
async def test_non_kind_writer_ua_untouched():
    """A plain Agent (no writes_kind) skips the validation entirely."""
    k = _kernel()
    raw = _ua_raw({})  # no writes_kind
    await k.write_document("scope-x", "Agent", "kw-smoke", raw)
