"""rec-embedding-port — ONNX all-MiniLM-L6-v2 golden vectors.

The real embedder is an ARTIFACT contract: `fastembed` runs the all-MiniLM-L6-v2
ONNX, and a given sentence must keep embedding to the same point in vector
space. The golden ``tests/golden-fixtures/onnx-embedding-golden.json`` pins
those vectors, so a model swap, a version bump, or a pooling/normalization
change in the adapter shows up as a cosine drop instead of as silently
degraded recall in production.

This test is DOUBLE-gated so it never runs in offline CI:
  - ``@pytest.mark.requires_network`` (auto-skips when DNA_OFFLINE=1 — the CI
    default — or with no outbound network); and
  - ``importorskip('fastembed')`` (the opt-in ``embed-onnx`` extra).

History: the same golden also gated a TypeScript transformers.js twin
(cross-language cosine measured at 1.000000). The TypeScript SDK was frozen
(tag ``sdk-ts-final``); the Python-side artifact lock is unaffected.
"""
from __future__ import annotations

import json
import math
import pathlib

import pytest

pytestmark = pytest.mark.requires_network

_GOLDEN = (
    pathlib.Path(__file__).resolve().parents[3]
    / "tests" / "golden-fixtures" / "onnx-embedding-golden.json"
)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb)


@pytest.mark.asyncio
async def test_onnx_embed_matches_golden():
    pytest.importorskip("fastembed", reason="`embed-onnx` extra not installed")
    from dna.adapters.embedding.onnx import ONNX_DIMS, OnnxEmbeddingProvider

    golden = json.loads(_GOLDEN.read_text())
    prov = OnnxEmbeddingProvider()
    assert prov.dims == ONNX_DIMS == golden["dims"]

    vecs = await prov.embed(golden["sentences"])
    assert len(vecs) == len(golden["sentences"])
    for vec, ref in zip(vecs, golden["vectors"]):
        assert len(vec) == ONNX_DIMS
        # L2-normalized sentence vectors.
        assert math.sqrt(sum(x * x for x in vec)) == pytest.approx(1.0, abs=1e-3)
        # Parity-by-artifact: the SAME ONNX model → the golden vector.
        assert _cosine(vec, ref) >= 0.99
