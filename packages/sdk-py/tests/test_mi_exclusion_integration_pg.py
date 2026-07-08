"""F2.5 two-planes Task 3: integration proof that the MI is O(composição).

Against a real Postgres source holding the `dna-development` scope (~14.7k
docs, overwhelmingly records), `kernel.instance_async` must materialize a
SMALL composition-only MI (< 500 docs) while `kernel.count` proves the
records exist in the source — i.e. the exclusion hit the build, not the
data.

PG-gated (DATABASE_URL / DNA_PG_TEST_URL — same gate as
test_postgres_source.py). Additionally SKIPS when the database has no
`dna-development` records (clean CI databases): this test proves a
property of the real dev dataset; the unit half lives in
test_mi_record_exclusion.py.
"""
from __future__ import annotations

import os
import time

import pytest

pytestmark = [
    pytest.mark.requires_postgres,
    pytest.mark.asyncio,
]

SCOPE = "dna-development"
RECORD_KINDS_PROBE = ("Story", "Issue", "LessonLearned")


def _dsn() -> str:
    return (
        os.environ.get("DNA_SOURCE_URL")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("DNA_PG_TEST_URL")
        or ""
    )


@pytest.mark.asyncio
async def test_dna_development_mi_materializes_composition_only(tmp_path):
    import asyncpg
    from dna.adapters.filesystem import FilesystemCache
    from dna.adapters.postgres import PostgresSource
    from dna.kernel import Kernel

    dsn = _dsn()
    pool = await asyncpg.create_pool(dsn)
    try:
        k = Kernel.auto()
        src = PostgresSource(pool)
        k._source = src  # bypass Protocol isinstance (test pattern)
        k.cache(FilesystemCache(str(tmp_path / ".dna-cache")))

        # 1. Prove the records EXIST in the source (kernel.count push-down).
        record_counts: dict[str, int] = {}
        for kind in RECORD_KINDS_PROBE:
            assert k.kind_plane(kind) == "record", f"{kind} must be plane=record"
            res = await k.count(SCOPE, kind)
            record_counts[kind] = res["total"]
        total_records_probed = sum(record_counts.values())
        if total_records_probed == 0:
            pytest.skip(
                f"{SCOPE} has no record docs in this database — "
                "dataset-dependent proof, see test_mi_record_exclusion.py "
                "for the unit half",
            )

        # 2. Materialize the MI cold and time it (report metric).
        t0 = time.perf_counter()
        mi = await k.instance_async(SCOPE, lazy=False)
        elapsed = time.perf_counter() - t0
        n_docs = len(mi.documents)
        print(
            f"\n[F2.5 Task 3] {SCOPE}: MI materialized {n_docs} docs in "
            f"{elapsed:.3f}s; records in source (probe {RECORD_KINDS_PROBE}): "
            f"{record_counts} (sum={total_records_probed})",
        )

        # 3. The MI is O(composição): small, and record-free.
        assert n_docs < 500, (
            f"MI must be composition-only (<500 docs), got {n_docs} — "
            "record exclusion not effective"
        )
        assert total_records_probed > n_docs, (
            "sanity: probed records must outnumber the whole MI "
            f"({total_records_probed} vs {n_docs})"
        )
        record_kinds_in_mi = {
            d.kind for d in mi.documents if k.kind_plane(d.kind) == "record"
        }
        assert record_kinds_in_mi == set(), (
            f"record kinds leaked into the MI: {record_kinds_in_mi}"
        )

        # 4. Delegation keeps record reads correct THROUGH the MI surface.
        # NB: >= not == — kernel.query unions the _lib inheritance
        # pass while kernel.count is strictly per-scope (spec D5).
        biggest = max(record_counts, key=lambda kk: record_counts[kk])
        docs = await mi.all_async(biggest)
        assert len(docs) >= record_counts[biggest]
    finally:
        await pool.close()
