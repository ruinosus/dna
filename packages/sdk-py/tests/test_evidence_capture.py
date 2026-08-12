"""Tests for evidence auto-capture via post_save hook.

i-107 slice 2 — the two literal Kind-name checks this path carried are gone:

    _EVAL_KINDS = {"EvalRun", "EvalBaseline", "Finding"}   → `record.produces-evidence`
    if kind == "Evidence"                                  → `record.is-evidence`

⚠️ ``"Finding"`` was in that literal set and is NOT a registered Kind (measured
12/08/2026: ``kind_port_for("Finding")`` returns None). The old
``test_extract_suite_from_finding_source`` below therefore asserted behaviour
for a Kind that does not exist, and passed — because a literal set answers for
any string you put in it. A declaration cannot: there is no port to hang the
trait on. That is the difference the swap buys, and it is why the replacement
test names a Kind that is really registered.
"""
import pytest

from dna.kernel import Kernel
from dna.kernel.kinds.base import KindBase
from dna.kernel.protocols import StorageDescriptor
from dna.kernel.write.evidence import (
    TRAIT_IS_EVIDENCE,
    TRAIT_PRODUCES_EVIDENCE,
    extract_suite,
)
from dna.extensions.evidence.builder import compute_content_hash


@pytest.fixture(scope="module")
def kernel():
    return Kernel.auto()


@pytest.fixture(scope="module")
def producing(kernel):
    return kernel.kinds_with_trait(TRAIT_PRODUCES_EVIDENCE)


def test_compute_content_hash_canonical():
    assert compute_content_hash({"b": 2, "a": 1}) == compute_content_hash({"a": 1, "b": 2})


# ---------------------------------------------------------------- the traits


def test_the_evidence_producers_are_declared_not_listed(producing):
    """The set comes from the descriptors, so this asserts the declarations
    are actually in place — not that a literal in the kernel still says so."""
    assert producing == {"EvalRun", "EvalBaseline"}


def test_exactly_one_kind_declares_itself_evidence(kernel):
    assert kernel.kinds_with_trait(TRAIT_IS_EVIDENCE) == {"Evidence"}


def test_finding_was_a_dead_entry_in_the_literal_set(kernel):
    """The evidence the docstring above rests on. If Finding is ever really
    registered, this fails and the story in the docstring must be retold."""
    assert kernel.kind_port_for("Finding") is None
    assert "Finding" not in kernel.kinds_with_trait(TRAIT_PRODUCES_EVIDENCE)


# ------------------------------------------------------------- extract_suite


def test_extract_suite_from_eval_run(producing):
    assert extract_suite(
        "EvalRun", {"suite": "smoke"}, None, producing_kinds=producing,
    ) == "smoke"


def test_extract_suite_from_source_field(producing):
    """Replaces test_extract_suite_from_finding_source — same contract (the
    `source` field is the fallback for `suite`), asserted on a Kind that is
    actually registered and actually declares the trait."""
    assert extract_suite(
        "EvalBaseline", {"source": "screening-reads"}, None,
        producing_kinds=producing,
    ) == "screening-reads"


def test_extract_suite_explicit_overrides(producing):
    assert extract_suite(
        "EvalRun", {"suite": "old"}, "explicit", producing_kinds=producing,
    ) == "explicit"


def test_extract_suite_non_producing_kind(producing):
    assert extract_suite(
        "Agent", {"suite": "irrelevant"}, None, producing_kinds=producing,
    ) is None


def test_no_registry_means_no_suite_never_the_old_literal_set():
    """⚠️ The anti-fallback assertion. If ``producing_kinds`` is omitted the
    answer is None — it must NOT quietly revert to {"EvalRun", "EvalBaseline",
    "Finding"}. A silent fallback would let a caller that forgot to pass the
    set keep working against a closed list, which is exactly what this change
    removed."""
    assert extract_suite("EvalRun", {"suite": "smoke"}, None) is None


# --------------------------------------------- the point: a Kind nobody knew


def test_a_kind_the_kernel_never_heard_of_can_produce_evidence():
    """⭐ What the trait buys. Before, evidence production was a closed set of
    three names in the kernel; a tenant-authored Kind could not join it, and
    there was no way to ask. Now it declares the trait and is in."""
    class _MarketAudit(KindBase):
        api_version = "market.example/v1"
        kind = "MarketAudit"
        alias = "market-marketaudit"
        storage = StorageDescriptor.yaml("marketaudits")
        traits = frozenset({TRAIT_PRODUCES_EVIDENCE})

    k = Kernel.auto()
    k.kind(_MarketAudit())

    producing = k.kinds_with_trait(TRAIT_PRODUCES_EVIDENCE)
    assert "MarketAudit" in producing, (
        "a Kind that DECLARES record.produces-evidence must be in the set even "
        "though the kernel has no line of code about it"
    )
    assert extract_suite(
        "MarketAudit", {"suite": "quarterly"}, None, producing_kinds=producing,
    ) == "quarterly", "and it must get the same suite-stamping behaviour"


def test_a_tenant_can_run_its_own_evidence_kind():
    """The other half: `record.is-evidence` is not pinned to the built-in
    name either. The trait's description says more than one is legal; this is
    that claim, executed."""
    class _MarketEvidence(KindBase):
        api_version = "market.example/v1"
        kind = "MarketEvidence"
        alias = "market-marketevidence"
        storage = StorageDescriptor.yaml("marketevidences")
        traits = frozenset({TRAIT_IS_EVIDENCE})

    k = Kernel.auto()
    k.kind(_MarketEvidence())
    assert k.kinds_with_trait(TRAIT_IS_EVIDENCE) == {"Evidence", "MarketEvidence"}
