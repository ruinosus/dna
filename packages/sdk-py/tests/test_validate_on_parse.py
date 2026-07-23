"""s-typed-models-for-dict-kinds — KindBase.validate_on_parse + enabled Kinds.

parse() validates a doc's spec against schema() when the Kind opts in. Specs are
passed FLAT here (the raw IS the spec) — _validate_spec accepts both flat and
enveloped shapes (gaia pattern).
"""
from __future__ import annotations

import jsonschema
import pytest

from dna.kernel import Kernel
from dna.kernel.kinds.base import KindBase
from dna.kernel.protocols import StorageDescriptor


class _Validated(KindBase):
    api_version = "x/v1"; kind = "Validated"; alias = "x-validated"
    storage = StorageDescriptor.yaml("validateds")
    validate_on_parse = True
    def schema(self):
        return {"type": "object", "required": ["name"],
                "properties": {"name": {"type": "string"}, "n": {"type": ["number", "null"]}}}


def test_valid_spec_parses_nullable_ok():
    k = _Validated()
    assert k.parse({"name": "ok", "n": None}) is not None
    assert k.parse({"name": "ok", "n": 3}) is not None
    # enveloped shape also accepted (validates raw['spec'])
    assert k.parse({"apiVersion": "x/v1", "kind": "Validated", "spec": {"name": "ok"}}) is not None


def test_invalid_spec_raises_clear_error():
    k = _Validated()
    with pytest.raises(jsonschema.ValidationError):
        k.parse({})  # missing required name
    with pytest.raises(jsonschema.ValidationError):
        k.parse({"name": 1})  # wrong type


def test_optout_kind_does_not_validate():
    class _Bare(KindBase):
        api_version = "x/v1"; kind = "Bare"; alias = "x-bare"
        storage = StorageDescriptor.yaml("bares")
        def schema(self): return {"type": "object", "required": ["name"]}
    assert _Bare().parse({}) is not None  # no raise (opt-out)


# Kinds still implemented as classes with validate_on_parse=True.
ENABLED_CLASS: list[str] = []

# F3 lote-3: Finding/EvalRun/Job/Evidence viraram descriptors — o port
# sintetizado valida POR CONSTRUÇÃO quando há schema (não existe o knob
# validate_on_parse), opera sobre o ENVELOPE e levanta ValueError claro
# (no kernel: typed=None + evento parse_error, nunca crash). expr batch A:
# EvalExperiment + AuditLog juntaram-se a este conjunto. expr batch B (Chunk
# 4): AgentExperiment (era validate_on_parse=True na classe extinta) migrou
# para descriptor — agora valida por construção.
ENABLED_DESCRIPTOR = ["Evidence", "AuditLog"]


@pytest.mark.parametrize("kind_name", ENABLED_CLASS)
def test_runtime_kind_opts_in_and_rejects_malformed(kind_name):
    kp = {getattr(k, "kind", None): k for k in Kernel.auto()._kinds.values()}[kind_name]
    assert getattr(kp, "validate_on_parse", False) is True
    schema = kp.schema()
    if schema and schema.get("required"):
        # an empty spec is missing required fields → clear rejection
        with pytest.raises(jsonschema.ValidationError):
            kp.parse({})


@pytest.mark.parametrize("kind_name", ENABLED_DESCRIPTOR)
def test_descriptor_kind_validates_by_construction(kind_name):
    kp = {getattr(k, "kind", None): k for k in Kernel.auto()._kinds.values()}[kind_name]
    assert getattr(kp, "__builtin_descriptor__", False) is True
    schema = kp.schema()
    assert schema and schema.get("required")
    # an envelope with an empty spec is missing required fields → ValueError
    with pytest.raises(ValueError):
        kp.parse({"apiVersion": kp.api_version, "kind": kind_name,
                  "metadata": {"name": "x"}, "spec": {}})


