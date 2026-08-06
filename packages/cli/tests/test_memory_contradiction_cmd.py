"""`dna memory --claim` / `consolidate --dry-run` — the CLI door.

The third face of the same core (s-grafo-2-contradicao). The MCP and REST doors
are covered in ``test_mcp_contradiction.py``; what only the CLI can prove is the
terse ``[SUBJECT::]PREDICATE=[!]OBJECT`` spelling — the shorthand exists so a
claim can be typed as fast as a tag, and a shorthand nobody parses correctly is
worse than no shorthand.
"""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

pytest.importorskip("sqlite_vec", reason="search-sqlite extra not installed")

from dna_cli import main  # noqa: E402
from dna_cli.memory_cmd import _parse_claim  # noqa: E402

_REASON = "a concrete reason long enough for the affect validator to accept in full"
_LIVRO = "KindDefinition/livro"


@pytest.fixture
def scoped(tmp_path, monkeypatch):
    base = tmp_path / "src" / "demo"
    base.mkdir(parents=True)
    (base / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/core/v1\n"
        "kind: Package\nmetadata:\n  name: demo\nspec:\n  title: Demo\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DNA_BASE_DIR", str(tmp_path / "src"))
    monkeypatch.setenv("DNA_SEARCH_DIR", str(tmp_path / "search"))
    return tmp_path


# ── the shorthand ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw, expected", [
    ("approval=pending", {"predicate": "approval", "object": "pending"}),
    (f"{_LIVRO}::approval=pending",
     {"predicate": "approval", "subject": _LIVRO, "object": "pending"}),
    ("approval=!approved",
     {"predicate": "approval", "polarity": "denies", "object": "approved"}),
    # an empty object is an EXISTENCE claim, not the empty string
    ("approval=", {"predicate": "approval", "object": None}),
    # no `=` at all: a bare predicate, and no object key to compare on
    ("approval", {"predicate": "approval"}),
])
def test_the_claim_shorthand_parses(raw, expected):
    assert _parse_claim(raw) == expected


def test_a_claim_with_no_predicate_is_refused():
    import click

    with pytest.raises(click.ClickException) as exc:
        _parse_claim("=pending")
    assert "PREDICATE" in str(exc.value)


# ── the whole loop through the CLI ──────────────────────────────────────────


def _remember(runner, summary, *claims):
    args = [
        "memory", "remember", summary, "--scope", "demo",
        "--area", _LIVRO, "--reason", _REASON, "--json",
    ]
    for claim in claims:
        args += ["--claim", claim]
    return runner.invoke(main, args)


def test_the_livro_contradiction_shows_up_in_the_dry_run(scoped):
    runner = CliRunner()
    assert _remember(
        runner, "O Kind Livro ainda precisa de aprovação.", "approval=pending",
    ).exit_code == 0
    assert _remember(
        runner, "O Kind Livro foi aprovado no portal.", "approval=approved",
    ).exit_code == 0

    res = runner.invoke(main, [
        "memory", "consolidate", "--scope", "demo", "--dry-run", "--json",
    ])
    assert res.exit_code == 0, res.output
    (conflict,) = json.loads(res.output)["contradictions"]
    assert conflict["subject"] == _LIVRO
    assert conflict["predicate"] == "approval"
    assert conflict["proposal"]["strategy"] == "await_confirmation"


def test_the_human_readable_pass_shouts_the_contradiction(scoped):
    """The report is FOR a human — if the terminal rendering swallows it, the
    detector is unreachable in the one face that has no structured consumer."""
    runner = CliRunner()
    _remember(runner, "O Kind Livro ainda precisa de aprovação.", "approval=pending")
    _remember(runner, "O Kind Livro foi aprovado no portal.", "approval=approved")

    res = runner.invoke(main, ["memory", "consolidate", "--scope", "demo", "--dry-run"])
    assert res.exit_code == 0, res.output
    assert "CONTRADICTION" in res.output
    assert _LIVRO in res.output
    assert "awaiting your call" in res.output
    assert "nothing was changed" in res.output


def test_a_malformed_claim_is_refused_by_the_cli(scoped):
    runner = CliRunner()
    res = runner.invoke(main, [
        "memory", "remember", "memória com claim inválido", "--scope", "demo",
        "--area", _LIVRO, "--reason", _REASON,
        "--claim", "approval=!",  # denies nothing — an existence denial is fine
    ])
    assert res.exit_code == 0, res.output

    res = runner.invoke(main, [
        "memory", "remember", "outra memória inválida", "--scope", "demo",
        "--area", _LIVRO, "--reason", _REASON, "--claim", "=pending",
    ])
    assert res.exit_code != 0
    assert "PREDICATE" in res.output
