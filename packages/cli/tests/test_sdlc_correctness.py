"""SDLC discoverability & correctness fixes.

Two CLI behaviours that were wrong/missing:

1. `epic show` counted 0/0 stories because it read the stale forward
   `Feature.spec.stories[]` list. The real link is `Story.spec.feature`
   (maintained one-way at `story create --feature`). `feature show` already
   reverse-looks-up; `epic show` must too.

2. There was no verb to move a Feature `discovery → in-development` without
   clobbering its fields (`feature create` is a full overwrite). `feature
   start` does a read-modify-write that preserves every other field and
   stamps the timeline.

Approach mirrors test_sdlc_workitem_cli.py: patch `dna_session` with an
in-memory fake. Here the fake also implements `query_list` (needed by the
reverse-lookup) and re-reads written docs.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from click.testing import CliRunner

from dna_cli.sdlc_cmd import sdlc
from dna_cli._ctx import SESSION_PROVIDER_KEY


@pytest.fixture
def runner(session_obj):
    """CliRunner whose invokes carry the injected session by default."""
    r = CliRunner()
    _orig = r.invoke

    def _invoke(*args, **kwargs):
        kwargs.setdefault("obj", session_obj)
        return _orig(*args, **kwargs)

    r.invoke = _invoke  # type: ignore[method-assign]
    return r


class _FakeDocView:
    def __init__(self, raw: dict):
        self._raw = raw
        self.name = raw.get("metadata", {}).get("name") or raw.get("name")
        self.kind = raw.get("kind")
        self.spec = raw.get("spec") or {}


class _FakeKernel:
    def __init__(self, store: dict):
        self._store = store
        self._kinds: dict = {}

    def with_tenant(self, tenant):
        return self

    async def write_document(self, scope, kind, name, raw, **_):
        self._store[(scope, kind, name)] = raw
        return "v1"


class _FakeSession:
    def __init__(self, store: dict, scope: str):
        self._store = store
        self.scope = scope
        self.kernel = _FakeKernel(store)
        self.holder = type("_H", (), {"reload": lambda self: None})()

    def get_doc(self, kind, name, *, tenant=None):
        raw = self._store.get((self.scope, kind, name))
        return _FakeDocView(raw) if raw is not None else None

    def query_list(self, kind, *, tenant=None):
        return [
            _FakeDocView(raw)
            for (sc, kd, _nm), raw in self._store.items()
            if sc == self.scope and kd == kind
        ]

    def run(self, coro):
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


@pytest.fixture
def store():
    """The in-memory backing dict the fake session reads/writes."""
    return {}


@pytest.fixture
def session_obj(store):
    """The ctx.obj to inject (f-cli-session-injection): a session factory."""

    @contextmanager
    def _fake(scope=None, *, tenant=None, timeout=30.0):
        yield _FakeSession(store, scope or "dna-development")

    return {SESSION_PROVIDER_KEY: _fake}


def _seed(store, kind, name, spec, scope="dna-development"):
    store[(scope, kind, name)] = {
        "kind": kind,
        "metadata": {"name": name},
        "spec": spec,
    }


# ─── Fix 1: epic show reverse-lookup ───────────────────────────────


def test_epic_show_counts_stories_via_reverse_lookup(runner, store):
    """Stories link to a Feature via Story.spec.feature; epic show must count
    them even when Feature.spec.stories[] is empty/stale. Features link to
    the Epic via the back-ref Feature.spec.epic (the forward
    Epic.spec.features[] is never populated)."""
    _seed(store, "Epic", "e-x", {"status": "planning"})
    # Feature has NO forward stories[] list — the stale-but-common case —
    # and links up via the back-ref Feature.spec.epic.
    _seed(store, "Feature", "f-x", {"status": "in-development", "epic": "e-x"})
    _seed(store, "Story", "s-a", {"status": "done", "feature": "f-x"})
    _seed(store, "Story", "s-b", {"status": "todo", "feature": "f-x"})

    result = runner.invoke(sdlc, ["epic", "show", "e-x"])
    assert result.exit_code == 0, result.output
    # 1 of 2 done — NOT 0/0.
    assert "1/2" in result.output
    assert "0/0" not in result.output


def test_epic_show_burndown_totals(runner, store):
    """Burndown line aggregates across features by reverse-lookup."""
    _seed(store, "Epic", "e-y", {"status": "planning"})
    _seed(store, "Feature", "f-1", {"status": "done", "epic": "e-y"})
    _seed(store, "Feature", "f-2", {"status": "in-development", "epic": "e-y"})
    _seed(store, "Story", "s-1", {"status": "done", "feature": "f-1"})
    _seed(store, "Story", "s-2", {"status": "done", "feature": "f-2"})
    _seed(store, "Story", "s-3", {"status": "todo", "feature": "f-2"})

    result = runner.invoke(sdlc, ["epic", "show", "e-y"])
    assert result.exit_code == 0, result.output
    assert "2/3" in result.output  # 2 done of 3 total


# ─── Fix 2: feature start (status transition, field-preserving) ────


def test_feature_start_moves_to_in_development(runner, store):
    """`feature start` flips discovery → in-development."""
    _seed(store, "Feature", "f-z", {
        "status": "discovery",
        "description": "important desc",
        "epic": "e-z",
        "priority": "high",
        "timeline": [{"type": "status_change", "to": "discovery"}],
    })
    result = runner.invoke(sdlc, ["feature", "start", "f-z"])
    assert result.exit_code == 0, result.output
    raw = store[("dna-development", "Feature", "f-z")]
    assert raw["spec"]["status"] == "in-development"


def test_feature_start_preserves_fields(runner, store):
    """The transition must NOT clobber desc/epic/priority (unlike create)."""
    _seed(store, "Feature", "f-keep", {
        "status": "discovery",
        "description": "do not lose me",
        "epic": "e-keep",
        "priority": "highest",
        "business_value": 800,
    })
    result = runner.invoke(sdlc, ["feature", "start", "f-keep"])
    assert result.exit_code == 0, result.output
    spec = store[("dna-development", "Feature", "f-keep")]["spec"]
    assert spec["description"] == "do not lose me"
    assert spec["epic"] == "e-keep"
    assert spec["priority"] == "highest"
    assert spec["business_value"] == 800


def test_feature_start_stamps_timeline(runner, store):
    """A status_change event lands on the timeline."""
    _seed(store, "Feature", "f-tl", {"status": "discovery", "timeline": []})
    result = runner.invoke(sdlc, ["feature", "start", "f-tl"])
    assert result.exit_code == 0, result.output
    tl = store[("dna-development", "Feature", "f-tl")]["spec"].get("timeline", [])
    assert any(
        e.get("type") == "status_change" and e.get("to") == "in-development"
        for e in tl
    ), tl


def test_feature_start_missing_feature_errors(runner, store):
    """Unknown feature → non-zero exit, clear message."""
    result = runner.invoke(sdlc, ["feature", "start", "f-ghost"])
    assert result.exit_code != 0
    assert "f-ghost" in result.output or "not found" in result.output.lower()


# ─── Fix 3: epic show resolves FEATURES via reverse-lookup ─────────
# (s-epic-show-forward-features) `feature create --epic X` sets only the
# back-ref Feature.spec.epic; the forward Epic.spec.features[] is never
# populated, so `epic show` printed "(no features linked)" even for
# correctly-linked features. epic show must reverse-look-up features.


def test_epic_show_lists_features_via_backref(runner, store):
    """Features appear even when Epic.spec.features[] is absent (the real
    world — the forward link is never maintained)."""
    _seed(store, "Epic", "e-p", {"status": "in-progress"})  # NO features[]
    _seed(store, "Feature", "f-a", {"status": "in-development", "epic": "e-p"})
    _seed(store, "Feature", "f-b", {"status": "done", "epic": "e-p"})
    _seed(store, "Feature", "f-other", {"status": "done", "epic": "e-zzz"})
    _seed(store, "Story", "s-1", {"status": "done", "feature": "f-a"})
    _seed(store, "Story", "s-2", {"status": "todo", "feature": "f-a"})

    result = runner.invoke(sdlc, ["epic", "show", "e-p"])
    assert result.exit_code == 0, result.output
    assert "f-a" in result.output
    assert "f-b" in result.output
    # A feature belonging to a DIFFERENT epic must not leak in.
    assert "f-other" not in result.output
    assert "(no features linked)" not in result.output
    # Burndown aggregates the reverse-looked-up features' stories: 1/2.
    assert "1/2" in result.output


def test_epic_show_no_features_when_none_reference_epic(runner, store):
    """The empty state still fires when truly no feature back-refs the epic."""
    _seed(store, "Epic", "e-empty", {"status": "planning"})
    _seed(store, "Feature", "f-elsewhere", {"status": "done", "epic": "e-other"})
    result = runner.invoke(sdlc, ["epic", "show", "e-empty"])
    assert result.exit_code == 0, result.output
    assert "(no features linked)" in result.output


def test_epic_ship_cascades_features_via_backref(runner, store):
    """epic ship cascade-closes features via reverse-lookup (back-ref), not
    the never-populated forward Epic.spec.features[] / Feature.spec.stories[]."""
    _seed(store, "Epic", "e-ship", {"status": "in-progress"})  # NO features[]
    _seed(store, "Feature", "f-done-kids", {"status": "in-development", "epic": "e-ship"})
    _seed(store, "Feature", "f-open-kids", {"status": "in-development", "epic": "e-ship"})
    _seed(store, "Story", "s-x", {"status": "done", "feature": "f-done-kids"})
    _seed(store, "Story", "s-y", {"status": "done", "feature": "f-done-kids"})
    _seed(store, "Story", "s-z", {"status": "todo", "feature": "f-open-kids"})

    result = runner.invoke(sdlc, ["epic", "ship", "e-ship"])
    assert result.exit_code == 0, result.output
    # All-done feature cascaded to done; the one with an open story did not.
    assert store[("dna-development", "Feature", "f-done-kids")]["spec"]["status"] == "done"
    assert store[("dna-development", "Feature", "f-open-kids")]["spec"]["status"] == "in-development"


# ─── Fix 4: `dna sdlc cite` accepts any citable Kind ──────────────
# (s-cite-any-citable-kind) cite used to hardcode the cited side to
# Reference/<name>. It now accepts <Kind>/<name> for the cited target
# (Research, ADR, Reference, ...) while a bare name still defaults to
# Reference (backwards-compat). Bidirectionality is preserved: the cited
# doc gains spec.cited_by, the caller gains spec.references.


def test_cite_cross_kind_research_from_adr(runner, store):
    """cite Research/<name> --from ADR/<name> links both sides."""
    _seed(store, "Research", "r-portability", {"title": "R", "status": "draft"})
    _seed(store, "ADR", "adr-0007", {"title": "A", "status": "accepted"})
    result = runner.invoke(
        sdlc, ["cite", "Research/r-portability", "--from", "ADR/adr-0007"]
    )
    assert result.exit_code == 0, result.output
    # Cited side: Research.spec.cited_by += "ADR/adr-0007".
    r = store[("dna-development", "Research", "r-portability")]["spec"]
    assert "ADR/adr-0007" in (r.get("cited_by") or [])
    # Caller side: ADR.spec.references += "Research/r-portability" (qualified).
    a = store[("dna-development", "ADR", "adr-0007")]["spec"]
    assert "Research/r-portability" in (a.get("references") or [])


def test_cite_bare_name_defaults_to_reference(runner, store):
    """A bare cited name still resolves to Reference (backwards-compat) and
    the caller stores the bare name (not a qualified ref)."""
    _seed(store, "Reference", "ref-x", {"title": "T", "kind_of": "web", "summary": "s"})
    _seed(store, "Spec", "spec-y", {"title": "S", "status": "draft"})
    result = runner.invoke(sdlc, ["cite", "ref-x", "--from", "Spec/spec-y"])
    assert result.exit_code == 0, result.output
    ref = store[("dna-development", "Reference", "ref-x")]["spec"]
    assert "Spec/spec-y" in (ref.get("cited_by") or [])
    spec = store[("dna-development", "Spec", "spec-y")]["spec"]
    # Bare form preserved for Reference targets.
    assert spec.get("references") == ["ref-x"]


def test_cite_missing_cited_doc_errors(runner, store):
    """Citing a non-existent target → non-zero exit, clear message."""
    _seed(store, "ADR", "adr-z", {"title": "A", "status": "accepted"})
    result = runner.invoke(
        sdlc, ["cite", "Research/ghost", "--from", "ADR/adr-z"]
    )
    assert result.exit_code != 0
    assert "Research/ghost" in result.output


def test_uncite_cross_kind_symmetric(runner, store):
    """uncite removes both the back-ref and the forward ref for any Kind."""
    _seed(store, "Research", "r-u", {
        "title": "R", "status": "draft", "cited_by": ["ADR/adr-u"],
    })
    _seed(store, "ADR", "adr-u", {
        "title": "A", "status": "accepted", "references": ["Research/r-u"],
    })
    result = runner.invoke(
        sdlc, ["uncite", "Research/r-u", "--from", "ADR/adr-u"]
    )
    assert result.exit_code == 0, result.output
    assert store[("dna-development", "Research", "r-u")]["spec"]["cited_by"] == []
    assert store[("dna-development", "ADR", "adr-u")]["spec"]["references"] == []
