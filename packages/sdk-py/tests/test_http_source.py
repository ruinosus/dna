"""``HttpSource`` — the token-authenticated ``SourcePort`` over the REST face (i-106).

These tests drive the adapter against a REAL socket (a stdlib ``http.server``
speaking the shapes the DNA REST face actually returns), because every
interesting property of this adapter is a property of a network conversation:
which routes it asks, what it does when the answer is 401, and what it does when
there is no answer at all.

What they freeze is the QUESTION, not the answer:

* an unreachable door RAISES — it never reads as "that scope holds nothing";
* a refused credential RAISES, and the message says ``setado``/``ausente``,
  never the token;
* a scope this door does not serve RAISES, because the instance routes answer
  the SERVED scope's content under whatever scope name you ask for;
* the Kind fan-out comes from ``/kinds/registry`` (every registered Kind), not
  from ``/kinds`` (only the workspace-AUTHORED ones);
* a document that cannot be fetched mid-fan-out fails the whole read rather than
  shortening it.

The end-to-end proof — the REAL REST face, a real ``DnaClient.from_env()`` and a
real ``resolve_copilot`` — lives in ``packages/cli/tests/test_http_source_e2e.py``,
where the face this adapter speaks to is importable.
"""
from __future__ import annotations

import http.server
import json
import socket
import threading
from typing import Any

import pytest

from dna.adapters.http_source import HttpSource, RemoteScopeMismatch
from dna.kernel.protocols import (
    ResolveAuthError,
    ResolveError,
    ResolveNetworkError,
)

SCOPE = "hosted-scope"

# Two Kinds, and only ONE of them is workspace-authored. The registry holds
# both; `/v1/kinds` holds the authored one. An adapter that fans out from the
# wrong route reads half the scope and calls it the scope.
_REGISTRY = ["Genome", "LayerPolicy", "KindDefinition", "Agent", "Copilot"]
_AUTHORED = ["KindDefinition"]


def _doc(kind: str, name: str, spec: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": kind,
        "metadata": {"name": name},
        "spec": spec or {},
    }


_STORE: dict[str, list[dict[str, Any]]] = {
    "Genome": [_doc("Genome", SCOPE, {"version": "0.1.0"})],
    "LayerPolicy": [_doc("LayerPolicy", "tenant", {"layer": "tenant"})],
    "KindDefinition": [_doc("KindDefinition", "deal", {"kind": "Deal"})],
    "Agent": [_doc("Agent", "helper", {"instruction": "help"})],
    "Copilot": [_doc("Copilot", "front", {"mounts": [{"agent": "helper"}]})],
}


class _Face(http.server.BaseHTTPRequestHandler):
    """The shapes the real face returns, and nothing else."""

    token = "a-fake-dev-token-not-a-secret"
    served_scope = SCOPE
    #: routes the test wants to fail, mapped to the status to answer with
    fail: dict[str, int] = {}

    def log_message(self, *args: Any) -> None:  # silence the stdlib access log
        return

    def _send(self, status: int, body: Any) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 — stdlib naming
        from urllib.parse import urlparse

        path = urlparse(self.path).path
        if type(self).fail.get(path):
            self._send(type(self).fail[path], {"detail": "forced"})
            return
        authz = self.headers.get("Authorization") or ""
        if authz != f"Bearer {type(self).token}":
            self._send(401, {"detail": "missing bearer token"})
            return
        if path == "/v1/kinds/registry":
            self._send(200, {
                "scope": type(self).served_scope,
                "kinds": [{"kind": k} for k in _REGISTRY],
            })
            return
        if path == "/v1/kinds":
            self._send(200, {
                "scope": type(self).served_scope,
                "kinds": [{"kind": k, "name": k.lower()} for k in _AUTHORED],
            })
            return
        parts = [p for p in path.split("/") if p]
        # /v1/kinds/{kind}/instances[/{name}]
        if len(parts) >= 4 and parts[0] == "v1" and parts[1] == "kinds" and parts[3] == "instances":
            kind = parts[2]
            rows = _STORE.get(kind)
            if rows is None:
                self._send(404, {"detail": f"unknown Kind {kind!r}"})
                return
            if len(parts) == 4:
                self._send(200, {
                    "scope": type(self).served_scope, "kind": kind,
                    "instances": [{"name": r["metadata"]["name"]} for r in rows],
                    "count": len(rows), "offset": 0, "has_more": False,
                    "projected": None,
                })
                return
            name = parts[4]
            hit = next((r for r in rows if r["metadata"]["name"] == name), None)
            if hit is None:
                self._send(404, {"detail": f"no {kind} named {name!r}"})
                return
            self._send(200, {
                "scope": type(self).served_scope, "kind": kind, "name": name,
                "instance": hit, "etag": "deadbeef",
            })
            return
        self._send(404, {"detail": "no route"})


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _Door:
    """The stub face's handle: its URL, its handler class (to make a route
    fail), and a ``stop()`` that takes the door DOWN at the same address — the
    only faithful way to test what happens when a hosted DNA goes away."""

    def __init__(self, url: str, server: Any) -> None:
        self.url = url
        self.handler = _Face
        self._server = server
        self._down = False

    def stop(self) -> None:
        if not self._down:
            self._server.shutdown()
            self._server.server_close()
            self._down = True


@pytest.fixture
def face():
    """The stub face, on a real port."""
    _Face.fail = {}
    _Face.served_scope = SCOPE
    port = _free_port()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Face)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    door = _Door(f"http://127.0.0.1:{port}/v1", server)
    try:
        yield door
    finally:
        door.stop()


def _source(base: str, **kw: Any) -> HttpSource:
    kw.setdefault("token", _Face.token)
    kw.setdefault("ttl", 0)
    return HttpSource(base, **kw)


# ── the scheme reaches the adapter at all ───────────────────────────────

@pytest.mark.asyncio
async def test_https_url_builds_the_http_source():
    """The whole feature is one env var, so the factory has to route the
    scheme. Both http and https — the second is production, the first is how
    anyone develops against it."""
    from dna.adapters.source_url import source_from_url

    for url in ("https://dna.example.com/v1", "http://127.0.0.1:8090/v1"):
        src = await source_from_url(url)
        assert isinstance(src, HttpSource)
        assert src.base_url == url


@pytest.mark.asyncio
async def test_an_unknown_scheme_still_fails_loud_and_names_https():
    from dna.adapters.source_url import UnsupportedSourceScheme, source_from_url

    with pytest.raises(UnsupportedSourceScheme) as err:
        await source_from_url("ftp://example.com/dna")
    assert "https://" in str(err.value)


def test_a_remote_document_needs_no_readers(face):
    base = face.url
    assert _source(base).supports_readers is False


def test_the_declaration_matches_the_reflection_oracle(face):
    """s-sourceport-contract-cleanup's rule: an adapter DECLARES its
    capabilities, and the derivation is the oracle that keeps the declaration
    honest. A declaration that drifts from what the class implements is the
    lie the flag exists to prevent."""
    from dna.kernel.capabilities import derive_capabilities

    base = face.url
    src = _source(base)
    declared = src.capabilities()
    derived = derive_capabilities(src, label=declared.source)
    assert declared == derived


# ── failure is never an empty list ──────────────────────────────────────

@pytest.mark.asyncio
async def test_an_unreachable_door_raises_instead_of_reading_as_empty():
    """THE rule of this house. An empty list would say "this scope holds
    nothing", which is a claim about content; the fact is "I could not ask"."""
    src = _source("http://127.0.0.1:1/v1")
    with pytest.raises(ResolveNetworkError):
        await src.load_all(SCOPE)
    with pytest.raises(ResolveNetworkError):
        await src.load_bootstrap_docs(SCOPE)


@pytest.mark.asyncio
async def test_a_refused_credential_raises_auth_and_never_prints_the_token(face):
    base = face.url
    src = _source(base, token="the-wrong-token-value")
    with pytest.raises(ResolveAuthError) as err:
        await src.load_all(SCOPE)
    message = str(err.value)
    assert "the-wrong-token-value" not in message
    assert "setado" in message


@pytest.mark.asyncio
async def test_a_missing_token_says_ausente_and_never_guesses(face):
    base = face.url
    src = HttpSource(base, token="", ttl=0)
    with pytest.raises(ResolveAuthError) as err:
        await src.load_all(SCOPE)
    assert "ausente" in str(err.value)


@pytest.mark.asyncio
async def test_the_token_comes_from_the_env_name_the_face_already_uses(face, monkeypatch):
    """``DNA_API_TOKEN`` is the name the REST face, both generated clients and
    the docs already use. Inventing a second name would leave a consumer with
    two places to look."""
    base = face.url
    monkeypatch.setenv("DNA_API_TOKEN", _Face.token)
    src = HttpSource(base, ttl=0)
    assert await src.served_scope() == SCOPE


# ── one door, one scope ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_scope_this_door_does_not_serve_is_refused_not_answered(face):
    """The instance routes take no ``scope`` param — the served scope is bound
    to the credential on the server. Measured against the real face: asking for
    another scope returns the SERVED scope's instances. So the adapter refuses;
    answering would put one scope's content under another's name."""
    base = face.url
    src = _source(base)
    with pytest.raises(RemoteScopeMismatch) as err:
        await src.load_all("some-other-scope")
    assert SCOPE in str(err.value)
    assert "some-other-scope" in str(err.value)


@pytest.mark.asyncio
async def test_list_scopes_reports_the_one_scope_rather_than_nothing(face):
    base = face.url
    assert await _source(base).list_scopes() == [SCOPE]


# ── what it reads ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bootstrap_returns_whole_documents_of_the_three_bootstrap_kinds(face):
    """A ``SourcePort`` returns DOCUMENTS. A row without ``apiVersion`` does
    not parse, and the list route's projection cannot produce one — which is
    why every instance costs its own GET."""
    from dna.kernel.protocols import BOOTSTRAP_KIND_NAMES

    base = face.url
    docs = await _source(base).load_bootstrap_docs(SCOPE)
    assert {d["kind"] for d in docs} == set(BOOTSTRAP_KIND_NAMES)
    for doc in docs:
        assert doc["apiVersion"]
        assert doc["metadata"]["name"]


@pytest.mark.asyncio
async def test_load_all_fans_out_from_the_registry_not_from_the_authored_kinds(face):
    """``/v1/kinds`` lists only what the workspace AUTHORED (measured against a
    real deployment: 2 Kinds, against 88 in the registry). Fanning out from it
    would read a fraction of the scope and report it as the scope."""
    base = face.url
    docs = await _source(base).load_all(SCOPE)
    kinds = {d["kind"] for d in docs}
    assert kinds == set(_REGISTRY), kinds
    assert any(d["kind"] == "Agent" for d in docs), "a registry-only Kind was dropped"


@pytest.mark.asyncio
async def test_granular_reads_answer_one_name_and_one_document(face):
    base = face.url
    src = _source(base)
    refs = await src.list_doc_refs(SCOPE, kind="Agent")
    assert refs == [("Agent", "helper")]
    one = await src.load_one(SCOPE, "Agent", "helper")
    assert one is not None and one["spec"]["instruction"] == "help"
    assert await src.load_one(SCOPE, "Agent", "nobody") is None


@pytest.mark.asyncio
async def test_a_document_that_cannot_be_fetched_fails_the_whole_read(face):
    """A short list is the same defect as an empty one, one degree quieter: a
    missing Agent renders as "no such agent", an accusation against data that
    exists."""
    base, handler = face.url, face.handler
    handler.fail = {"/v1/kinds/Agent/instances/helper": 500}
    with pytest.raises(ResolveError) as err:
        await _source(base).load_all(SCOPE)
    assert "Agent/helper" in str(err.value)


@pytest.mark.asyncio
async def test_load_layer_never_serves_the_base_under_a_layer_name(face):
    """i-006: ``load_layer`` is an OVERLAY read. ``__base__`` is the sentinel
    for "no overlay", never a tenant — serving the scope's base content for it
    is how ``dna source diff/push`` once digested ``{}`` on both sides and went
    quietly no-op. The same holds for a layer plane this door does not have."""
    base = face.url
    src = _source(base)
    assert await src.load_layer(SCOPE, "tenant", "__base__") == []
    assert await src.load_layer(SCOPE, "region", "eu") == []


# ── offline: decided, not inherited ─────────────────────────────────────

@pytest.mark.asyncio
async def test_without_the_opt_in_a_dead_door_fails_loud_even_with_a_snapshot(
    face, tmp_path,
):
    """Serving yesterday's definitions without saying so is worse than not
    booting. The snapshot exists; the opt-in does not; the read raises."""
    base = face.url
    src = _source(base, snapshot_dir=str(tmp_path))
    assert await src.load_all(SCOPE)
    assert list(tmp_path.iterdir()), "a snapshot should have been written"

    face.stop()
    dead = _source(base, snapshot_dir=str(tmp_path))
    with pytest.raises(ResolveNetworkError):
        await dead.load_all(SCOPE)


@pytest.mark.asyncio
async def test_with_the_opt_in_a_dead_door_serves_the_snapshot_and_says_so(
    face, tmp_path, caplog,
):
    """A consumer that will not boot because the network blinked is worse than
    one running yesterday's definitions — so the fallback exists. It is opt-in
    twice (a snapshot dir AND ``stale-ok``), it announces itself in the log,
    and it records the age so a face can report it.

    The cold source is a FRESH object against a door that is now down — a
    process that restarted during the outage, which is the case the snapshot
    exists for and the one an in-process cache would have missed."""
    import logging

    base = face.url
    warm = _source(base, snapshot_dir=str(tmp_path))
    fresh = await warm.load_all(SCOPE)

    face.stop()
    cold = _source(base, snapshot_dir=str(tmp_path), offline="stale-ok")
    with caplog.at_level(logging.WARNING):
        stale = await cold.load_all(SCOPE)
    assert [d["kind"] for d in stale] == [d["kind"] for d in fresh]
    assert cold.stale_since is not None
    assert "STALE" in caplog.text
    # …and it learned WHICH scope it is serving without being able to ask.
    assert await cold.list_scopes() == [SCOPE]


@pytest.mark.asyncio
async def test_a_refused_credential_is_never_answered_from_a_snapshot(face, tmp_path):
    """An auth failure is a decision about THIS caller. Answering it from a
    cache would serve exactly what the door just declined to serve."""
    base = face.url
    warm = _source(base, snapshot_dir=str(tmp_path))
    await warm.load_all(SCOPE)

    refused = _source(
        base, token="wrong", snapshot_dir=str(tmp_path), offline="stale-ok",
    )
    with pytest.raises(ResolveAuthError):
        await refused.load_all(SCOPE)


@pytest.mark.asyncio
async def test_the_memo_hands_out_copies_so_one_build_cannot_mark_the_next(face):
    """The kernel mutates raw docs in place (``_inherited_from`` markers,
    overlay merges). A memo that handed out its own list would carry one
    build's marks into every later one."""
    base = face.url
    src = _source(base, ttl=60)
    first = await src.load_all(SCOPE)
    first[0]["_inherited_from"] = "somewhere"
    second = await src.load_all(SCOPE)
    assert all("_inherited_from" not in d for d in second)
