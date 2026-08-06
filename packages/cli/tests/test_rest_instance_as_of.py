"""``GET /v1/kinds/{kind}/instances/{name}?as_of=`` — the read in TIME (i-106).

THE BUG THIS SUITE EXISTS FOR, measured 06/08/2026 against the local runtime:
the route ACCEPTED ``?as_of=`` and ignored it. FastAPI drops an undeclared query
param in silence, so an instance with 18 versions — the first recorded at 13:19
on the 5th, the last at 00:27 on the 6th — answered ``status: resolved`` with 6
timeline events both for *now* and for *14:00 on the 5th*, when it was neither.
200, no warning, nothing in the body to contradict the caller.

Two ways out existed: implement the read, or refuse the parameter. IMPLEMENTED,
because the material was already there and refusing would have cost the same
diff while leaving the caller with nothing: ``dna.memory.as_of.resolve_as_of``
was always keyed on ``(scope, kind, name)``, the adapter's ``load_one_as_of``
never knew ``Engram`` from any other Kind, and both refusals (no history at all,
history pruned) were already written. Only memory had a door to it.

**Through the door, never through the function.** The whole defect was that the
function was never reached: a unit test on ``get_instance_impl`` would have been
green on the broken build. Every assertion here is an HTTP call.

The FOUR outcomes are asserted apart, because collapsing any two re-creates the
defect one house over — a caller that cannot tell them apart is back to
guessing:

    200  the belief state at that instant, labelled as such
    404  the instance did not exist yet — an ANSWER
    410  its history was pruned past the instant — a REFUSAL, not an answer
    501  this store keeps no version history at all
    422  the instant is not ISO-8601 — the caller's error, not the server's
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil
from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi", reason="the REST read-API needs the optional 'fastapi' extra")

from fastapi.testclient import TestClient  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_SDLC_API = "github.com/ruinosus/dna/sdlc/v1"

_SQL_SKIP = (
    "the SQL adapter's async driver stack is an SDK extra the CLI does not pull; "
    "the 501 lane still runs, and it is the one only this suite can prove."
)


def _client(**kwargs) -> TestClient:
    return TestClient(R.build_app(scope=_SCOPE, **kwargs))


def _story(name: str, status: str, description: str) -> dict:
    return {
        "apiVersion": _SDLC_API, "kind": "Story",
        "metadata": {"name": name},
        "spec": {"description": description, "status": status},
    }


def _engram(name: str, summary: str) -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Engram",
        "metadata": {"name": name},
        "spec": {
            "summary": summary, "area": "infra", "affect": "triumph",
            "surface_when": ["feature_touched"], "source_refs": ["i-106"],
        },
    }


async def _tick() -> str:
    """An instant strictly BETWEEN two writes.

    ``created_at`` is microsecond-resolution, but the sleeps are not
    superstition: two writes in the same event-loop turn can land on timestamps
    no test can cut between, and the failure would read as a bug in as-of
    rather than in the fixture.
    """
    await asyncio.sleep(0.02)
    t = datetime.now(timezone.utc).isoformat()
    await asyncio.sleep(0.02)
    return t


@pytest.fixture
def fs_dir(tmp_path, monkeypatch):
    """The filesystem store — declares ``versions=True`` and retains nothing."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")
    return dst


@pytest.fixture
def history(tmp_path, monkeypatch):
    """A SQLite store with REAL history, written through the REAL write path.

    Seeded by the kernel, never by inserting version rows: history exists in
    this product because somebody wrote an instance twice, and a fixture that
    forged the rows would let the route pass with no producer behind it.

    Returns the instants the assertions cut on. ``t_before`` precedes v1;
    ``t_mid`` sits between the ``todo`` and the ``done``.
    """
    for _module in ("aiosqlite", "greenlet", "alembic"):
        pytest.importorskip(_module, reason=_SQL_SKIP)
    url = f"sqlite+aiosqlite:///{tmp_path / 'as-of.db'}"
    monkeypatch.setenv("DNA_SOURCE_URL", url)
    monkeypatch.delenv("DNA_BASE_DIR", raising=False)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")
    monkeypatch.delenv("DNA_REF_VALIDATION", raising=False)

    marks: dict[str, str] = {}

    async def seed():
        from dna.adapters.sqlalchemy_ import SqlAlchemySource
        from dna.kernel import Kernel

        src = SqlAlchemySource(url)
        await src.connect()
        k = Kernel.auto()
        k.source(src)

        marks["t_before"] = await _tick()
        await k.write_instance(
            _SCOPE, "Story", "s-x", _story("s-x", "todo", "the first belief"),
        )
        marks["t_mid"] = await _tick()
        await k.write_instance(
            _SCOPE, "Story", "s-x", _story("s-x", "done", "the second belief"),
        )

        # An Engram rewritten past VERSION_CHURN_RETENTION (3) — the pruning is
        # the product's, not the test's: `write_instance` applies it for the
        # curated churn Kinds. Five writes leave versions 3..5 on disk.
        for i in range(5):
            await k.write_instance(
                _SCOPE, "Engram", "e-churn", _engram("e-churn", f"belief {i}"),
            )
            await asyncio.sleep(0.01)
        marks["t_after_all"] = await _tick()
        await src.close()

    asyncio.run(seed())
    return marks


# ── 200: the belief state, and it is DIFFERENT from the present ────────────


class TestTheReadInTime:
    def test_as_of_returns_the_past_not_the_present(self, history):
        """THE assertion i-106 is about, at the wire.

        Two calls, one parameter apart, must not agree — the whole complaint
        was that they did.
        """
        with _client() as c:
            now = c.get("/v1/kinds/Story/instances/s-x")
            then = c.get(
                "/v1/kinds/Story/instances/s-x",
                params={"as_of": history["t_mid"]},
            )
        assert now.status_code == 200, now.text
        assert then.status_code == 200, then.text
        assert now.json()["instance"]["spec"]["status"] == "done"
        assert then.json()["instance"]["spec"]["status"] == "todo", (
            "the as-of read handed back the CURRENT instance — the i-106 "
            "defect, restored"
        )
        assert then.json()["instance"]["spec"]["description"] == "the first belief"

    def test_the_response_says_it_is_historical(self, history):
        """A body a caller cannot tell apart from a live read is the defect
        with extra steps: the version and the RECORDING time both travel."""
        with _client() as c:
            r = c.get("/v1/kinds/Story/instances/s-x",
                      params={"as_of": history["t_mid"]})
        body = r.json()
        assert body["as_of"], "the instant did not come back"
        assert body["as_of_version"] == 1
        assert body["as_of_recorded_at"] <= body["as_of"], (
            "the version that answered was recorded AFTER the instant asked for"
        )
        # ... and a live read carries none of the three, so the distinction is
        # readable in both directions.
        with _client() as c:
            live = c.get("/v1/kinds/Story/instances/s-x").json()
        assert live.get("as_of") is None
        assert live.get("as_of_version") is None
        assert live.get("as_of_recorded_at") is None

    def test_the_instant_comes_back_normalized(self, history):
        """``Z`` in, ``+00:00`` out — echoing what the caller typed would let a
        misread offset survive the round trip unnoticed."""
        with _client() as c:
            r = c.get("/v1/kinds/Story/instances/s-x",
                      params={"as_of": "2099-01-01T00:00:00Z"})
        assert r.status_code == 200, r.text
        assert r.json()["as_of"] == "2099-01-01T00:00:00+00:00"


# ── the three refusals, each distinguishable from the others ───────────────


class TestTheRefusals:
    def test_before_it_existed_is_404(self, history):
        """An ANSWER: nothing was recorded under that name by then."""
        with _client() as c:
            r = c.get("/v1/kinds/Story/instances/s-x",
                      params={"as_of": history["t_before"]})
        assert r.status_code == 404, r.text
        assert "s-x" in r.text

    def test_pruned_history_is_410_not_404(self, history):
        """⚠️ The one that must NOT be a 404.

        404 reads as "the instance did not exist then". The store does not know
        that — it knows it kept no record. Answering the first out of the second
        is the one mistake a history read may never make, so the code differs
        and the message says which situation this is.
        """
        with _client() as c:
            r = c.get("/v1/kinds/Engram/instances/e-churn",
                      params={"as_of": history["t_before"]})
        assert r.status_code == 410, r.text
        assert "pruned" in r.text
        # And the same instance, asked about NOW, is perfectly readable —
        # so the 410 is about the instant, not about the instance.
        with _client() as c:
            assert c.get("/v1/kinds/Engram/instances/e-churn").status_code == 200

    def test_a_store_without_history_is_501_not_the_present(self, fs_dir):
        """The refusal only this lane can prove: the filesystem adapter
        declares ``versions=True`` and keeps nothing. Serving the current
        instance here would be a fabricated past wearing a real answer's
        clothes."""
        with _client(base_dir=str(fs_dir)) as c:
            r = c.get("/v1/kinds/Agent/instances/concierge",
                      params={"as_of": "2026-08-05T14:00:00Z"})
        assert r.status_code == 501, r.text
        assert "history" in r.text
        # Anti-vacuity: without `as_of` the very same call is a normal 200, so
        # the 501 is the parameter's doing and not a broken fixture.
        with _client(base_dir=str(fs_dir)) as c:
            assert c.get("/v1/kinds/Agent/instances/concierge").status_code == 200

    def test_a_nonsense_instant_is_422(self, fs_dir):
        """The caller's error, answered BEFORE the store's capability is even
        consulted — a 501 here would blame the deployment for a typo."""
        with _client(base_dir=str(fs_dir)) as c:
            r = c.get("/v1/kinds/Agent/instances/concierge",
                      params={"as_of": "ontem à tarde"})
        assert r.status_code == 422, r.text
        assert "ISO-8601" in r.text


# ── the parameter is DECLARED, which is what makes it findable ─────────────


def test_openapi_declares_as_of_on_this_route(fs_dir):
    """i-106 was found by reading ``openapi.json`` and seeing ``as_of`` on two
    memory routes and nowhere else. The published schema is where a client
    learns what a route accepts, so the fix is not real until it is there."""
    with _client(base_dir=str(fs_dir)) as c:
        schema = c.get("/openapi.json").json()
    params = schema["paths"]["/v1/kinds/{kind}/instances/{name}"]["get"]["parameters"]
    as_of = [p for p in params if p["name"] == "as_of"]
    assert as_of, "as_of is implemented but not published — an invisible feature"
    assert "transaction time" in (as_of[0].get("description") or "")


def test_the_sibling_routes_refuse_as_of_rather_than_ignoring_it(fs_dir):
    """The LIST and the REFS routes do not answer in time — and now say so.

    Left as-is they would be the next i-106: same shape, same silence, found by
    the same accident. Refusing is the honest state until somebody implements
    the read; it is not a placeholder that renders as a feature."""
    with _client(base_dir=str(fs_dir)) as c:
        for path in ("/v1/kinds/Agent/instances",
                     "/v1/kinds/Agent/instances/concierge/refs"):
            r = c.get(path, params={"as_of": "2026-08-05T14:00:00Z"})
            assert r.status_code == 400, f"{path}: {r.text}"
            assert "as_of" in r.text
