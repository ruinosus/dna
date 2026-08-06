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


# ── the CLI says WHEN to declare one, to the HUMAN reading --help ───────────
#
# The third reader of the same instruction, and the only one who cannot be
# handed 1.5 KB inline: `--claim` sits beside a dozen other options. So the flag
# carries the one-line discriminant and the command's epilog carries the whole
# rule — and BOTH must survive, because someone who reads only the flag would
# otherwise get the trigger without its two counter-cases, which is the
# over-triggering half on its own.


def _remember_help() -> str:
    result = CliRunner().invoke(main, ["memory", "remember", "--help"])
    assert result.exit_code == 0, result.output
    return result.output


def test_the_flag_help_carries_the_discriminant():
    from dna.memory.contradiction import WHEN_TO_CLAIM_SHORT

    out = " ".join(_remember_help().split())  # click rewraps; compare unwrapped
    assert "would make this one false" in out.lower(), "the flag lost the rule"
    assert " ".join(WHEN_TO_CLAIM_SHORT.split()) in out, (
        "`--claim` explains the SPELLING and not the trigger — a human told "
        "only how to type a claim types one for everything"
    )


def test_the_command_help_carries_the_whole_rule_including_the_no_cases():
    """The epilog, pre-wrapped by us so click prints it as a list.

    Asserted on the RENDERED help and not on the constant: click reflows
    anything it is handed, and a four-case list reflowed into one paragraph
    loses the two NO cases exactly where they carry their weight.
    """
    from dna.memory.contradiction import WHEN_TO_CLAIM

    rendered = _remember_help()
    flat = " ".join(rendered.split())
    for block in WHEN_TO_CLAIM.split("\n\n"):
        assert " ".join(block.split()) in flat, block

    bullets = [ln for ln in rendered.splitlines() if ln.strip().startswith("- ")]
    assert len(bullets) == 4, (
        "the four cases must render as four bullets; click reflowed them into "
        f"prose ({len(bullets)} found)"
    )


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
