"""Public testing kit for SDK port adapters (s-dna-source-conformance-kit).

Ship-with-the-SDK compliance suites, in the spirit of the DB-API
compliance suite: an adapter author hands us a *factory* for their
adapter and gets back the battery of cases every conforming
implementation must pass.

    from dna.testing import source_conformance_suite

    async def my_factory():
        src = MySource(...)
        async def cleanup():
            await src.close()
        return src, cleanup

    # pytest consumption — one test per case:
    import pytest
    CASES = source_conformance_suite(my_factory)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
    async def test_source_conformance(case):
        await case.run()

Division of labor (keep this straight):
  - ``kernel.source()`` boot gate  → NAMES ONLY (runtime_checkable
    Protocols can't check behavior). First line of defense.
  - THIS kit                       → BEHAVIOR, capability-aware: it reads
    the adapter's declared ``SourceCapabilities`` and fails when a
    declared capability isn't honored. The real safety net.
"""
from dna.testing.source_conformance import (
    FIXTURE_SCOPE,
    CaseNotApplicable,
    ConformanceCase,
    ConformanceReport,
    fixture_docs,
    run_source_conformance,
    source_conformance_suite,
)
from dna.testing.rw_conformance import (
    RWConformanceCase,
    default_fixture,
    reader_writer_conformance_suite,
)
from dna.testing.memory_conformance import (
    MEMORY_FIXTURE_SCOPE,
    MemoryCaseNotApplicable,
    MemoryConformanceCase,
    MemoryConformanceReport,
    MemoryScoringCase,
    fixture_memories,
    memory_conformance_suite,
    memory_scoring_conformance_suite,
    run_memory_conformance,
    run_memory_scoring_conformance,
)
from dna.testing.record_search_conformance import (
    RecordSearchCase,
    RecordSearchReport,
    SearchCaseNotApplicable,
    fixture_records,
    record_search_conformance_suite,
    run_record_search_conformance,
)
from dna.testing.stubs import CoreSourceStub

__all__ = [
    "FIXTURE_SCOPE",
    "MEMORY_FIXTURE_SCOPE",
    "CaseNotApplicable",
    "ConformanceCase",
    "ConformanceReport",
    "CoreSourceStub",
    "MemoryCaseNotApplicable",
    "MemoryConformanceCase",
    "MemoryConformanceReport",
    "MemoryScoringCase",
    "RWConformanceCase",
    "RecordSearchCase",
    "RecordSearchReport",
    "SearchCaseNotApplicable",
    "default_fixture",
    "fixture_memories",
    "memory_conformance_suite",
    "memory_scoring_conformance_suite",
    "reader_writer_conformance_suite",
    "record_search_conformance_suite",
    "run_memory_conformance",
    "run_memory_scoring_conformance",
    "run_record_search_conformance",
    "fixture_docs",
    "fixture_records",
    "run_source_conformance",
    "source_conformance_suite",
]
