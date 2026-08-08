"""s-indice-por-dimensao — the routing, and the four mutants it must kill.

These run OFFLINE (no Postgres, default CI job) on purpose. The behavioural
half lives in ``test_migration_0013_dimensao.py`` and
``test_pgvector_search_conformance.py``, both gated on a real database — but a
guard that only runs in the ``postgres`` job is a guard that is absent from most
runs, and the property being defended (*"data-access code never runs DDL"*) is a
property of the SOURCE, readable without a database.

The four things that must not go wrong, and where each is planted:

===================================================  ========================
mutant                                                killed by
===================================================  ========================
routing ignores ``dims`` and mixes spaces              ``test_routing_*`` here
                                                       + the pg behaviour test
a different ``model_id`` is mixed in                   the pg behaviour test;
                                                       here, the source guard
                                                       that every predicate
                                                       carries ``model_id``
an unseen dimension creates a table                    ``test_unsupported_*``
DDL runs outside a migration                           ``test_provider_source_
                                                       contains_no_ddl``
===================================================  ========================

⚠️ The source-reading guards read STRING LITERALS via ``ast``, not the file's
text. A grep would trip on the module docstring — which quotes ``CREATE TABLE``
precisely to explain why there isn't one — and a guard that has to be weakened
to stop crying wolf is a guard nobody trusts. SQL lives in string literals; the
AST is where they are, unambiguously.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

from dna.adapters.search.dimensions import (
    SUPPORTED_DIMS, TABLE_PREFIX, UnsupportedEmbeddingDims, search_table,
)

_SDK = pathlib.Path(__file__).resolve().parents[1] / "dna"
_PGVECTOR = _SDK / "adapters" / "search" / "pgvector.py"
_MIGRATION = (
    _SDK / "adapters" / "sqlalchemy_" / "alembic" / "versions"
    / "0013_uma_tabela_por_dimensao.py"
)


def _string_literals(path: pathlib.Path) -> list[str]:
    """Every string literal in a module EXCEPT docstrings — f-strings included.

    Docstrings are prose about the code; the guards below are about what the
    code SAYS TO THE DATABASE. Conflating the two is what makes source guards
    noisy enough to get deleted.

    ⚠️ The f-string half is not a detail, it is the whole thing: **every routed
    statement in this provider is an f-string** (the table and schema are
    interpolated, they cannot be bind parameters). A first version of this
    helper collected only ``ast.Constant`` and came back with an empty list —
    green, and measuring nothing. ``JoinedStr`` is rendered back with
    ``ast.unparse`` so ``{table}`` survives as text, and its ``Constant``
    children are excluded so a statement is not counted twice in pieces.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", None) or []
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                skip.add(id(body[0].value))
        if isinstance(node, ast.JoinedStr):
            for child in ast.walk(node):
                if child is not node:
                    skip.add(id(child))

    out: list[str] = []
    for node in ast.walk(tree):
        if id(node) in skip:
            continue
        if isinstance(node, ast.JoinedStr):
            out.append(ast.unparse(node))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
    return out


# ---------------------------------------------------------------------------
# routing — dims decides the table, and nothing else does
# ---------------------------------------------------------------------------

def test_routing_gives_each_supported_width_its_own_table():
    tables = {d: search_table(d) for d in SUPPORTED_DIMS}
    assert len(set(tables.values())) == len(SUPPORTED_DIMS), (
        "two widths sharing a table is the mixing this story exists to stop: "
        f"{tables}"
    )
    for dims, table in tables.items():
        assert table == f"{TABLE_PREFIX}{dims}"


def test_routing_reads_dims_and_never_the_model_name():
    """⛔ No heuristic, no config, no looking at the model's name.

    Two providers with the SAME width and wildly different names route to the
    SAME table — the width is the only input. (They are then kept apart by the
    ``model_id`` FILTER, not by the table; see the pg behaviour test.)
    """
    assert search_table(1536) == search_table(1536)
    for name_shaped_number in ("1536", "text-embedding-3-small"):
        # There is no overload taking a name: the only door is an int width.
        with pytest.raises((TypeError, UnsupportedEmbeddingDims, ValueError)):
            search_table(name_shaped_number)  # type: ignore[arg-type]


@pytest.mark.parametrize("dims", [1, 100, 383, 385, 512, 2048, 4096, 0, -384])
def test_unsupported_width_fails_loud_and_names_the_migration(dims):
    """⭐ An unseen dimension fails HIGH and points at the missing migration —
    it never creates a table, and never degrades to a neighbouring width."""
    with pytest.raises(UnsupportedEmbeddingDims) as exc:
        search_table(dims)
    message = str(exc.value)
    assert "migration" in message.lower(), message
    assert str(dims) in message, message
    assert "never runs DDL" in message, (
        "the refusal must say WHY the store does not just create it — a bare "
        f"'unsupported' invites the next reader to add the CREATE: {message}"
    )
    assert exc.value.dims == dims


def test_unsupported_width_is_a_valueerror():
    """Callers that already catch ValueError around embedding wiring keep
    working; the subclass only adds the width."""
    assert issubclass(UnsupportedEmbeddingDims, ValueError)


# ---------------------------------------------------------------------------
# ⛔ MUTANT: DDL outside a migration
# ---------------------------------------------------------------------------

_DDL = re.compile(
    r"\b(CREATE\s+(TABLE|INDEX|EXTENSION|SCHEMA)|ALTER\s+(TABLE|INDEX)"
    r"|DROP\s+(TABLE|INDEX|SCHEMA))\b",
    re.IGNORECASE,
)


def test_provider_source_contains_no_ddl():
    """``CLAUDE.md``: *"Data-access code never runs DDL."*

    The whole reason a dynamic table was refused. If this goes red, the fix is
    a migration, never a wider regex.
    """
    offenders = [s for s in _string_literals(_PGVECTOR) if _DDL.search(s)]
    assert not offenders, (
        "the pgvector provider emits DDL — the schema must be owned by an "
        f"alembic revision, not by data-access code: {offenders}"
    )


def test_provider_never_names_the_retired_unsuffixed_table():
    """A hardcoded ``dna_search_docs`` would bypass the routing entirely and
    read the table 0013 renamed away — the mutant that looks like a leftover."""
    bare = re.compile(r"\bdna_search_docs\b(?!_)")
    offenders = [s for s in _string_literals(_PGVECTOR) if bare.search(s)]
    assert not offenders, (
        "the retired unsuffixed table name appears in SQL; every statement "
        f"must route through search_table(dims): {offenders}"
    )


def test_every_provider_statement_that_reads_rows_filters_by_model_id():
    """⚠️ ``model_id`` is a FILTER, not a label.

    Every SELECT and every INSERT in the provider carries it — except the
    DELETE, which is deliberately model-blind (a record gone from the source
    has no business staying indexed in any space) and the metadata resolve,
    which reads ids the two planes already constrained. Both exceptions are
    named here so removing the filter somewhere else cannot hide behind them.
    """
    literals = _string_literals(_PGVECTOR)
    reads = [
        s for s in literals
        if re.search(r"\b(SELECT|INSERT)\b", s, re.IGNORECASE)
        and "{table}" in s.replace("{self._schema}", "")
    ]
    assert reads, "found no routed SQL at all — the guard is measuring nothing"
    missing = [
        s for s in reads
        if "model_id" not in s and "id = ANY" not in s
    ]
    assert not missing, (
        "a routed statement reads/writes rows without pinning the embedding "
        f"space: {missing}"
    )


# ---------------------------------------------------------------------------
# ⛔ MUTANT: the runtime list and the migration drift apart
# ---------------------------------------------------------------------------

def _migration_dims() -> list[int]:
    """The widths the revision actually creates, read from ITS source.

    Deliberately parsed rather than imported: the revision does not import
    ``SUPPORTED_DIMS`` (a revision is a frozen fact and cannot re-render itself
    from today's code), so this is a genuinely INDEPENDENT second list. If the
    two ever became one list, this comparison would be measuring itself.
    """
    tree = ast.parse(_MIGRATION.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        targets = (
            node.targets if isinstance(node, ast.Assign)
            else [node.target] if isinstance(node, ast.AnnAssign)
            else []
        )
        if any(isinstance(t, ast.Name) and t.id == "_DIMS" for t in targets):
            return [
                int(elt.elts[0].value)  # type: ignore[attr-defined]
                for elt in node.value.elts  # type: ignore[attr-defined]
            ]
    raise AssertionError("_DIMS not found in 0013 — did the revision get renamed?")


def test_runtime_widths_and_migration_widths_agree():
    """⭐ Adding a width to ``SUPPORTED_DIMS`` without writing the migration is
    RED here. That is the signal the old ``CREATE TABLE`` at boot swallowed:
    the store simply created whatever it needed and nobody found out."""
    assert sorted(_migration_dims()) == sorted(SUPPORTED_DIMS), (
        "the widths the store routes to and the widths a migration creates "
        "have drifted — every routable width needs a table, and a table "
        "nobody routes to is dead schema"
    )


def test_the_five_widths_are_the_decided_ones():
    """The founder's decision named them (i-104, 08/08/2026). Pinned so a
    quiet edit shows up as a decision being changed, not a constant tweaked."""
    assert sorted(SUPPORTED_DIMS) == [384, 768, 1024, 1536, 3072]


def test_migration_creates_a_table_for_every_routable_width():
    source = _MIGRATION.read_text(encoding="utf-8")
    for dims in SUPPORTED_DIMS:
        assert search_table(dims) in source.replace(
            'f"dna_search_docs_{dims}"', ""
        ) or "dna_search_docs_{dims}" in source, (
            f"revision 0013 never names {search_table(dims)}"
        )


def test_3072_is_documented_as_unindexable_not_silently_skipped():
    """pgvector refuses ivfflat/hnsw above 2000 dimensions (measured against
    0.8.2). The largest width therefore has no ANN index — which is fine, and
    must be SAID. A table quietly missing its accelerator is the kind of thing
    that gets discovered as 'search got slow' six months later."""
    source = _MIGRATION.read_text(encoding="utf-8")
    assert "2000" in source and "ivfflat" in source, source[:200]
    dims_block = source[source.index("_DIMS:"):source.index("_LEGACY")]
    assert "(3072, False)" in dims_block, dims_block
    assert "(1536, True)" in dims_block, dims_block
