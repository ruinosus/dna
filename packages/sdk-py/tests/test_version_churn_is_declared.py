"""i-107 — version-history churn is DECLARED by the Kind, not listed by the kernel.

``kernel/write/pipeline.py`` capped retained version history from
``kernel/__init__.py::VERSION_CHURN_KINDS``, a literal set of three Kind names.
It was never the source of truth: the line ABOVE the membership test already
read ``getattr(port, "version_retention", None)`` and won when present, so the
set was the FALLBACK for Kinds that declared nothing — which is to say a second
copy of a per-Kind fact.

⭐ NOT A NEW TRAIT. ``version_retention`` is already a ``KindPort`` attribute AND
a descriptor field (``spec.version_retention``, validated by
``KindDefinitionSpec.parse`` down to "must be >= 1"). A ``record.churny`` trait
would be its THIRD spelling — the exact overdo ``kinds/vocabulary.py`` refuses:
*"a trait that merely restates [a fact] already declared twice"*. The fix is to
delete the copy, not to add a vocabulary. Same shape as
``test_scope_inheritance_is_declared.py``, one axis over.

⚠️ The field was one of the two the ratchet's own docstring names as **shipped
declarative with ZERO adopters** — *"a declarative mechanism nobody is forced to
use is a mechanism nobody uses"*. It had zero adopters because the kernel's set
answered for the only two Kinds that needed it. Engram and Canvas are its first
two, and they are the ones the set used to name.

What the set could not do
-------------------------
A tenant whose autopilot rewrites its own Kind ten thousand times had no way to
say so. Not "was not configured to" — the set lived in the kernel, so the answer
required an upstream edit. ``test_a_kind_the_kernel_has_never_heard_of_can_declare_it``
is the proof that it now does, which is the test that says the translation
finished rather than merely moved.
"""
from __future__ import annotations

import pytest

from dna.kernel import (
    Kernel,
    LEGACY_VERSION_CHURN_KINDS,
    VERSION_CHURN_RETENTION,
)
from dna.kernel.kinds.base import KindBase
from dna.kernel.protocols import StorageDescriptor

#: The literal set as it stood immediately before deletion. Frozen HERE, in the
#: test, on purpose: a parity proof whose "before" side can be edited by the
#: change it is proving is not a proof. Never import this from production code.
LITERAL_BEFORE_DELETION = frozenset({"Engram", "Canvas", "VibeSession"})


@pytest.fixture(scope="module")
def kernel():
    return Kernel.auto()


def _declared_retention(kernel) -> dict[str, int]:
    """Every REGISTERED Kind that declares ``version_retention``, derived."""
    out: dict[str, int] = {}
    for port in kernel.kind_ports():
        value = getattr(port, "version_retention", None)
        if value is not None:
            out[port.kind] = value
    return out


def test_the_derived_set_preserves_every_member_of_the_old_list(kernel):
    """FIDELITY — the assertion that had to pass BEFORE the set was deleted.

    Nothing the literal set capped may start keeping unbounded history because
    the set went away. Each old member is now covered either by its own
    declaration or by the legacy tombstone set, and by nothing else.
    """
    declared = set(_declared_retention(kernel))
    covered = declared | set(LEGACY_VERSION_CHURN_KINDS)
    lost = sorted(LITERAL_BEFORE_DELETION - covered)
    assert not lost, (
        "Deleting VERSION_CHURN_KINDS changed behaviour for these Kinds — they "
        f"used to be capped and now keep full history: {lost}\n\n"
        "Each must declare `version_retention` on its Kind class or "
        "`version_retention: <n>` in its descriptor. Do NOT re-add the set."
    )


def test_the_two_registered_members_declare_it_themselves(kernel):
    """The set's two REGISTERED members are the field's first two adopters.

    Spelled out rather than folded into the fidelity test above, because
    "covered" there also accepts the tombstone escape hatch — and a Kind that
    HAS a class quietly falling through to the tombstone set would be the
    regression, not the fix.
    """
    declared = _declared_retention(kernel)
    for kind in ("Engram", "Canvas"):
        assert declared.get(kind) == VERSION_CHURN_RETENTION, (
            f"{kind} must declare version_retention={VERSION_CHURN_RETENTION} "
            f"itself; got {declared.get(kind)!r}. It was in VERSION_CHURN_KINDS "
            "and the kernel no longer knows its name."
        )
        assert kind not in LEGACY_VERSION_CHURN_KINDS, (
            f"{kind} has a Kind port to declare on — the tombstone set is only "
            "for retired doc-kinds with nothing to declare on."
        )


def test_the_tombstone_survives_the_derivation():
    """``VibeSession`` is a retired doc-kind that never got a Kind class (the
    same reason it rides ``Kernel._LEGACY_NON_INHERITABLE``). There is nothing
    to declare ON, and a stale row must not start accumulating unbounded
    history just because its Kind was retired."""
    assert LEGACY_VERSION_CHURN_KINDS == frozenset({"VibeSession"}), (
        "The tombstone set only SHRINKS. A Kind that is registered today "
        "declares `version_retention` itself; adding a name here means "
        "claiming it has no Kind port, which is checkable — check it."
    )


def test_the_tombstone_set_holds_no_registered_kind(kernel):
    """The escape hatch cannot be used as a shortcut: every name in it must
    genuinely have no Kind port, or it is a literal list wearing a tombstone."""
    registered = {p.kind for p in kernel.kind_ports()}
    assert len(registered) > 50, "the registry oracle looks empty"
    smuggled = sorted(LEGACY_VERSION_CHURN_KINDS & registered)
    assert not smuggled, (
        f"{smuggled} are REGISTERED Kinds sitting in the tombstone set. They "
        "can declare `version_retention` themselves — move the declaration to "
        "the Kind and drop the name."
    )


def test_authored_kinds_still_keep_full_history(kernel):
    """The negative case. Story/Spec/ADR are record-plane but AUTHORED — the
    distinction the curated set existed to draw against a blanket
    ``plane == record`` rule, and it must survive the set's deletion."""
    declared = _declared_retention(kernel)
    for authored in ("Story", "Spec", "ADR", "Feature", "Plan"):
        assert authored not in declared, (
            f"{authored} is AUTHORED — capping its history is the bug the "
            "curated set existed to avoid, and the declaration must not "
            "reintroduce it."
        )
        assert authored not in LEGACY_VERSION_CHURN_KINDS


@pytest.mark.asyncio
async def test_a_kind_the_kernel_has_never_heard_of_can_declare_it(tmp_path):
    """⭐ THE POINT OF THE SLICE — and the thing a literal set could never do.

    A Kind invented here, registered at runtime, that the kernel has no line of
    code about, declares ``version_retention`` and gets EXACTLY the pruning the
    built-in churn Kinds get. Its sibling, declaring nothing, keeps every
    version. Same assertion the ratchet demands of every translation: a
    tenant-authored Kind must receive the same behaviour as a built-in one, or
    the translation only moved the knowledge instead of opening it.
    """
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    class _TenantJournal(KindBase):
        api_version = "market.example/v1"
        kind = "TenantJournal"
        alias = "market-tenantjournal"
        storage = StorageDescriptor.yaml("tenantjournals")
        version_retention = 3

    class _TenantCharter(KindBase):
        api_version = "market.example/v1"
        kind = "TenantCharter"
        alias = "market-tenantcharter"
        storage = StorageDescriptor.yaml("tenantcharters")
        # declares nothing → full history, the default

    source = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp_path / 'churn.db'}")
    await source.connect()
    k = Kernel()
    k.kind(_TenantJournal())
    k.kind(_TenantCharter())
    k.source(source)
    try:
        for i in range(5):
            await k.write_instance("s", "TenantJournal", "j", {"spec": {"i": i}})
            await k.write_instance("s", "TenantCharter", "c", {"spec": {"i": i}})

        journal = await source.list_versions("s", "TenantJournal", "j")
        charter = await source.list_versions("s", "TenantCharter", "c")
        assert len(journal) == 3, (
            "a Kind that DECLARES version_retention must be pruned even though "
            "the kernel has never heard of it — if this fails, the kernel is "
            f"still deciding by name (got {len(journal)} versions)"
        )
        assert len(charter) == 5
    finally:
        await source.close()


def test_the_literal_set_is_gone():
    """It must not come back. A second copy of a per-Kind fact is what let the
    scope-inheritance list drift three times."""
    import dna.kernel as kernel_module

    assert not hasattr(kernel_module, "VERSION_CHURN_KINDS"), (
        "VERSION_CHURN_KINDS is back. Version churn is declared by the Kind "
        "(`version_retention`), read by the write pipeline. A literal set is a "
        "second copy, and the kernel does not know Kind names."
    )
