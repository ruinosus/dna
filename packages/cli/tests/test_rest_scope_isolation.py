"""The REST face's scope binding, proven ON THE WIRE (issue ``i-034``).

``packages/sdk-py/tests/test_scope_binding_guard.py`` pins the POLICY. This file
pins that the REST face actually *asks* it — which is the half i-034 was really
about. The policy had a workspace rule; the REST face called it behind
``if workspace and ...``, and the deployed configuration (``dna api serve
--auth token``, a shared service credential that resolves no workspace) therefore
never reached it. A correct policy nobody consults is not a control.

So every assertion here goes through the real FastAPI app via ``TestClient`` and
asserts a STATUS CODE — the thing an attacker actually observes. A refactor that
moves the check from middleware to a dependency, or from the face into the core,
should leave this file entirely green; a refactor that drops the check on the way
must turn it red.

The fixture source ships two scopes (``concierge`` and ``retrofit``), so
"reach another scope" is a real, observable read of data the credential was not
granted — not a 404 that would pass for any reason.
"""
from __future__ import annotations

import pathlib
import shutil

import pytest

pytest.importorskip("fastapi", reason="the REST read-API needs the optional 'fastapi' extra")

from fastapi.testclient import TestClient  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_HOME = "concierge"        # the scope the server is booted on.
_FOREIGN = "retrofit"      # a real, populated scope the credential is NOT granted.
_TOKEN = "service-token-not-a-real-secret"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.delenv("DNA_TOKEN_SCOPES", raising=False)
    return dst


def _client(dna_dir, **kwargs) -> TestClient:
    return TestClient(R.build_app(base_dir=str(dna_dir), scope=_HOME, **kwargs))


def _svc(dna_dir, **kwargs) -> TestClient:
    return _client(dna_dir, auth="token", token=_TOKEN, **kwargs)


_AUTH = {"Authorization": f"Bearer {_TOKEN}"}

# Every read endpoint that takes a `scope` query param. Parametrizing over the
# whole surface is deliberate: i-034 was found on `/v1/board` alone, and a
# per-endpoint fix would have left the rest open. The property is about the FACE,
# not about one route.
_SCOPED_ENDPOINTS = [
    "/v1/agents",
    "/v1/tools",
    "/v1/memories",
    "/v1/board",
]


# ── the legitimate paths (so the denials below are not vacuous) ─────────────


@pytest.mark.parametrize("endpoint", _SCOPED_ENDPOINTS)
def test_the_service_credential_still_reads_its_own_scope(endpoint, dna_dir):
    """Baseline, per endpoint. Without this, every denial below could pass on a
    face that rejects EVERY scoped request — a control that breaks the product is
    not a control, and it is how a 'fix' passes its tests and fails in prod.

    Naming the home scope explicitly must be served."""
    with _svc(dna_dir) as c:
        assert c.get(endpoint, params={"scope": _HOME}, headers=_AUTH).status_code == 200


def test_omitting_the_scope_is_served_and_never_binds(dna_dir):
    """A request that names NO scope must stay served — it resolves to the
    server's own default, which is the workspace-bound answer by construction.

    Pinned because the cheapest way to pass every denial test in this file is to
    reject any request whose scope is not explicitly granted, including the ones
    that named none. That would break the portal's most common read."""
    with _svc(dna_dir) as c:
        assert c.get("/v1/agents", headers=_AUTH).status_code == 200
        assert c.get("/v1/tools", headers=_AUTH).status_code == 200


def test_the_foreign_scope_is_genuinely_readable_when_granted(dna_dir):
    """Anti-vacuity for the DENIALS specifically: prove ``retrofit`` is real,
    populated and reachable — so a 403 below means 'refused', not 'empty' or
    'missing'. If this ever returns an empty agent list, every isolation test in
    this file has quietly stopped proving anything."""
    with _svc(dna_dir, token_scopes=[_FOREIGN, _HOME]) as c:
        r = c.get("/v1/agents", params={"scope": _FOREIGN}, headers=_AUTH)
        assert r.status_code == 200
        assert r.json()["scope"] == _FOREIGN
        assert r.json()["agents"], "fixture regression: the foreign scope is empty"


# ── SECURITY: the reported i-034 exposure ──────────────────────────────────


@pytest.mark.parametrize("endpoint", _SCOPED_ENDPOINTS)
def test_a_service_token_cannot_read_a_scope_it_was_not_granted(endpoint, dna_dir):
    """THE property, reproduced as reported: a valid service credential naming
    another scope is REFUSED, on every scoped endpoint.

    i-034's live verification was ``GET /v1/board?scope=<another-scope>`` served
    without denial. That request is this test."""
    with _svc(dna_dir) as c:
        r = c.get(endpoint, params={"scope": _FOREIGN}, headers=_AUTH)
        assert r.status_code == 403, r.text


def test_the_denial_is_not_merely_the_401_in_disguise(dna_dir):
    """The refusal must be attributable to the SCOPE, not to authentication.

    Without this, a 'fix' that broke the bearer check would satisfy every denial
    test above while actually granting nothing and refusing everyone. The
    unauthenticated request must still be a 401, and the authenticated-but-
    ungranted one a 403 — two distinct failures with two distinct causes."""
    with _svc(dna_dir) as c:
        assert c.get("/v1/agents", params={"scope": _FOREIGN}).status_code == 401
        r = c.get("/v1/agents", params={"scope": _FOREIGN}, headers=_AUTH)
        assert r.status_code == 403
        assert "scope" in r.text.lower()


def test_a_forged_tenant_param_does_not_unlock_a_foreign_scope(dna_dir):
    """Under shared-token auth the ``tenant`` param is caller-supplied and
    unverified (the face's own long-standing TODO says so). It must not become an
    input to the scope decision — otherwise the binding is defeated by adding a
    query parameter, which is no binding at all."""
    with _svc(dna_dir) as c:
        for tenant in ("someone-else", "", _HOME, _FOREIGN):
            r = c.get(
                "/v1/agents",
                params={"scope": _FOREIGN, "tenant": tenant},
                headers=_AUTH,
            )
            assert r.status_code == 403, f"tenant={tenant!r} unlocked the scope"


def test_health_stays_reachable_and_unscoped(dna_dir):
    """Liveness must not be collateral damage. A binding that 403s the probe
    takes the container down on the next restart — the classic way a security fix
    becomes an outage."""
    with _svc(dna_dir) as c:
        assert c.get("/health").status_code == 200


# ── the operator's explicit grant ──────────────────────────────────────────


def test_the_grant_is_what_opens_the_scope_and_it_is_exact(dna_dir):
    """Access must follow the GRANT, not the request. Granting the foreign scope
    opens exactly it; a near-miss spelling of the same grant does not."""
    with _svc(dna_dir, token_scopes=[_FOREIGN]) as c:
        assert c.get("/v1/agents", params={"scope": _FOREIGN},
                     headers=_AUTH).status_code == 200
    with _svc(dna_dir, token_scopes=[_FOREIGN.upper()]) as c:
        assert c.get("/v1/agents", params={"scope": _FOREIGN},
                     headers=_AUTH).status_code == 403


def test_the_env_var_configures_the_same_grant_as_the_flag(dna_dir, monkeypatch):
    """The env var is how the deployed container will be configured, so it must
    be exercised, not assumed equivalent to the CLI flag."""
    monkeypatch.setenv("DNA_TOKEN_SCOPES", f"{_HOME}, {_FOREIGN}")
    with _svc(dna_dir) as c:
        assert c.get("/v1/agents", params={"scope": _FOREIGN},
                     headers=_AUTH).status_code == 200


def test_the_wildcard_optout_restores_multiscope_reads(dna_dir, monkeypatch):
    """The escape hatch must genuinely work. An operator running a trusted
    multi-scope BFF (which is what DNA Cloud's portal is today) has to be able to
    say so and keep working — otherwise this control gets reverted wholesale
    rather than configured."""
    monkeypatch.setenv("DNA_TOKEN_SCOPES", "*")
    with _svc(dna_dir) as c:
        assert c.get("/v1/agents", params={"scope": _FOREIGN},
                     headers=_AUTH).status_code == 200


# ── OPEN CORE: --auth none is not bound ────────────────────────────────────


@pytest.mark.parametrize("endpoint", _SCOPED_ENDPOINTS)
def test_unauthenticated_local_serving_reads_any_scope(endpoint, dna_dir):
    """The open-core hard rule at the face: ``dna api serve --auth none`` — local
    dev, self-host, no credential — must reach any scope in its own source.

    There is no credential to grant anything to and no tenancy to isolate; a
    binding here would cap the OSS runtime. If this file's other tests were
    implemented by binding *every* request rather than every *authenticated*
    request, this goes red."""
    with _client(dna_dir) as c:
        assert c.get(endpoint, params={"scope": _FOREIGN}).status_code == 200
