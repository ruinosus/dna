"""i-106 — a query param this face does not implement is REFUSED, never ignored.

THE DEFECT, measured 06/08/2026 against the local runtime:
``GET /v1/kinds/Issue/instances/i-087-...`` answered 200 with ``status:
resolved`` and 6 timeline events. The SAME call with
``?as_of=2026-08-05T14:00:00Z`` answered **exactly the same** — on an instance
with 18 versions whose first was recorded at 13:19 on the 5th. At 14:00 that day
it was neither resolved nor six events long. ``as_of`` was declared on
``/v1/memories`` and ``/v1/memories/search`` and nowhere else, and FastAPI drops
an undeclared query param in silence, so the call passed, answered 200, and the
caller believed they had read the past.

Accepting a parameter you ignore is worse than refusing it. The caller holds a
belief about history with nothing in the response to contradict it — the same
family as the blueprint warning that told the truth about the wrong thing, and
the graph's ``unresolved[]`` that claimed more than the runtime knew.

**THE SWEEP IS THE POINT.** The one instance was found by accident, so any other
would be too. This suite is the systematic version: it walks EVERY route the
face mounts, and for each one asserts that a parameter that route does not read
comes back 400. It is written as a loop over ``app.routes`` — not as a list of
paths — precisely so a route added tomorrow is covered the day it is added,
without anyone remembering this file exists.

What the sweep found (see the PR): the ``as_of`` instance, and nothing else that
CHANGES an answer. The rest of the surface either declares what it reads or
reads it face-wide.
"""
from __future__ import annotations

import pathlib
import re
import shutil

import pytest

pytest.importorskip("fastapi", reason="the REST read-API needs the optional 'fastapi' extra")

from fastapi.testclient import TestClient  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"

#: A parameter no route could plausibly declare — so a 200 means "swallowed".
_BOGUS = "definitivamente_nao_declarado"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _client(dna_dir, **kwargs) -> TestClient:
    return TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE, **kwargs))


def _concrete(path: str) -> str:
    """A path template with every ``{placeholder}`` filled with a name nothing
    matches. The route only has to MATCH — the guard runs before the handler,
    so a 404-worthy name is fine and keeps the sweep from writing anything."""
    return re.sub(r"\{[^}]+\}", "nao-existe", path)


def _sweepable(app):
    """Every mounted route, with the ONE method the sweep drives it with.

    ``/health`` is excluded and that exclusion is load-bearing, not a
    convenience: it is the liveness probe, and probes are routinely pinged with
    a cache-buster (``/health?t=1712...``). Refusing those would turn an
    honesty guard into an outage. It is also the only route with no
    ``dependencies=guarded``, which is what structurally keeps it out.
    """
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        if not path.startswith("/v1/"):
            continue
        for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            if method in methods:
                yield method, path
                break


# ── the sweep ──────────────────────────────────────────────────────────────


def test_every_route_refuses_a_parameter_it_does_not_read(dna_dir):
    """The systematic half of i-106: no route on this face answers 2xx to a
    query parameter it never reads.

    Driven through the DOOR with a real HTTP call per route, not by inspecting
    signatures — a guard that only reads the declaration would stay green if
    the dependency stopped being mounted (``guard-existe-porta-nao-chama``).
    """
    with _client(dna_dir) as c:
        app = c.app
        swept = []
        for method, path in _sweepable(app):
            r = c.request(method, _concrete(path), params={_BOGUS: "1"}, json={})
            swept.append((method, path, r.status_code))
            assert r.status_code == 400, (
                f"{method} {path} answered {r.status_code} to an undeclared "
                f"query param — it was swallowed in silence. {r.text}"
            )
            assert _BOGUS in r.text, (
                f"{method} {path} refused without NAMING the parameter; a "
                f"caller cannot fix what the message does not identify."
            )
    # Anti-vacuity: an empty sweep would pass every assertion above.
    assert len(swept) >= 50, f"the sweep covered only {len(swept)} routes"


def test_the_sweep_is_not_refusing_everything(dna_dir):
    """The mutant this suite must kill: a guard that 400s unconditionally would
    make the sweep above green while breaking the whole face.

    So the SAME routes, called with only the params they declare, must NOT be
    400 — whatever else they answer (404 for a name that does not exist, 422
    for a missing body, 403 for a gate) is fine and is not this test's
    business."""
    with _client(dna_dir) as c:
        checked = 0
        for method, path in _sweepable(c.app):
            r = c.request(method, _concrete(path), json={})
            assert r.status_code != 400 or _BOGUS not in r.text
            assert "does not implement the query parameter" not in r.text, (
                f"{method} {path} refused a call that passed NO query params "
                f"at all: {r.text}"
            )
            checked += 1
    assert checked >= 50


# ── the two face-wide params, and why they are exactly two ──────────────────


def test_face_wide_params_reach_every_route(dna_dir):
    """``scope`` and ``tenant`` are never refused, on any route.

    Not an escape hatch: both are read by the auth middlewares on every
    non-public path (``scope`` for the i-034 grant check, ``tenant`` for the
    Model-B workspace bind), and the config lane WRITES ``tenant`` back into the
    query string itself. A guard that refused them per-route would bill the
    caller for the face's own doing."""
    with _client(dna_dir) as c:
        for method, path in _sweepable(c.app):
            r = c.request(
                method, _concrete(path),
                params={"scope": _SCOPE, "tenant": "ws-x"}, json={},
            )
            assert "does not implement the query parameter" not in r.text, (
                f"{method} {path} refused a face-wide param: {r.text}"
            )


def test_the_face_wide_list_matches_what_the_middlewares_actually_read():
    """DERIVED, not decided — the enumeration-vs-derivation rule.

    ``_FACE_WIDE_QUERY_PARAMS`` is a hand-written tuple, and a hand-written
    tuple beside a live behaviour is a comment that compiles. So read the module
    for every ``request.query_params.get("<name>")`` the FACE performs outside a
    route handler, and require the two sets to be equal. A middleware that
    starts reading a third param fails here until the tuple says so; one that
    stops reading ``scope`` fails here until the tuple shrinks."""
    source = pathlib.Path(R.__file__).read_text(encoding="utf-8")
    read_by_middleware = set(
        re.findall(r"request\.query_params\.get\(\s*[\"']([^\"']+)[\"']", source)
    )
    assert read_by_middleware, "the extraction found nothing — the pattern drifted"
    assert read_by_middleware == set(R._FACE_WIDE_QUERY_PARAMS), (
        f"the face reads {sorted(read_by_middleware)} across routes but declares "
        f"{sorted(R._FACE_WIDE_QUERY_PARAMS)} as face-wide"
    )


# ── the refusal is not a lane, and it does not outrank auth ────────────────


def test_auth_answers_before_the_query_guard(dna_dir):
    """401 beats 400. A caller who cannot reach a route must not learn from a
    400 which parameters that route would have accepted."""
    with _client(dna_dir, auth="token", token="s3cr3t") as c:
        r = c.get("/v1/agents", params={_BOGUS: "1"})
        assert r.status_code == 401, r.text
        assert _BOGUS not in r.text
        ok = c.get("/v1/agents", params={_BOGUS: "1"},
                   headers={"Authorization": "Bearer s3cr3t"})
        assert ok.status_code == 400, ok.text


def test_health_still_answers_a_cache_buster(dna_dir):
    """The one deliberate exemption, asserted so it stays deliberate."""
    with _client(dna_dir) as c:
        r = c.get("/health", params={"t": "1754400000"})
        assert r.status_code == 200, r.text
