"""F3 D3: funil builtin + conflito unificado + idempotência forte + lint.

Spec: docs/superpowers/specs/2026-06-10-kinds-descriptor-f3-design.md (D3).
"""
import pytest

from dna.kernel import Kernel, KindRegistrationError
from test_kinddef_f3_fields import RAW_FULL


def test_kind_from_descriptor_registers_with_builtin_marker():
    k = Kernel()
    port = k.kind_from_descriptor(RAW_FULL)
    assert getattr(port, "__builtin_descriptor__", False) is True
    assert getattr(port, "__declarative__", False) is True
    assert k.kind_port_for("KaizenLike") is port


def test_kind_from_descriptor_stamps_digest():
    """Digest = sha256 do json canônico do spec — MESMA receita do
    sync/hash.py:document_hash (e do documentHash TS), pinada aqui pra
    paridade cross-runtime."""
    import hashlib
    import json

    k = Kernel()
    port = k.kind_from_descriptor(RAW_FULL)
    expected = hashlib.sha256(
        json.dumps(RAW_FULL["spec"], sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    assert port.__descriptor_digest__ == expected


def test_perscope_kinddef_loses_to_builtin_with_warning():
    """Conflito: per-scope no mesmo (apiVersion, kind) que um builtin →
    SKIP com warning + evento kinddef_conflict (não silencioso, não overwrite)."""
    k = Kernel()
    builtin = k.kind_from_descriptor(RAW_FULL)
    events = []
    k.on("kinddef_conflict", lambda ctx: events.append(ctx))
    # per-scope chega via _register_kind_definitions (fase 1 do load)
    perscope_raw = {**RAW_FULL, "metadata": {"name": "kz-override"}}
    k._register_kind_definitions([perscope_raw])
    assert k.kind_port_for("KaizenLike") is builtin  # builtin venceu
    assert k.kind_port_for("KaizenLike").__builtin_descriptor__ is True
    # NOTA: o warn existente é gated process-wide (_GLOBAL_KINDDEF_CONFLICT_WARNED)
    # → o assert ROBUSTO é o evento (não-gated); caplog seria best-effort:
    # evento emitido (mesmo contrato do conflito com extension-class)
    assert len(events) == 1


def test_idempotent_same_descriptor_reregister_is_noop():
    k = Kernel()
    first = k.kind_from_descriptor(RAW_FULL)
    again = k.kind_from_descriptor(RAW_FULL)  # mesmo digest → no-op, sem raise
    assert again is first  # devolve o port já registrado


def test_different_descriptor_same_key_raises():
    k = Kernel()
    k.kind_from_descriptor(RAW_FULL)
    other = {**RAW_FULL, "spec": {**RAW_FULL["spec"], "alias": "test-other-alias"}}
    with pytest.raises(KindRegistrationError):
        k.kind_from_descriptor(other)


def test_plane_lint_applies_to_descriptor_funnels():
    k = Kernel()
    bad = {**RAW_FULL, "spec": {**RAW_FULL["spec"], "plane": "record", "prompt_target": True}}
    with pytest.raises(KindRegistrationError, match="plane"):
        k.kind_from_descriptor(bad)
    # e no funil per-scope: NÃO registra + warning (per-scope nunca derruba o boot)
    k2 = Kernel()
    k2._register_kind_definitions([bad])
    assert k2.kind_port_for("KaizenLike") is None


# --- F3 D4: embeddability derivation ----------------------------------------

def test_kernel_embeddable_kinds_derives_from_embed_fields():
    """D4: kernel.embeddable_kinds() = kinds whose port declares embed_fields
    (descriptor `embed:` OR class-level `embed_fields`). RAW_FULL declares
    embed: [body, labels]."""
    k = Kernel()
    k.kind_from_descriptor(RAW_FULL)
    assert k.embeddable_kinds() == frozenset({"KaizenLike"})


def test_kernel_embeddable_kinds_empty_without_declarations():
    assert Kernel().embeddable_kinds() == frozenset()


def test_kernel_embeddable_kinds_sees_class_declared_fields():
    """KindBase.embed_fields (the parity hook for not-yet-migrated classes)
    must feed the same derivation."""
    from dna.kernel.kinds.base import KindBase
    from dna.kernel.protocols import StorageDescriptor

    class _EmbCls(KindBase):
        api_version = "test.io/v1"
        kind = "Emb"
        alias = "test-emb"
        storage = StorageDescriptor.yaml("embs")
        plane = "record"
        embed_fields = ["title"]

    k = Kernel()
    k.kind(_EmbCls())
    assert "Emb" in k.embeddable_kinds()
