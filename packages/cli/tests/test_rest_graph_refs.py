"""``GET /v1/kinds/{kind}/instances/{name}/refs`` — the graph, THROUGH the door.

The kernel-side walk has its own suite in the SDK. This one exists because a
guard that is only exercised in a unit test is a guard no door calls: the
refusals that matter here — 501 on a store that keeps no edges, 400 on a
nonsense direction, 404 on an unknown Kind — are only real if the ROUTE makes
them, with the response code a client will actually see.

Two lanes, deliberately:

* the **filesystem** store, which records no edges at all and must therefore
  answer **501** — never ``{"edges": []}``, which reads as "nothing points at
  this instance" and is a claim only a store that keeps edges may make;
* a **SQLite** store, where a real write produces a real edge and the walk
  returns it with the honesty fields (``resolved``, ``stop``,
  ``graph_producer``) attached.
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
_SCOPE = "concierge"
_SDLC_API = "github.com/ruinosus/dna/sdlc/v1"


@pytest.fixture
def fs_dir(tmp_path, monkeypatch):
    """A filesystem store — the adapter that keeps no edges."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")
    return dst


@pytest.fixture
def sql_dir(tmp_path, monkeypatch):
    """A SQLite store, seeded through the REAL write path.

    Seeded by the kernel rather than by inserting rows: an edge exists in this
    product because somebody wrote an instance, and a fixture that inserted the
    row directly would let the route pass with no producer behind it — the
    exact failure that left the first edge table empty for fourteen months.
    """
    import asyncio

    _reason = (
        "the SQL adapter's async driver stack is an SDK extra the CLI does not "
        "pull; the 501 lane above — the refusal only this suite can prove — "
        "still runs, and the walk itself is covered against BOTH dialects by "
        "the SDK's own graph suite."
    )
    for _module in ("aiosqlite", "greenlet", "alembic"):
        pytest.importorskip(_module, reason=_reason)
    db = tmp_path / "graph.db"
    url = f"sqlite+aiosqlite:///{db}"
    monkeypatch.setenv("DNA_SOURCE_URL", url)
    monkeypatch.delenv("DNA_BASE_DIR", raising=False)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")
    monkeypatch.delenv("DNA_REF_VALIDATION", raising=False)

    def _doc(kind, name, **spec):
        base = {"description": "d", "status": "todo"}
        base.update(spec)
        return {
            "apiVersion": _SDLC_API, "kind": kind,
            "metadata": {"name": name}, "spec": base,
        }

    async def seed():
        from dna.adapters.sqlalchemy_ import SqlAlchemySource
        from dna.kernel import Kernel

        src = SqlAlchemySource(url)
        await src.connect()
        k = Kernel.auto()
        k.source(src)
        await k.write_instance(_SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))
        await k.write_instance(
            _SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"),
        )
        await src.close()

    asyncio.run(seed())
    return url


def _client(**kwargs) -> TestClient:
    return TestClient(R.build_app(scope=_SCOPE, **kwargs))


class TestTheUnsupportedRefusal:
    def test_a_store_without_edges_answers_501_not_an_empty_list(self, fs_dir):
        """⚠️ The refusal that matters most, at the wire.

        ``200 {"edges": []}`` would tell a client that nothing points at this
        instance. The filesystem adapter has no idea whether that is true.
        """
        with _client(base_dir=str(fs_dir)) as c:
            r = c.get("/v1/kinds/Agent/instances/concierge/refs")
        assert r.status_code == 501, r.text
        assert "not the same as" in r.text


class TestTheWalkThroughTheDoor:
    def test_what_points_at_this_document(self, sql_dir):
        with _client() as c:
            r = c.get("/v1/kinds/Feature/instances/f-y/refs")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["direction"] == "in"
        assert [(e["from_kind"], e["from_name"], e["field"]) for e in body["edges"]] == [
            ("Story", "s-x", "feature"),
        ]

    def test_the_honesty_fields_travel(self, sql_dir):
        """``stop`` and ``graph_producer`` are not decoration: without them a
        screen cannot tell a complete answer from a truncated one, nor an empty
        graph from a producer that is switched off."""
        with _client() as c:
            body = c.get("/v1/kinds/Feature/instances/f-y/refs").json()
        assert body["stop"] in ("complete", "depth_reached", "truncated")
        assert body["graph_producer"] == "warn"
        assert body["edges"][0]["resolved"] is True
        assert body["edges"][0]["declared_to"] == ["Feature"]

    def test_out_is_the_other_direction(self, sql_dir):
        with _client() as c:
            body = c.get(
                "/v1/kinds/Story/instances/s-x/refs",
                params={"direction": "out"},
            ).json()
        assert [(e["to_kind"], e["to_name"]) for e in body["edges"]] == [
            ("Feature", "f-y"),
        ]

    def test_a_nonsense_direction_is_400_not_500(self, sql_dir):
        with _client() as c:
            r = c.get(
                "/v1/kinds/Feature/instances/f-y/refs",
                params={"direction": "sideways"},
            )
        assert r.status_code == 400, r.text

    def test_an_unknown_kind_is_404_naming_it(self, sql_dir):
        with _client() as c:
            r = c.get("/v1/kinds/NaoExiste/instances/x/refs")
        assert r.status_code == 404, r.text
        assert "NaoExiste" in r.text
