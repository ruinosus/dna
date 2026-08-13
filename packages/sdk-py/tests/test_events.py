"""i-107 slice 3 — the post_save event_type is DECLARED by the Kind.

``kernel/boot/events.py`` used to hold ``_FIXED_EVENTS`` and ``_SPLIT_EVENTS``:
three Kind names, in the kernel, for three Kinds that live in extensions. The
tests below used to call ``derive_event_type("EvalRun", ...)`` with no registry
and assert against those dicts — which is to say they asserted the kernel's copy
of somebody else's fact.

They now go through a real registry, so what is asserted is that the
DECLARATION (``spec.post_save_event`` in the descriptor) is read.
"""
import pytest

from dna.kernel import Kernel
from dna.kernel.boot.events import derive_event_type, event_type_for_port
from dna.kernel.kinds.base import KindBase
from dna.kernel.protocols import StorageDescriptor


@pytest.fixture(scope="module")
def kernel():
    return Kernel.auto()


# ------------------------------------------------- declared, from a descriptor


def test_eval_run_is_completed_on_create_and_update(kernel):
    """A single declared string means one name for both transitions — a run is
    "completed" whether the row is new or rewritten."""
    assert derive_event_type("EvalRun", is_update=False, kernel=kernel) == "eval_run_completed"
    assert derive_event_type("EvalRun", is_update=True, kernel=kernel) == "eval_run_completed"


def test_eval_baseline_is_pinned(kernel):
    assert derive_event_type("EvalBaseline", is_update=False, kernel=kernel) == "baseline_pinned"
    assert derive_event_type("EvalBaseline", is_update=True, kernel=kernel) == "baseline_pinned"


def test_the_declaration_really_comes_from_the_descriptor(kernel):
    """Not from a table that happens to agree. Read it off the port."""
    assert getattr(kernel.kind_port_for("EvalRun"), "post_save_event", None) == "eval_run_completed"
    assert getattr(kernel.kind_port_for("EvalBaseline"), "post_save_event", None) == "baseline_pinned"


# ------------------------------------------------------------------- generic


def test_ordinary_kinds_get_the_generic_pair(kernel):
    assert derive_event_type("Agent", is_update=False, kernel=kernel) == "document_created"
    assert derive_event_type("Skill", is_update=False, kernel=kernel) == "document_created"
    assert derive_event_type("Agent", is_update=True, kernel=kernel) == "document_modified"
    assert derive_event_type("Soul", is_update=True, kernel=kernel) == "document_modified"


def test_no_kernel_means_generic_never_the_old_table():
    """⚠️ The anti-fallback assertion. Called without a registry there is
    nothing to read, so every Kind is generic. It must NOT quietly fall back to
    the old three-name table — a silent fallback would let a caller that forgot
    to pass the kernel keep working against a closed list."""
    assert derive_event_type("EvalRun", is_update=False) == "document_created"
    assert derive_event_type("EvalRun", is_update=True) == "document_modified"


def test_finding_is_gone_because_it_was_never_a_registered_kind(kernel):
    """``_SPLIT_EVENTS`` held ``Finding`` and ``Finding`` is not registered
    (measured 12/08/2026). A dict can hold a key for a Kind that does not
    exist; a declaration has to live on something. Its entry disappeared with
    no replacement, and that is the correct outcome."""
    assert kernel.kind_port_for("Finding") is None
    assert derive_event_type("Finding", is_update=False, kernel=kernel) == "document_created"


# ---------------------------------------------------- the split pair, declared


def test_a_kind_may_declare_a_create_update_pair():
    """The shape ``_SPLIT_EVENTS`` existed for, now declarable by any Kind."""
    class _Ticket(KindBase):
        api_version = "market.example/v1"
        kind = "Ticket"
        alias = "market-ticket"
        storage = StorageDescriptor.yaml("tickets")
        post_save_event = ("ticket_opened", "ticket_status_changed")

    k = Kernel.auto()
    k.kind(_Ticket())
    assert derive_event_type("Ticket", is_update=False, kernel=k) == "ticket_opened"
    assert derive_event_type("Ticket", is_update=True, kernel=k) == "ticket_status_changed"


def test_a_yaml_declared_pair_arrives_as_a_list_and_still_works():
    """YAML has no tuples. The descriptor path must behave identically to the
    class path, or a Kind author sees a difference they cannot explain."""
    port = type("P", (), {"post_save_event": ["opened", "changed"]})()
    assert event_type_for_port(port, is_update=False) == "opened"
    assert event_type_for_port(port, is_update=True) == "changed"


def test_a_malformed_declaration_degrades_instead_of_failing_the_write():
    """This runs inside post_save emission. Raising would fail a WRITE that
    already succeeded, because its notification is misdeclared — the row is
    good, so degrading the event name is the proportionate response."""
    for bad in (["only-one"], ["a", "b", "c"], 42, {"a": 1}):
        port = type("P", (), {"post_save_event": bad})()
        assert event_type_for_port(port, is_update=False) == "document_created"
        assert event_type_for_port(port, is_update=True) == "document_modified"


# ------------------------------------------------ the point: an unknown Kind


def test_a_tenant_kind_can_finally_name_its_own_event():
    """⭐ Why this slice is worth more than tidiness. EvidencePolicy selects
    which writes to capture BY event_type. A Kind whose event_type could only
    be ``document_created`` could not be named by a policy written against a
    meaningful event — so a tenant-authored Kind could not participate in
    evidence capture at all, and there was no way to ask for it."""
    class _Deployment(KindBase):
        api_version = "market.example/v1"
        kind = "Deployment"
        alias = "market-deployment"
        storage = StorageDescriptor.yaml("deployments")
        post_save_event = "deployment_completed"

    k = Kernel.auto()
    k.kind(_Deployment())
    assert derive_event_type("Deployment", is_update=False, kernel=k) == "deployment_completed"
    assert derive_event_type("Deployment", is_update=True, kernel=k) == "deployment_completed"
