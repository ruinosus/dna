"""rec-embedding-port — the deterministic zero-dep fake floor + kernel facade.

The FAKE is the offline/CI default ``EmbeddingPort``: a stable, content-addressed
vector so the search plane has *something* deterministic to run against without
any ML dependency. Its defining property is BIT-EXACT Py↔TS parity — enforced
here (and in the TS twin ``tests/fake-embedding.test.ts``) against the shared
golden ``tests/parity-fixtures/fake-embedding-golden.json``.
"""
from __future__ import annotations

import json
import math
import pathlib

import pytest

from dna.kernel import Kernel
from dna.kernel.embedding import (
    FAKE_EMBEDDING_DIMS,
    FAKE_EMBEDDING_MODEL_ID,
    FakeEmbeddingProvider,
    fake_embed_one,
)
from dna.kernel.protocols import EmbeddingPort

_GOLDEN = (
    pathlib.Path(__file__).resolve().parents[3]
    / "tests" / "parity-fixtures" / "fake-embedding-golden.json"
)


def _load_golden() -> dict:
    return json.loads(_GOLDEN.read_text())


def test_fake_provider_satisfies_embedding_port():
    prov = FakeEmbeddingProvider()
    assert isinstance(prov, EmbeddingPort)  # runtime_checkable structural match
    assert prov.model_id == FAKE_EMBEDDING_MODEL_ID
    assert prov.dims == FAKE_EMBEDDING_DIMS


def test_fake_is_deterministic_and_normalized():
    a = fake_embed_one("the quick brown fox")
    b = fake_embed_one("the quick brown fox")
    assert a == b, "same input must give the identical vector"
    assert len(a) == FAKE_EMBEDDING_DIMS
    norm = math.sqrt(sum(x * x for x in a))
    assert norm == pytest.approx(1.0, abs=1e-12), "non-empty text → unit vector"


def test_fake_tokenizes_lowercase_alnum():
    # Case + punctuation are normalized away by the [a-z0-9]+ tokenizer.
    assert fake_embed_one("Hello, WORLD!") == fake_embed_one("hello world")


def test_fake_empty_text_is_all_zeros():
    v = fake_embed_one("")
    assert v == [0.0] * FAKE_EMBEDDING_DIMS
    # tokenless punctuation collapses to the same honest zero vector.
    assert fake_embed_one("!!!  ...") == [0.0] * FAKE_EMBEDDING_DIMS


def test_fake_matches_golden_exactly():
    """BIT-EXACT parity: the fake reproduces the shared golden vectors — the
    same fixture the TS suite asserts against. Any drift here or in TS turns a
    suite red (the golden is regenerated only on an intentional scheme bump,
    which is a new model_id)."""
    golden = _load_golden()
    assert golden["model_id"] == FAKE_EMBEDDING_MODEL_ID
    assert golden["dims"] == FAKE_EMBEDDING_DIMS
    for text, expected in golden["vectors"].items():
        actual = fake_embed_one(text)
        assert actual == expected, f"fake vector drifted from golden for {text!r}"


@pytest.mark.asyncio
async def test_fake_provider_embed_batch_order():
    prov = FakeEmbeddingProvider()
    texts = ["alpha", "beta", "gamma"]
    out = await prov.embed(texts)
    assert out == [fake_embed_one(t) for t in texts]
    assert await prov.embed([]) == []


@pytest.mark.asyncio
async def test_kernel_embed_uses_fake_floor_by_default():
    """No provider registered → kernel.embed uses the fake floor; the surface
    (embed / embedding_dims / embedding_model_id) reports the fake space."""
    k = Kernel()
    assert k.embedding_model_id == FAKE_EMBEDDING_MODEL_ID
    assert k.embedding_dims == FAKE_EMBEDDING_DIMS
    out = await k.embed(["the quick brown fox"])
    assert out == [fake_embed_one("the quick brown fox")]
    assert await k.embed([]) == []


@pytest.mark.asyncio
async def test_kernel_embed_uses_registered_provider():
    """A registered provider replaces the fake floor (boot-time wiring)."""

    class StubProvider:
        model_id = "stub-v1"
        dims = 2

        async def embed(self, texts):
            return [[float(len(t)), 0.0] for t in texts]

    k = Kernel()
    k.embedding_provider(StubProvider())
    assert k.embedding_model_id == "stub-v1"
    assert k.embedding_dims == 2
    assert await k.embed(["abc"]) == [[3.0, 0.0]]


@pytest.mark.asyncio
async def test_with_tenant_shares_embedding_provider():
    """with_tenant shallow copies share the registered provider (boot-time
    wiring), same as the search provider."""

    class StubProvider:
        model_id = "stub-v1"
        dims = 1

        async def embed(self, texts):
            return [[1.0] for _ in texts]

    k = Kernel(tenant="acme")
    k.embedding_provider(StubProvider())
    scoped = k.with_tenant("other")
    assert scoped.embedding_model_id == "stub-v1"
    assert await scoped.embed(["x"]) == [[1.0]]
