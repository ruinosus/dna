"""Revision 0003 against a database that already holds real content.

A schema migration that only ever runs on a fresh bootstrap is untested where
it matters. These build a database at the PREVIOUS revision, fill it with the
shape a running deployment has — several Kinds, tenant overlays, published
semver releases, version history, bundle entries (text and binary), and the
awkward rows: an instance that declares no apiVersion, a bundle entry whose
instance is gone — then migrate it and prove nothing was lost or misattributed.

They also prove the refusal: where a row's Kind is genuinely undecidable, the
migration fails with the list instead of picking, and the transaction leaves
the database exactly as it was.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

PREVIOUS_REVISION = "0002_quota_counters"

CORE = "github.com/ruinosus/dna/v1"
SDLC = "github.com/ruinosus/dna/sdlc/v1"
POLICY = "github.com/ruinosus/dna/policy/v1"
MEM = "github.com/ruinosus/dna/memory/v1"
#: The namespace a Card used to live under, before it moved to CORE.
MOVED_FROM = "old.example/v1"


# ---------------------------------------------------------------------------
# harness — async because the only Postgres driver this package depends on is
# asyncpg (there is no sync psycopg in the dependency set, and adding one just
# for a test would be a dependency the product does not have).
# ---------------------------------------------------------------------------

#: Tables that revision 0007 (i-111, documento -> instância) renamed. This
#: harness deliberately builds databases in the PRE-0007 era and migrates them,
#: so the PHYSICAL name depends on where in the ladder the database currently
#: is — call sites keep naming the CURRENT name and ``table()`` resolves it.
_RENAMED_AT_0007 = {
    "instances": "documents",
    "layer_instances": "layer_documents",
}


class _Db:
    """A database pinned at ``PREVIOUS_REVISION``, with raw SQL access."""

    def __init__(self, engine, schema: str | None) -> None:
        self.engine = engine
        self.schema = schema
        self.is_pg = engine.dialect.name == "postgresql"
        self.prefix = "dna_" if self.is_pg else ""
        self.migrated = False

    def table(self, name: str) -> str:
        if not self.migrated:
            name = _RENAMED_AT_0007.get(name, name)
        base = f"{self.prefix}{name}"
        return f"{self.schema}.{base}" if self.schema else base

    async def exec(self, stmt: str, params: dict | None = None,
                   binds: list | None = None) -> None:
        text = sa.text(stmt)
        if binds:
            text = text.bindparams(*binds)
        async with self.engine.begin() as conn:
            await conn.execute(text, params or {})

    async def rows(self, stmt: str, params: dict | None = None) -> list:
        async with self.engine.connect() as conn:
            return (await conn.execute(sa.text(stmt), params or {})).all()

    async def count(self, table: str) -> int:
        return (await self.rows(f"SELECT count(*) FROM {self.table(table)}"))[0][0]

    async def alembic(self, revision: str) -> None:
        from alembic import command

        from dna.adapters.sqlalchemy_.migrate import build_config

        schema = self.schema

        def _run(sync_conn):
            command.upgrade(build_config(schema, connection=sync_conn), revision)

        async with self.engine.begin() as conn:
            await conn.run_sync(_run)

    async def upgrade_to_head(self) -> None:
        await self.alembic("head")
        # Only on SUCCESS: a refused migration rolls back, and the refusal
        # tests read the table again afterwards — under its OLD name.
        self.migrated = True


async def _sqlite_db(tmp_path) -> tuple[_Db, Any]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'prod.db'}")
    db = _Db(engine, None)
    await db.alembic(PREVIOUS_REVISION)
    return db, engine.dispose


async def _postgres_db(_tmp_path) -> tuple[_Db, Any]:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("DATABASE_URL not set — skipping Postgres dialect")

    url = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    schema = f"dna_mig_{os.getpid()}_{id(asyncio):x}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await conn.execute(sa.text(f"CREATE SCHEMA {schema}"))
    db = _Db(engine, schema)
    await db.alembic(PREVIOUS_REVISION)

    async def cleanup() -> None:
        async with engine.begin() as conn:
            await conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await engine.dispose()

    return db, cleanup


@pytest.fixture(params=[
    pytest.param(_sqlite_db, id="sqlite"),
    # Marked so the CI Postgres job (`-m requires_postgres`) actually collects
    # this leg; the ordinary job skips it with a reason.
    pytest.param(_postgres_db, id="postgres",
                 marks=pytest.mark.requires_postgres),
])
def db_factory(request, tmp_path):
    async def build() -> tuple[_Db, Any]:
        return await request.param(tmp_path)

    return build


# ---------------------------------------------------------------------------
# the fixture — a deployment's shape, not a toy
# ---------------------------------------------------------------------------

#: (scope, kind, apiVersion-in-content, name, tenant). ``None`` for the
#: apiVersion means the stored instance declares none — the row the founder's
#: question is about.
_DOCS: list[tuple[str, str, str | None, str, str]] = [
    ("acme", "Genome", CORE, "acme", ""),
    ("acme", "Genome", CORE, "acme", "tenant-one"),        # tenant overlay
    ("acme", "Story", SDLC, "s-alpha", ""),
    ("acme", "Story", SDLC, "s-bravo", ""),
    ("acme", "Feature", SDLC, "f-one", ""),
    ("acme", "Agent", CORE, "planner", ""),
    ("acme", "Agent", CORE, "planner", "tenant-one"),
    ("acme", "LayerPolicy", POLICY, "default", ""),
    ("acme", "Engram", MEM, "e-recall-1", ""),
    ("acme", "Engram", MEM, "e-recall-2", "tenant-one"),
    # The undecidable-adjacent case in its BENIGN form: an instance declaring no
    # apiVersion whose Kind name is used by exactly one apiVersion elsewhere.
    # Nothing is inferred for it — it records ''.
    ("acme", "Story", None, "s-legacy", ""),
    ("beta", "Genome", CORE, "beta", ""),
    ("beta", "Story", SDLC, "s-alpha", ""),               # same name, other scope
]

#: (scope, kind, name, tenant, entry_path, body)
_ENTRIES: list[tuple[str, str, str, str, str, Any]] = [
    ("acme", "Agent", "planner", "", "SKILL.md", "# planner"),
    ("acme", "Agent", "planner", "", "assets/logo.bin", b"\x00\x01\x02"),
    ("acme", "Agent", "planner", "tenant-one", "SKILL.md", "# forked"),
    ("acme", "Story", "s-alpha", "", "notes.md", "notes"),
    # Owner published under CORE, archived under MOVED_FROM — the published
    # instance is the one that must win.
    ("acme", "Card", "c-moved", "", "front.md", "moved"),
    # No published row at all: the newest archived version is the only owner.
    ("acme", "Card", "c-unpublished", "", "front.md", "unpublished"),
    # ORPHAN: no instances row and no versions row owns this. Nothing is left
    # to inherit from, so it keeps ''.
    ("acme", "Deck", "gone", "", "leftover.md", "orphan"),
]


def _content(kind: str, api_version: str | None, name: str) -> str:
    raw: dict[str, Any] = {"kind": kind, "metadata": {"name": name},
                           "spec": {"title": name}}
    if api_version is not None:
        raw["apiVersion"] = api_version
    return json.dumps(raw)


def _stored_tenant(db: _Db, tenant: str) -> str | None:
    """[dialect] base-tenant sentinel: ``''`` on pg, ``NULL`` on sqlite."""
    if tenant:
        return tenant
    return "" if db.is_pg else None


def _seeded_docs(db: _Db) -> list[tuple[str, str, str | None, str, str]]:
    """The ``instances`` rows this dialect can actually hold.

    [dialect] i-092: the SQLite ``instances`` primary key does not include
    ``tenant``, so a tenant overlay cannot sit beside its base row there. That
    is pre-existing schema debt this revision deliberately does NOT change —
    widening the key with ``api_version`` is one change, and quietly fixing a
    different key at the same time would hide it. The overlay rows are seeded on
    Postgres only; their ``versions`` and ``bundle_entries`` rows exist on both.
    """
    if db.is_pg:
        return _DOCS
    return [d for d in _DOCS if not d[4]]


async def _seed(db: _Db) -> None:
    docs, vers, entries = (db.table("instances"), db.table("versions"),
                           db.table("bundle_entries"))
    seeded = _seeded_docs(db)
    for scope, kind, api_version, name, tenant in _DOCS:
        body = _content(kind, api_version, name)
        if (scope, kind, api_version, name, tenant) in seeded:
            await db.exec(
                f"INSERT INTO {docs} (scope, kind, name, content, version, "
                "updated_at, tenant) "
                "VALUES (:s, :k, :n, :c, 3, '2026-01-01', :t)",
                {"s": scope, "k": kind, "n": name, "c": body,
                 # [dialect] the base-tenant sentinel a running adapter really
                 # writes: '' on pg (NOT NULL DEFAULT ''), NULL on sqlite.
                 "t": _stored_tenant(db, tenant)},
            )
        # Three archived versions each — the shape an instance that has been
        # edited a few times really has.
        for v in (1, 2, 3):
            await db.exec(
                f"INSERT INTO {vers} (scope, kind, name, content, version, "
                "is_draft, author, created_at, tenant, semver) "
                "VALUES (:s, :k, :n, :c, :v, :d, 'seed', '2026-01-01', :t, :sv)",
                {"s": scope, "k": kind, "n": name, "c": body, "v": v,
                 "d": False, "t": _stored_tenant(db, tenant),
                 # Genome rows carry a published semver (the module catalog).
                 "sv": f"1.0.{v}" if kind == "Genome" else None},
                binds=[sa.bindparam("d", type_=sa.Boolean)],
            )
    # An instance whose apiVersion CHANGED over its history: the published row
    # says CORE, the archived versions still say the old namespace. The two
    # backfill sources for a bundle entry therefore disagree, which is the only
    # way to prove the published instance wins — with identical values either
    # path would look right.
    await db.exec(
        f"INSERT INTO {docs} (scope, kind, name, content, version, updated_at, "
        "tenant) VALUES ('acme', 'Card', 'c-moved', :c, 2, '2026-01-01', :t)",
        {"c": _content("Card", CORE, "c-moved"), "t": _stored_tenant(db, "")},
    )
    await db.exec(
        f"INSERT INTO {vers} (scope, kind, name, content, version, is_draft, "
        "author, created_at, tenant, semver) VALUES ('acme', 'Card', 'c-moved', "
        ":c, 1, :d, 'seed', '2026-01-01', :t, NULL)",
        {"c": _content("Card", MOVED_FROM, "c-moved"), "d": False,
         "t": _stored_tenant(db, "")},
        binds=[sa.bindparam("d", type_=sa.Boolean)],
    )
    # An instance with version history but no published row — the entry has
    # nothing to inherit from except the newest archived version.
    await db.exec(
        f"INSERT INTO {vers} (scope, kind, name, content, version, is_draft, "
        "author, created_at, tenant, semver) VALUES ('acme', 'Card', "
        "'c-unpublished', :c, 1, :d, 'seed', '2026-01-01', :t, NULL)",
        {"c": _content("Card", POLICY, "c-unpublished"), "d": True,
         "t": _stored_tenant(db, "")},
        binds=[sa.bindparam("d", type_=sa.Boolean)],
    )
    for scope, kind, name, tenant, path, payload in _ENTRIES:
        is_bytes = isinstance(payload, bytes)
        if db.is_pg:
            await db.exec(
                f"INSERT INTO {entries} (scope, kind, name, entry_path, "
                "content, updated_at, tenant, content_binary) "
                "VALUES (:s, :k, :n, :p, :c, '2026-01-01', :t, :b)",
                {"s": scope, "k": kind, "n": name, "p": path,
                 "c": "" if is_bytes else payload, "t": tenant,
                 "b": payload if is_bytes else None},
                binds=[sa.bindparam("b", type_=sa.LargeBinary)],
            )
        else:
            await db.exec(
                f"INSERT INTO {entries} (scope, kind, name, entry_path, "
                "content, updated_at, tenant) "
                "VALUES (:s, :k, :n, :p, :c, '2026-01-01', :t)",
                {"s": scope, "k": kind, "n": name, "p": path, "c": payload,
                 "t": tenant},
            )


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migration_preserves_every_row_and_attributes_it_correctly(
    db_factory,
):
    db, cleanup = await db_factory()
    try:
        await _seed(db)
        tables = ("instances", "versions", "bundle_entries")
        before = {t: await db.count(t) for t in tables}

        await db.upgrade_to_head()

        after = {t: await db.count(t) for t in tables}
        print(f"\n[{db.engine.dialect.name}] row counts before: {before}")
        print(f"[{db.engine.dialect.name}] row counts after : {after}")
        assert after == before, (
            "the api_version rekey changed the row count — the new key is a "
            "strict superset of the old one, so this cannot happen unless rows "
            "collided"
        )

        # Every instances/versions row carries EXACTLY what its own content says.
        for table in ("instances", "versions"):
            for scope, kind, name, tenant, api_version, content in await db.rows(
                f"SELECT scope, kind, name, COALESCE(tenant, ''), api_version, "
                f"content FROM {db.table(table)}"
            ):
                declared = json.loads(content).get("apiVersion") or ""
                assert api_version == declared, (
                    f"{table} row (scope={scope} kind={kind} name={name} "
                    f"tenant={tenant}) was attributed {api_version!r} but its "
                    f"instance declares {declared!r}"
                )

        # The instance that declares nothing keeps '' — not the apiVersion of
        # the other Story rows. Nothing was inferred for it.
        assert await db.rows(
            f"SELECT api_version FROM {db.table('instances')} "
            "WHERE name = 's-legacy'"
        ) == [("",)]

        # Bundle entries inherited their instance's apiVersion...
        owned = dict(await db.rows(
            f"SELECT entry_path || '@' || tenant, api_version "
            f"FROM {db.table('bundle_entries')} WHERE kind = 'Agent'"
        ))
        assert owned == {"SKILL.md@": CORE, "assets/logo.bin@": CORE,
                         "SKILL.md@tenant-one": CORE}, owned
        assert await db.rows(
            f"SELECT api_version FROM {db.table('bundle_entries')} "
            "WHERE kind = 'Story'"
        ) == [(SDLC,)]
        # The published instance wins over the archived versions...
        assert await db.rows(
            f"SELECT api_version FROM {db.table('bundle_entries')} "
            "WHERE name = 'c-moved'"
        ) == [(CORE,)]
        # ...and with no published row, the newest archived version is used.
        assert await db.rows(
            f"SELECT api_version FROM {db.table('bundle_entries')} "
            "WHERE name = 'c-unpublished'"
        ) == [(POLICY,)]
        # ...and the orphan, with no instance to inherit from, kept ''.
        assert await db.rows(
            f"SELECT api_version FROM {db.table('bundle_entries')} "
            "WHERE kind = 'Deck'"
        ) == [("",)]

        # Content itself is byte-identical — the migration touched keys, not data.
        for scope, kind, api_version, name, tenant in _seeded_docs(db):
            stored = await db.rows(
                f"SELECT content FROM {db.table('instances')} WHERE scope = :s "
                "AND kind = :k AND name = :n AND COALESCE(tenant, '') = :t",
                {"s": scope, "k": kind, "n": name, "t": tenant},
            )
            assert stored == [(_content(kind, api_version, name),)], (
                f"content changed for {scope}/{kind}/{name}"
            )
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_the_adapter_reads_a_migrated_database_back(db_factory):
    """After the migration the running adapter serves the same instances."""
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    db, cleanup = await db_factory()
    src = None
    try:
        await _seed(db)
        await db.upgrade_to_head()

        src = SqlAlchemySource(
            db.engine.url.render_as_string(hide_password=False),
            schema=db.schema,
        )
        await src.connect()  # idempotent — already at head
        docs = await src.load_all("acme")
        found = {(d.get("kind"), (d.get("metadata") or {}).get("name"))
                 for d in docs}
        assert ("Story", "s-alpha") in found
        assert ("Story", "s-legacy") in found, (
            "the instance that declares no apiVersion stopped being visible"
        )
        # Bare reads answer exactly as they did before the column existed.
        one = await src.load_one("acme", "Agent", "planner")
        assert one is not None and one["apiVersion"] == CORE
        # And a pinned read now resolves the exact Kind.
        assert await src.load_one(
            "acme", "Agent", "planner", api_version=CORE) == one
        # The bundle survived, including the binary entry.
        assert await src.fetch_bundle_entry(
            "acme", "Agent", "planner", "SKILL.md") == b"# planner"
        assert await src.fetch_bundle_entry(
            "acme", "Agent", "planner", "assets/logo.bin") == b"\x00\x01\x02"
        # Version history is intact.
        assert len(await src.list_versions("acme", "Story", "s-alpha")) == 3
        # The Genome module catalog still lists its published releases.
        cat = await src.list_module_versions("acme")
        assert [e["version"] for e in cat] == ["1.0.1", "1.0.2", "1.0.3"]
        # And a NEW write lands next to the migrated rows without disturbing them.
        await src.save_instance("acme", "Story", "s-alpha", {
            "apiVersion": SDLC, "kind": "Story",
            "metadata": {"name": "s-alpha"}, "spec": {"title": "edited"},
        })
        assert (await src.load_one("acme", "Story", "s-alpha"))["spec"]["title"] \
            == "edited"
        assert len(await src.list_versions("acme", "Story", "s-alpha")) == 4
    finally:
        if src is not None:
            await src.close()
        await cleanup()


@pytest.mark.asyncio
async def test_an_undecidable_row_refuses_the_migration_with_the_list(db_factory):
    """The ambiguity is the point: refuse and name the rows, never pick.

    Two Kinds named ``Deal`` under different namespaces, plus a third row that
    declares no apiVersion at all. Nothing in the database says which of the two
    that row belongs to, and writing a guess into a column that is about to be
    part of the identity would make the ambiguity permanent.
    """
    db, cleanup = await db_factory()
    try:
        docs = db.table("instances")
        for api_version, name in (("a.example/v1", "d-1"),
                                  ("b.example/v1", "d-2"),
                                  (None, "d-3")):
            await db.exec(
                f"INSERT INTO {docs} (scope, kind, name, content, version, "
                "updated_at, tenant) VALUES ('acme', 'Deal', :n, :c, 1, "
                "'2026-01-01', '')",
                {"n": name, "c": _content("Deal", api_version, name)},
            )
        before = await db.count("instances")

        with pytest.raises(RuntimeError) as exc:
            await db.upgrade_to_head()

        message = str(exc.value)
        print(f"\n[{db.engine.dialect.name}] refusal:\n{message}")
        assert "declare no apiVersion" in message, message
        assert "name='d-3'" in message, (
            f"the refusal did not name the offending row:\n{message}")
        assert "a.example/v1, b.example/v1" in message, (
            f"the refusal did not list the candidate Kinds:\n{message}")

        # The transaction rolled back: the database is exactly as it was, still
        # on the previous revision, still serving.
        assert await db.count("instances") == before
        prefix = f"{db.schema}." if db.schema else ""
        revision = await db.rows(f"SELECT version_num FROM {prefix}alembic_version")
        assert revision == [(PREVIOUS_REVISION,)], (
            f"the failed migration left the database at {revision} — a "
            "partially applied rekey is worse than a refused one"
        )
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_a_source_that_connects_migrates_the_database_it_finds(db_factory):
    """The adapter's posture on an unmigrated database: MIGRATE, on connect.

    That is not new — ``connect()`` has always applied the schema, deliberately,
    because this library owns tables inside its consumer's database and those
    consumers boot several processes expecting the schema to be there. Adding a
    column that joins the row key does not change the posture; it just makes the
    property worth restating: after connect there is no such thing as a
    half-keyed table.
    """
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    db, cleanup = await db_factory()
    src = None
    try:
        await _seed(db)
        src = SqlAlchemySource(
            db.engine.url.render_as_string(hide_password=False),
            schema=db.schema,
        )
        applied = await src.run_schema_migrations()
        assert "0003_api_version" in applied, applied
        assert (await src.load_one("acme", "Story", "s-alpha")) is not None
        assert await src.run_schema_migrations() == [], (
            "re-running the migration applied something a second time"
        )
    finally:
        if src is not None:
            await src.close()
        await cleanup()


@pytest.mark.asyncio
async def test_an_unmigrated_database_fails_loudly_instead_of_answering(db_factory):
    """A read against the OLD shape errors; it never answers half-right.

    The only unacceptable outcome is a silent wrong answer. If a caller
    bypasses ``connect()``/``run_schema_migrations()`` and queries a database
    that still has the pre-0003 tables, every keyed statement names a column
    that is not there, so the database itself refuses. Asserted here because
    "it would obviously fail" is the kind of claim that stops being true the
    day someone adds a fallback.
    """
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    db, cleanup = await db_factory()
    src = None
    try:
        await _seed(db)
        src = SqlAlchemySource(
            db.engine.url.render_as_string(hide_password=False),
            schema=db.schema,
        )
        with pytest.raises(sa.exc.DatabaseError) as exc:
            await src.load_all("acme")   # NOTE: no connect()
        assert "api_version" in str(exc.value)
    finally:
        if src is not None:
            await src.close()
        await cleanup()


@pytest.mark.asyncio
async def test_a_writer_that_predates_the_column_still_produces_readable_rows(
    db_factory,
):
    """An OLD SDK writing into a MIGRATED database degrades, never corrupts.

    A process running a pre-0003 build inserts without naming ``api_version``.
    The column's ``DEFAULT ''`` catches that: the row lands as "declares no
    apiVersion", which is what a writer that does not know about the column can
    honestly claim, and the current adapter serves it on a bare read exactly as
    it always did. The row is simply not reachable by a PINNED read — correct,
    since nothing about it says which Kind it is.
    """
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    db, cleanup = await db_factory()
    src = None
    try:
        await db.upgrade_to_head()
        # Verbatim the INSERT the pre-0003 adapter emitted.
        await db.exec(
            f"INSERT INTO {db.table('instances')} (scope, kind, name, content, "
            "version, updated_at, tenant) "
            "VALUES ('acme', 'Story', 's-old', :c, 1, '2026-01-01', :t)",
            {"c": _content("Story", SDLC, "s-old"),
             "t": _stored_tenant(db, "")},
        )
        assert await db.rows(
            f"SELECT api_version FROM {db.table('instances')}"
        ) == [("",)]

        src = SqlAlchemySource(
            db.engine.url.render_as_string(hide_password=False),
            schema=db.schema,
        )
        await src.connect()
        assert (await src.load_one("acme", "Story", "s-old")) is not None
        assert await src.load_one(
            "acme", "Story", "s-old", api_version=SDLC) is None
    finally:
        if src is not None:
            await src.close()
        await cleanup()


@pytest.mark.asyncio
async def test_an_undeclared_row_is_not_inferred_from_its_neighbours(db_factory):
    """One candidate is still not evidence — the row records ``''``.

    The temptation is to say "every other Story here is sdlc/v1, so this one is
    too". That is the same guess the refusal exists to prevent, one instance
    smaller, and the instance itself says nothing. ``''`` is a fact about the
    row; the neighbour's apiVersion would be a story about it.
    """
    db, cleanup = await db_factory()
    try:
        docs = db.table("instances")
        for api_version, name in ((SDLC, "s-one"), (None, "s-two")):
            await db.exec(
                f"INSERT INTO {docs} (scope, kind, name, content, version, "
                "updated_at, tenant) VALUES ('acme', 'Story', :n, :c, 1, "
                "'2026-01-01', '')",
                {"n": name, "c": _content("Story", api_version, name)},
            )

        await db.upgrade_to_head()

        # Re-resolved on purpose: revision 0007 renamed the table under it.
        assert dict(await db.rows(
            f"SELECT name, api_version FROM {db.table('instances')}"
        )) == {"s-one": SDLC, "s-two": ""}
    finally:
        await cleanup()
