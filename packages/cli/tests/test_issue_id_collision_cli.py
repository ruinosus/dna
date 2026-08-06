"""``dna sdlc issue file`` and the id that stopped identifying.

Measured on the dna-cloud board 05/08/2026: 13 Issues sharing 4 numbers
(``i-094`` ×4, ``i-095`` ×2, ``i-096`` ×2, ``i-097`` ×5) — every one filed
through this command, which computed ``max(NNN)+1`` from the filesystem and
then called ``write_document`` bare. Two agents in two git WORKTREES read the
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

from dna_cli.sdlc_cmd import sdlc

_SCOPE = "dna-development"


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
    # It names WHICH documents collide — "there is a duplicate somewhere" is
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

    It used to build ``i-NNN-<slug>`` and call ``write_document`` — an upsert.
    An enumeration that under-reported (a stale read, a concurrent writer, a
    replica behind) produced a number that was already taken, and the new Issue
    landed ON the live one, replacing its status and timeline while the command
    printed success.

    The double below is exactly that source: ``i-001-ja-existe`` is invisible to
    the enumeration but real on disk. The old code would have written straight
    over it. Two assertions, because either alone can pass for the wrong reason
    — that ``if_absent`` was ASKED FOR, and that the hidden document survived.
    """
    import contextlib

    from dna.kernel.errors import DocumentNameTaken
    from dna_cli._ctx import SESSION_PROVIDER_KEY

    _seed(store, "i-001-ja-existe", description="a que já estava lá")
    asked_if_absent: list[bool] = []

    class _BlindKernel:
        _kinds: dict = {}

        def with_tenant(self, tenant):
            return self

        async def get_document(self, scope, kind, name):
            return store.get((scope, kind, name))

        async def query(self, scope, kind, *, projection=None, **_):
            """Reports nothing — the source that has not caught up."""
            return
            yield  # pragma: no cover — makes this an async generator

        async def write_document(self, scope, kind, name, raw, *,
                                 if_absent=False, **_):
            asked_if_absent.append(if_absent)
            if if_absent and (scope, kind, name) in store:
                raise DocumentNameTaken(f"{kind} {name!r} already exists")
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
