"""Deterministic hash-based embedding — the zero-dependency offline floor.

This is the default ``EmbeddingPort`` the kernel falls back to when no real
provider (e.g. the opt-in ONNX all-MiniLM-L6-v2 adapter) is registered. It is
NOT a semantic embedder — it is a stable, content-addressed vector so the
search plane and its tests have *something* deterministic to run against in CI
and offline, without pulling any ML dependency.

Parity contract (rsh-memory-similarity-evolution → rec-embedding-port): the
TypeScript twin ``src/kernel/embedding.ts`` produces the BIT-IDENTICAL vector
for the same string. That is guaranteed *by construction*, not by luck:

  1. Tokenization is ``[a-z0-9]+`` over the lower-cased text — identical token
     lists in Py (``re.findall``) and TS (``String.match``) for ASCII input.
  2. Each token is hashed with SHA-256 (stdlib ``hashlib`` / ``js-sha256``);
     the first 4 bytes pick a dimension (big-endian uint32 mod ``dims``) and
     the 5th byte's low bit picks a sign (±1). Accumulation is INTEGER, so the
     pre-normalization vector is exact on both sides regardless of order.
  3. L2-normalization divides each integer component by ``sqrt(sum(cᵢ²))``.
     The sum-of-squares is an exact integer; ``sqrt`` and division are both
     IEEE-754 correctly-rounded, so the resulting doubles are bit-identical
     across the two runtimes.

The golden fixture ``tests/parity-fixtures/fake-embedding-golden.json`` pins a
handful of strings to their exact vectors; both language suites assert against
it (see ``tests/test_fake_embedding.py`` / ``tests/fake-embedding.test.ts``).
"""
from __future__ import annotations

import hashlib
import math
import re

# Default dimensionality of the fake space. Matches all-MiniLM-L6-v2 (the real
# ONNX provider) so swapping providers keeps the vector length — and any
# downstream vector-store column width — stable.
FAKE_EMBEDDING_DIMS = 384

# Stable identity of this embedding space. Versioned so a future change to the
# hashing scheme is a NEW space (old vectors stay honestly incomparable).
FAKE_EMBEDDING_MODEL_ID = "dna-fake-hash-v1"

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def fake_embed_one(text: str, dims: int = FAKE_EMBEDDING_DIMS) -> list[float]:
    """Deterministic, L2-normalized hash embedding of a single string.

    Bit-identical to the TS ``fakeEmbedOne``. Empty/tokenless text → all-zeros
    (an all-zero vector is honestly "no signal", never normalized)."""
    counts = [0] * dims
    for token in _TOKEN_RE.findall(text.lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[0:4], "big") % dims
        sign = 1 if (digest[4] & 1) else -1
        counts[idx] += sign
    norm_sq = sum(c * c for c in counts)
    if norm_sq == 0:
        return [0.0] * dims
    norm = math.sqrt(norm_sq)
    return [c / norm for c in counts]


class FakeEmbeddingProvider:
    """Zero-dependency ``EmbeddingPort`` — the offline/CI default.

    Structurally satisfies ``dna.kernel.protocols.EmbeddingPort``
    (``model_id``, ``dims``, async ``embed``)."""

    def __init__(self, dims: int = FAKE_EMBEDDING_DIMS) -> None:
        self.dims = dims
        self.model_id = FAKE_EMBEDDING_MODEL_ID

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [fake_embed_one(t, self.dims) for t in texts]
