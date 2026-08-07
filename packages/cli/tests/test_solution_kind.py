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


def write_app(tmp_path: Path, name: str, **spec) -> None:
    """Put a real `App` instance in the scope the `scope` fixture set up.

    Written as the file the filesystem source reads, because the point is that
    `unanswered_cost_question` goes and LOOKS: a stubbed kernel would prove it
    calls something rather than that it reads the App.
    """
    apps = tmp_path / "store" / ".dna" / "board" / "apps"
    apps.mkdir(parents=True, exist_ok=True)
    (apps / f"{name}.yaml").write_text(
        yaml.dump(
            {
                "apiVersion": "github.com/ruinosus/dna/v1",
                "kind": "App",
                "metadata": {"name": name},
                "spec": {"title": name, "copilots": ["c"], **spec},
            }
        )
    )


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


# ── the cost question: asked here, ANSWERED on the App ───────────────────────
#
# `spec-app-e-o-servico` (07/08/2026) moved the commitment out of
# `services[].pode_dormir` and onto `App.can_sleep`. The reason is granularity:
# an entry in `services[]` is one per DEPLOYMENT, and an `App` now IS the
# deployment — nine services are nine entries and nine Apps. One fact in two
# places is two names for one fact. What could NOT move is the semantics, and
# that is what these tests pin: absent means NOBODY ANSWERED, and absent is
# never `False`.


def test_a_resposta_do_template_fica_em_answers_e_nao_vira_campo(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """A procedência do render permanece; a PROMOÇÃO dela a campo acabou.

    Se a resposta do Copier tivesse sido descartada junto com o campo, o
    registro teria perdido informação numa mudança que era para não perder
    nenhuma — e é isso que a primeira asserção mede.
    """
    generate(runner, template, destination, service_name="api", can_sleep="false")
    runner.invoke(solution, ["record", str(destination), "--solution", "s"])

    layer = layer_of("s", "api")
    assert layer["answers"]["can_sleep"] is False, (
        "a resposta do template é a procedência do render e continua gravada"
    )
    assert "pode_dormir" not in layer


def test_o_compromisso_de_custo_e_lido_do_App_de_mesmo_nome(
    runner: CliRunner, template: Path, destination: Path, tmp_path: Path, scope: str
) -> None:
    """A chave entre as duas listas é `services[].name` == `App.metadata.name`.

    `api` tem App que respondeu, `worker` tem App que não respondeu. Se a
    função ainda lesse `services[].pode_dormir`, `api` apareceria como não
    respondido (o campo não existe mais) e o teste falharia — que é o que faz
    dele uma medição e não uma formalidade.
    """
    generate(runner, template, destination, service_name="api", can_sleep="false")
    generate(runner, template, destination, service_name="worker", can_sleep="true")
    write_app(tmp_path, "api", can_sleep=False)
    write_app(tmp_path, "worker")  # existe, mas nunca respondeu

    result = runner.invoke(
        solution, ["record", str(destination), "--solution", "s", "--json"]
    )
    assert json.loads(result.output)["unanswered_cost"] == ["worker"]


def test_can_sleep_false_e_uma_RESPOSTA_e_ausente_nao_e_false(
    runner: CliRunner, template: Path, destination: Path, tmp_path: Path, scope: str
) -> None:
    """⚠️ A asserção que a mudança de casa tinha de preservar, nos dois sentidos.

    `False` é a resposta CARA — uma réplica fixa, ~US$ 90/mês, para sempre — e
    reportá-la como "não respondida" seria gritar lobo até ninguém ouvir mais.
    Ausente é o oposto: ninguém foi perguntado, e presumir o lado barato é
    exatamente como essa réplica entra na frota sem decisão.

    Um teste que só checasse `unanswered == []` para `False` passaria com a
    função devolvendo `[]` sempre; por isso os dois casos são medidos no MESMO
    run, e a lista tem de conter um e não o outro.
    """
    generate(runner, template, destination, service_name="pago")
    generate(runner, template, destination, service_name="mudo")
    write_app(tmp_path, "pago", can_sleep=False)   # respondeu, e é o caro
    # "mudo" não tem App nenhum

    result = runner.invoke(
        solution, ["record", str(destination), "--solution", "s", "--json"]
    )
    unanswered = json.loads(result.output)["unanswered_cost"]

    assert "pago" not in unanswered, "`can_sleep: false` é uma RESPOSTA"
    assert unanswered == ["mudo"], "ausente é `não respondeu`, nunca `false`"


def test_um_servico_sem_App_nao_presume_o_lado_barato(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """Nenhum `App` declarado é o terceiro estado, e ele cai no lado ALTO.

    A finding fala em TODA execução, como `divergent_answers` e ao contrário de
    `moved_defaults`: uma condição que continua verdadeira tem de continuar
    sendo dita.
    """
    generate(runner, template, destination, service_name="api")

    result = runner.invoke(
        solution, ["record", str(destination), "--solution", "s", "--json"]
    )
    assert json.loads(result.output)["unanswered_cost"] == ["api"]

    strict = runner.invoke(
        solution, ["record", str(destination), "--solution", "s", "--strict"]
    )
    assert strict.exit_code == solution_cmd.EXIT_FINDINGS
    assert "US$ 90" in strict.output


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


# ── the relation to App ──────────────────────────────────────────────────────


def test_apps_e_uma_relacao_declarada_e_vazio_e_o_caso_comum(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """`apps` is optional, because the first real solution has none.

    Measured in the spec (§6-B): *"o dna-cloud gera 9 serviços e nenhum App"*.
    A `required: [apps]` would be an obligation the first example already
    violates.
    """
    generate(runner, template, destination, service_name="api")
    result = runner.invoke(solution, ["record", str(destination), "--solution", "s"])

    assert result.exit_code == 0, result.output
    assert "apps" not in solution_spec("s")


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
    # ⚠️ E o compromisso de custo não mora mais aqui de forma nenhuma: nem
    # como campo, nem como exigência. A casa dele é `App.can_sleep`, e este
    # `additionalProperties: false` é o que garante que ele não volte de
    # fininho por uma gravação antiga.
    assert "pode_dormir" not in layer["properties"]
    assert layer["additionalProperties"] is False


def test_o_que_upsert_grava_continua_cabendo_no_schema_da_Solution() -> None:
    """A trava do AC 2 de `Story/s-kinds-a-conta-declarada`, no lugar onde ela
    é decidida — o CONSUMIDOR.

    `Spec/spec-app-e-o-servico` pede que `services[]` deixe de existir como
    campo, com o argumento de que `Solution` tem 0 instâncias e portanto mexer
    nele custa zero. A contagem está certa; a conclusão não segue dela, e este
    teste é a medição:

    * o schema é `additionalProperties: false` com `required: [title,
      services]`, então remover a propriedade não a torna opcional — torna
      TODA gravação de `Solution` inválida;
    * `upsert_solution` escreve `spec["services"]` em todo caminho, e é o
      único caminho por onde `dna solution new` / `update` gravam.

    Logo `dna solution` inteiro para de funcionar no commit que remove o campo,
    e este teste é o que diz isso em voz alta em vez de deixar o CI descobrir
    de lado. O founder reescreveu o AC com esta medição na tela: a remoção
    total está cancelada, e o que saiu foi `pode_dormir` — um campo, não a
    lista. As respostas do Copier não têm outra casa.
    """
    import jsonschema
    from dna.kernel import Kernel

    port = Kernel.auto()._kinds[("github.com/ruinosus/dna/v1", "Solution")]
    layer = solution_kind.Layer(
        name="mcp",
        answers_file=".copier-answers.mcp.yml",
        template_src="gh:ruinosus/dna",
        template_ref="v0.74.0",
        answers={"identity": "workos", "graph_obo": True},
    )
    spec = {"title": "dna-cloud", "services": [layer.to_spec()]}

    jsonschema.validate(spec, port.schema())
    assert "services" in port.schema()["required"]
    assert port.schema()["additionalProperties"] is False
    # e o que o registro guarda e o `App` não tem onde guardar:
    assert set(layer.to_spec()) >= {"answers", "answers_file", "template"}


def test_a_relacao_com_App_nao_e_declaravel_de_dentro_de_services() -> None:
    """⛔ Por que `services[].name` NÃO virou relação declarada — medido.

    O founder pediu que virasse, usando `by:`. `by:` não serve, e a razão é
    estrutural: ele diz onde o valor CASA NO ALVO, nunca onde ele é LIDO NA
    ORIGEM — `relation_values` faz `spec.get(<nome da relação>)`, primeiro
    nível, sempre. `kind_graph` já nomeia a limitação
    (`top_level_properties_only`).

    O que este teste mede é a FORMA DO DEFEITO, que é o que torna a recusa
    obrigatória em vez de opcional: a declaração passaria no lint, se
    anunciaria como imposta, e leria zero. Uma guarda verde que não guarda
    nada é o pior dos dois mundos, e é o que aconteceria se alguém "arrumasse"
    isto no futuro.
    """
    from dna.kernel.kinds.relations import (
        normalize_relations,
        relation_values,
        schema_contradictions,
    )

    rels = normalize_relations({"services": {"to": "App", "cardinality": "many"}})
    schema = {
        "type": "object",
        "properties": {
            "services": {
                "type": "array",
                "items": {"type": "object",
                          "properties": {"name": {"type": "string"}}},
            }
        },
    }
    spec = {"services": [{"name": "mcp"}, {"name": "mcp-entra"}]}

    assert schema_contradictions(rels, schema) == [], "o lint passaria VERDE"
    assert rels["services"].resolved and rels["services"].enforced, (
        "e ela se anunciaria como resolvida E imposta"
    )
    assert relation_values(rels["services"], spec) == [], (
        "…lendo ZERO valores: nenhuma aresta, nenhum veto, em silêncio"
    )

    # A que FUNCIONA é `apps[]`, de primeiro nível — e é a declarada.
    apps = normalize_relations({"apps": {"to": "App", "cardinality": "many"}})
    assert relation_values(apps["apps"], {"apps": ["mcp", "mcp-entra"]}) == [
        "mcp", "mcp-entra",
    ]
