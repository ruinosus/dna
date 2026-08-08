"""The SqlAlchemySource table model — ONE definition of the schema.

Before i-038 the schema existed twice: as DDL payloads (``migrations.py``)
and as ``sa.Table`` objects built inline in ``source.py``, with nothing
checking that they agreed. They drifted for two weeks (``content_binary``
was added to the code but never to a migration, so every fresh bootstrap
broke — see the retired PG migration v9).

Now there is one model, here, and it is the ``target_metadata`` Alembic
autogenerates against. ``tests/test_schema_autogenerate_guard.py`` boots a
database from the Alembic revisions and asserts the model and the database
agree; a column added here without a revision (or vice versa) fails that
test instead of shipping.

Because the model is now compared against a real database, the columns
carry their real constraints (``nullable``, ``primary_key``,
``server_default``) rather than the loose bare-``Column`` shorthand the
inline version used — a model that lies about nullability cannot be a
drift detector.

[dialect] The two dialects' schemas are genuinely disjoint — different
table names (``dna_``-prefixed vs bare), different primary keys
(``instances`` includes ``tenant`` on pg, not on sqlite — i-092), and pg
has two tables sqlite does not (the Phase 15.1 eventbus). ``build_metadata``
branches on ``is_pg`` exactly as the retired ``_build_tables`` did.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa

# Import-safe: ``dimensions`` is pure constants + one pure function, with no
# asyncpg/pgvector import anywhere in it (the isolation guard in
# ``tests/test_search_import_isolation.py`` covers the modules that are not).
from dna.adapters.search.dimensions import SUPPORTED_DIMS as _SEARCH_DIMS

# Indexes deliberately NOT represented in the model, and therefore excluded
# from autogenerate comparison (see ``alembic/env.py::include_object``).
#
# Every one of these is a partial and/or expression index. SQLAlchemy cannot
# round-trip them: reflection on SQLite outright skips expression indexes
# ("SAWarning: Skipped unsupported reflection of expression-based index"), and
# on Postgres it returns them as opaque ``_textual_index_element`` objects that
# never compare equal to a model-side definition. Left in the comparison they
# would report a phantom "remove_index" on every single run, and a guard that
# always fails is a guard nobody reads.
#
# The tradeoff is explicit and narrow: these index names are pinned here, so
# autogenerate stays silent about THESE indexes only. A NEW index — or any
# table/column drift, which is the ``content_binary`` failure mode this guard
# exists to catch — is still reported.
UNMANAGED_INDEXES: frozenset[str] = frozenset({
    # Postgres — hot-field expression indices, partial on `content ? 'spec'`.
    "dna_insts_status_idx",
    "dna_insts_feature_idx",
    "dna_insts_updated_at_idx",
    "dna_insts_spec_gin_idx",
    # Postgres — partial indexes on `semver IS NOT NULL` / `kind = 'Genome'`.
    "dna_versions_semver_unique",
    "dna_versions_package_lookup",
    # SQLite — json_extract expression indices.
    "insts_status_idx",
    "insts_feature_idx",
    "insts_updated_at_idx",
    # SQLite — the same two partial indexes.
    "versions_semver_unique",
    "versions_package_lookup",
})


#: Tables inside the DNA database that the Source model does NOT own, and
#: which autogenerate must therefore not propose dropping.
FOREIGN_TABLES: frozenset[str] = frozenset({
    # Retired control tables (kept excluded so a database mid-cutover does
    # not look like it has a stray table).
    "schema_migrations", "dna_schema_migrations",
    # ⭐ The pgvector search store's own retired control tables. Its schema
    # USED to be parametrized by embedding width and applied by the provider
    # at first search — the sentence that stood here said that width "cannot
    # live in a static revision", and s-indice-por-dimensao showed it can:
    # revision 0013 creates ONE TABLE PER WIDTH, so the parameter became a
    # finite list and the DDL came home to the ladder. These three names are
    # what that cutover left behind (0013 renames `dna_search_docs` to its
    # dimension); they stay excluded so a database mid-cutover does not look
    # like it has a stray table.
    "dna_search_migrations", "dna_search_docs", "dna_search_meta",
    # The sqlite-vec store — a file per scope, its own ladder, never in this
    # database.
    "search_docs", "search_vec", "search_fts", "search_meta",
    # ⚠️ The per-width tables 0013 DOES create. They are excluded for a
    # different reason than everything else in this set: the ladder owns them,
    # but the MODEL cannot describe them. `embedding vector(N)` has no
    # SQLAlchemy type without the `pgvector` package, which is not a dependency
    # of the base install (the store is the optional `search-pgvector` extra) —
    # so a model entry would either lie about the type or drag an optional
    # dependency into every install. Derived from SUPPORTED_DIMS, never typed
    # out: a sixth width added there without this line following would be a
    # table autogenerate proposes dropping.
    *(f"dna_search_docs_{d}" for d in _SEARCH_DIMS),
    # AUTOINCREMENT bookkeeping, owned by SQLite itself.
    "sqlite_sequence",
    # Alembic's own control table. Alembic filters it out of its own
    # schema automatically, but not when reflecting a named schema.
    "alembic_version",
})


def make_include_name(schema: str | None):
    """Restrict reflection to the ONE schema this Source owns.

    [dialect] Postgres only. ``include_schemas`` has to be on so the named
    DNA schema is reflected at all, but with it on Alembic reflects EVERY
    schema in the database and reports every table it finds elsewhere as a
    table to drop. A DNA schema shares its database with other things —
    dna-cloud's Postgres hosts several — so an unrestricted autogenerate
    would cheerfully propose dropping tables that belong to someone else.
    This admits the target schema and nothing else.
    """

    def include_name(name, type_, parent_names) -> bool:
        if type_ == "schema":
            return name == schema
        return True

    return include_name


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Filter what autogenerate is allowed to have an opinion about.

    Lives here rather than in ``alembic/env.py`` because the guard test
    must apply the SAME filter, and ``env.py`` executes Alembic context
    setup at import time (Alembic loads it by path, not as a module).
    """
    if type_ == "index" and name in UNMANAGED_INDEXES:
        return False
    if type_ == "table" and name in FOREIGN_TABLES:
        return False
    return True


def compare_type(context_, inspected_column, metadata_column,
                 inspected_type, metadata_type):
    """Alembic's default type comparison, minus one known false positive.

    [dialect] SQLite has no native BOOLEAN — ``is_draft`` is stored as
    INTEGER 0/1 (the retired payload said ``INTEGER NOT NULL DEFAULT 1``).
    The model says ``sa.Boolean`` because that is what the code means and
    how it queries (``is_draft.is_(True)``). Reflection returns INTEGER, so
    the default comparator would report a type change on every run.
    Suppress exactly that pair, on SQLite only.

    Returns ``None`` to defer to Alembic's default comparison.
    """
    if context_.dialect.name != "postgresql":
        if isinstance(metadata_type, sa.Boolean) and isinstance(
            inspected_type, sa.Integer
        ):
            return False
    return None


@dataclass(frozen=True)
class Tables:
    """The tables ``SqlAlchemySource`` binds to, plus their shared MetaData."""

    metadata: sa.MetaData
    instances: sa.Table
    versions: sa.Table
    bundle_entries: sa.Table
    layer_instances: sa.Table
    #: The derived reference graph (spec-grafo-1) — both dialects.
    edges: sa.Table
    # [dialect] pg-only (Phase 15.1 eventbus); None on sqlite.
    outbox: sa.Table | None
    versions_seq: sa.Table | None
    # [dialect] pg-only CONTROL-PLANE table. Not bound by SqlAlchemySource --
    # nothing in the instance path reads or writes it. It lives in this model
    # anyway because the model is what autogenerate compares against: a table
    # created by a revision but absent here would be reported as a table to
    # DROP on every run (see FOREIGN_TABLES for the other way out, taken by
    # the search stores, whose DDL cannot live in a static revision). Written
    # by the MCP metering store (``dna_cli._mcp_quota.PostgresQuotaStore``).
    quota_counters: sa.Table | None = None
    # [dialect] pg-only CONTROL-PLANE tables, same reasoning as
    # quota_counters: nothing in the instance path touches them, but the model
    # is what autogenerate compares against. Written by the span processor in
    # ``dna.runtime.telemetry``; read by the portal's console.
    turn: sa.Table | None = None
    turn_step: sa.Table | None = None
    approval: sa.Table | None = None


def build_metadata(*, is_pg: bool, schema: str | None = None) -> Tables:
    """Build the table model for one dialect.

    Args:
        is_pg: Postgres if True, SQLite otherwise. Selects table names,
            primary keys, column nullability and which tables exist.
        schema: Postgres schema namespace; must be None on SQLite.
    """
    md = sa.MetaData(schema=schema)
    # [dialect] pg tables are dna_-prefixed; sqlite's are bare.
    p = "dna_" if is_pg else ""

    # [dialect] tenant: pg is NOT NULL DEFAULT '' and part of the instances
    # PK; sqlite left it nullable and outside the PK (i-092 lives here).
    doc_tenant = (
        sa.Column("tenant", sa.Text, nullable=False,
                  server_default=sa.text("''"), primary_key=True)
        if is_pg else
        sa.Column("tenant", sa.Text, nullable=True)
    )
    # [dialect] pg-only — WORLD time as a column (revision 0010). SQLite has no
    # range type, no GiST and no EXCLUDE constraint, and there is no honest
    # partial version: two scalar TEXT columns would carry the endpoints and
    # NOT the invariant (no two validity periods for one instance may overlap),
    # which is the half worth having. So the sqlite dialect does not get the
    # column at all and declares ``valid_time=False`` — the same shape as the
    # pg-only eventbus tables below, and the reason
    # ``SourceCapabilities.valid_time`` is per-BINDING rather than per-class.
    valid_time_args: list[Any] = []
    if is_pg:
        from sqlalchemy.dialects.postgresql import TSTZRANGE, ExcludeConstraint
        valid_time_args = [
            # ONE range column, not two timestamps, and PG18 is why: its
            # temporal keys are ``PRIMARY KEY (id, valid_at WITHOUT OVERLAPS)``
            # and the docs require that column to be *"a range or multirange
            # type"*. A pair of scalars could not be adopted by the engine
            # without rewriting the table; this shape is adopted by swapping
            # the constraint below for the key and touching no data.
            #
            # NOT NULL with an unbounded default, rather than nullable. NULL
            # would mean "declares no window", which is real information — but
            # an exclusion constraint SKIPS any row with a NULL operand, so a
            # nullable column would leave the constraint enforcing nothing on
            # the 400 of 414 instances (measured 06/08/2026) that say nothing
            # about world time. A guard that ships green over every row in the
            # table is the failure mode this house has already paid for. The
            # unbounded window is not an invention either: it is exactly what
            # ``dna.memory.decay.currently_valid`` has always meant by an unset
            # ``valid_to``, stated in the schema instead of re-derived in
            # Python. ``ValidWindow.bounded`` is how a reader still tells "said
            # nothing" from "said always".
            sa.Column(
                "valid_at",
                TSTZRANGE,
                nullable=False,
                server_default=sa.text(
                    "tstzrange('-infinity'::timestamptz, "
                    "'infinity'::timestamptz, '[)')"
                ),
            ),
            # The invariant, stated where it can be enforced: ONE instance has
            # at most ONE state true at any world instant. ``id`` and not the
            # natural key, because identity is what a validity period belongs
            # to and a rename must not split the history (i-114). Rows with a
            # NULL ``id`` are skipped by the constraint — correctly: a row with
            # no identity cannot conflict with another row's identity.
            #
            # ⚠️ Needs ``btree_gist`` for the ``=`` half over a TEXT id (GiST
            # speaks ranges natively and nothing else). Confirmed on the Azure
            # Flexible Server allowlist — 1.7 on PG16, no
            # ``shared_preload_libraries`` — and the revision CREATEs it.
            ExcludeConstraint(
                (sa.literal_column("id"), "="),
                (sa.literal_column("valid_at"), "&&"),
                name=f"{p}instances_valid_at_excl",
                using="gist",
            ),
        ]

    instances = sa.Table(
        f"{p}instances", md,
        sa.Column("scope", sa.Text, primary_key=True, nullable=False),
        sa.Column("kind", sa.Text, primary_key=True, nullable=False),
        # A Kind's identity is (apiVersion, kind) — that is the registry key,
        # and tenant-authored Kinds depend on it: two workspaces may each
        # declare a `Deal` under their own namespace. Keying rows on the bare
        # Kind NAME made those two indistinguishable HERE, so a save silently
        # overwrote and a delete silently reached into the other Kind's rows.
        # In the PK on both dialects (revision 0003_api_version_identity).
        # ``''`` is not a default apiVersion: it is the recorded fact that the
        # stored instance declares none (see the revision's backfill).
        sa.Column("api_version", sa.Text, primary_key=True, nullable=False,
                  server_default=sa.text("''")),
        sa.Column("name", sa.Text, primary_key=True, nullable=False),
        # i-114 — the instance's IDENTITY, as opposed to its address.
        # Deliberately NOT in the primary key: the key is still the natural
        # 5-tuple, because that is what every reader addresses. This column is
        # the durable handle a rename does not move, and the value ``dna_edges``
        # records beside the target's name. Redundant with ``content``'s
        # ``metadata.id`` on purpose — a JSON field cannot be indexed for the
        # prefix scan that is the whole point.
        # Nullable, and no default: NULL is the honest reading of an instance
        # written by an adapter or a code path that has not stamped one, and a
        # generated default here would mint identity in the STORE, which is the
        # kernel's job and only the kernel's.
        sa.Column("id", sa.Text, nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False,
                  server_default=sa.text("1")),
        sa.Column("updated_at", sa.Text, nullable=False),
        doc_tenant,
        sa.Index(f"{p}instances_tenant_idx", "tenant", "scope", "kind",
                 "api_version", "name"),
        # ``tenant`` leads so a lookup never walks another tenant's ids.
        # HONEST LIMIT: this serves the EXACT-id lookup. Prefix resolution is
        # ``LIKE 'abcd%'``, and Postgres will not use a default-collation btree
        # for that — it wants ``text_pattern_ops``. Not added, deliberately: an
        # extra operator class is a thing ``alembic check`` has to be taught
        # about forever, and the prefix scan reads a few hundred short rows on
        # a store this size. When an instance count makes that false, the fix
        # is a second index with the operator class, not a redesign.
        sa.Index(f"{p}instances_id_idx", "tenant", "id"),
        *valid_time_args,
    )

    versions = sa.Table(
        f"{p}versions", md,
        # [dialect] pg's SERIAL is NOT NULL; sqlite's INTEGER PRIMARY KEY is
        # the rowid alias, which accepts NULL on insert (that is HOW you ask
        # for an autoassigned id) and reflects as nullable. Stating that
        # here rather than suppressing the diff keeps the model honest --
        # the flag affects comparison only, never emitted DDL, because the
        # revisions carry their own frozen DDL.
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True,
                  nullable=not is_pg),
        sa.Column("scope", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        # Same identity widening as `instances`. `versions` has no business
        # primary key (``id`` is a surrogate), so the column carries its weight
        # through the indexes below and the semver uniqueness index.
        sa.Column("api_version", sa.Text, nullable=False,
                  server_default=sa.text("''")),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        # [dialect] pg stores a real BOOLEAN; sqlite stores INTEGER 0/1.
        # The model says Boolean on both -- the source code compares with
        # ``is_(True)`` -- and env.py's compare_type suppresses the sqlite
        # affinity false-positive rather than the model lying about intent.
        sa.Column("is_draft", sa.Boolean, nullable=False,
                  server_default=sa.text("true" if is_pg else "1")),
        sa.Column("author", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column(
            "tenant", sa.Text,
            nullable=not is_pg,
            server_default=sa.text("''") if is_pg else None,
        ),
        sa.Column("semver", sa.Text, nullable=True),
        # [dialect] sqlite used INTEGER PRIMARY KEY AUTOINCREMENT, which is
        # observably different from a bare rowid alias (it creates
        # sqlite_sequence and stops rowid reuse).
        sqlite_autoincrement=not is_pg,
    )
    if is_pg:
        versions.append_constraint(
            sa.Index(f"{p}versions_tenant_idx", "tenant", "scope", "kind",
                     "api_version", "name")
        )

    bundle_cols: list[sa.Column] = [
        sa.Column("scope", sa.Text, primary_key=True, nullable=False),
        sa.Column("kind", sa.Text, primary_key=True, nullable=False),
        # A bundle entry belongs to an instance, hence to that instance's Kind:
        # without this the two `Deal`s' entries collide on one row.
        sa.Column("api_version", sa.Text, primary_key=True, nullable=False,
                  server_default=sa.text("''")),
        sa.Column("name", sa.Text, primary_key=True, nullable=False),
        sa.Column("entry_path", sa.Text, primary_key=True, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.Column("tenant", sa.Text, primary_key=True, nullable=False,
                  server_default=sa.text("''")),
    ]
    if is_pg:
        # [dialect] only pg has the BYTEA column; sqlite stores bytes in
        # `content` via type affinity. THIS is the column whose absence from
        # the migrations went unnoticed for two weeks.
        bundle_cols.append(sa.Column("content_binary", sa.LargeBinary, nullable=True))
    bundle_entries = sa.Table(
        f"{p}bundle_entries", md, *bundle_cols,
        sa.Index(f"{p}bundle_entries_scope_kind_idx", "scope", "kind",
                 "api_version"),
        sa.Index(f"{p}bundle_entries_tenant_idx", "tenant", "scope", "kind",
                 "api_version"),
    )

    # The DERIVED reference graph (spec-grafo-1, revision 0006). One row per
    # declared ``x-dna-ref`` VALUE of one instance — written by the write path
    # inside the same transaction as the instance itself, never by a scanner
    # and never by guessing at slugs.
    #
    # Present on BOTH dialects, unlike the pg-only control-plane tables: this
    # is instance data derived from instance data, and a SQLite self-host asks
    # "what points at this?" exactly as a hosted Postgres does. The traversal
    # is a recursive CTE in standard SQL, identical on both.
    #
    # Four decisions the DDL retired in i-039 did not have:
    #
    # 1. ``source_field`` AND ``ordinal`` are IN the primary key. Without the
    #    field, two fields of one instance pointing at the same target collide
    #    and the graph loses "by which field" — which is precisely what a
    #    relations view renders. Without the ordinal, ``Epic.features[3]``
    #    cannot be told from ``[0]``, and the order of an array is the author's
    #    data.
    # 2. ``to_kind`` NULL means DANGLING, not absent. With
    #    ``DNA_REF_VALIDATION=warn`` (the default) an instance with an
    #    unresolvable reference persists; dropping that row would render a
    #    tidier graph than the data deserves. The dangling rows are the most
    #    valuable content of this table — they are the list of what is broken.
    # 3. ``to_scope`` is separate from ``scope`` because ``get_instance`` falls
    #    back to parent scopes: a reference may resolve in a DIFFERENT scope,
    #    and recording that as an intra-scope relation would assert a link that
    #    does not exist. NULL = resolved through the inheritance chain, parent
    #    not recorded.
    # 4. ``from_version`` is the instance version the edges were derived from —
    #    the drift detector for the non-atomic paths (backfill, an adapter
    #    without the kwarg) and the anchor a future as-of traversal needs.
    #
    # No foreign keys: a Kind is not a table, and ``to_name`` deliberately may
    # name an instance that does not exist.
    edge_cols: list[sa.Column] = [
        sa.Column("scope", sa.Text, primary_key=True, nullable=False),
        sa.Column("tenant", sa.Text, primary_key=True, nullable=False,
                  server_default=sa.text("''")),
        sa.Column("from_api_version", sa.Text, primary_key=True, nullable=False,
                  server_default=sa.text("''")),
        sa.Column("from_kind", sa.Text, primary_key=True, nullable=False),
        sa.Column("from_name", sa.Text, primary_key=True, nullable=False),
        sa.Column("source_field", sa.Text, primary_key=True, nullable=False),
        sa.Column("ordinal", sa.Integer, primary_key=True, nullable=False,
                  server_default=sa.text("0")),
        sa.Column("to_scope", sa.Text, nullable=True),
        sa.Column("to_kind", sa.Text, nullable=True),
        sa.Column("to_name", sa.Text, nullable=False),
        # i-114, decision 5 of this table: ``to_id`` beside ``to_name``.
        # This is the whole point of the id feature landing in the DERIVED
        # layer rather than in the authored file. The author wrote a NAME —
        # that is what ``to_name`` preserves, and what keeps the ``.dna/`` diff
        # readable. The write path RESOLVED that name to an instance, and which
        # instance it was is a fact the author did not state and cannot be
        # recovered later once the name moves. Kubernetes' ``ownerReferences``
        # carries exactly this pair for exactly this reason: delete and
        # recreate under the same name and the uid changes, so a controller can
        # tell it is looking at a different object.
        # NULL means one of two things, both honest: the relation is DANGLING
        # (``to_kind`` is NULL too), or the target has no id yet. It never
        # means "same as before".
        sa.Column("to_id", sa.Text, nullable=True),
        # i-110.3 / fatia 1 de ``spec-topologia-do-grafo``: a aresta sabe de
        # que apiVersion ela SAI e passa a saber para qual ela ENTRA.
        #
        # O lado FROM carrega ``from_api_version`` desde a 0006 — está na chave
        # primária, porque é a identidade da origem. O lado TO não carregava, e
        # a razão pela qual isso FUNCIONAVA não estava escrita em lugar nenhum
        # desta tabela: ela morava em ``dna.kernel.kinds.registry``, na guarda
        # da i-195 que recusa registrar dois Kinds homônimos sob apiVersions
        # diferentes. Ou seja: a integridade do grafo dependia, calada, de uma
        # invariante de OUTRO módulo, e nenhuma guarda ligando as duas coisas.
        # A catraca que passa a ligá-las está em
        # ``tests/test_edge_knows_target_api_version.py``.
        #
        # A ``KIND_NAME_COLLISION_ALLOWLIST`` citada aqui como "lista de
        # exceções aberta" foi esvaziada em 06/08/2026 (i-127) — a única
        # entrada estava morta. ⚠️ Isso NÃO torna a unicidade global: o funil
        # de ``KindDefinition`` por escopo segue permitindo homônimos por
        # desenho e nunca consulta a constante. É exatamente por isso que a
        # catraca que importa pergunta ao REGISTRY VIVO, e não à constante.
        #
        # O docstring da revisão 0008 já tinha nomeado a consequência ao
        # explicar por que o backfill de ``to_id`` deixa NULL: *"a aresta grava
        # to_kind/to_name mas não a api_version do alvo, então dois Kinds
        # homônimos em namespaces diferentes tornam o alvo indeterminado"*.
        # Esta coluna é a resposta a essa frase.
        #
        # O desenho vem do MESMO lugar que ``to_id``: a ``OwnerReference`` do
        # Kubernetes carrega ``apiVersion`` **e** ``kind`` **e** ``name`` **e**
        # ``uid`` — quatro campos, e o ``apiVersion`` está lá exatamente porque
        # ``kind`` sozinho é ambíguo entre grupos de API. A tabela agora carrega
        # os quatro (``to_api_version``/``to_kind``/``to_name``/``to_id``), mais
        # o ``to_scope`` que é o ``namespace``.
        #
        # Nullable e SEM default, como ``to_id`` e pelo mesmo motivo: NULL é
        # "não sei" — aresta pendurada, ou linha escrita antes da 0009 cujo
        # alvo o backfill não alcançou. NULL nunca significa "a mesma de
        # sempre". String VAZIA é o "não sei" herdado do lado FROM (o
        # ``server_default`` da 0006), e a travessia trata os dois igual.
        sa.Column("to_api_version", sa.Text, nullable=True),
        sa.Column("declared_to", sa.Text, nullable=False,
                  server_default=sa.text("''")),
        sa.Column("from_version", sa.Integer, nullable=False,
                  server_default=sa.text("0")),
    ]
    edge_cols.append(
        # [dialect] pg gets a real timestamp with the server clock as default;
        # sqlite keeps the ISO-8601 TEXT the rest of its tables use
        # (``instances.updated_at``), written by the adapter's own ``_now()``.
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()"))
        if is_pg else
        sa.Column("updated_at", sa.Text, nullable=False)
    )
    edge_cols.append(
        # i-131 — QUANDO a instância que esta aresta resolveu foi apagada.
        #
        # A coluna existe porque ``to_kind IS NOT NULL`` respondia a pergunta
        # ERRADA. Ele é um fato do INSTANTE DA ESCRITA ("a referência achou um
        # alvo, deste Kind"), e a travessia o servia como se fosse um fato do
        # instante da LEITURA ("isto ainda aponta para algo"). Apagado o alvo,
        # a linha continuava — corretamente, ver o comentário do
        # ``delete_instance`` — dizendo ``resolved: true``. Não era impreciso:
        # era o oposto, entregue com a mesma confiança.
        #
        # ⚠️ NULL é "nenhum delete foi observado", NUNCA "o alvo existe". Uma
        # linha anterior a esta revisão diz NULL porque ninguém estava olhando,
        # e a 0011 deliberadamente NÃO faz backfill: ver o docstring dela.
        #
        # É TIMESTAMP e não booleano pelo mesmo preço: "sumiu" e "sumiu em tal
        # instante" custam a mesma escrita, e só o segundo se cruza com o
        # ``dna_versions.created_at`` da origem para dizer se a aresta foi
        # escrita antes ou depois de o alvo morrer.
        sa.Column("to_deleted_at", sa.DateTime(timezone=True), nullable=True)
        if is_pg else
        sa.Column("to_deleted_at", sa.Text, nullable=True)
    )
    edges = sa.Table(
        f"{p}edges", md, *edge_cols,
        # The two directions the traversal walks. "out" is served by the PK
        # prefix as well, but naming it keeps the pair symmetric and survives a
        # future key change; "in" has no other index that could serve it, and
        # without it "what points at this instance?" is a full scan.
        sa.Index(f"{p}edges_out_idx", "scope", "tenant", "from_kind", "from_name"),
        sa.Index(f"{p}edges_in_idx", "scope", "tenant", "to_kind", "to_name"),
    )

    layer_instances = sa.Table(
        f"{p}layer_instances", md,
        sa.Column("scope", sa.Text, primary_key=True, nullable=False),
        sa.Column("layer_id", sa.Text, primary_key=True, nullable=False),
        sa.Column("layer_value", sa.Text, primary_key=True, nullable=False),
        sa.Column("kind", sa.Text, primary_key=True, nullable=False),
        sa.Column("name", sa.Text, primary_key=True, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
    )

    outbox = versions_seq = quota_counters = None
    turn = turn_step = approval = None
    if is_pg:
        # [dialect] the DNA Cloud metering counter — the DURABLE half of the
        # MCP quota meter (``dna_cli._mcp_quota``). Postgres-only on purpose:
        # its whole reason to exist is to be correct across RESTARTS and
        # across N REPLICAS, which a single-file SQLite self-host does not
        # have and does not need (that deployment keeps the in-process
        # counter). One row per (day, tenant, tier); the counter is advanced
        # with INSERT ... ON CONFLICT DO UPDATE SET calls = calls + 1, never
        # read-modify-write, so concurrent replicas cannot lose an increment.
        #
        # `day` is a DATE in UTC, written by the store (not a server default)
        # so the bucket boundary is the store's clock, not the database
        # server's timezone.
        #
        # The PK (day, tenant, tier) is also the read path's index: the daily
        # billing rollup filters `day = <today> AND tenant = <t>`, and both
        # are equality predicates on a leading prefix of the PK, so no
        # secondary index is warranted.
        quota_counters = sa.Table(
            f"{p}quota_counters", md,
            sa.Column("day", sa.Date, primary_key=True, nullable=False),
            sa.Column("tenant", sa.Text, primary_key=True, nullable=False),
            sa.Column("tier", sa.Text, primary_key=True, nullable=False),
            sa.Column("calls", sa.BigInteger, nullable=False,
                      server_default=sa.text("0")),
        )
        # [dialect] the Phase 15.1 eventbus is Postgres infrastructure
        # (outbox + LISTEN/NOTIFY); sqlite has no cross-process bus.
        outbox = sa.Table(
            f"{p}outbox", md,
            sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.Column("scope", sa.Text, nullable=False),
            sa.Column("tenant", sa.Text, nullable=False,
                      server_default=sa.text("''")),
            sa.Column("kind", sa.Text, nullable=False),
            sa.Column("name", sa.Text, nullable=False),
            sa.Column("op", sa.Text, nullable=False),
            sa.Column("doc_version", sa.Integer, nullable=False),
            sa.Column("actor", sa.Text, nullable=True),
            sa.Column("cause", sa.Text, nullable=True),
            sa.Index(f"{p}outbox_scope_id_idx", "scope", "tenant", "id"),
            sa.Index(f"{p}outbox_occurred_at_idx", "occurred_at"),
        )
        # [dialect] o REGISTRO do que um turno fez — a metade duravel da
        # observabilidade (`dna.runtime.telemetry`). Postgres-only pelo mesmo
        # motivo do quota_counters: e uma tabela de plano de controle, e um
        # self-host de processo unico nao tem a pergunta que ela responde.
        #
        # `input_text`/`output_text` sao TRUNCADOS por quem escreve, nao pelo
        # banco — ver a revisao 0004.
        turn = sa.Table(
            f"{p}turn", md,
            sa.Column("turn_id", sa.Text, primary_key=True, nullable=False),
            sa.Column("trace_id", sa.Text, nullable=False,
                      server_default=sa.text("''")),
            sa.Column("thread_id", sa.Text, nullable=False,
                      server_default=sa.text("''")),
            sa.Column("workspace", sa.Text, nullable=False,
                      server_default=sa.text("''")),
            sa.Column("oid", sa.Text, nullable=False,
                      server_default=sa.text("''")),
            sa.Column("agent", sa.Text, nullable=False,
                      server_default=sa.text("''")),
            sa.Column("model", sa.Text, nullable=False,
                      server_default=sa.text("''")),
            sa.Column("input_text", sa.Text, nullable=True),
            sa.Column("output_text", sa.Text, nullable=True),
            sa.Column("input_tokens", sa.Integer, nullable=False,
                      server_default=sa.text("0")),
            sa.Column("output_tokens", sa.Integer, nullable=False,
                      server_default=sa.text("0")),
            # NULO = desconhecido (linhas anteriores a 0012). `false` = a conta
            # esta fechada; `true` = alguma chamada ao modelo nao reportou uso e
            # `input_tokens` e um PISO, nao a conta. Ver a revisao 0012.
            sa.Column("tokens_partial", sa.Boolean, nullable=True),
            sa.Column("status", sa.Text, nullable=False,
                      server_default=sa.text("'ok'")),
            # ⭐ O que o turno CONSEGUIU — DECLARADO, nunca inferido do `status`.
            # Vazio significa DESCONHECIDO, jamais `resolved`. Ver a revisao 0012.
            sa.Column("outcome", sa.Text, nullable=False,
                      server_default=sa.text("''")),
            sa.Column("error", sa.Text, nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_ms", sa.Integer, nullable=False,
                      server_default=sa.text("0")),
            sa.Index(f"{p}turn_thread_started_idx",
                     "workspace", "thread_id", sa.text("started_at DESC")),
        )
        turn_step = sa.Table(
            f"{p}turn_step", md,
            sa.Column("turn_id", sa.Text,
                      sa.ForeignKey(f"{md.schema + '.' if md.schema else ''}{p}turn.turn_id",
                                    ondelete="CASCADE"),
                      primary_key=True, nullable=False),
            sa.Column("step_index", sa.Integer, primary_key=True, nullable=False),
            sa.Column("name", sa.Text, nullable=False),
            sa.Column("input", sa.Text, nullable=True),
            sa.Column("output", sa.Text, nullable=True),
            sa.Column("status", sa.Text, nullable=False,
                      server_default=sa.text("'ok'")),
            sa.Column("error", sa.Text, nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.Column("duration_ms", sa.Integer, nullable=False,
                      server_default=sa.text("0")),
        )
        # [dialect] a TRILHA DE APROVACAO. Separada de `turn_step` de proposito:
        # as garantias sao opostas (aquela descarta e trunca; esta nao pode
        # perder nem cortar). Append-only, sem `updated_at`.
        approval = sa.Table(
            f"{p}approval", md,
            sa.Column("approval_id", sa.Text, primary_key=True, nullable=False),
            sa.Column("turn_id", sa.Text, nullable=False, server_default=sa.text("''")),
            sa.Column("thread_id", sa.Text, nullable=False, server_default=sa.text("''")),
            sa.Column("workspace", sa.Text, nullable=False, server_default=sa.text("''")),
            sa.Column("oid", sa.Text, nullable=False, server_default=sa.text("''")),
            sa.Column("actor_email", sa.Text, nullable=False, server_default=sa.text("''")),
            sa.Column("tool", sa.Text, nullable=False),
            sa.Column("arguments", sa.Text, nullable=False, server_default=sa.text("''")),
            sa.Column("decision", sa.Text, nullable=False, server_default=sa.text("''")),
            sa.Column("edited_args", sa.Text, nullable=False, server_default=sa.text("''")),
            sa.Column("reason", sa.Text, nullable=False, server_default=sa.text("''")),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Index(f"{p}approval_thread_idx", "thread_id", sa.text("requested_at DESC")),
            sa.Index(f"{p}approval_workspace_idx", "workspace", sa.text("requested_at DESC")),
        )
        versions_seq = sa.Table(
            f"{p}versions_seq", md,
            sa.Column("scope", sa.Text, primary_key=True, nullable=False),
            sa.Column("tenant", sa.Text, primary_key=True, nullable=False,
                      server_default=sa.text("''")),
            sa.Column("last_id", sa.BigInteger, nullable=False),
            sa.Column("last_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
        )

    return Tables(
        metadata=md, instances=instances, versions=versions,
        bundle_entries=bundle_entries, layer_instances=layer_instances,
        edges=edges,
        outbox=outbox, versions_seq=versions_seq,
        quota_counters=quota_counters, turn=turn, turn_step=turn_step,
        approval=approval,
    )
