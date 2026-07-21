"""Story ``s-ws-res-source`` — the per-WORKSPACE base scope (Model B isolation).

The physical-isolation half beneath the auth resolver: ``LiveDna.default_scope`` /
``LiveDna.scope_is_bound`` key the ``(scope, tenant=workspace_id)`` source per
workspace. This is the #114 ``vendor_tenant`` machinery ported to workspace
vocabulary (``s/tid/workspace_id/``) — the storage shape is unchanged; only the
value flowing into the opaque ``tenant`` column (now a workspace id) and how it is
resolved differs.

With multi-workspace OFF (``vendor_workspace`` unset) the scope-less default stays
``base_scope`` for everyone (today's behavior / the OSS path). With it ON, a
scope-less read resolves PER WORKSPACE — the RESERVED vendor workspace to
``base_scope`` (``dna-development`` stays the vendor's, un-moved), every other
workspace to its OWN ``tenant-<id>`` scope — so a new outside workspace never
reads the vendor's data.

The reservation is by CONFIGURATION (whatever id is passed as
``vendor_workspace``), never by recognizing anything about the id itself. That is
why decision **D5** — workspace ids are generated, an Azure ``tid`` is not an
identity — left this mechanism untouched: the vendor id in these tests is a
fixture string and nothing here inspects its shape. The literal below happens to
be the vendor workspace's real id, which was once the founder's tid; that is
historical trivia, not a rule.
"""
from __future__ import annotations

from dna.application.live import LiveDna


def _live(vendor: str | None = None, prefix: str = "tenant-") -> LiveDna:
    return LiveDna(
        base_scope="dna-development", kernel=None, provider=None,
        vendor_workspace=vendor, workspace_scope_prefix=prefix,
    )


def test_default_scope_multiworkspace_off_is_base_for_all():
    live = _live(vendor=None)
    assert live.default_scope(None) == "dna-development"
    assert live.default_scope("ws-acme") == "dna-development"  # OFF → unchanged.


def test_default_scope_no_workspace_is_base():
    # Even with multi-workspace ON, an un-resolved (stdio / local) read is base.
    assert _live(vendor="c5b891f7").default_scope(None) == "dna-development"


def test_default_scope_vendor_workspace_reserved_to_base():
    # The workspace CONFIGURED as the vendor's keeps the base scope. Reservation
    # is by configuration; the id is opaque to this code.
    live = _live(vendor="c5b891f7")
    assert live.default_scope("c5b891f7") == "dna-development"


def test_default_scope_other_workspace_gets_own_scope():
    live = _live(vendor="c5b891f7")
    assert live.default_scope("ws-acme") == "tenant-ws-acme"
    assert live.default_scope("ws-globex") == "tenant-ws-globex"


def test_default_scope_prefix_is_configurable():
    assert _live(vendor="v", prefix="ws-").default_scope("acme") == "ws-acme"


# NOTE on the ``authenticated=True`` below: issue ``i-034`` added that keyword
# because the binder's real axis is whether a CREDENTIAL was presented, not whether
# a workspace happens to be present — the workspace-LESS authenticated caller (the
# portal's shared service token) was the one slipping through, precisely because it
# had no workspace to be compared against. These three tests describe the
# RESOLVED-workspace regime, which by definition only exists for an authenticated
# request, so they now say so explicitly. Only the SETUP moved; every answer below
# is byte-identical to what it was before i-034. The fail-closed half is pinned
# separately in ``packages/sdk-py/tests/test_scope_binding_guard.py``.


def test_scope_is_bound_off_allows_any_scope():
    # Multi-workspace OFF → binding is a no-op (the shared-scope + overlay model).
    live = _live(vendor=None)
    assert live.scope_is_bound("anything", "ws-acme", authenticated=True) is True


def test_scope_is_bound_allows_none_and_own_scope():
    live = _live(vendor="c5b891f7")
    a = {"authenticated": True}
    assert live.scope_is_bound(None, "ws-acme", **a) is True             # omitted → default.
    assert live.scope_is_bound("tenant-ws-acme", "ws-acme", **a) is True  # own scope.
    assert live.scope_is_bound("dna-development", "c5b891f7", **a) is True  # vendor's own.


def test_scope_is_bound_denies_cross_workspace():
    live = _live(vendor="c5b891f7")
    a = {"authenticated": True}
    # a non-vendor workspace naming the vendor's scope → cross-workspace.
    assert live.scope_is_bound("dna-development", "ws-acme", **a) is False
    # a workspace naming ANOTHER workspace's scope → cross-workspace.
    assert live.scope_is_bound("tenant-ws-globex", "ws-acme", **a) is False
