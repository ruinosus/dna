"""i-136 — ``POST /v1/memories/{name}/forget``: the door the refusal names.

The defect these tests were written against, in one sentence: i-130 made
``DELETE /v1/memories/{name}`` refuse and the refusal named ``forget``, but the
REST face did not expose ``forget`` — so the only retire affordance this lane
had was the one that now says no, and the remedy it names was unreachable from
here. The portal's memory dashboard lost its delete button, and its memory EDIT
— implemented as a REPLACE (write the new, retire the old) — started leaving
BOTH copies live, with recall answering from both. That second one is the worse
half, because it fails quietly.

The shape of the defect is one this house has a name for: *"the guard exists,
the door does not call it"*, in its other direction — the door exists (the verb,
the core, the MCP tool, the CLI command) and this lane has no way in. So the
tests here cross the REAL FastAPI door with ``TestClient``, never the impl: the
i-130 defect was precisely a function that existed and a route that did not call
it, and a test at the function would have been green through the whole outage.

What each property pins:

* the refusal's remedy names a route the app ACTUALLY serves (derived from the
  app's own route table — rename the route and this goes red);
* forgetting retires the memory from ``list``/``recall`` and leaves the instance
  and its ``valid_to`` readable — invalidated, not deleted;
* **the edit leaves exactly ONE memory live** — the mutant that must be red;
* ``superseded_by`` survives the ``response_model`` (the silent-discard trap)
  AND lands on the tombstone as ``spec.superseded_by_memory``;
* the retry of a half-finished edit works, and lands the pointer;
* an unknown name is a 404 that names the partition, never a confident 200;
* another tenant cannot retire your memory;
* every mutating route on the memory surface is plan-gated (derived over the
  route table, so the NEXT one is covered too).
"""
from __future__ import annotations

import asyncio
import inspect
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


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    """A writable copy of the concierge scope, wired as the source via DNA_BASE_DIR."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _client(dna_dir, **kwargs) -> TestClient:
    return TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE, **kwargs))


def _seed_memory(dna_dir, summary: str, *, tenant: str | None = None) -> dict:
    """Seed one memory via the SAME core the MCP ``remember`` tool uses."""
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        return await M.remember_impl(live, summary, scope=_SCOPE, tenant=tenant)

    return asyncio.run(go())


def _names(c: TestClient, tenant: str) -> set[str]:
    r = c.get("/v1/memories", params={"scope": _SCOPE, "tenant": tenant})
    assert r.status_code == 200, r.text
    return {m["name"] for m in r.json()["memories"]}


def _spec(c: TestClient, name: str, tenant: str) -> dict:
    """Read the stored instance back through the GENERIC instance door — the
    proof that the row is still there is worth nothing if it comes from the
    same route that claims to have kept it."""
    r = c.get(f"/v1/kinds/Engram/instances/{name}",
              params={"scope": _SCOPE, "tenant": tenant})
    assert r.status_code == 200, r.text
    body = r.json()
    return body.get("instance", body).get("spec", {})


# ── the refusal now names a door that exists ────────────────────────────────


def test_the_refused_delete_names_a_route_this_lane_can_actually_call(dna_dir):
    """THE i-136 defect, stated as a property: a refusal must name a remedy the
    reader can perform from where they are standing.

    The kernel's message names the verb, the CLI command, the MCP tool and the
    Python function — four doors, none of them reachable by an HTTP client, and
    that was every door the message had. A caller who cannot perform any of them
    does not stop wanting the memory retired; they go around the wall, and the
    way around this wall is ``psql``.

    The route name is not asserted as a literal: it is EXTRACTED from the
    refusal the caller actually received and looked up in the app's own route
    table. Mutant: rename or move the forget route and leave the hint behind,
    and this goes red — which a hard-coded string in the test could not do,
    because it would be describing the same stale sentence twice."""
    seeded = _seed_memory(dna_dir, "memory the delete button aimed at", tenant="acme")
    app = R.build_app(base_dir=str(dna_dir), scope=_SCOPE)
    served = {getattr(r, "path", "") for r in app.routes}
    with TestClient(app) as c:
        r = c.delete(f"/v1/memories/{seeded['name']}",
                     params={"scope": _SCOPE, "tenant": "acme"})
        assert r.status_code == 403, r.text
        detail = r.json()["detail"]

    # Every `…/v1/…` the message quotes, with the HTTP verb (if any) stripped:
    # what is looked up is the PATH, which is what the route table is keyed on.
    quoted = re.findall(r"`(?:[A-Z]+\s+)?(/v1/[^`\s]+)`", detail)
    assert quoted, (
        f"the refusal names no HTTP route at all, so an HTTP caller is told "
        f"only that the answer is no: {detail!r}"
    )
    for path in quoted:
        assert path in served, (
            f"the refusal points at {path!r}, which this app does not serve — a "
            f"signpost to nowhere is worse than no signpost, because it is "
            f"believed"
        )
    assert "/v1/memories/{name}/forget" in quoted


# ── forgetting retires it, and the row survives ─────────────────────────────


def test_forget_retires_the_memory_and_the_instance_survives(dna_dir):
    """The whole point of the verb, through the real door: the memory leaves
    ``list`` and ``recall``, and the INSTANCE is still readable with its
    ``valid_to`` stamped.

    Both halves matter and they pull in opposite directions. Only the first
    would be satisfied by a hard delete (which is what i-130 stopped); only the
    second would be satisfied by doing nothing at all. Mutant: point the route
    at ``delete_memory_impl`` instead of ``forget_impl`` — the first half stays
    green (it does disappear) and the second goes red, which is the exact
    substitution i-130 was about."""
    seeded = _seed_memory(dna_dir, "the pricing page ships on tuesday", tenant="acme")
    name = seeded["name"]
    with _client(dna_dir) as c:
        assert name in _names(c, "acme")

        r = c.post(f"/v1/memories/{name}/forget",
                   params={"scope": _SCOPE, "tenant": "acme"}, json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["forgotten"] is True
        assert body["outcome"] == "forgotten"
        assert body["kind"] == "Engram"
        assert body["name"] == name
        # Nothing replaced it, so nothing is claimed to have.
        assert body["superseded_by"] is None

        assert name not in _names(c, "acme"), "a forgotten memory still recalls"
        hits = c.get("/v1/memories/search",
                     params={"q": "pricing page tuesday", "scope": _SCOPE,
                             "tenant": "acme", "k": 10}).json()["hits"]
        assert name not in {h.get("name") for h in hits}

        # ... and it was INVALIDATED, not removed: the instance answers, and
        # says when it stopped being in force.
        spec = _spec(c, name, "acme")
        assert spec.get("valid_to"), (
            "the memory vanished from recall without a tombstone — that is a "
            "delete wearing the verb's name"
        )
        assert spec.get("summary") == "the pricing page ships on tuesday"


# ── ⚠️ THE MUTANT: the edit must leave exactly one memory live ──────────────


def test_the_edit_leaves_exactly_one_memory_live(dna_dir):
    """⚠️ The failure i-136 was filed for, driven end to end at the REST level
    the portal drives: write the new version, then retire the old one naming it.

    This is the assertion that must go RED if the second half is skipped,
    refused or silently swallowed — because "the edit left both copies alive"
    is not a crash, not a 500 and not a red suite anywhere else. It is a portal
    that says "saved", a recall that answers with two versions of the same
    thought, and nobody finding out until the answers start contradicting each
    other.

    The count is asserted as EXACTLY one, over the pair, rather than "the new
    one is present": the bug's whole signature is an extra row, and an assertion
    that only looks for the new memory cannot see an extra one."""
    old = _seed_memory(dna_dir, "we bill monthly, per seat", tenant="acme")
    with _client(dna_dir) as c:
        # 1. the portal writes the new version.
        r = c.post("/v1/memories", params={"scope": _SCOPE, "tenant": "acme"},
                   json={"summary": "we bill monthly, per seat, with an annual "
                                    "option at two months free"})
        assert r.status_code == 201, r.text
        new_name = r.json()["name"]

        # 2. and retires the old one, saying what replaced it.
        r = c.post(f"/v1/memories/{old['name']}/forget",
                   params={"scope": _SCOPE, "tenant": "acme"},
                   json={"superseded_by": new_name})
        assert r.status_code == 200, r.text

        live = _names(c, "acme")
        pair = {old["name"], new_name}
        assert live & pair == {new_name}, (
            f"the edit left {sorted(live & pair)} in force — an edit that does "
            f"not retire the original is not an edit, it is a duplicate, and "
            f"recall will answer with both"
        )

        # And the same is true of the surface a user actually reads: recall.
        hits = c.get("/v1/memories/search",
                     params={"q": "how do we bill", "scope": _SCOPE,
                             "tenant": "acme", "k": 20}).json()["hits"]
        assert old["name"] not in {h.get("name") for h in hits}


def test_superseded_by_survives_the_response_model_and_lands_on_the_tombstone(dna_dir):
    """Two hops, and each one has eaten a field in this repo before.

    **The wire.** FastAPI's ``response_model`` DISCARDS what the model does not
    declare, in SILENCE — three fields went that way in one day. So the echo is
    read off the HTTP response, never off ``forget_impl``'s return value.

    **The store.** An echo proves the route read the parameter, not that
    anything was written. So the pointer is read back through the generic
    instance door as ``spec.superseded_by_memory`` — the field ``recall``, the
    contradiction report and the MIF export all follow.

    Mutant for the first: drop ``superseded_by`` from ``ForgetMemoryResponse``.
    Mutant for the second: stop passing it through ``forget_impl`` to the verb.
    Neither one raises anything anywhere; both go red here."""
    old = _seed_memory(dna_dir, "the retro is on fridays", tenant="acme")
    with _client(dna_dir) as c:
        r = c.post("/v1/memories", params={"scope": _SCOPE, "tenant": "acme"},
                   json={"summary": "the retro moved to thursdays"})
        new_name = r.json()["name"]

        r = c.post(f"/v1/memories/{old['name']}/forget",
                   params={"scope": _SCOPE, "tenant": "acme"},
                   json={"superseded_by": new_name})
        assert r.status_code == 200, r.text
        assert r.json()["superseded_by"] == new_name, (
            "the route accepted the pointer and the response model ate it — "
            "the caller cannot tell a recorded supersession from an ignored one"
        )

        spec = _spec(c, old["name"], "acme")
        assert spec.get("superseded_by_memory") == new_name, (
            "the tombstone does not say where the thought went; a later reader "
            "finds a memory that stopped being true and no way to the one that "
            "replaced it"
        )
        assert spec.get("valid_to")


def test_the_response_model_declares_every_key_the_core_returns(dna_dir):
    """The silent-discard trap as a DERIVED guard rather than one field's test.

    The failure mode is not "``superseded_by`` is missing" — it is "the core
    grew a key and the model did not", which is the same accident with a
    different name every time. So the key set comes from ``forget_impl``
    itself, run for real, and is checked against the model's declared fields.
    Add a key to the core's return and forget the model, and this goes red at
    the moment of the mistake instead of in a portal that quietly never sees
    it."""
    from dna_cli import _mcp_server as M
    from dna_cli import _rest_models as m

    seeded = _seed_memory(dna_dir, "a memory to measure the envelope with",
                          tenant="acme")

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        return await M.forget_impl(
            live, seeded["name"], scope=_SCOPE, tenant="acme",
            superseded_by="rem-whatever-0000",
        )

    core_keys = set(asyncio.run(go()))
    declared = set(m.ForgetMemoryResponse.model_fields)
    assert core_keys <= declared, (
        f"{sorted(core_keys - declared)} would be dropped from the response in "
        f"silence — FastAPI does not warn, and the caller cannot tell a field "
        f"that was never sent from one that was filtered out"
    )


# ── idempotence: the half-finished edit is retryable ────────────────────────


def test_forget_is_idempotent_so_a_half_finished_edit_can_be_retried(
    dna_dir, monkeypatch,
):
    """The edit is TWO writes and cannot be made one, so the honest answer is to
    make the second one safe to repeat.

    A retry has to be distinguishable from a first attempt (``outcome`` says
    ``already_forgotten``) without being an ERROR (200, not 409) — a client that
    is told "no" for repeating a step it may have completed will either give up
    or start guessing. And the retry must still be able to land the pointer:
    the crash window for the portal's edit is exactly between the two writes, so
    the recovery path is a forget whose ``superseded_by`` was never recorded.

    Mutant: make the second call 409/404, or let it overwrite ``valid_to`` with
    a fresh stamp — the first moves the memory's end-of-validity forward every
    time somebody retries, which silently rewrites when it stopped being true.

    ⚠️ **The clock is faked, and it has to be.** ``valid_to`` is stamped at
    ``timespec="seconds"``, so two forgets in one test land on the SAME string
    and "the stamp did not move" is true no matter what the code does. Measured:
    the re-stamp mutant above ran GREEN through this assertion before the fake
    clock went in — an assertion passing because the resolution is coarse is
    indistinguishable from one passing because the behaviour is right, and this
    one was the first kind."""
    import dna.memory.verbs as V

    ticks = iter([f"2026-08-07T10:0{i}:00+00:00" for i in range(1, 9)])
    monkeypatch.setattr(V, "_now_iso", lambda now=None: next(ticks))

    seeded = _seed_memory(dna_dir, "standup is at ten", tenant="acme")
    name = seeded["name"]
    with _client(dna_dir) as c:
        first = c.post(f"/v1/memories/{name}/forget",
                       params={"scope": _SCOPE, "tenant": "acme"}, json={})
        assert first.status_code == 200
        assert first.json()["outcome"] == "forgotten"
        stamped = _spec(c, name, "acme")["valid_to"]

        # The retry — with the pointer the interrupted attempt never sent.
        second = c.post(f"/v1/memories/{name}/forget",
                        params={"scope": _SCOPE, "tenant": "acme"},
                        json={"superseded_by": "rem-the-new-one"})
        assert second.status_code == 200, second.text
        assert second.json()["outcome"] == "already_forgotten"
        assert second.json()["forgotten"] is False  # nothing NEW was retired

        spec = _spec(c, name, "acme")
        assert spec["valid_to"] == stamped, (
            "the retry moved the tombstone's date — when a memory stopped being "
            "true is a fact, not a function of how many times somebody retried"
        )
        assert spec["superseded_by_memory"] == "rem-the-new-one", (
            "a retry that cannot finish the half it is retrying is not a retry"
        )


# ── the two ways it says no ─────────────────────────────────────────────────


def test_forget_an_unknown_name_is_a_404_that_names_the_partition(dna_dir):
    """``not_found`` is a 404 and not a 200 with ``forgotten: false``.

    The core reports three outcomes and only two of them are "I retired it, or
    it was already retired". The third means the caller is looking in the wrong
    place — and the commonest wrong place is not a typo, it is the PARTITION: a
    personal Engram is invisible from the workspace lane, which is the exact
    confusion the collapsed boolean hid for so long. So the message says so.

    Mutant: map ``not_found`` to 200. A portal deleting a memory it cannot see
    then reports success, and the user believes it."""
    with _client(dna_dir) as c:
        r = c.post("/v1/memories/rem-no-such-memory-00000/forget",
                   params={"scope": _SCOPE, "tenant": "acme"}, json={})
        assert r.status_code == 404, r.text
        detail = r.json()["detail"]
        assert "personal" in detail, (
            "the likeliest cause of this 404 is the partition, and a 404 that "
            "does not name it sends the caller hunting for a typo"
        )


def test_forget_cannot_reach_another_tenants_memory(dna_dir):
    """#83 isolation, on the new door, stated as the thing that must not happen:
    globex asking to retire acme's memory changes nothing acme can see.

    The status is a 404 rather than a 403 on purpose and it is the SAME 404 as
    an unknown name — because from globex's layer that is exactly what it is,
    and a 403 would confirm the memory exists, which is the leak."""
    acme = _seed_memory(dna_dir, "acme private roadmap note", tenant="acme")
    with _client(dna_dir) as c:
        r = c.post(f"/v1/memories/{acme['name']}/forget",
                   params={"scope": _SCOPE, "tenant": "globex"}, json={})
        assert r.status_code == 404, r.text
        assert acme["name"] in _names(c, "acme"), "another tenant retired it"
        assert not _spec(c, acme["name"], "acme").get("valid_to")


# ── the surface stays metered as it grows ───────────────────────────────────


def test_every_mutating_memory_route_is_plan_gated(dna_dir):
    """Derived over the app's OWN route table, because the failure this guards
    is a route that does not exist yet.

    i-042 wired the plan gate onto the REST write path route by route, and
    nothing has since required a NEW write route to carry it — so the next one
    ships ungated, and the way anybody finds out is a Free workspace writing
    through the web surface for free. Enumerating the four routes that exist
    today would have been the same guard with the same blind spot: it would
    have passed on the day the forget route was added without a gate.

    Static on purpose (it reads the endpoint's source, not its behaviour) — the
    BEHAVIOUR of the gate is proven per route in ``test_rest_write_quota.py``,
    with real tiers and a real store. What is missing there, and only here, is
    the question "did anyone forget to ask?" asked of every route at once."""
    app = R.build_app(base_dir=str(dna_dir), scope=_SCOPE)
    mutating = [
        r for r in app.routes
        if getattr(r, "path", "").startswith("/v1/memories")
        and (getattr(r, "methods", None) or set()) - {"GET", "HEAD", "OPTIONS"}
    ]
    assert len(mutating) >= 4, (
        f"only {len(mutating)} mutating memory routes found — this guard passes "
        f"vacuously if the filter stops matching"
    )
    ungated = [
        r.path for r in mutating
        if "_plan_gate" not in inspect.getsource(r.endpoint)
    ]
    assert not ungated, (
        f"{ungated} write to the memory surface without crossing the plan gate "
        f"— an unmetered door into a family the caller's tier gates"
    )
