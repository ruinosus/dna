"""``dna sdlc issue file`` and the id that stopped identifying.

Measured on the dna-cloud board 05/08/2026: 13 Issues sharing 4 numbers
(``i-094`` ×4, ``i-095`` ×2, ``i-096`` ×2, ``i-097`` ×5) — every one filed
through this command, which computed ``max(NNN)+1`` from the filesystem and
then called ``write_instance`` bare. Two agents in two git WORKTREES read the
same board, pick the same number, and write files with DIFFERENT names, so
``git merge`` joins both without a conflict.

Two things are testable here and both are:

* the command DELEGATES to ``dna.application.sdlc.create_issue`` now, so it
  carries the atomic claim it never had (a name filed twice is refused, not
  overwritten);
* it SAYS SO when the board it just read already has ids claimed twice. The
  allocator cannot prevent the collision — nothing at allocation time can, when
  the writers are separate filesystems — so telling the person doing board work
  is the move that is actually available. CI checks the merged tree; this
  checks the workstation.
"""
from __future__ import annotations

import subprocess

import pytest

from dna_cli.sdlc_cmd import sdlc

_SCOPE = "dna-development"


# ── a real clone with a real second worktree ───────────────────────────────
#
# It has to be real. The whole defect is a property of `git worktree add` — two
# working directories, two `.dna/`, ONE `.git` — and a double that returns a
# hardcoded list of sibling paths would pass whether or not the command can
# actually find them. `git` is already a hard dependency of `dna sdlc` (the
# story/PR verbs shell out to it), so this costs nothing new.


def _git(*args: str, cwd) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


@pytest.fixture
def two_worktrees(tmp_path):
    """``(main, sibling)`` — two worktrees of one clone, each with its own
    ``.dna/<scope>/issues/``, exactly as two agents get them."""
    main = tmp_path / "clone"
    main.mkdir()
    _git("init", "-q", "-b", "main", cwd=main)
    _git("config", "user.email", "t@example.com", cwd=main)
    _git("config", "user.name", "t", cwd=main)
    (main / ".dna" / _SCOPE / "issues").mkdir(parents=True)
    (main / "README.md").write_text("seed\n")
    _git("add", "-A", cwd=main)
    _git("commit", "-qm", "seed", cwd=main)

    sibling = tmp_path / "sibling"
    _git("worktree", "add", "-q", "-b", "outra-branch", str(sibling), cwd=main)
    (sibling / ".dna" / _SCOPE / "issues").mkdir(parents=True)
    return main, sibling


def _plant(worktree, name: str, kind_dir: str = "issues") -> None:
    """Write a board doc into a worktree's board source, the way the CLI does:
    one YAML per instance, file stem == instance name."""
    d = worktree / ".dna" / _SCOPE / kind_dir
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/sdlc/v1\n"
        f"kind: Issue\nmetadata:\n  name: {name}\nspec: {{}}\n"
    )


def _seed(store, name: str, *, description: str = "seeded") -> None:
    store[(_SCOPE, "Issue", name)] = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
        "kind": "Issue",
        "metadata": {"name": name},
        "spec": {"description": description, "type": "bug",
                 "severity": "medium", "status": "open"},
    }


def test_issue_file_warns_when_the_board_already_has_a_number_claimed_twice(
    sdlc_runner, store,
):
    _seed(store, "i-095-egress-por-plano-copiada-em-duas-apps")
    _seed(store, "i-095-terraform-fases-2-4-decisao")

    result = sdlc_runner.invoke(
        sdlc, ["issue", "file", "--slug", "nova", "--desc", "uma nova issue"],
    )

    assert result.exit_code == 0, result.output
    assert "i-095" in result.output
    # It names WHICH instances collide — "there is a duplicate somewhere" is
    # not actionable, and the whole failure mode is that the number no longer
    # tells you which item is meant.
    assert "i-095-egress-por-plano-copiada-em-duas-apps" in result.output
    assert "i-095-terraform-fases-2-4-decisao" in result.output
    # …and it still files, at the next number. The board being untidy is not a
    # reason to refuse work.
    assert ("dna-development", "Issue", "i-096-nova") in store


def test_issue_file_is_quiet_on_a_healthy_board(sdlc_runner, store):
    """A warning that fires on a clean board is a warning nobody reads."""
    _seed(store, "i-001-primeira")

    result = sdlc_runner.invoke(
        sdlc, ["issue", "file", "--slug", "segunda", "--desc", "d"],
    )

    assert result.exit_code == 0, result.output
    assert "⚠️" not in result.output
    assert ("dna-development", "Issue", "i-002-segunda") in store


def test_issue_file_claims_the_name_atomically_and_never_overwrites(
    runner, store, monkeypatch,
):
    """The protection the CLI gained by delegating to the shared core.

    It used to build ``i-NNN-<slug>`` and call ``write_instance`` — an upsert.
    An enumeration that under-reported (a stale read, a concurrent writer, a
    replica behind) produced a number that was already taken, and the new Issue
    landed ON the live one, replacing its status and timeline while the command
    printed success.

    The double below is exactly that source: ``i-001-ja-existe`` is invisible to
    the enumeration but real on disk. The old code would have written straight
    over it. Two assertions, because either alone can pass for the wrong reason
    — that ``if_absent`` was ASKED FOR, and that the hidden instance survived.
    """
    import contextlib

    from dna.kernel.errors import InstanceNameTaken
    from dna_cli._ctx import SESSION_PROVIDER_KEY

    _seed(store, "i-001-ja-existe", description="a que já estava lá")
    asked_if_absent: list[bool] = []

    class _BlindKernel:
        _kinds: dict = {}

        def with_tenant(self, tenant):
            return self

        async def get_instance(self, scope, kind, name):
            return store.get((scope, kind, name))

        async def query(self, scope, kind, *, projection=None, **_):
            """Reports nothing — the source that has not caught up."""
            return
            yield  # pragma: no cover — makes this an async generator

        async def write_instance(self, scope, kind, name, raw, *,
                                 if_absent=False, **_):
            asked_if_absent.append(if_absent)
            if if_absent and (scope, kind, name) in store:
                raise InstanceNameTaken(f"{kind} {name!r} already exists")
            store[(scope, kind, name)] = raw
            return "v1"

    class _BlindSession:
        scope = _SCOPE
        kernel = _BlindKernel()

        def get_doc(self, kind, name, *, tenant=None):
            return None

        def query_list(self, kind, *, tenant=None):
            return []

        def run(self, coro):
            import asyncio

            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

    @contextlib.contextmanager
    def _provider(scope=None, **_):
        yield _BlindSession()

    result = runner.invoke(
        sdlc, ["issue", "file", "--slug", "ja-existe", "--desc", "a nova"],
        obj={SESSION_PROVIDER_KEY: _provider},
    )

    assert result.exit_code == 0, result.output
    assert asked_if_absent and all(asked_if_absent), (
        "the CLI wrote without asking for an atomic create — it is not going "
        "through create_issue"
    )
    kept = store[(_SCOPE, "Issue", "i-001-ja-existe")]["spec"]
    assert kept["description"] == "a que já estava lá", "the live Issue was overwritten"
    assert store[(_SCOPE, "Issue", "i-002-ja-existe")]["spec"]["description"] == "a nova"


# ── the recurrence, and the read that stops it ─────────────────────────────


def test_issue_file_skips_a_number_a_sibling_worktree_already_claimed(
    sdlc_runner, store, monkeypatch, two_worktrees,
):
    """THE regression. Reproduced exactly as it happened on 06/08/2026.

    This tree holds ``i-100``. A sibling worktree — same clone, same board, a
    branch this tree has never merged — already holds ``i-101``. ``max+1`` over
    THIS tree says 101, and it is arithmetically right; that is how two agents
    filed two different ``i-101`` hours apart, and why the atomic claim, the
    probe and the duplicate warning shipped the day before could not help: the
    two names differ, so every write was legitimate and ``git merge`` joined
    both without a conflict.

    Nothing here is a lock. The sibling is simply READ — `git worktree list`
    names it, one shared ``.git`` guarantees it exists on this machine — so the
    number the allocator picks is above both trees, not just this one.
    """
    main, sibling = two_worktrees
    monkeypatch.setenv("DNA_SDLC_WORKTREE_SCAN", "1")
    monkeypatch.setenv("DNA_SOURCE_URL", f"file://{main / '.dna'}")
    monkeypatch.chdir(main)
    _seed(store, "i-100-nesta-arvore")
    _plant(sibling, "i-101-na-outra-worktree")

    result = sdlc_runner.invoke(
        sdlc, ["issue", "file", "--slug", "nova", "--desc", "uma nova issue"],
    )

    assert result.exit_code == 0, result.output
    assert (_SCOPE, "Issue", "i-101-nova") not in store, (
        "filed i-101 while another worktree of this clone already holds an "
        "i-101 — this is the collision, reproduced"
    )
    assert (_SCOPE, "Issue", "i-102-nova") in store
    # A gap with no explanation is what gets "fixed" by turning the scan off.
    assert "i-101-na-outra-worktree" in result.output
    assert str(sibling) in result.output


def test_the_scan_is_what_does_it__off_the_collision_returns(
    sdlc_runner, store, monkeypatch, two_worktrees,
):
    """The same setup with ``DNA_SDLC_WORKTREE_SCAN=0`` files ``i-101``.

    Two jobs. It instances the escape hatch honestly — off means the old
    behavior, collision included, not "off but still safe". And it is the
    mutant-killer for the test above: if the assertion there could pass with the
    scan disabled, the scan would not be what earned it.
    """
    main, sibling = two_worktrees
    monkeypatch.setenv("DNA_SDLC_WORKTREE_SCAN", "0")
    monkeypatch.setenv("DNA_SOURCE_URL", f"file://{main / '.dna'}")
    monkeypatch.chdir(main)
    _seed(store, "i-100-nesta-arvore")
    _plant(sibling, "i-101-na-outra-worktree")

    result = sdlc_runner.invoke(
        sdlc, ["issue", "file", "--slug", "nova", "--desc", "uma nova issue"],
    )

    assert result.exit_code == 0, result.output
    assert (_SCOPE, "Issue", "i-101-nova") in store


def test_the_scan_never_breaks_filing_outside_a_git_repo(
    sdlc_runner, store, monkeypatch, tmp_path,
):
    """No git, no repo, no ``.dna`` in the tree — file the Issue anyway.

    The scan is an optimization of the READ. Every way it can fail (git absent,
    source outside the working tree, an unreadable sibling) has to degrade to
    the behavior that existed before it, because a board command that refuses
    to run because it could not enumerate someone else's worktree is worse than
    the bug it is fixing.
    """
    monkeypatch.setenv("DNA_SDLC_WORKTREE_SCAN", "1")
    loose = tmp_path / "not-a-repo"
    (loose / ".dna" / _SCOPE / "issues").mkdir(parents=True)
    monkeypatch.setenv("DNA_SOURCE_URL", f"file://{loose / '.dna'}")
    monkeypatch.chdir(loose)
    _seed(store, "i-007-so-esta")

    result = sdlc_runner.invoke(
        sdlc, ["issue", "file", "--slug", "nova", "--desc", "d"],
    )

    assert result.exit_code == 0, result.output
    assert (_SCOPE, "Issue", "i-008-nova") in store


def test_kaizen_reads_across_worktrees_too__the_sibling_that_had_nothing(
    sdlc_runner, store, monkeypatch, two_worktrees,
):
    """``kz-NNN`` is the same allocator, and it had none of the hardening.

    #321 gave ``issue file`` a probe, an atomic claim and a warning, and stopped
    there. ``kaizen flag`` kept computing ``max(kz-NNN)+1`` over one worktree
    and writing bare — same defect, one prefix over, with a docstring asserting
    the counter guaranteed uniqueness. Fixing one sibling and leaving the other
    is how a closed bug comes back wearing a different name.
    """
    main, sibling = two_worktrees
    monkeypatch.setenv("DNA_SDLC_WORKTREE_SCAN", "1")
    monkeypatch.setenv("DNA_SOURCE_URL", f"file://{main / '.dna'}")
    monkeypatch.chdir(main)
    store[(_SCOPE, "Story", "s-alvo")] = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Story",
        "metadata": {"name": "s-alvo"}, "spec": {"status": "in-progress"},
    }
    (sibling / ".dna" / _SCOPE / "kaizen").mkdir(parents=True)
    (sibling / ".dna" / _SCOPE / "kaizen" / "kz-001-na-outra.yaml").write_text(
        "kind: Kaizen\nmetadata:\n  name: kz-001-na-outra\nspec: {}\n")

    result = sdlc_runner.invoke(
        sdlc, ["kaizen", "flag", "Story/s-alvo", "--body", "uma observacao"],
    )

    assert result.exit_code == 0, result.output
    written = [n for (sc, kd, n) in store if kd == "Kaizen"]
    assert written and not any(n.startswith("kz-001") for n in written), (
        f"kaizen re-issued kz-001 across worktrees: {written}"
    )
    assert any(n.startswith("kz-002") for n in written), written


def test_kaizen_claims_its_name_atomically_and_never_overwrites(
    runner, store, monkeypatch,
):
    """A Kaizen observation must not silently replace another one.

    The double below is a source that under-reports: ``kz-001-uma-observacao``
    exists but the enumeration cannot see it. Writing bare — which is what this
    path did — lands the new observation ON the old one and prints success, with
    no trace that two were ever recorded.
    """
    import contextlib

    from dna.kernel.errors import InstanceNameTaken
    from dna_cli._ctx import SESSION_PROVIDER_KEY

    store[(_SCOPE, "Story", "s-alvo")] = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Story",
        "metadata": {"name": "s-alvo"}, "spec": {"status": "in-progress"},
    }
    store[(_SCOPE, "Kaizen", "kz-001-uma-observacao")] = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Kaizen",
        "metadata": {"name": "kz-001-uma-observacao"},
        "spec": {"body": "a que já estava lá"},
    }

    class _BlindKernel:
        _kinds: dict = {}

        def with_tenant(self, tenant):
            return self

        async def get_instance(self, scope, kind, name):
            return store.get((scope, kind, name))

        async def query(self, scope, kind, *, projection=None, **_):
            return
            yield  # pragma: no cover — makes this an async generator

        async def write_instance(self, scope, kind, name, raw, *,
                                 if_absent=False, **_):
            if if_absent and (scope, kind, name) in store:
                raise InstanceNameTaken(f"{kind} {name!r} already exists")
            store[(scope, kind, name)] = raw
            return "v1"

    class _BlindSession:
        scope = _SCOPE
        kernel = _BlindKernel()

        def get_doc(self, kind, name, *, tenant=None):
            raw = store.get((self.scope, kind, name))
            if raw is None:
                return None
            return type("_D", (), {"name": name, "kind": kind,
                                   "spec": raw.get("spec") or {}})()

        def query_list(self, kind, *, tenant=None):
            return []  # the source that has not caught up

        def run(self, coro):
            import asyncio

            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

    @contextlib.contextmanager
    def _provider(scope=None, **_):
        yield _BlindSession()

    result = runner.invoke(
        sdlc, ["kaizen", "flag", "Story/s-alvo", "--body", "uma observacao"],
        obj={SESSION_PROVIDER_KEY: _provider},
    )

    assert result.exit_code == 0, result.output
    kept = store[(_SCOPE, "Kaizen", "kz-001-uma-observacao")]["spec"]
    assert kept["body"] == "a que já estava lá", "the live Kaizen was overwritten"
    assert (_SCOPE, "Kaizen", "kz-002-uma-observacao") in store
