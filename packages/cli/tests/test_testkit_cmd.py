"""Unit net for `dna sdlc test-guide / test-run` helpers (testkit Phase C)."""
from __future__ import annotations

import click

from dna_cli._ctx import SESSION_PROVIDER_KEY
from dna_cli import testkit_cmd as tk


def test_ac_text_normalizes_dict_and_string() -> None:
    assert tk._ac_text({"text": "  foo  "}) == "foo"
    assert tk._ac_text({"criterion": "bar"}) == "bar"
    assert tk._ac_text("baz") == "baz"
    assert tk._ac_text(None) == ""


def test_ref_story_name_extracts_only_stories() -> None:
    assert tk._ref_story_name("Story/s-x") == "s-x"
    assert tk._ref_story_name("s-x") == "s-x"  # bare passes through
    assert tk._ref_story_name("Issue/i-y") is None  # only Stories carry the hub
    assert tk._ref_story_name("") is None


def test_build_testkit_raw_uses_testkit_api_version() -> None:
    raw = tk._build_testkit_raw("TestGuide", "tg-x", {"description": "d"})
    assert raw["apiVersion"] == "github.com/ruinosus/dna/testkit/v1"
    assert raw["kind"] == "TestGuide"
    assert raw["metadata"]["name"] == "tg-x"
    assert raw["spec"]["description"] == "d"


class _FakeRun:
    def __init__(self, name: str, spec: dict) -> None:
        self.name = name
        self.spec = spec


class _FakeSession:
    def __init__(self, runs: list, guides: list | None = None) -> None:
        self._runs = runs
        self._guides = guides or []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def query_list(self, kind: str):
        if kind == "TestRun":
            return self._runs
        if kind == "TestGuide":
            return self._guides
        return []


# Default product-lane guide so the legacy verifies/outcome assertions still
# hold once the gate requires a product (smoke|manual) guide.
_SMOKE_GUIDE = _FakeRun("tg-smoke", {"kind_of_test": "smoke"})


def _runs_ctx(runs, guides=None):
    """A click context carrying the fake session — direct helper calls run
    inside `with _runs_ctx(...):` so open_session resolves the injected fake
    (f-cli-session-injection: the context IS the port; no module patching)."""
    def _fake(scope):
        return _FakeSession(runs, guides if guides is not None else [_SMOKE_GUIDE])

    return click.Context(click.Command("t"), obj={SESSION_PROVIDER_KEY: _fake})


def test_passing_run_finds_the_passing_one() -> None:
    with _runs_ctx([
        _FakeRun("tr-1", {"outcome": "fail", "verifies": ["Story/s-x"], "guide_ref": "tg-smoke"}),
        _FakeRun("tr-2", {"outcome": "pass", "verifies": ["Story/s-x"], "guide_ref": "tg-smoke"}),
    ]):
        assert tk.passing_run_for_story("dna-development", "s-x") == "tr-2"


def test_passing_run_none_when_only_failures() -> None:
    with _runs_ctx([_FakeRun("tr-1", {"outcome": "fail", "verifies": ["Story/s-x"]})]):
        assert tk.passing_run_for_story("dna-development", "s-x") is None


def test_passing_run_ignores_runs_for_other_stories() -> None:
    with _runs_ctx([_FakeRun("tr-1", {"outcome": "pass", "verifies": ["Story/s-other"]})]):
        assert tk.passing_run_for_story("dna-development", "s-x") is None


def test_passing_run_accepts_bare_story_name_in_verifies() -> None:
    with _runs_ctx([_FakeRun("tr-1", {"outcome": "pass", "verifies": ["s-x"], "guide_ref": "tg-smoke"})]):
        assert tk.passing_run_for_story("dna-development", "s-x") == "tr-1"


# ── s-testkit-done-requires-product-smoke: gate counts the PRODUCT lane ───────
def test_passing_run_ignores_automated_lane() -> None:
    # A pass run whose guide is integration (automated lane, proven by CI) does
    # NOT satisfy the done-gate — only smoke|manual count.
    with _runs_ctx(
        [_FakeRun("tr-int", {"outcome": "pass", "verifies": ["Story/s-x"], "guide_ref": "tg-int"})],
        guides=[_FakeRun("tg-int", {"kind_of_test": "integration"})],
    ):
        assert tk.passing_run_for_story("dna-development", "s-x") is None


def test_passing_run_counts_smoke_lane() -> None:
    with _runs_ctx(
        [_FakeRun("tr-sm", {"outcome": "pass", "verifies": ["Story/s-x"], "guide_ref": "tg-sm"})],
        guides=[_FakeRun("tg-sm", {"kind_of_test": "smoke"})],
    ):
        assert tk.passing_run_for_story("dna-development", "s-x") == "tr-sm"


def test_passing_run_counts_manual_lane() -> None:
    with _runs_ctx(
        [_FakeRun("tr-man", {"outcome": "pass", "verifies": ["s-x"], "guide_ref": "tg-man"})],
        guides=[_FakeRun("tg-man", {"kind_of_test": "manual"})],
    ):
        assert tk.passing_run_for_story("dna-development", "s-x") == "tr-man"


# ── i-100: test-guide create also stamps the verified Story's produces[] ──────
class _FakeDoc:
    def __init__(self, name, spec):
        self.name = name
        self.spec = spec


class _CapturingKernel:
    def __init__(self):
        self.written = []

    def write_document(self, scope, kind, name, raw):
        self.written.append((scope, kind, name, raw))
        return None


class _StampSession:
    """Fake session: returns a stub Story on get_doc, captures writes."""
    def __init__(self, story_spec):
        self._story_spec = story_spec
        self.kernel = _CapturingKernel()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_doc(self, kind, name):
        return _FakeDoc(name, dict(self._story_spec))

    def run(self, coro):
        return coro  # write_document is sync in the fake → returns None


def test_stamp_verified_stories_appends_testguide_to_produces() -> None:
    sess = _StampSession({"status": "todo"})

    # direct helper call (no CliRunner): construct the click context by hand
    # and inject the session through it — same front door the CLI uses.
    with click.Context(click.Command("t"), obj={SESSION_PROVIDER_KEY: lambda scope: sess}):
        tk._stamp_verified_stories(
            "dna-development", ["Story/s-x"],
            produced_kind="TestGuide", produced_name="tg-x", role="test-guide",
            timeline_summary="TestGuide tg-x (manual)",
        )

    assert sess.kernel.written, "expected a Story write"
    _, kind, name, raw = sess.kernel.written[-1]
    assert (kind, name) == ("Story", "s-x")
    produces = raw["spec"]["produces"]
    entry = next(p for p in produces if p["kind"] == "TestGuide" and p["name"] == "tg-x")
    assert entry["role"] == "test-guide"
    types = [e.get("type") for e in raw["spec"].get("timeline", [])]
    assert "artifact_produced" in types


def test_stamp_skips_non_story_refs() -> None:
    sess = _StampSession({"status": "todo"})
    with click.Context(click.Command("t"), obj={SESSION_PROVIDER_KEY: lambda scope: sess}):
        tk._stamp_verified_stories(
            "dna-development", ["Issue/i-y"],  # not a Story → skipped
            produced_kind="TestGuide", produced_name="tg-x", role="test-guide",
            timeline_summary="x",
        )
    assert not sess.kernel.written


# ── s-testkit-product-guide-authoring: --product UI-first stub ────────────────
def test_step_stub_product_is_ui_first() -> None:
    s = tk._step_stub("o card aparece no FOCUS", product=True)
    assert "No Studio" in s["action"]
    assert ":scope" in s["where"]                # route placeholder for the tester
    assert "quebrado" in s["expected"].lower()   # the don't-force-fail guidance


def test_step_stub_default_is_generic() -> None:
    s = tk._step_stub("X", product=False)
    assert s == {"action": "Validar: X", "expected": "<descreva o resultado esperado>"}
    assert "where" not in s
