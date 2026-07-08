"""Unit tests for the InvalidationController collaborator (kernel-decompose-continue).

The controller is STATELESS (back-ref to the kernel); state — batch depth,
write-observers, holders — stays on the kernel. These pin the cache-coherence
behavior: Evidence-skip, schema-affecting base drop, holder reload, observer
fan-out, and batch_writes coalescing. The cross-process EventBus path is covered
by test_eventbus.py via the kernel delegators.
"""
from __future__ import annotations

from dna.kernel import Kernel
from dna.kernel.invalidation import InvalidationController


class _StubHolder:
    def __init__(self, scope):
        self.scope = scope
        self.reloads = 0

    def reload(self):
        self.reloads += 1


def test_kernel_wires_stateless_controller():
    k = Kernel()
    assert isinstance(k._invctl, InvalidationController)
    assert k._invctl._k is k


def test_on_write_observer_fires():
    k = Kernel()
    seen = []
    k.on_write(lambda s, kd, n, op: seen.append((s, kd, n, op)))
    k.invalidate(scope="hr", tenant="", kind="Skill", name="x", op="write")
    assert seen == [("hr", "Skill", "x", "write")]


def test_invalidate_skips_evidence():
    k = Kernel()
    h = _StubHolder("hr")
    k.register_holder(h)
    k.invalidate(scope="hr", tenant="", kind="Evidence", name="ev", op="write")
    assert h.reloads == 0  # audit-churn-avoidance


def test_invalidate_reloads_matching_holder_only():
    k = Kernel()
    a, b = _StubHolder("hr"), _StubHolder("other")
    k.register_holder(a)
    k.register_holder(b)
    k.invalidate(scope="hr", tenant="", kind="Skill", name="x", op="write")
    assert a.reloads == 1
    assert b.reloads == 0


def test_batch_writes_coalesces_to_one_invalidate_per_scope():
    k = Kernel()
    h = _StubHolder("hr")
    k.register_holder(h)
    with k.batch_writes():
        for i in range(5):
            k.invalidate(scope="hr", tenant="", kind="Skill", name=f"x{i}", op="write")
        assert h.reloads == 0  # suppressed inside the block
    assert h.reloads == 1  # one consolidated reload on exit


def test_batch_writes_reentrant():
    k = Kernel()
    h = _StubHolder("hr")
    k.register_holder(h)
    with k.batch_writes():
        with k.batch_writes():
            k.invalidate(scope="hr", tenant="", kind="Skill", name="x", op="write")
        assert h.reloads == 0  # inner exit does NOT flush
    assert h.reloads == 1  # only the outermost exit flushes


def test_batch_depth_not_shared_across_with_tenant():
    # State lives on the kernel instance → with_tenant copies keep their own
    # batch depth (shallow-copy of the int), preserving pre-extraction semantics.
    k = Kernel()
    with k.batch_writes():
        k2 = k.with_tenant("acme")
        assert k2._batch_mode_depth == 1  # snapshot at copy
        # Mutating the copy's depth doesn't affect the original.
        k2._batch_mode_depth += 1
        assert k._batch_mode_depth == 1
