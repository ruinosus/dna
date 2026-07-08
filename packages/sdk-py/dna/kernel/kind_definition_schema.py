"""Published JSON Schema for the KindDefinition descriptor format.

s-dna-kindport-descriptor-schema: the `.kind.yaml` / per-scope KIND.yaml
shape used to be validated ONLY by the hand-rolled checks in
``models.KindDefinitionSpec.from_raw`` — no machine-readable contract a
contributor could point an editor at. The contract is now a draft
2020-12 JSON Schema:

- canonical published copy: ``docs/schemas/kind-definition.schema.json``
  (referenced by docs/KIND-AUTHORING.md; yaml-language-server can
  autocomplete/validate descriptors against it);
- byte-identical runtime copy: ``dna/kernel/schemas/
  kind-definition.schema.json`` (package data, loaded here) —
  ``tests/test_kind_definition_schema.py`` enforces the identity.

``TypedKindDefinition.from_raw`` runs the hand-rolled checks FIRST
(didactic messages) and then :func:`validate_kind_definition` as the
backstop — typo'd/unknown spec fields and wrong types that the
hand-rolled checks silently ignored now fail loudly. Registration
funnels keep their existing error contracts: builtin descriptors raise
at boot; per-scope KindDefinitions warn + skip (never take a boot down).

TS twin: the Zod ``KindDefinitionSpecSchema`` (models.ts) IS the TS
runtime validation; ``kind-definition-schema.test.ts`` locks the Zod
key set against this schema so the two can't drift.
"""
from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files as _pkg_files
from typing import Any

_SCHEMA_FILENAME = "kind-definition.schema.json"


@lru_cache(maxsize=1)
def kind_definition_schema() -> dict[str, Any]:
    """The packaged KindDefinition JSON Schema (draft 2020-12)."""
    text = (
        _pkg_files("dna.kernel") / "schemas" / _SCHEMA_FILENAME
    ).read_text(encoding="utf-8")
    return json.loads(text)


@lru_cache(maxsize=1)
def _validator():
    import jsonschema  # core dep (pyproject: jsonschema>=4.0)

    schema = kind_definition_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def validate_kind_definition(raw: dict[str, Any]) -> None:
    """Validate a full KindDefinition envelope against the published schema.

    Raises ``ValueError`` (the same error family as the hand-rolled
    ``from_raw`` checks, so every existing catch site keeps working)
    with the first — most specific — schema violation and its JSON path.
    """
    errors = sorted(
        _validator().iter_errors(raw),
        key=lambda e: (-len(e.absolute_path), list(map(str, e.absolute_path))),
    )
    if not errors:
        return
    err = errors[0]
    path = "$" + "".join(
        f"[{p}]" if isinstance(p, int) else f".{p}" for p in err.absolute_path
    )
    raise ValueError(
        f"KindDefinition does not match the published descriptor schema "
        f"(docs/schemas/kind-definition.schema.json) at {path}: {err.message}"
    )
