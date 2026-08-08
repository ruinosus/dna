"""The rendered tree of the reference template, frozen.

A template is the only thing in this repo that produces source code without a
contract, and the repo already knows what to do about that: the emit contract
is pinned by golden files, and a change to any emitter has to re-freeze them
deliberately (`docs/guides/writing-an-emitter.md`). A template deserves exactly
the same treatment, for exactly the same reason — the output is what somebody
else runs, and a diff nobody looked at is a change nobody decided.

What is frozen: the full rendered tree for two fixed answer sets, byte for
byte, filenames included.

* ``baseline`` — every default taken. It is what a first-time `dna solution
  new` produces, so a regression here is a regression in the first thing anyone
  sees.
* ``entra-external`` — the answers that turn every conditional the other way:
  ``identity=entra`` (which is also what un-gates ``graph_obo``), an external
  ingress, an app that may not sleep, a different replica ceiling. Its job is
  to make the `{% if %}` branches load-bearing: with only the baseline frozen,
  deleting a whole conditional block would still be green.

To re-freeze, on purpose::

    DNA_FREEZE_GOLDEN=1 packages/cli/.venv/bin/python -m pytest \\
        packages/cli/tests/test_solution_golden.py

and then READ the diff. That reading is the review; the environment variable is
only what makes it possible to have one.

⚠️ Two values in the answers file are normalised before freezing: `_src_path`
(an absolute path, different on every machine) and `_commit` (absent here,
because the golden renders the template as a plain directory rather than a
tagged clone — a hash in a golden would re-freeze itself on every commit and
teach everyone to stop reading the diff).
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from dna_cli.solution_cmd import solution

pytest.importorskip("copier", reason="needs dna-cli[scaffold]")

REPO_ROOT = Path(__file__).resolve().parents[3]
REFERENCE_TEMPLATE = REPO_ROOT / "templates" / "app-container"
GOLDEN_DIR = Path(__file__).parent / "goldens" / "solution"

FREEZE = os.environ.get("DNA_FREEZE_GOLDEN") == "1"

# The fixed answer sets. Adding one is cheap and is the right move whenever a
# new conditional enters the template — an unexercised `{% if %}` is a branch
# the golden cannot see.
CASES: dict[str, dict[str, str]] = {
    "baseline": {
        "service_name": "api",
    },
    "entra-external": {
        "service_name": "mcp-entra",
        "image_name": "mcp",
        "description": "the delegated door",
        "identity": "entra",
        "graph_obo": "true",
        "ingress": "external",
        "port": "8000",
        "env_prefix": "DNA_MCP",
        "can_sleep": "false",
        "max_replicas": "5",
    },
    # ⭐ The App that does NOT SERVE (i-099, 08/08/2026). `ingress: none` is a
    # value the `App` Kind has accepted since PR #355 and this template could
    # not produce — an App anyone could DECLARE and nobody could GENERATE.
    #
    # Frozen as a whole TREE because the claim is an ABSENCE spread over six
    # files: no ingress block in the bicep, no published port in the compose
    # fragment, no EXPOSE and no `*_PORT` in the Dockerfile, no `PORT` in
    # `server.py`, no `uvicorn` in `pyproject.toml`, and — the one that decides
    # — no `port` in the ANSWERS file. An absence is what a golden freezes well
    # and a grep freezes badly, because the comment that explains an absence
    # contains the word.
    #
    # `identity: none` rides along on purpose: `worker` consumes a queue, it
    # does not verify anybody's token, and this is the only golden case that
    # exercises that branch of `pyproject.toml` in the same tree.
    "no-ingress": {
        "service_name": "worker",
        "description": "the queue worker — it answers nobody",
        "identity": "none",
        "ingress": "none",
        "can_sleep": "true",
        "max_replicas": "4",
    },
    # ⭐ The case measured in dna-cloud on 07/08/2026: NINE deployable services
    # over FOUR `apps/` directories, so EIGHT of the nine are another
    # deployment of an image that already exists. `owns_code: false` is that
    # eight, and what it must render is ONLY the wiring — regenerating
    # `apps/mcp/src/` because somebody declared `mcp-ws` would overwrite
    # production code.
    #
    # Frozen as a golden rather than only asserted in a test because the file
    # SET is the whole claim here: the golden's file-set assertion fails the
    # moment a Dockerfile reappears, which is the exact regression.
    "shared-image": {
        "service_name": "mcp-ws",
        "image_name": "mcp",
        "owns_code": "false",
        "description": "a second door over the mcp image",
        "identity": "workos",
        "ingress": "external",
        "port": "8001",
        "env_prefix": "DNA_MCP",
        "can_sleep": "true",
        "max_replicas": "3",
    },
}


def _is_byproduct(path: Path) -> bool:
    """Anything a tool left behind rather than the template rendering.

    A golden tree contains real `.py` files, so anything that imports or
    executes it can drop `__pycache__` INSIDE the golden — and the next
    comparison would then report a file-set difference caused by having looked
    at the golden. `tests/goldens/conftest.py` stops pytest collecting them;
    this is the second lock, because a golden that mutates when observed is
    worth locking twice.
    """
    return "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}


def _normalise(relpath: str, text: str) -> str:
    """Strip the two values that are true but not stable."""
    if not relpath.startswith(".copier-answers"):
        return text
    out = []
    for line in text.splitlines(keepends=True):
        if line.startswith("_src_path:"):
            out.append("_src_path: <TEMPLATE>\n")
        elif line.startswith("_commit:"):
            out.append("_commit: <REF>\n")
        else:
            out.append(line)
    return "".join(out)


def _render(case: str, tmp_path: Path) -> dict[str, str]:
    destination = tmp_path / case
    destination.mkdir(parents=True)
    args = ["new", str(REFERENCE_TEMPLATE), str(destination), "--defaults"]
    for key, value in CASES[case].items():
        args += ["--data", f"{key}={value}"]
    result = CliRunner().invoke(solution, args)
    assert result.exit_code == 0, result.output

    tree: dict[str, str] = {}
    for path in sorted(destination.rglob("*")):
        if not path.is_file() or _is_byproduct(path):
            continue
        relpath = str(path.relative_to(destination))
        tree[relpath] = _normalise(relpath, path.read_text(encoding="utf-8"))
    return tree


def _freeze(case: str, tree: dict[str, str]) -> None:
    target = GOLDEN_DIR / case
    if target.exists():
        shutil.rmtree(target)
    for relpath, text in tree.items():
        out = target / relpath
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")


def _frozen(case: str) -> dict[str, str]:
    target = GOLDEN_DIR / case
    return {
        str(p.relative_to(target)): p.read_text(encoding="utf-8")
        for p in sorted(target.rglob("*"))
        if p.is_file() and not _is_byproduct(p)
    }


@pytest.mark.parametrize("case", sorted(CASES))
def test_a_arvore_renderizada_e_a_congelada(case: str, tmp_path: Path) -> None:
    tree = _render(case, tmp_path)

    if FREEZE:
        _freeze(case, tree)
        pytest.skip(f"re-froze goldens/solution/{case} — now read the diff")

    target = GOLDEN_DIR / case
    assert target.is_dir(), (
        f"no golden for '{case}'. Freeze it on purpose:\n"
        "  DNA_FREEZE_GOLDEN=1 packages/cli/.venv/bin/python -m pytest "
        "packages/cli/tests/test_solution_golden.py"
    )
    frozen = _frozen(case)

    # Filenames first, and separately: a template whose paths changed produces
    # a hundred content diffs that all say the same thing, and the one line
    # worth reading is which file moved.
    assert sorted(tree) == sorted(frozen), (
        "the rendered FILE SET changed. If that was the intent, re-freeze with "
        "DNA_FREEZE_GOLDEN=1 and put the new tree in the diff."
    )
    for relpath in sorted(frozen):
        assert tree[relpath] == frozen[relpath], (
            f"{case}/{relpath} changed. Re-freeze with DNA_FREEZE_GOLDEN=1 only "
            "after deciding the new output is what you meant."
        )


def test_o_golden_exercita_os_dois_lados_de_cada_condicional() -> None:
    """The golden cases have to disagree on every gated value.

    A case that happened to answer like the baseline would look like coverage
    and buy nothing — this is the assertion that keeps the variants from
    decaying into copies of `baseline`. Each name below gates a `{% if %}`
    somewhere in the template, `owns_code` most consequentially of all: it gates
    whether the code files exist at all.
    """
    baseline_defaults = {
        "identity": "workos",
        "graph_obo": "false",
        "ingress": "internal",
        "can_sleep": "true",
        "owns_code": "true",
    }
    variants = [answers for case, answers in CASES.items() if case != "baseline"]
    for name, default in baseline_defaults.items():
        assert any(answers.get(name, default) != default for answers in variants), (
            f"'{name}' is answered the same in every golden case, so the branch it "
            "gates is never rendered both ways."
        )


def test_todo_valor_de_ingress_chega_a_um_golden() -> None:
    """⭐ `ingress` is the one answer with THREE sides, so "both ways" is not enough.

    Derived from `copier.yml`'s own `choices` rather than from a list kept
    here: a fourth value added to the question would otherwise enter the
    template with no golden rendering it, which is the exact hole i-099 was —
    a value the declaration accepted and nothing generated.
    """
    from dna._yaml import safe_load

    questions = safe_load((REFERENCE_TEMPLATE / "copier.yml").read_text())
    choices = set(questions["ingress"]["choices"])
    default = questions["ingress"]["default"]

    covered = {answers.get("ingress", default) for answers in CASES.values()}
    assert choices <= covered, (
        f"ingress values with no golden: {sorted(choices - covered)}. Every "
        "choice the question offers has to be rendered by some case, or the "
        "template accepts a value nobody ever saw the output of."
    )


def test_o_golden_nunca_e_coletado(pytestconfig: pytest.Config) -> None:
    """⚠️ The golden tree ships real `test_*.py`, so pytest must not recurse into it.

    Measured, in a full-suite run and not a targeted one: collected, those files
    import against packages that do not exist here, two golden trees ship a
    module of the same basename, and running them writes `__pycache__` INSIDE
    the golden — which the very next comparison then reports as a file-set
    difference. A golden that mutates by being observed.

    ⛔ And the fix that looks obvious is the one that broke three unrelated
    suites: a `tests/goldens/conftest.py` shadows `tests/conftest.py`, because
    `pythonpath = ["tests"]` puts `tests/` on sys.path and several modules do
    `from conftest import ...`. Hence `norecursedirs` in `pyproject.toml`,
    asserted here — with the precondition asserted too, so this guard cannot
    quietly become vacuous if the template ever stops shipping a test file.
    """
    shipped_tests = [
        p for p in GOLDEN_DIR.rglob("test_*.py") if p.is_file()
    ]
    assert shipped_tests, (
        "no golden ships a test file any more — re-read this guard before "
        "deleting it, and check whether `norecursedirs` is still earning its keep."
    )
    assert "goldens" in pytestconfig.getini("norecursedirs"), (
        "tests/goldens/** ships collectible test files "
        f"({[str(p.relative_to(GOLDEN_DIR)) for p in shipped_tests]}) and pytest "
        "would import them. Keep `goldens` in norecursedirs — and do NOT 'fix' "
        "this with tests/goldens/conftest.py, which shadows tests/conftest.py."
    )


def test_o_golden_cobre_todo_arquivo_que_o_template_declara() -> None:
    """Every template file reaches at least one golden.

    Derived from the template directory rather than from a hand-kept list: a
    file added to the template and excluded from rendering by accident would
    otherwise be a silent hole, and the golden would happily freeze its
    absence. Counted by NAME because the paths themselves are templated.
    """
    if FREEZE:
        pytest.skip("freezing")
    rendered = set()
    for case in CASES:
        rendered |= {Path(p).name for p in _frozen(case)}

    declared = {
        _unconditional(p.name).removesuffix(".jinja")
        for p in REFERENCE_TEMPLATE.rglob("*.jinja")
        if "_copier_conf" not in str(p)
    }
    missing = declared - rendered
    assert not missing, f"template files that reach no golden: {sorted(missing)}"


_JINJA_BLOCK = re.compile(r"\{%.*?%\}")


def _unconditional(name: str) -> str:
    """A template file name with its `{% if %}` gates stripped.

    ⚠️ Not cosmetic. `{% if owns_code %}Dockerfile{% endif %}.jinja` is how the
    template emits a file for some answers and not others — Copier skips a path
    whose rendered segment is empty — so the LITERAL file name in the tree is
    not the name of the rendered file, and a coverage check comparing them
    directly would report every conditional file as uncovered forever.
    """
    return _JINJA_BLOCK.sub("", name)
