"""``write_document`` is an UPDATE, not a silent REPLACE.

The hole this closes: the generic write built its document from scratch —
``{"apiVersion", "kind", "metadata": {"name"}, "spec": dict(spec)}`` — and handed
it to ``kernel.write_document``. Every consequence of that was invisible until it
had already destroyed something:

* **history erased.** A Story / Issue / ADR carries ``spec.timeline`` — an
  append-only activity log. Updating ``priority`` through the generic tool
  replaced the whole spec, so the timeline vanished unless the caller happened to
  re-send every event it had ever accumulated.
* **the read surfaces went blind.** No ``created_at`` / ``updated_at`` stamp, so
  a Kaizen / ADR / Spike created generically never reached ``sdlc_digest``'s
  buckets (the exact i-078 failure, one write path later).
* **lost updates.** Two writers, last one wins, no way to even notice.

Four properties are asserted here, each one a thing that used to be impossible:

1. an update MERGES over the stored spec — untouched fields (the timeline above
   all) survive;
2. it STAMPS what :data:`~dna.application.sdlc.DATED_SPEC_FIELDS` declares for
   the target Kind — and nothing for a Kind outside that registry, whose schema
   may forbid the keys;
3. a caller can still CLEAR a field (explicit ``None``) and still REPLACE the
   whole spec (``merge=False``) — the destructive semantics stay reachable, but
   only on purpose;
4. ``if_match`` (the etag ``get_document`` hands back) makes the lost update
   detectable instead of silent.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.application import documents as D
from dna.application import sdlc as S
from dna.application.live import LiveDna
from dna.kernel import Kernel

_SCOPE = "board"


def _write_yaml(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(doc, default_flow_style=False))


@pytest.fixture()
def live(tmp_path: Path) -> LiveDna:
    base = tmp_path / ".dna"
    _write_yaml(base / _SCOPE / "Genome.yaml", {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": _SCOPE}, "spec": {},
    })
    (base / "_lib").mkdir(parents=True, exist_ok=True)
    k = Kernel.auto()
    k.source(FilesystemWritableSource(str(base), kernel=k))
    k.cache(FilesystemCache(str(base)))
    return LiveDna(base_scope=_SCOPE, kernel=k, provider=None,
                   vendor_workspace=None)


async def _seed_story(live: LiveDna, name: str = "s-one") -> dict[str, Any]:
    """A Story filed through the NAMED write core — i.e. with a real timeline."""
    await S.create_feature(
        live.kernel, _SCOPE, "f-one", title="F", description="d")
    await S.create_story(
        live.kernel, _SCOPE, name, feature="f-one", description="d",
        title="T", actor="founder@example.test",
        acceptance_criteria=["Given a seeded Story, when read, then it exists"],
        definition_of_done=["seeded"],
    )
    return await live.kernel.get_document(_SCOPE, "Story", name)


# ── 1. an update MERGES — the timeline survives ─────────────────────────────


@pytest.mark.asyncio
async def test_update_preserves_the_timeline_and_the_untouched_fields(live):
    """THE regression. A one-field update through the generic write used to
    replace the whole spec: the timeline, the status, the feature link and the
    description all disappeared because the caller only sent ``priority``."""
    before = await _seed_story(live)
    assert len(before["spec"]["timeline"]) == 1  # the create's status_change

    await D.write_document_impl(
        live, kind="Story", name="s-one", scope=_SCOPE,
        spec={"priority": "high"},
    )

    after = (await D.get_document_impl(
        live, kind="Story", name="s-one", scope=_SCOPE))["document"]["spec"]
    assert after["timeline"] == before["spec"]["timeline"]   # history intact
    assert after["status"] == "todo"                         # untouched
    assert after["feature"] == "f-one"
    assert after["description"] == "d"
    assert after["title"] == "T"
    assert after["priority"] == "high"                       # the actual change


@pytest.mark.asyncio
async def test_update_reports_that_it_merged_and_did_not_create(live):
    await _seed_story(live)
    out = await D.write_document_impl(
        live, kind="Story", name="s-one", scope=_SCOPE, spec={"priority": "low"})
    assert out["created"] is False
    assert out["merged"] is True


@pytest.mark.asyncio
async def test_create_through_the_generic_write_still_works(live):
    out = await D.write_document_impl(
        live, kind="ADR", name="adr-x", scope=_SCOPE,
        spec={"title": "T", "status": "proposed", "context": "c",
              "decision": "d"},
    )
    assert out["created"] is True
    got = await D.get_document_impl(
        live, kind="ADR", name="adr-x", scope=_SCOPE)
    assert got["document"]["spec"]["decision"] == "d"


# ── 2. it stamps exactly what the Kind's read surfaces date it by ───────────


@pytest.mark.asyncio
async def test_create_stamps_the_dated_fields_the_kind_declares(live):
    """An ADR filed generically is dated, so ``sdlc_digest`` can place it in a
    window. Before this, ``_digest._creation_field`` read ``created_at``,
    ``parse_iso_utc(None)`` returned None, and the ADR never reached ``decided``
    — in any window, forever."""
    await D.write_document_impl(
        live, kind="ADR", name="adr-dated", scope=_SCOPE,
        spec={"title": "T", "status": "proposed", "context": "c",
              "decision": "d"},
    )
    spec = (await D.get_document_impl(
        live, kind="ADR", name="adr-dated", scope=_SCOPE))["document"]["spec"]
    for field in S.DATED_SPEC_FIELDS["ADR"]:
        assert spec.get(field), f"ADR must be stamped with {field}"


@pytest.mark.asyncio
async def test_kaizen_is_stamped_with_only_what_its_registry_entry_declares(live):
    """A Kaizen is an observation, not a work item — the registry declares
    ``created_at`` and no ``updated_at`` arc, and the generic write owes exactly
    that. (Its schema is ``additionalProperties: false``, so inventing fields
    here would be a write-time schema veto, not a cosmetic difference.)"""
    assert S.DATED_SPEC_FIELDS["Kaizen"] == ("created_at",)
    await D.write_document_impl(
        live, kind="Kaizen", name="kz-1", scope=_SCOPE,
        spec={"body": "observed something", "status": "observed"},
    )
    spec = (await D.get_document_impl(
        live, kind="Kaizen", name="kz-1", scope=_SCOPE))["document"]["spec"]
    assert spec.get("created_at")
    assert "updated_at" not in spec


@pytest.mark.asyncio
async def test_a_kind_outside_the_dated_registry_gets_no_stamps(live):
    """The registry is the contract, both ways: a Kind no read surface dates
    must not have timestamps invented for it — many such Kinds close their
    schema and would veto the write."""
    assert "ModelProfile" not in S.DATED_SPEC_FIELDS
    await D.write_document_impl(
        live, kind="ModelProfile", name="m-1", scope=_SCOPE,
        spec={"model_id": "m-1", "provider": "openai"},
    )
    spec = (await D.get_document_impl(
        live, kind="ModelProfile", name="m-1", scope=_SCOPE))["document"]["spec"]
    assert spec == {"model_id": "m-1", "provider": "openai"}


@pytest.mark.asyncio
async def test_updated_at_moves_but_created_at_is_never_reforged(live):
    await D.write_document_impl(
        live, kind="Story", name="s-stamp", scope=_SCOPE,
        spec={"description": "d", "status": "todo"},
    )
    first = (await D.get_document_impl(
        live, kind="Story", name="s-stamp", scope=_SCOPE))["document"]["spec"]
    await D.write_document_impl(
        live, kind="Story", name="s-stamp", scope=_SCOPE,
        spec={"priority": "high"}, now="2030-01-01T00:00:00+00:00",
    )
    second = (await D.get_document_impl(
        live, kind="Story", name="s-stamp", scope=_SCOPE))["document"]["spec"]
    assert second["created_at"] == first["created_at"]
    assert second["updated_at"] == "2030-01-01T00:00:00+00:00"


@pytest.mark.asyncio
async def test_an_explicit_stamp_from_the_caller_wins(live):
    """Importing a document with its real dates must stay possible — the stamp
    is a floor for what the readers need, not an override of the caller."""
    await D.write_document_impl(
        live, kind="ADR", name="adr-old", scope=_SCOPE,
        spec={"title": "T", "status": "accepted", "context": "c",
              "decision": "d", "created_at": "2019-03-04T05:06:07+00:00"},
    )
    spec = (await D.get_document_impl(
        live, kind="ADR", name="adr-old", scope=_SCOPE))["document"]["spec"]
    assert spec["created_at"] == "2019-03-04T05:06:07+00:00"


@pytest.mark.asyncio
async def test_created_at_is_never_forged_onto_an_older_document(live):
    """A pre-existing document with no ``created_at`` and no timeline is left
    undated rather than stamped "today" — the same honesty rule
    ``plan_date_repair`` holds: a confidently wrong date pollutes every future
    digest window, an undated document merely says it does not know."""
    await live.kernel.write_document(_SCOPE, "Story", "s-legacy", {
        "apiVersion": S.SDLC_API_VERSION, "kind": "Story",
        "metadata": {"name": "s-legacy"},
        "spec": {"description": "filed long ago", "status": "todo"},
    })
    await D.write_document_impl(
        live, kind="Story", name="s-legacy", scope=_SCOPE,
        spec={"priority": "low"},
    )
    spec = (await D.get_document_impl(
        live, kind="Story", name="s-legacy", scope=_SCOPE))["document"]["spec"]
    assert "created_at" not in spec
    assert spec["updated_at"]  # the write itself IS datable — this one is honest


@pytest.mark.asyncio
async def test_created_at_self_heals_from_the_documents_own_timeline(live):
    """…but when the document CAN prove when it started (its own timeline, written
    by the create path at create time), the update repairs the missing stamp —
    the same self-heal ``set_status`` / ``add_comment`` already do."""
    await live.kernel.write_document(_SCOPE, "Story", "s-heal", {
        "apiVersion": S.SDLC_API_VERSION, "kind": "Story",
        "metadata": {"name": "s-heal"},
        "spec": {"description": "d", "status": "todo", "timeline": [
            {"at": "2026-01-02T03:04:05+00:00", "actor": "cli",
             "type": "status_change", "source": "cli", "to": "todo"},
        ]},
    })
    await D.write_document_impl(
        live, kind="Story", name="s-heal", scope=_SCOPE, spec={"priority": "low"})
    spec = (await D.get_document_impl(
        live, kind="Story", name="s-heal", scope=_SCOPE))["document"]["spec"]
    assert spec["created_at"] == "2026-01-02T03:04:05+00:00"


# ── 3. clearing and replacing stay possible — on purpose ────────────────────


@pytest.mark.asyncio
async def test_explicit_null_clears_one_field(live):
    """The cost of merge semantics is that omission no longer means removal, so
    removal needs a word: JSON ``null``. Unambiguous over the wire, and no board
    field wants a literal null value."""
    await _seed_story(live)
    await D.write_document_impl(
        live, kind="Story", name="s-one", scope=_SCOPE, spec={"priority": "high"})
    await D.write_document_impl(
        live, kind="Story", name="s-one", scope=_SCOPE, spec={"priority": None})
    spec = (await D.get_document_impl(
        live, kind="Story", name="s-one", scope=_SCOPE))["document"]["spec"]
    assert "priority" not in spec
    assert spec["timeline"]  # clearing one field is still not a wipe


@pytest.mark.asyncio
async def test_merge_false_is_the_explicit_replace_door(live):
    """The old behavior, reachable only by asking for it by name."""
    await _seed_story(live)
    out = await D.write_document_impl(
        live, kind="Story", name="s-one", scope=_SCOPE, merge=False,
        spec={"description": "rewritten", "status": "todo"},
    )
    assert out["merged"] is False
    spec = (await D.get_document_impl(
        live, kind="Story", name="s-one", scope=_SCOPE))["document"]["spec"]
    assert "timeline" not in spec        # the caller asked for a replace
    assert spec["description"] == "rewritten"


# ── 4. the lost update is detectable ───────────────────────────────────────


@pytest.mark.asyncio
async def test_get_document_hands_back_an_etag(live):
    await _seed_story(live)
    got = await D.get_document_impl(
        live, kind="Story", name="s-one", scope=_SCOPE)
    assert got["etag"]
    again = await D.get_document_impl(
        live, kind="Story", name="s-one", scope=_SCOPE)
    assert again["etag"] == got["etag"]  # stable for unchanged content


@pytest.mark.asyncio
async def test_if_match_refuses_a_stale_write_and_writes_nothing(live):
    await _seed_story(live)
    stale = (await D.get_document_impl(
        live, kind="Story", name="s-one", scope=_SCOPE))["etag"]
    # somebody else moves the document…
    await D.write_document_impl(
        live, kind="Story", name="s-one", scope=_SCOPE, spec={"owner": "bob"})
    # …and the first writer's read-modify-write is now based on stale content.
    with pytest.raises(D.ConcurrentWriteError) as ei:
        await D.write_document_impl(
            live, kind="Story", name="s-one", scope=_SCOPE,
            spec={"owner": "alice"}, if_match=stale,
        )
    assert "s-one" in str(ei.value)
    assert stale in str(ei.value)
    spec = (await D.get_document_impl(
        live, kind="Story", name="s-one", scope=_SCOPE))["document"]["spec"]
    assert spec["owner"] == "bob"  # the loser wrote nothing


@pytest.mark.asyncio
async def test_the_etag_a_write_returns_chains_into_the_next_if_match(live):
    await _seed_story(live)
    etag = (await D.get_document_impl(
        live, kind="Story", name="s-one", scope=_SCOPE))["etag"]
    out = await D.write_document_impl(
        live, kind="Story", name="s-one", scope=_SCOPE,
        spec={"owner": "alice"}, if_match=etag)
    assert out["etag"] and out["etag"] != etag
    # the returned etag is immediately usable — no re-read round trip.
    await D.write_document_impl(
        live, kind="Story", name="s-one", scope=_SCOPE,
        spec={"owner": "carol"}, if_match=out["etag"])


@pytest.mark.asyncio
async def test_if_match_on_an_absent_document_is_refused(live):
    """``if_match`` asserts "I am updating the document I read". Letting it
    satisfy a CREATE would turn the guard into a no-op exactly when the document
    the caller thought it had was deleted under it."""
    with pytest.raises(D.ConcurrentWriteError, match="no Story"):
        await D.write_document_impl(
            live, kind="Story", name="s-ghost", scope=_SCOPE,
            spec={"description": "d", "status": "todo"}, if_match="deadbeef",
        )
