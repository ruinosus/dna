"""Real ``EmbeddingPort`` adapters (opt-in extras).

Nothing here is imported by the default SDK — importing ``dna`` or booting a
kernel must never pull ONNX/torch/fastembed (guard:
``tests/test_embedding_import_isolation.py``). Install the extra and import the
adapter explicitly to register a real provider:

    pip install "dna-sdk[embed-onnx]"
    from dna.adapters.embedding.onnx import OnnxEmbeddingProvider
    kernel.embedding_provider(OnnxEmbeddingProvider())
"""
