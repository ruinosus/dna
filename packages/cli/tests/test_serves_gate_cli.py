"""The SERVES gate (i-117), tested THROUGH THE DOOR — the CLI commands, with
and without a citation.

WHAT IS BEING DEFENDED. A Spec's execution is DERIVED from citation
(``references`` ∪ ``cited_by``, crossed with delivery on the board), and nothing
obliged the citation. A delivery that shipped a design without citing it left
the design counted as pending work, and that number picked work twice.

WHY THESE TESTS AND NOT UNIT TESTS. The house has already been bitten by a guard
that was correct in unit and unreachable at the door (``guard-existe-porta-nao-
chama``), so every assertion here invokes ``sdlc`` through ``CliRunner`` and then
reads the STORE — the bytes that were actually written — never the return value
of the helper.

THE MUTANTS each test kills are named on the test. The two that matter most:

* **the gate that passes but does not write.** ``--serves Spec/x`` returning 0 is
  not the behaviour; the behaviour is ``Spec/x.cited_by`` containing the closer.
  Every happy-path test asserts BOTH SIDES of the citation, because a one-sided
  write is invisible to the portal's derivation and would leave i-117 open while
  looking fixed.
* **the gate that always refuses.** The whole calibration is that a close with
  nothing to answer is never asked. A guard that fires on every close is not a
  stricter version of this one, it is a different and worse thing — so the
  silence cases are tested as hard as the refusals.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from click.testing import CliRunner

from dna_cli.sdlc_cmd import sdlc
from dna_cli._ctx import SESSION_PROVIDER_KEY


SCOPE = "dna-development"


# ── fake session (same shape as test_focus_gates_cli.py) ─────────────────────

class _FakeDocView:
    def __init__(self, raw: dict):
        self._raw = raw
        self.name = raw.get("metadata", {}).get("name")
        self.kind = raw.get("kind")
        self.spec = raw.get("spec") or {}


class _FakeKernel:
    def __init__(self, store: dict):
        self._store = store
        self._kinds: dict = {}

    def with_tenant(self, tenant):
        return self

    async def write_instance(self, scope, kind, name, raw, **_):
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

    def query_list(self, kind):
        return [
            _FakeDocView(raw)
            for (sc, k, _n), raw in self._store.items()
            if sc == self.scope and k == kind
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
    return {}


@pytest.fixture
def session_obj(store):
    @contextmanager
    def _fake(scope=None, *, tenant=None, timeout=30.0):
        yield _FakeSession(store, scope or SCOPE)

    return {SESSION_PROVIDER_KEY: _fake}


@pytest.fixture
def runner(session_obj):
    r = CliRunner()
    _orig = r.invoke

    def _invoke(*args, **kwargs):
        kwargs.setdefault("obj", session_obj)
        return _orig(*args, **kwargs)

    r.invoke = _invoke  # type: ignore[method-assign]
    return r


def _put(store, kind, name, spec):
    store[(SCOPE, kind, name)] = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": kind,
        "metadata": {"name": name}, "spec": spec,
    }


def _seed_spec(store, name, *, status="accepted", **extra):
    _put(store, "Spec", name, {"title": name, "status": status, **extra})


def _seed_story(store, name, *, status="review", **extra):
    _put(store, "Story", name, {
        "status": status,
        "timeline": [{"type": "status_change", "from": None, "to": status,
                      "at": "2026-08-06T00:00:00+00:00"}],
        **extra,
    })


def _seed_issue(store, name, *, status="in-progress", **extra):
    _put(store, "Issue", name, {
        "status": status, "type": "bug", "severity": "high",
        "timeline": [], **extra,
    })


def _spec_of(store, kind, name):
    return store[(SCOPE, kind, name)]["spec"]


DONE = ["--no-commit", "--allow-no-tests", "--no-narrate",
        "--allow-no-produces", "--scope", SCOPE]


# ── 1. the refusal: prose names an open Spec, nothing declared ───────────────

def test_story_done_refuses_when_its_own_prose_names_an_uncited_spec(runner, store):
    """THE DEFECT, reproduced. `s-grafo-1-arestas-e-travessia` named its Spec in
    a timeline comment, shipped, and the Spec stayed in the pending bucket.

    Mutant killed: a gate that only warns. The exit code must be 1 AND the Story
    must still be open — a refusal that closed the item anyway is not a refusal.
    """
    _seed_spec(store, "spec-grafo-1-arestas-e-travessia")
    _seed_story(store, "s-grafo-1", timeline=[
        {"type": "comment", "at": "2026-08-06T00:00:00+00:00",
         "summary": "o degrau 1 de spec-grafo-1-arestas-e-travessia está entregue"},
    ])
    r = runner.invoke(sdlc, ["story", "done", "s-grafo-1", *DONE])
    assert r.exit_code == 1, r.output
    assert "spec-grafo-1-arestas-e-travessia" in r.output
    assert "--serves none" in r.output
    assert _spec_of(store, "Story", "s-grafo-1")["status"] == "review"


def test_the_refusal_names_the_candidate_as_a_pasteable_flag(runner, store):
    """Derivar o candidato é o que troca atrito por uma colagem. A recusa que só
    diz 'faltou citação' devolve o problema; esta devolve a linha pronta."""
    _seed_spec(store, "spec-interaction-voice")
    _seed_story(store, "s-voz", description="entrega a spec-interaction-voice")
    r = runner.invoke(sdlc, ["story", "done", "s-voz", *DONE])
    assert "--serves Spec/spec-interaction-voice" in r.output


# ── 2. the silences — the calibration, and it is half the design ─────────────

def test_story_done_is_SILENT_when_nothing_in_the_prose_names_a_spec(runner, store):
    """Mutant killed: the gate that fires on every close. A required field is
    the fix that destroys itself — everyone fills it with anything. This close
    has nothing to answer and must not be asked."""
    _seed_spec(store, "spec-alguma-coisa")
    _seed_story(store, "s-comum", description="ajusta o CSS do header")
    r = runner.invoke(sdlc, ["story", "done", "s-comum", *DONE])
    assert r.exit_code == 0, r.output
    assert "serves" not in r.output
    assert _spec_of(store, "Story", "s-comum")["status"] == "done"


def test_an_already_cited_story_is_never_asked(runner, store):
    """A trace that exists is the answer. Asking again is pure friction."""
    _seed_spec(store, "spec-x")
    _seed_story(store, "s-ja-cita", description="entrega spec-x",
                references=["Spec/spec-x"])
    r = runner.invoke(sdlc, ["story", "done", "s-ja-cita", *DONE])
    assert r.exit_code == 0, r.output


def test_spec_refs_counts_as_a_trace_too(runner, store):
    """The gate wants A TRACE, not one particular field — `spec_refs` is the
    Story Kind's own declared M:N link to Spec and satisfies it."""
    _seed_spec(store, "spec-x")
    _seed_story(store, "s-spec-refs", description="entrega spec-x",
                spec_refs=["spec-x"])
    r = runner.invoke(sdlc, ["story", "done", "s-spec-refs", *DONE])
    assert r.exit_code == 0, r.output


def test_produces_hub_counts_as_a_trace_too(runner, store):
    _seed_spec(store, "spec-x")
    _seed_story(store, "s-produces", description="entrega spec-x",
                produces=[{"kind": "Spec", "name": "spec-x"}])
    r = runner.invoke(sdlc, ["story", "done", "s-produces", *DONE])
    assert r.exit_code == 0, r.output


@pytest.mark.parametrize("status", ["executed", "shelved", "deprecated", "superseded"])
def test_a_terminal_spec_is_not_a_candidate(runner, store, status):
    """The gate defends the DERIVATION, and the derivation can only get the OPEN
    bucket wrong. Eligibility is `spec_board_bucket(...) == "open"`, derived from
    the Kind's own arc — never a second hand-kept list of terminal statuses.

    Mutant killed: candidacy enumerated here instead of derived, which goes stale
    in silence the day the Spec arc gains a state."""
    _seed_spec(store, "spec-morta", status=status)
    _seed_story(store, "s-t", description="menciona spec-morta")
    r = runner.invoke(sdlc, ["story", "done", "s-t", *DONE])
    assert r.exit_code == 0, r.output


@pytest.mark.parametrize(("short", "longer"), [
    # The one `\b` gets WRONG, and the reason the boundary is `[\w-]` and not
    # `\b`: after `spec-grafo`, a `-` IS a word boundary to Python, so `\b`
    # happily finds `spec-grafo` inside `spec-grafo-1-arestas-e-travessia` and
    # would put a refusal (and, if confirmed, a citation) on the wrong design.
    ("spec-grafo", "spec-grafo-1-arestas-e-travessia"),
    ("spec-app", "spec-app-como-composicao"),
    # `\b` happens to get this one right; kept so the set documents that the
    # boundary must hold for BOTH kinds of following character.
    ("spec-grafo-1", "spec-grafo-10-outra-coisa"),
])
def test_a_longer_slug_that_merely_CONTAINS_the_name_is_not_a_match(
    runner, store, short, longer,
):
    """Mutant killed: `\\b` (or plain substring) as the boundary. A prefix of
    another Spec's slug is a citation to a DIFFERENT design — and these slugs are
    hyphenated, which is exactly where `\\b` stops being a whole-identifier test.
    """
    _seed_spec(store, short)
    _seed_story(store, "s-b", description=f"isto entrega {longer}")
    r = runner.invoke(sdlc, ["story", "done", "s-b", *DONE])
    assert r.exit_code == 0, r.output
    assert _spec_of(store, "Story", "s-b")["status"] == "done"


# ── 3. the happy path — and it must WRITE, on both sides ────────────────────

def test_serves_writes_the_citation_on_BOTH_documents(runner, store):
    """Mutant killed: the gate that passes and writes nothing (or writes one
    side). The portal derives execution from the SPEC's `cited_by`; a forward-only
    write would satisfy every exit code and fix nothing at all."""
    _seed_spec(store, "spec-quota-como-politica")
    _seed_story(store, "s-quota", description="entrega spec-quota-como-politica")
    r = runner.invoke(sdlc, [
        "story", "done", "s-quota", "--serves", "Spec/spec-quota-como-politica", *DONE,
    ])
    assert r.exit_code == 0, r.output
    assert _spec_of(store, "Spec", "spec-quota-como-politica")["cited_by"] == [
        "Story/s-quota",
    ]
    assert _spec_of(store, "Story", "s-quota")["references"] == [
        "Spec/spec-quota-como-politica",
    ]
    # …and the close still happened.
    assert _spec_of(store, "Story", "s-quota")["status"] == "done"


def test_the_forward_ref_is_QUALIFIED_not_bare(runner, store):
    """A bare name in `references` means a Reference (the `cite` default). A Spec
    citation stored bare would be read as a citation to something else."""
    _seed_spec(store, "spec-x")
    _seed_story(store, "s-q")
    runner.invoke(sdlc, ["story", "done", "s-q", "--serves", "spec-x", *DONE])
    assert _spec_of(store, "Story", "s-q")["references"] == ["Spec/spec-x"]


def test_serves_survives_the_status_write_that_follows_it(runner, store):
    """Mutant killed: the citation written and then CLOBBERED. `story done` flips
    the status through its own load-modify-write; a `references` appended to a
    stale copy of the spec vanishes on the next read, exit code 0 and all."""
    _seed_spec(store, "spec-x")
    _seed_story(store, "s-clobber")
    runner.invoke(sdlc, ["story", "done", "s-clobber", "--serves", "Spec/spec-x", *DONE])
    final = _spec_of(store, "Story", "s-clobber")
    assert final["status"] == "done"
    assert final["references"] == ["Spec/spec-x"]


def test_multiple_serves_cite_every_named_spec(runner, store):
    _seed_spec(store, "spec-a")
    _seed_spec(store, "spec-b")
    _seed_story(store, "s-multi")
    r = runner.invoke(sdlc, [
        "story", "done", "s-multi",
        "--serves", "Spec/spec-a", "--serves", "Spec/spec-b", *DONE,
    ])
    assert r.exit_code == 0, r.output
    assert _spec_of(store, "Spec", "spec-a")["cited_by"] == ["Story/s-multi"]
    assert _spec_of(store, "Spec", "spec-b")["cited_by"] == ["Story/s-multi"]


def test_citing_is_idempotent(runner, store):
    """Closing twice must not double the citation."""
    _seed_spec(store, "spec-x", cited_by=["Story/s-idem"])
    _seed_story(store, "s-idem", references=["Spec/spec-x"])
    runner.invoke(sdlc, ["story", "done", "s-idem", "--serves", "Spec/spec-x", *DONE])
    assert _spec_of(store, "Spec", "spec-x")["cited_by"] == ["Story/s-idem"]
    assert _spec_of(store, "Story", "s-idem")["references"] == ["Spec/spec-x"]


# ── 4. `--serves none` — absence as an ASSERTION, the third state ───────────

def test_serves_none_passes_the_gate_and_is_RECORDED(runner, store):
    """Mutant killed: `none` swallowed silently. If it only unlocks the gate and
    leaves no trace, "nobody said" and "somebody said no" still read alike — which
    is the exact confusion i-117 is about, moved one level down."""
    _seed_spec(store, "spec-grafo-1-arestas-e-travessia")
    _seed_story(store, "s-nao-serve",
                description="menciona spec-grafo-1-arestas-e-travessia de passagem")
    r = runner.invoke(sdlc, ["story", "done", "s-nao-serve", "--serves", "none", *DONE])
    assert r.exit_code == 0, r.output
    final = _spec_of(store, "Story", "s-nao-serve")
    assert final["serves_no_spec"] is True
    assert final["serves_declared_at"]
    assert final["status"] == "done"
    # and NOTHING was cited
    assert not _spec_of(store, "Spec", "spec-grafo-1-arestas-e-travessia").get("cited_by")


def test_serves_none_mixed_with_a_spec_is_refused(runner, store):
    """The two together are not an assertion, they are a contradiction."""
    _seed_spec(store, "spec-x")
    _seed_story(store, "s-mix")
    r = runner.invoke(sdlc, [
        "story", "done", "s-mix", "--serves", "none", "--serves", "Spec/spec-x", *DONE,
    ])
    assert r.exit_code == 2, r.output
    assert _spec_of(store, "Story", "s-mix")["status"] == "review"


# ── 5. the anti-friction property: the field CANNOT take noise ──────────────

def test_serves_refuses_a_spec_that_does_not_exist(runner, store):
    """THE reason this is not a free-text field. `spec executed --summary` can be
    satisfied with "done"; `--serves` cannot be satisfied by any cheap string —
    it has to name a Spec that exists, or say `none`."""
    _seed_story(store, "s-lixo")
    r = runner.invoke(sdlc, ["story", "done", "s-lixo", "--serves", "qualquer-coisa", *DONE])
    assert r.exit_code == 2, r.output
    assert _spec_of(store, "Story", "s-lixo")["status"] == "review"


def test_serves_refuses_a_non_spec_kind_instead_of_coercing_it(runner, store):
    """`--serves Feature/f-x` is a person saying the wrong sentence. Rewriting it
    to `Spec/f-x` would invent a citation nobody made."""
    _seed_story(store, "s-kind")
    _put(store, "Feature", "f-x", {"status": "in-development"})
    r = runner.invoke(sdlc, ["story", "done", "s-kind", "--serves", "Feature/f-x", *DONE])
    assert r.exit_code == 2, r.output
    assert "Spec" in r.output


# ── 6. the siblings that also close work ────────────────────────────────────

def test_issue_resolve_refuses_and_then_accepts_serves(runner, store):
    """i-084 / i-087 — the two Issues whose resolutions PROVED two Specs and
    cited neither. Both named their Spec in the timeline."""
    _seed_spec(store, "spec-conversa-como-dado-do-dna")
    _seed_issue(store, "i-084-conversa", timeline=[
        {"type": "comment", "at": "2026-08-06T00:00:00+00:00",
         "summary": "fecha o desenho de spec-conversa-como-dado-do-dna"},
    ])
    r = runner.invoke(sdlc, ["issue", "resolve", "i-084-conversa", "--scope", SCOPE])
    assert r.exit_code == 1, r.output
    assert _spec_of(store, "Issue", "i-084-conversa")["status"] == "in-progress"

    r = runner.invoke(sdlc, [
        "issue", "resolve", "i-084-conversa",
        "--serves", "Spec/spec-conversa-como-dado-do-dna", "--scope", SCOPE,
    ])
    assert r.exit_code == 0, r.output
    assert _spec_of(store, "Issue", "i-084-conversa")["status"] == "resolved"
    assert _spec_of(store, "Spec", "spec-conversa-como-dado-do-dna")["cited_by"] == [
        "Issue/i-084-conversa",
    ]
    assert _spec_of(store, "Issue", "i-084-conversa")["references"] == [
        "Spec/spec-conversa-como-dado-do-dna",
    ]


def test_feature_ship_refuses_and_then_accepts_serves(runner, store):
    _seed_spec(store, "spec-copilot-f6-capacidades")
    _put(store, "Feature", "f-skills-runtime", {
        "status": "in-development",
        "description": "entrega spec-copilot-f6-capacidades",
    })
    r = runner.invoke(sdlc, [
        "feature", "ship", "f-skills-runtime", "--allow-no-produces", "--scope", SCOPE,
    ])
    assert r.exit_code == 1, r.output
    assert _spec_of(store, "Feature", "f-skills-runtime")["status"] == "in-development"

    r = runner.invoke(sdlc, [
        "feature", "ship", "f-skills-runtime", "--allow-no-produces",
        "--serves", "Spec/spec-copilot-f6-capacidades", "--scope", SCOPE,
    ])
    assert r.exit_code == 0, r.output
    assert _spec_of(store, "Feature", "f-skills-runtime")["status"] == "done"
    assert _spec_of(store, "Spec", "spec-copilot-f6-capacidades")["cited_by"] == [
        "Feature/f-skills-runtime",
    ]


def test_feature_ship_children_check_still_refuses_FIRST(runner, store):
    """Ordering: a Feature with open children has a bigger problem than an
    unstated citation, and must hear about that one."""
    _seed_spec(store, "spec-x")
    _put(store, "Feature", "f-aberta", {
        "status": "in-development", "description": "entrega spec-x",
    })
    _seed_story(store, "s-filha", status="todo", feature="f-aberta")
    r = runner.invoke(sdlc, ["feature", "ship", "f-aberta", "--scope", SCOPE])
    assert r.exit_code != 0
    assert "non-done children" in r.output


# ── 7. the option surface (mirrors test_focus_gates_cli.py's last test) ─────

def test_the_three_closers_expose_serves():
    from dna_cli import sdlc_cmd

    for cmd in (sdlc_cmd.cmd_story_done, sdlc_cmd.cmd_issue_resolve,
                sdlc_cmd.cmd_feature_ship):
        assert "serves" in {o.name for o in cmd.params}, cmd.name
