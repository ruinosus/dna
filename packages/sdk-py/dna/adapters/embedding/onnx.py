"""ONNX all-MiniLM-L6-v2 embedding provider (opt-in ``embed-onnx`` extra).

The REAL embedder (rec-embedding-port): the same ``sentence-transformers/
all-MiniLM-L6-v2`` ONNX artifact run by ``fastembed`` (Py) and
``@huggingface/transformers`` (TS) — parity by artifact, not reimplementation.
Cosine ≈ 1 across the two runtimes (see ``tests/test_embedding_onnx_parity.py``,
which is network-gated and skips offline).

Lazy-download + cache, the Chroma pattern: the model is a downloaded artifact,
never an install-time dependency. ``fastembed`` fetches and caches the ONNX on
the FIRST ``embed`` call, not at import — so importing this module (with the
extra installed) still costs nothing until you actually embed.
"""
from __future__ import annotations

# Same model + vector width as the TS twin (src/adapters/embedding/onnx.ts) and
# the fake floor (FAKE_EMBEDDING_DIMS) so providers are swap-compatible.
ONNX_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
ONNX_DIMS = 384


class OnnxEmbeddingProvider:
    """``EmbeddingPort`` backed by fastembed's ONNX runtime.

    Structurally satisfies ``dna.kernel.protocols.EmbeddingPort``. The heavy
    import (``fastembed``, which drags ``onnxruntime``) is deferred to first
    use so merely importing this module never pulls ML deps into a process
    that does not embed."""

    def __init__(self, model_id: str = ONNX_MODEL_ID, dims: int = ONNX_DIMS) -> None:
        self.model_id = model_id
        self.dims = dims
        self._model = None  # lazily constructed on first embed()

    def _ensure_model(self):
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:  # pragma: no cover - exercised via extra
                raise ImportError(
                    "OnnxEmbeddingProvider needs the 'embed-onnx' extra: "
                    "pip install 'dna-sdk[embed-onnx]'"
                ) from exc
            # Downloads + caches the ONNX artifact on first construction.
            self._model = TextEmbedding(model_name=self.model_id)
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._ensure_model()
        # fastembed yields L2-normalized mean-pooled sentence vectors (same
        # recipe transformers.js uses with pooling='mean', normalize=true).
        return [list(map(float, vec)) for vec in model.embed(list(texts))]
