"""``GET /v1/memories`` must answer the same question as everything else.

The REST face carried its OWN ``list_memories_impl`` — a copy of the core's,
which had drifted. The copy dropped a memory carrying **any** ``valid_to``;
``dna.application.list_memories_impl`` and ``recall`` both decide with
``currently_valid``, which keeps a memory whose expiry is in the FUTURE. So one
memory, two answers.

**Sharper than "a duplicate drifted": the two answers are two sibling routes of
the SAME app.** ``GET /v1/memories/personal`` already delegates to the core and
unions the shared base scope, so a memory with a future expiry appeared under
"your personal memory" and was missing from the workspace list — on one screen.

And it is reachable today, not in principle: ``interchange.py`` writes
``temporal.validUntil`` through verbatim as ``spec.valid_to``, and
``import_memories_impl`` defaults to ``memory_scope="workspace"``.

The fix deletes the duplicate and delegates, which also closes three adjacent
drifts the copy had introduced — a missing ``affect``, a missing ``personal``
flag, and a sort by NAME where every other memory surface sorts newest-first.
Each is asserted below, because a delegation that quietly dropped one of them
would still make the first assertion pass.
"""
from __future__ import annotations

import pathlib
import shutil

import pytest
import yaml

pytest.importorskip("fastapi", reason="the REST read-API needs the optional 'fastapi' extra")

from fastapi.testclient import TestClient  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"

#: Far enough out that the suite cannot age into the past mid-run, and far
#: enough back that a clock skew cannot drag the tombstone into the present.
_FUTURE = "2099-01-01T00:00:00+00:00"
_PAST = "2000-01-01T00:00:00+00:00"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.setenv("DNA_PERSONAL_ID", "oid-solo")
    return dst


def _client(dna_dir) -> TestClient:
    """``--auth none`` — the single-user local deployment. It is the one mode in
    which BOTH routes under test are reachable without a token, which is what
    lets the divergence be shown as one screen rather than two deployments."""
    return TestClient(R.build_app(
        base_dir=str(dna_dir), scope=_SCOPE, auth="none",
    ))


def _remember(c, summary: str, *, affect: str) -> str:
    r = c.post("/v1/memories", json={
        "summary": summary, "area": "ops", "tags": ["t"], "affect": affect,
    })
    assert r.status_code == 201, r.text
    return r.json()["name"]


def _patch(dna_dir, name: str, **spec_updates) -> None:
    """Edit a stored Engram's spec in place.

    Direct on-disk, deliberately: ``valid_to`` is not something a REST caller
    can set, and the point is that the MIF import path writes exactly this —
    ``temporal.validUntil`` verbatim — so the fixture must produce the instance
    that path produces, not one the API happens to allow."""
    p = dna_dir / _SCOPE / "lessons-learned" / f"{name}.yaml"
    doc = yaml.safe_load(p.read_text())
    doc["spec"].update(spec_updates)
    p.write_text(yaml.dump(doc, allow_unicode=True))


@pytest.fixture
def seeded(dna_dir):
    """Three memories, written then edited on disk BEFORE any read.

    Order matters: the app caches instances for 60s, so a read taken before the
    edit would serve the pre-edit instance and the test would measure the cache
    rather than the route. Seeding and asserting therefore use two separate
    clients.

    ``created_at`` is stamped explicitly because the write path uses second
    precision — three writes in one second are indistinguishable, and "sorted
    newest-first" would hold for a list that was not sorted at all.
    """
    with _client(dna_dir) as c:
        live = _remember(c, "the live one", affect="triumph")
        expiring = _remember(c, "expires in 2099", affect="surprise")
        forgotten = _remember(c, "already forgotten", affect="wistful")

    _patch(dna_dir, live, created_at="2026-01-01T00:00:00+00:00")
    # A FUTURE expiry — still valid, and the whole point.
    _patch(dna_dir, expiring,
           created_at="2026-03-01T00:00:00+00:00", valid_to=_FUTURE)
    # A PAST expiry — a real tombstone, which must STAY hidden.
    _patch(dna_dir, forgotten,
           created_at="2026-02-01T00:00:00+00:00", valid_to=_PAST)
    return {"live": live, "expiring": expiring, "forgotten": forgotten}


def _names(payload) -> list[str]:
    return [m["name"] for m in payload["memories"]]


def test_a_memory_whose_expiry_is_in_the_future_is_still_listed(dna_dir, seeded):
    """THE regression. ``valid_to`` in the future means "valid until then", not
    "gone" — which is what ``currently_valid`` says and what ``recall`` does."""
    with _client(dna_dir) as c:
        listed = c.get("/v1/memories")
    assert listed.status_code == 200, listed.text
    assert seeded["expiring"] in _names(listed.json()), (
        "a memory whose expiry has not arrived was dropped from the workspace "
        "list — the copy tested `if spec.get('valid_to')`, which is true for "
        "any expiry at all"
    )


def test_a_memory_whose_expiry_has_passed_stays_hidden(dna_dir, seeded):
    """The other half, and the one that stops the fix being "delete the
    filter". A forgotten memory is a tombstone: ``forget`` demotes rather than
    deletes, and both surfaces must keep hiding it."""
    with _client(dna_dir) as c:
        listed = c.get("/v1/memories")
    assert seeded["forgotten"] not in _names(listed.json()), (
        "a memory demoted by forget resurfaced — the guard was removed rather "
        "than corrected"
    )


def test_the_two_sibling_routes_give_one_answer(dna_dir, seeded):
    """The divergence as a user meets it: both routes, one app, one memory.

    ``/v1/memories/personal`` unions the caller's partition with the shared
    base, so the SAME instance is in scope for both — and before the fix it was
    present in one list and absent from the other on the same screen."""
    with _client(dna_dir) as c:
        workspace = c.get("/v1/memories")
        personal = c.get("/v1/memories/personal")
    assert workspace.status_code == 200, workspace.text
    assert personal.status_code == 200, personal.text

    name = seeded["expiring"]
    in_personal = name in _names(personal.json())
    in_workspace = name in _names(workspace.json())
    assert in_personal, (
        "fixture broken: the personal route (which already delegates to the "
        "core) does not see the memory, so it cannot demonstrate a divergence"
    )
    assert in_workspace == in_personal, (
        f"the same memory is visible on /v1/memories/personal "
        f"({in_personal}) and not on /v1/memories ({in_workspace}) — two "
        f"routes of one app answering one question two ways"
    )


def test_the_listing_carries_affect_and_the_personal_flag(dna_dir, seeded):
    """Two fields the duplicate silently omitted. ``affect`` is stored on every
    Engram and is what a card renders; ``personal`` (i-068) is the per-item flag
    that tells a caller's own memory apart from a shared one."""
    with _client(dna_dir) as c:
        listed = c.get("/v1/memories").json()
    row = next(m for m in listed["memories"] if m["name"] == seeded["live"])
    assert row["affect"] == "triumph", row
    assert row["personal"] is False, (
        "a workspace read is never personal, but the field has to BE there — "
        "its absence is what made the two list surfaces different shapes"
    )


def test_the_listing_is_newest_first(dna_dir, seeded):
    """The duplicate sorted by NAME — and a memory's name is a hash-prefixed
    slug, so the order was effectively arbitrary. Every other memory surface
    answers newest-first."""
    with _client(dna_dir) as c:
        listed = c.get("/v1/memories").json()
    created = [m["created_at"] for m in listed["memories"] if m["created_at"]]
    assert created == sorted(created, reverse=True), (
        f"the workspace list is not newest-first: {created}"
    )
    # And it is genuinely ordered by DATE, not by a name that happens to sort
    # the same way — the two seeded survivors are checked by identity.
    names = _names(listed)
    assert names.index(seeded["expiring"]) < names.index(seeded["live"]), (
        "the newer memory did not come first"
    )


def test_a_workspaces_list_reads_the_scope_its_writes_land_in(tmp_path, monkeypatch):
    """The fourth divergence, and the least visible: WHICH SCOPE is read.

    The deleted copy resolved ``scope or live.base_scope``. Every other memory
    verb — ``remember``, ``recall``, ``forget`` — resolves through
    ``_resolve_memory_target`` → ``live.default_scope(tenant)``, which under
    multi-workspace (``DNA_VENDOR_WORKSPACE`` set) is ``tenant-<ws>`` for a
    non-vendor workspace, NOT the vendor's base.

    So the list was reading a scope that workspace never writes to, while its
    memories sat where ``remember`` had put them. A memory written and
    recallable was absent from the list — for a reason that has nothing to do
    with ``valid_to``.

    Asserted end to end (write through the route, read through the route) so it
    cannot pass by agreeing with a hard-coded scope name.
    """
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    ws = "ws-outsider"
    # Provision the workspace's own scope. Without it a filesystem store raises
    # "Scope not found" — which is what EVERY route resolving default_scope
    # already does here (``/v1/agents`` included) and is not this test's subject.
    scope_dir = dst / f"tenant-{ws}"
    scope_dir.mkdir(parents=True, exist_ok=True)
    (scope_dir / "Genome.yaml").write_text(yaml.dump({
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": f"tenant-{ws}"}, "spec": {},
    }))
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.setenv("DNA_VENDOR_WORKSPACE", "ws-vendor")

    with _client(dst) as c:
        written = c.post("/v1/memories", params={"tenant": ws}, json={
            "summary": "the outsider's own", "area": "ops",
            "tags": [], "affect": "triumph",
        })
        assert written.status_code == 201, written.text
        name = written.json()["name"]
        listed = c.get("/v1/memories", params={"tenant": ws})

    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["scope"] == f"tenant-{ws}", (
        f"the list resolved scope {body['scope']!r}; a non-vendor workspace's "
        f"memories live in tenant-{ws}, which is where remember/recall/forget "
        f"all resolve"
    )
    assert name in _names(body), (
        "a memory this workspace just wrote through this same app is missing "
        "from its own list — the read and the write resolved different scopes"
    )
