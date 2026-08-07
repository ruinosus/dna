"""The `Solution` record — the second view of the answers, and the longer one.

What these tests are actually about
===================================
Fatia 3 measured a defect it could name and not fix: an answer behind `when:`
is erased from `.copier-answers.<svc>.yml` when its condition stops holding,
and returns as the TEMPLATE's default — not the human's value — if the
condition comes back. The guide states the fix as a fact about shape rather
than code: *"a record that outlives the answers file is the only place such a
value can survive."*

So the load-bearing assertions here are the ones that would go green for the
wrong reason if written any other way:

* :func:`test_a_resposta_gated_volta_como_a_do_humano_e_nao_o_default_do_template`
  — the round trip that fatia 3 documented as unrecoverable, now recovered.
  Delete the merge and the value comes back `False`. That is the headline.
* :func:`test_o_piso_que_so_o_registro_guarda_e_comparado_e_nao_some` — the
  silent failure nº 1 of this family, re-entering by the new door. If the
  record's answers are re-passed but NOT merged into the variable the report
  compares, a floor that lives only in the record moves nobody and says
  nothing.
* :func:`test_toda_resposta_do_registro_chega_ao_copier` — the mutant guard,
  at the seam rather than at the output, for the same reason the fatia-3 one is
  written that way: Copier's own memory makes re-passing indistinguishable from
  not re-passing when the file still holds the value.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from dna_cli import solution_cmd, solution_kind
from dna_cli.solution_cmd import solution

copier = pytest.importorskip("copier", reason="needs dna-cli[scaffold]")

REPO_ROOT = Path(__file__).resolve().parents[3]
REFERENCE_TEMPLATE = REPO_ROOT / "templates" / "app-container"


# ── helpers, shared in spirit with test_solution_cmd.py ──────────────────────


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    ).stdout


def commit_all(repo: Path, message: str) -> None:
    git(repo, "add", "-A")
    git(
        repo, "-c", "user.email=t@example.com", "-c", "user.name=t",
        "commit", "-qm", message,
    )


def init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    return path


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def template(tmp_path: Path) -> Path:
    dst = tmp_path / "template"
    subprocess.run(["cp", "-R", str(REFERENCE_TEMPLATE), str(dst)], check=True)
    init_repo(dst)
    commit_all(dst, "v1")
    git(dst, "tag", "v1.0.0")
    return dst


@pytest.fixture
def destination(tmp_path: Path) -> Path:
    return init_repo(tmp_path / "repo")


@pytest.fixture
def scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """A real filesystem scope for the Solution instances to land in.

    Deliberately a REAL kernel write, not a stub: the whole claim of this slice
    is that the declaration becomes governed data, and a stub would prove the
    command calls a function rather than that the Kind accepts what it writes.
    The schema, the relation to `App` and the write guards all run.
    """
    base = tmp_path / "store" / ".dna"
    board = base / "board"
    board.mkdir(parents=True)
    (board / "manifest.yaml").write_text(
        yaml.dump(
            {
                "apiVersion": "github.com/ruinosus/dna/v1",
                "kind": "Genome",
                "metadata": {"name": "board", "description": "test scope"},
                "spec": {},
            }
        )
    )
    monkeypatch.setenv("DNA_SOURCE_URL", f"file://{base}")
    monkeypatch.setenv("DNA_SCOPE_DEFAULT", "board")
    return "board"


def bump_template(template: Path, *, tag: str, old: str, new: str) -> None:
    """Evolve `copier.yml` by replacing one fragment, then tag."""
    text = (template / "copier.yml").read_text()
    assert old in text, f"fragment not in copier.yml: {old!r}"
    (template / "copier.yml").write_text(text.replace(old, new))
    commit_all(template, tag)
    git(template, "tag", tag)


def generate(runner: CliRunner, template: Path, destination: Path, **answers):
    args = ["new", str(template), str(destination), "--defaults"]
    for key, value in answers.items():
        args += ["--data", f"{key}={value}"]
    result = runner.invoke(solution, args)
    assert result.exit_code == 0, result.output
    return result


def solution_spec(name: str) -> dict:
    spec = solution_kind.read_solution(name)
    assert spec is not None, f"no Solution {name!r} was recorded"
    return spec


def layer_of(name: str, service: str) -> dict:
    entry = solution_kind.recorded_layer(solution_spec(name), service)
    assert entry is not None, f"Solution {name!r} holds no layer {service!r}"
    return entry


# ── the record is written, and it is a real instance ─────────────────────────


def test_new_grava_a_declaracao_e_as_respostas_como_instancia(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """`new --solution` writes a Solution the kernel accepted.

    Through `write_instance`, so the descriptor's schema, its
    `additionalProperties: false` and the `apps → App` relation all ran. A test
    that asserted on a dict this command built would have proven nothing about
    the Kind.
    """
    result = runner.invoke(
        solution,
        ["new", str(template), str(destination), "--defaults",
         "--data", "service_name=api", "--solution", "dna-cloud"],
    )
    assert result.exit_code == 0, result.output

    entry = layer_of("dna-cloud", "api")
    assert entry["answers_file"] == ".copier-answers.api.yml"
    assert entry["template"]["src"] == str(template)
    assert entry["template"]["ref"] == "v1.0.0"
    assert entry["answers"]["dna_floor"] == "0.74"
    assert entry["answers"]["identity"] == "workos"


def test_o_registro_guarda_um_PONTEIRO_e_nunca_o_corpo_do_template(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """⛔ The line that decides whether the idea is worth having.

    §2.3 already refused a code field on `McpServer`, and §5.3 kept
    Scaffold-as-Kind out of the recipe. This asserts the refusal on the DATA
    rather than on the schema: nothing rendered — not the Dockerfile, not the
    bicep, not the server skeleton — reaches the instance. A Kind that declared
    the code would be the code written in YAML, which serves nobody.
    """
    generate(runner, template, destination, service_name="api")
    runner.invoke(
        solution,
        ["record", str(destination), "--solution", "s"],
    )
    blob = json.dumps(solution_spec("s"))

    for rendered in ("FROM ", "containerApp", "def main", "[project]"):
        assert rendered not in blob, f"template body leaked into the record: {rendered}"
    assert "Dockerfile" not in blob


def test_um_answers_file_sem_src_path_recusa_em_vez_de_gravar_meia_verdade(
    runner: CliRunner, tmp_path: Path, scope: str
) -> None:
    """A layer with no template pointer cannot be updated, so it is not recorded.

    Recording it would create an instance that claims to be the declaration of
    an updatable tree and is not — the "campo que parece aplicado e não é"
    failure this house pays most for.
    """
    tree = init_repo(tmp_path / "orphan")
    (tree / ".copier-answers.api.yml").write_text("service_name: api\n")

    result = runner.invoke(
        solution, ["record", str(tree), "--solution", "s"]
    )

    assert result.exit_code == solution_cmd.EXIT_REFUSED
    assert "_src_path" in result.output
    assert solution_kind.read_solution("s") is None


# ── ⭐ the seam: the record feeds what fatia 3 built ──────────────────────────


def test_toda_resposta_do_registro_chega_ao_copier(
    runner: CliRunner, template: Path, destination: Path, scope: str, monkeypatch
) -> None:
    """⭐ THE MUTANT. Stop merging the record into `before` and this goes red.

    A seam guard, and labelled as one for the same reason the fatia-3 twin is:
    with the file still holding the answers, re-passing them is behaviourally
    identical to not re-passing them, so an assertion on rendered output would
    pass for the wrong reason. What is measured is that the answers the RECORD
    holds are the ones handed to Copier.
    """
    generate(runner, template, destination, service_name="mcp", identity="entra")
    commit_all(destination, "generated")
    runner.invoke(solution, ["record", str(destination), "--solution", "s"])

    # A value only the record holds — the shape a `when:`-erased answer has.
    spec = solution_spec("s")
    spec["services"][0]["answers"]["so_no_registro"] = "sobrevivente"
    solution_kind.upsert_solution(
        "s",
        [
            solution_kind.Layer(
                name="mcp",
                answers_file=spec["services"][0]["answers_file"],
                template_src=spec["services"][0]["template"]["src"],
                template_ref=spec["services"][0]["template"]["ref"],
                answers=spec["services"][0]["answers"],
                pode_dormir=spec["services"][0].get("pode_dormir"),
            )
        ],
    )

    captured: dict = {}
    real = copier.run_update

    def spy(*args, **kwargs):
        captured.update(kwargs.get("data") or {})
        return real(*args, **kwargs)

    monkeypatch.setattr(copier, "run_update", spy)

    result = runner.invoke(
        solution,
        ["update", str(destination), "--service", "mcp", "--solution", "s"],
    )
    assert result.exit_code == 0, result.output
    assert captured.get("so_no_registro") == "sobrevivente", (
        "an answer only the record held never reached Copier: " f"{sorted(captured)}"
    )


def test_a_resposta_gated_volta_como_a_do_humano_e_nao_o_default_do_template(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """⭐ THE HEADLINE. The round trip fatia 3 measured as unrecoverable.

    Measured then, and documented in `solution-scaffolding.md`::

        identity=entra, graph_obo=true   ->  graph_obo: true
        update to identity=workos        ->  (absent)
        update back to identity=entra    ->  graph_obo: false   <- was true

    The third line is the defect: `when:` erased the value and Copier answered
    with the TEMPLATE's default. Nothing in `dna solution` could undo it,
    because the answers file was the only place holding it.

    With a `Solution` recorded there is a second place, and the human's `true`
    comes back. This is the one assertion whose failure means the slice did not
    happen — and its twin below proves the failure is real without the record,
    so a green here cannot be Copier being clever on its own.
    """
    generate(
        runner, template, destination,
        service_name="mcp", identity="entra", graph_obo="true",
    )
    commit_all(destination, "generated")
    runner.invoke(solution, ["record", str(destination), "--solution", "s"])

    for identity in ("workos", "entra"):
        result = runner.invoke(
            solution,
            ["update", str(destination), "--service", "mcp", "--solution", "s",
             "--data", f"identity={identity}"],
        )
        assert result.exit_code == 0, result.output
        commit_all(destination, f"identity={identity}")

    answers = yaml.safe_load((destination / ".copier-answers.mcp.yml").read_text())
    assert answers["graph_obo"] is True, (
        "the human's gated answer came back as the template default — the record "
        "did not outlive the answers file"
    )


def test_sem_registro_a_mesma_ida_e_volta_continua_perdendo_o_valor(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """The control, and the reason the test above is not a tautology.

    Same trip, no `--solution`. If this ever goes green, Copier changed and the
    headline test stopped measuring anything — better to learn it here than to
    trust a green that no longer means what it says.
    """
    generate(
        runner, template, destination,
        service_name="mcp", identity="entra", graph_obo="true",
    )
    commit_all(destination, "generated")

    for identity in ("workos", "entra"):
        runner.invoke(
            solution,
            ["update", str(destination), "--service", "mcp",
             "--data", f"identity={identity}"],
        )
        commit_all(destination, f"identity={identity}")

    answers = yaml.safe_load((destination / ".copier-answers.mcp.yml").read_text())
    assert answers["graph_obo"] is False


def test_o_piso_que_so_o_registro_guarda_e_comparado_e_nao_some(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """⭐ The silent failure nº 1, re-entering by the new door.

    `update` without re-passing the recorded answers does not move the SDK
    floor, in silence — that is what the adversarial test measured, and the
    two-tier report is what fatia 3 built for it. If the record's answers are
    re-passed but NOT merged into the variable the report compares against,
    an answer living only in the record is compared against nothing: it moves
    nobody and says nothing, which is the same defect with a nicer command
    line.

    So: an answer erased from the file, kept by the record, with the template's
    default moving under it. It has to appear in `moved_defaults`.
    """
    generate(
        runner, template, destination,
        service_name="mcp", identity="entra", graph_obo="false",
    )
    commit_all(destination, "generated")
    runner.invoke(solution, ["record", str(destination), "--solution", "s"])

    # Erase it from the FILE the way `when:` does, leaving the record holding it.
    runner.invoke(
        solution,
        ["update", str(destination), "--service", "mcp", "--solution", "s",
         "--data", "identity=workos"],
    )
    commit_all(destination, "gated off")
    assert "graph_obo" not in yaml.safe_load(
        (destination / ".copier-answers.mcp.yml").read_text()
    )

    bump_template(
        template,
        tag="v2.0.0",
        old="  default: false\n  when: \"{{ identity == 'entra' }}\"",
        new="  default: true\n  when: \"{{ identity == 'entra' }}\"",
    )

    result = runner.invoke(
        solution,
        ["update", str(destination), "--service", "mcp", "--solution", "s",
         "--data", "identity=entra", "--json"],
    )
    report = json.loads(result.output)

    moved = {m["name"]: m for m in report["moved_defaults"]}
    assert "graph_obo" in moved, (
        "a default moved under an answer only the record held, and the report "
        f"said nothing: {report['moved_defaults']}"
    )
    assert moved["graph_obo"]["recorded"] is False
    assert moved["graph_obo"]["new_default"] is True
    assert report["restored_answers"] == ["graph_obo"]


def test_a_perda_reportada_e_a_do_ARQUIVO_e_nao_a_do_registro(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """A restored answer is not a lost one, on the update after the next.

    `lost_answers` compares the FILE's start and end. Handing it the merged
    view would report every value the record keeps alive as a loss, on every
    single update, forever — a permanent false alarm produced by the fix for a
    real alarm.
    """
    generate(
        runner, template, destination,
        service_name="mcp", identity="entra", graph_obo="true",
    )
    commit_all(destination, "generated")
    runner.invoke(solution, ["record", str(destination), "--solution", "s"])

    first = runner.invoke(
        solution,
        ["update", str(destination), "--service", "mcp", "--solution", "s",
         "--data", "identity=workos", "--json"],
    )
    commit_all(destination, "gated off")
    assert [a["name"] for a in json.loads(first.output)["lost_answers"]] == [
        "graph_obo"
    ], "the update that actually erased it must say so"

    second = runner.invoke(
        solution,
        ["update", str(destination), "--service", "mcp", "--solution", "s", "--json"],
    )
    assert json.loads(second.output)["lost_answers"] == [], (
        "an answer the record is keeping alive was reported as lost again"
    )


def test_o_registro_acumula_em_vez_de_espelhar_o_arquivo(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """The write-back keeps what the file dropped.

    Mirroring the post-update file would delete the gated value from the record
    on the very update that deleted it from the file, and the record would be a
    slower copy instead of a longer memory. Verified against copier 9.17: an
    accumulated answer the template no longer asks about is ignored, so keeping
    it costs nothing.
    """
    generate(
        runner, template, destination,
        service_name="mcp", identity="entra", graph_obo="true",
    )
    commit_all(destination, "generated")
    runner.invoke(solution, ["record", str(destination), "--solution", "s"])

    runner.invoke(
        solution,
        ["update", str(destination), "--service", "mcp", "--solution", "s",
         "--data", "identity=workos"],
    )

    assert layer_of("s", "mcp")["answers"]["graph_obo"] is True
    assert layer_of("s", "mcp")["answers"]["identity"] == "workos", (
        "an answer the human DID move must be updated, not preserved"
    )


def test_update_sem_solution_nao_toca_registro_nenhum(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """The record is opt-in, and rendering must keep working without a scope."""
    generate(runner, template, destination, service_name="api")
    commit_all(destination, "generated")

    result = runner.invoke(
        solution, ["update", str(destination), "--service", "api", "--json"]
    )
    report = json.loads(result.output)

    assert result.exit_code == 0, result.output
    assert report["solution"] is None
    assert report["restored_answers"] == []


def test_update_com_solution_inexistente_recusa_nomeando_o_conserto(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    generate(runner, template, destination, service_name="api")
    commit_all(destination, "generated")

    result = runner.invoke(
        solution,
        ["update", str(destination), "--service", "api", "--solution", "ausente"],
    )

    assert result.exit_code == solution_cmd.EXIT_REFUSED
    assert "dna solution record" in result.output


# ── the cost question, as a field instead of something someone remembers ─────


def test_pode_dormir_e_gravado_a_partir_da_resposta_de_custo(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """The CLAUDE.md cost gate becomes part of the declaration.

    Not a second answer the human retypes — that would be two sources for one
    fact — but the same fact under the name a reader of the FLEET can use
    without knowing this template spelled it `can_sleep`.
    """
    generate(runner, template, destination, service_name="api", can_sleep="false")
    generate(runner, template, destination, service_name="worker", can_sleep="true")
    runner.invoke(solution, ["record", str(destination), "--solution", "s"])

    assert layer_of("s", "api")["pode_dormir"] is False
    assert layer_of("s", "worker")["pode_dormir"] is True


def test_uma_camada_sem_resposta_de_custo_nao_presume_o_lado_barato(
    runner: CliRunner, tmp_path: Path, scope: str
) -> None:
    """⚠️ Absent is reported, never defaulted to `true`.

    Presuming the cheap side is how a fixed replica — ~US$ 90/month, forever —
    gets into the fleet with nobody deciding it. The finding speaks on EVERY
    run, like `divergent_answers` and unlike `moved_defaults`, because a
    condition that stays true has to keep being said.
    """
    silent = tmp_path / "silent-template"
    silent.mkdir()
    (silent / "copier.yml").write_text(
        '_answers_file: ".copier-answers.{{ service_name }}.yml"\n'
        '_templates_suffix: ".jinja"\n'
        "service_name:\n  type: str\n  default: api\n"
    )
    (silent / "{{ _copier_conf.answers_file }}.jinja").write_text(
        "{{ _copier_answers|to_nice_yaml -}}\n"
    )
    init_repo(silent)
    commit_all(silent, "v1")
    git(silent, "tag", "v1.0.0")

    tree = init_repo(tmp_path / "tree")
    runner = CliRunner()
    runner.invoke(solution, ["new", str(silent), str(tree), "--defaults"])

    result = runner.invoke(
        solution, ["record", str(tree), "--solution", "s", "--json"]
    )

    assert json.loads(result.output)["unanswered_cost"] == ["api"]
    assert "pode_dormir" not in layer_of("s", "api")

    strict = runner.invoke(
        solution, ["record", str(tree), "--solution", "s", "--strict"]
    )
    assert strict.exit_code == solution_cmd.EXIT_FINDINGS
    assert "US$ 90" in strict.output


def test_sleep_answer_nomeia_a_pergunta_quando_o_template_a_chama_de_outra_coisa(
    runner: CliRunner, tmp_path: Path, scope: str
) -> None:
    """`can_sleep` is a GUESS, and the escape from it is a named option.

    The guess never hides: when the key is absent nothing is presumed. Which is
    what makes a default acceptable here at all — it fails loudly rather than
    quietly, unlike the fallbacks this house has been bitten by.
    """
    other = tmp_path / "other-template"
    other.mkdir()
    (other / "copier.yml").write_text(
        '_answers_file: ".copier-answers.{{ service_name }}.yml"\n'
        '_templates_suffix: ".jinja"\n'
        "service_name:\n  type: str\n  default: api\n"
        "scale_to_zero:\n  type: bool\n  default: false\n"
    )
    (other / "{{ _copier_conf.answers_file }}.jinja").write_text(
        "{{ _copier_answers|to_nice_yaml -}}\n"
    )
    init_repo(other)
    commit_all(other, "v1")
    git(other, "tag", "v1.0.0")

    tree = init_repo(tmp_path / "tree")
    runner.invoke(solution, ["new", str(other), str(tree), "--defaults"])

    guessed = runner.invoke(
        solution, ["record", str(tree), "--solution", "guess", "--json"]
    )
    assert json.loads(guessed.output)["unanswered_cost"] == ["api"]

    named = runner.invoke(
        solution,
        ["record", str(tree), "--solution", "named", "--json",
         "--sleep-answer", "scale_to_zero"],
    )
    assert json.loads(named.output)["unanswered_cost"] == []
    assert layer_of("named", "api")["pode_dormir"] is False


# ── one template overlaid N times, one record ────────────────────────────────


def test_uma_solucao_guarda_uma_CAMADA_por_answers_file(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """Nine services over four images is nine entries, not one giant record.

    §4.4 regra 3, and the reason `services[]` is a list of layers rather than a
    solution-wide `answers` map: each layer updates alone.
    """
    for service in ("mcp", "mcp-entra", "mcp-ws"):
        generate(
            runner, template, destination,
            service_name=service, image_name="mcp",
        )
    runner.invoke(solution, ["record", str(destination), "--solution", "doors"])

    spec = solution_spec("doors")
    # Sorted by answers-file name, which `discover_answers_files` fixes — not by
    # generation order, which nothing records and nothing should depend on.
    assert sorted(entry["name"] for entry in spec["services"]) == [
        "mcp", "mcp-entra", "mcp-ws"
    ]
    assert {entry["answers"]["image_name"] for entry in spec["services"]} == {"mcp"}
    assert {entry["template"]["src"] for entry in spec["services"]} == {str(template)}


def test_gravar_uma_camada_nunca_apaga_as_outras(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """Upsert per layer. A run knows about one app and must not erase eight."""
    generate(runner, template, destination, service_name="api")
    generate(runner, template, destination, service_name="web")
    runner.invoke(solution, ["record", str(destination), "--solution", "s"])

    runner.invoke(
        solution, ["record", str(destination), "--solution", "s", "--service", "api"]
    )

    assert [e["name"] for e in solution_spec("s")["services"]] == ["api", "web"]


def test_o_new_sabe_qual_camada_acabou_de_criar(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """The second `new` in a repo records the layer it wrote, not `None`.

    Before this slice `answers_file` was reported as `null` from the second
    `new` onward (`found[0] if len(found) == 1`). Harmless while nothing read
    it; wrong the moment a record has to name the layer it just created.
    """
    generate(runner, template, destination, service_name="api")

    result = runner.invoke(
        solution,
        ["new", str(template), str(destination), "--defaults",
         "--data", "service_name=web", "--solution", "s", "--json"],
    )
    report = json.loads(result.output)

    assert report["answers_file"] == ".copier-answers.web.yml"
    assert [e["name"] for e in solution_spec("s")["services"]] == ["web"]


# ── ⭐ Duas metades: o ledger fica, só o custo muda de casa ───────────────────


def one_layer(**overrides) -> solution_kind.Layer:
    fields = dict(
        name="mcp-ws",
        answers_file=".copier-answers.mcp-ws.yml",
        template_src="/templates/app-container",
        template_ref="v1.0.0",
        answers={
            "service_name": "mcp-ws",
            "python_module": "mcp",
            "port": 8001,
            "can_sleep": False,
            "description": "a second door over the mcp image",
        },
        pode_dormir=False,
    )
    fields.update(overrides)
    return solution_kind.Layer(**fields)


def test_o_App_recebe_a_IDENTIDADE_do_servico_e_nao_o_livro_razao() -> None:
    """⭐ Founder decision, 07/08/2026: FOUR fields, not seven.

    The `App` is the DEPLOYMENT, so it carries what a reader of the fleet needs
    without opening anybody's repo — which module, which port, and whether it
    sleeps.

    ⚠️ And it deliberately does NOT carry the ledger. `answers_file`,
    `template` and `answers` are the provenance of the RENDER and stay in
    `Solution.services[]`; `answers` in particular is the only place a
    `when:`-erased answer survives, so moving it would have put the fatia-3
    rescue on the table for nothing. Asserted as an ABSENCE, because that is
    the half a later "tidy-up" would quietly undo.
    """
    spec = one_layer().to_app_spec()

    assert spec["service_name"] == "mcp-ws"
    assert spec["python_module"] == "mcp"
    assert spec["port"] == 8001
    assert spec["can_sleep"] is False
    assert spec["title"] == "a second door over the mcp image"

    for ledger in ("answers_file", "template", "answers"):
        assert ledger not in spec, (
            f"`{ledger}` is the render's provenance and belongs to "
            "Solution.services[] — one fact, one house"
        )
    assert set(spec) <= set(solution_kind.APP_SERVICE_FIELDS) | {"title", "description"}


def test_o_ledger_fica_e_so_o_custo_muda_de_casa() -> None:
    """The two halves, and the seam between them.

    `services[]` keeps `name` / `answers_file` / `template` / `answers` in both
    worlds — it is not part of the move, and never was. `pode_dormir` is the
    one thing that changes house, and it changes house COMPLETELY: written in
    one or the other, never both. Two houses for one fact is two answers to
    "does this sleep?" that can disagree, and the one that disagrees is found
    by the invoice.
    """
    layer = one_layer()

    stays = layer.to_spec(cost_on_app=False)
    moved = layer.to_spec(cost_on_app=True)

    for entry in (stays, moved):
        assert entry["name"] == "mcp-ws"
        assert entry["answers_file"] == ".copier-answers.mcp-ws.yml"
        assert entry["template"] == {"src": "/templates/app-container", "ref": "v1.0.0"}
        assert entry["answers"]["port"] == 8001

    assert stays["pode_dormir"] is False
    assert "pode_dormir" not in moved, (
        "the cost was written on the App, so writing it here too would BE the "
        "second house the decision exists to remove"
    )


def test_o_App_gerado_nunca_apaga_o_que_o_portal_escreveu() -> None:
    """A scaffolding run must not delete an entitlement.

    An `App` is also a portal record — its title, its icon, the plan that opens
    it, the copilots it composes — and `dna solution` knows nothing about any of
    that. A write that replaced the spec would cancel a paying App's
    `requires_plan` because somebody re-rendered its Dockerfile, and would look
    like a successful scaffold while doing it.
    """
    layer = solution_kind.Layer(
        name="api", answers_file=".copier-answers.api.yml",
        template_src="/t", template_ref=None,
        answers={"python_module": "api", "port": 8080}, pode_dormir=True,
    )

    spec = layer.to_app_spec(
        existing={
            "title": "The Analyst",
            "requires_plan": "pro",
            "copilots": ["analista"],
            "port": 9999,
        }
    )

    assert spec["requires_plan"] == "pro"
    assert spec["copilots"] == ["analista"]
    assert spec["title"] == "The Analyst", "a human's title outranks a copier answer"
    assert spec["port"] == 8080, "but the generated facts ARE refreshed"


def test_a_prontidao_do_descritor_e_medida_e_nunca_presumida() -> None:
    """⚠️ Asked of the live descriptor, so it cannot go stale.

    `App` declares `additionalProperties: false`, so a field it does not know is
    a REFUSED write, not a tolerated extra — measured 07/08/2026::

        write vetoed for board/App/api: Additional properties are not allowed
        ('can_sleep', 'port', 'python_module', 'service_name' were unexpected)

    The predicate therefore reads the schema instead of carrying a flag
    somebody has to remember to flip. The day
    `Story/s-kinds-a-conta-declarada` lands, this test keeps passing and the
    behaviour changes by itself — which is the only kind of handover that does
    not depend on anyone noticing.
    """
    from dna.kernel import Kernel

    port = Kernel.auto()._kinds[("github.com/ruinosus/dna/v1", "App")]
    properties = set((port.schema() or {}).get("properties") or {})
    absent = set(solution_kind.app_kind_absent_fields())

    assert absent == {f for f in solution_kind.APP_SERVICE_FIELDS if f not in properties}
    assert solution_kind.app_is_the_deployment() is not bool(absent)


def test_o_ledger_nao_depende_do_descritor_e_e_gravado_sempre(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """⭐ `services[]` is written on BOTH sides of the handover.

    The one thing waiting on a descriptor is which house the cost lives in.
    The render's provenance is not waiting on anything, and a test that only
    checked the post-move world would let a regression in the pre-move one
    through — which is the world every run is in today.
    """
    generate(runner, template, destination, service_name="api")
    result = runner.invoke(solution, ["record", str(destination), "--solution", "s"])
    assert result.exit_code == 0, result.output

    from dna_cli._ctx import open_session

    with open_session(scope) as session:
        stored = dict(session.get_doc("Solution", "s").spec or {})

    entry = next(e for e in stored["services"] if e["name"] == "api")
    assert entry["answers_file"] == ".copier-answers.api.yml"
    assert entry["template"]["src"] == str(template)
    assert entry["answers"]["identity"] == "workos"


def test_enquanto_o_App_nao_aceita_a_identidade_a_gravacao_DIZ_onde_o_custo_ficou(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """⭐ A bridge announces itself; a fallback goes quiet.

    Two stories share this handover: the descriptor is
    `s-kinds-a-conta-declarada`'s, the command is
    `s-template-dirigido-pelo-app`'s. While the first has not landed the cost
    stays in `Solution.services[].pode_dormir` — and the run says so, names the
    fields the `App` cannot hold, and names the story that moves them.

    Without this line the value would sit in the old house in silence, and a
    value that renders the same whether it is in the right house or the wrong
    one is the failure this house has paid for repeatedly.
    """
    if solution_kind.app_is_the_deployment():
        pytest.skip("the descriptor landed — the bridge is gone, and so is its line")

    generate(runner, template, destination, service_name="api", can_sleep="false")
    result = runner.invoke(
        solution, ["record", str(destination), "--solution", "s", "--json"]
    )
    report = json.loads(result.output)

    assert "can_sleep" in report["app_kind_missing_fields"]
    assert layer_of("s", "api")["pode_dormir"] is False, (
        "while the App cannot hold it, the ledger must still carry the cost — "
        "an announcement is not permission to drop the value"
    )
    prose = runner.invoke(solution, ["record", str(destination), "--solution", "s"])
    assert "s-kinds-a-conta-declarada" in prose.output
    assert "pode_dormir" in prose.output


@pytest.mark.skipif(
    not solution_kind.app_is_the_deployment(),
    reason="waits for s-kinds-a-conta-declarada: App must declare "
    "service_name / python_module / port / can_sleep",
)
def test_a_gravacao_escreve_as_DUAS_METADES_e_elas_casam_pelo_nome(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """⭐ The story's acceptance criterion, through the REAL kernel.

    Both halves in one write: the ledger in `services[]`, the identity on the
    `App`, joined by `services[].name` == the App's `metadata.name` — the key
    that already existed (it is what azd calls a service) and that the founder's
    decision turned into the declared relation.

    Auto-enabling: the skip reads the live descriptor, so the day the sibling
    story lands this starts running without anybody editing it.
    """
    generate(runner, template, destination, service_name="mcp", can_sleep="false")
    result = runner.invoke(solution, ["record", str(destination), "--solution", "s"])
    assert result.exit_code == 0, result.output

    from dna_cli._ctx import open_session

    with open_session(scope) as session:
        stored = dict(session.get_doc("Solution", "s").spec or {})
        app_doc = session.get_doc("App", "mcp")
        app = dict(app_doc.spec or {})

    entry = next(e for e in stored["services"] if e["name"] == "mcp")
    # the ledger half — untouched by the move
    assert entry["answers_file"] == ".copier-answers.mcp.yml"
    assert entry["template"]["src"] == str(template)
    assert entry["answers"]["can_sleep"] is False
    # the identity half — and the cost written HERE, once
    assert app["service_name"] == "mcp"
    assert app["python_module"] == "mcp"
    assert app["port"] == 8080
    assert app["can_sleep"] is False
    assert "pode_dormir" not in entry, "one fact, one house"
    # the join — declared on `apps`, which is the only level the kernel reads
    assert app_doc.name == entry["name"]
    assert stored["apps"] == ["mcp"]
    assert solution_kind.join_disagreements(stored) == ([], [])
    # …and the read path still answers the update path's question.
    assert layer_of("s", "mcp")["pode_dormir"] is False


# ── the relation to App ──────────────────────────────────────────────────────


def test_apps_e_uma_relacao_declarada_e_vazio_e_o_caso_comum(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """`apps` is optional in the SCHEMA, and complete whenever it is written.

    Measured in the spec (§6-B): *"o dna-cloud gera 9 serviços e nenhum App"*.
    A `required: [apps]` would be an obligation the first example already
    violates, so the field stays optional.

    ⭐ But once an `App` is a deployment, `apps` and the set of
    `services[].name` denote the same things — and `apps` is the ONLY one the
    kernel can enforce. Measured in #351: `relation_values` reads
    `spec.get(rel.name)` at the top level, always, so a pointer inside
    `services[].items` is not declarable as a relation — declaring one lints
    green, reports `resolved/enforced = True/True` and resolves `[]`. An
    incomplete `apps` would therefore be the system's one enforced relation
    being incomplete on purpose.

    So consistency is what is asserted, on both sides of the handover.
    """
    generate(runner, template, destination, service_name="api")
    generate(runner, template, destination, service_name="web")
    result = runner.invoke(solution, ["record", str(destination), "--solution", "s"])
    assert result.exit_code == 0, result.output

    spec = solution_spec("s")
    services = {entry["name"] for entry in spec["services"]}
    assert services == {"api", "web"}
    assert solution_kind.join_disagreements(spec) == ([], [])

    if solution_kind.app_is_the_deployment():
        assert set(spec["apps"]) == services, (
            "an App IS a deployment — the only enforceable join has to name all of them"
        )
    else:
        assert "apps" not in spec, (
            "no App instance was written, and `apps` is an ENFORCED relation: "
            "pointing at something that does not exist is the dangling reference "
            "the veto exists for"
        )


def test_apps_e_services_que_discordam_sao_recusados_com_os_DOIS_lados(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """⭐ The mechanism that replaces "just don't populate it".

    One fact in two lists is a real hazard — they disagree on the first run
    that touches only one — and the lists cannot be collapsed: `apps` is the
    only enforceable join, `services[]` is the only place the ledger fits. So
    the answer is a check derived from both sides, run BEFORE the write, so an
    inconsistent record is never stored at all.

    It names both sides. A refusal that only said "they differ" would leave the
    reader diffing two lists by eye, which is the step people skip.
    """
    generate(runner, template, destination, service_name="api")

    result = runner.invoke(
        solution,
        ["record", str(destination), "--solution", "s", "--app", "algum-outro"],
    )

    assert result.exit_code == solution_cmd.EXIT_REFUSED
    assert "api" in result.output, "the service left out of `apps` must be named"
    assert "algum-outro" in result.output, "and the `apps` entry with no service"
    assert solution_kind.read_solution("s") is None, (
        "the guard runs before the write — an inconsistent record must never "
        "reach storage"
    )


def test_a_guarda_da_junta_e_derivada_dos_dois_lados() -> None:
    """Derived, never enumerated — the shape that survives a new service.

    A hand-kept list of expected names would go stale the first time somebody
    added a service, and would then report "consistent" about a set it no
    longer covers. Asserted on the function directly, so the derivation itself
    is what is under test.
    """
    consistent = {
        "services": [{"name": "api"}, {"name": "web"}],
        "apps": ["web", "api"],
    }
    assert solution_kind.join_disagreements(consistent) == ([], []), (
        "order is not disagreement — these are sets of names"
    )

    drifted = {
        "services": [{"name": "api"}, {"name": "worker"}],
        "apps": ["api", "fantasma"],
    }
    assert solution_kind.join_disagreements(drifted) == (["worker"], ["fantasma"])

    # ⚠️ Undeclared is not drifted. A record older than this guard, or one from a
    # repo that delivers no App at all (§6-B: nine services, zero Apps), has no
    # `apps` — and a guard that shouted at those would be a guard somebody turns
    # off before it ever catches a real one.
    undeclared = {"services": [{"name": "api"}]}
    assert solution_kind.join_disagreements(undeclared) == ([], [])
    assert solution_kind.join_disagreements({**undeclared, "apps": []}) == ([], [])


def test_a_relacao_apps_aponta_para_App_por_nome_e_e_enforced() -> None:
    """⚠️ Read before declaring: `enforced` is what authorises the wizard picker.

    Fatia 1 measured that on `CopilotBlueprint.nome` and did NOT declare the
    relation, because there the human TYPES the name of a copilot the screen is
    about to create, and a picker would offer the thing that does not exist yet.

    Here the reading inverts on the same test: nothing in this path creates an
    `App` — it is a portal record made elsewhere, and a Solution only says
    which of them its code delivers. So choosing from a list is the honest
    control, and a veto on a dangling pointer is the right veto.

    Asserted on the port rather than on the YAML: the YAML is where somebody
    would write `by: title` believing it changes nothing.
    """
    from dna.kernel import Kernel

    port = Kernel.auto()._kinds[("github.com/ruinosus/dna/v1", "Solution")]
    apps = port.relations["apps"]

    assert apps.to == ("App",)
    assert apps.cardinality == "many"
    assert apps.by == "name"
    assert apps.enforced is True


def test_o_plane_e_record_e_esta_declarado() -> None:
    """`record`, and DECLARED — undeclared is not the same fact as the default.

    Measured rather than chosen: none of the four `COMPOSITION_SIGNALS` is set,
    so `default_plane` (i-123) would answer `record` anyway. Declaring it is
    what keeps a later `prompt_target: true` from flipping the plane silently.
    """
    from dna.kernel.kinds.base import COMPOSITION_SIGNALS, default_plane
    from dna._yaml import safe_load

    descriptor = safe_load(
        (
            REPO_ROOT
            / "packages/sdk-py/dna/extensions/helix/kinds/solution.kind.yaml"
        ).read_text(encoding="utf-8")
    )
    spec = descriptor["spec"]

    assert spec["plane"] == "record"
    assert not any(spec.get(key) for key in COMPOSITION_SIGNALS.values())
    assert default_plane(spec) == "record"


def test_o_kind_nao_e_tenanted_porque_a_porta_que_grava_nao_tem_tenant() -> None:
    """⚠️ Measured, not preferred.

    `WritePipeline` refuses a TENANTED kind when no tenant is effective, and
    `dna solution` runs on a user's machine against a local `.dna` with no
    tenant at all — `tenanted` would make the only door that writes this Kind
    unable to. `global` would break the other end (a workspace recording its
    own solution, fatia 6). Permissive is the only value that serves both.
    """
    from dna.kernel import Kernel

    port = Kernel.auto()._kinds[("github.com/ruinosus/dna/v1", "Solution")]
    assert getattr(port, "scope", None) is None


def test_o_schema_nao_exige_nenhuma_resposta_do_template() -> None:
    """A schema that required a gated answer would refuse the rescue case.

    The guide states it as a rule for anyone modelling these answers elsewhere:
    *"a schema must not require a `when:`-gated field, because it legitimately
    disappears"*. `answers` is therefore a free map with no `required`, and
    this asserts the absence — the kind of thing that gets "tidied up" by
    someone adding types for autocomplete.
    """
    from dna.kernel import Kernel

    port = Kernel.auto()._kinds[("github.com/ruinosus/dna/v1", "Solution")]
    layer = port.schema()["properties"]["services"]["items"]
    answers = layer["properties"]["answers"]

    assert answers["type"] == "object"
    assert "required" not in answers
    assert "properties" not in answers, (
        "typing the template's questions here would make this Kind one "
        "particular copier.yml written twice"
    )
    assert "pode_dormir" not in layer["required"]
