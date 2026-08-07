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

    No `copilots`, deliberately — this is the App of a GENERATED SERVICE, and
    a generated service serves no copilot. It is the shape that could not be
    written at all until `copilots` stopped being required.
    """
    apps = tmp_path / "store" / ".dna" / "board" / "apps"
    apps.mkdir(parents=True, exist_ok=True)
    (apps / f"{name}.yaml").write_text(
        yaml.dump(
            {
                "apiVersion": "github.com/ruinosus/dna/v1",
                "kind": "App",
                "metadata": {"name": name},
                "spec": {"title": name, **spec},
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


@pytest.fixture
def template_mudo(tmp_path: Path) -> Path:
    """Um template que NUNCA pergunta o custo.

    ⚠️ É o que sobrou como fonte genuína de "ninguém respondeu" depois que
    `dna solution record` passou a GRAVAR o App (`s-template-dirigido-pelo-app`):
    com o template de referência, a resposta existe sempre — é pergunta dele —
    e o App sai respondido. Plantar um App vazio à mão testaria o leitor contra
    um estado que o gravador não produz mais; este produz.
    """
    other = tmp_path / "template-mudo"
    other.mkdir()
    (other / "copier.yml").write_text(
        '_answers_file: ".copier-answers.{{ service_name }}.yml"\n'
        '_templates_suffix: ".jinja"\n'
        "service_name:\n  type: str\n  default: mudo\n"
    )
    (other / "{{ _copier_conf.answers_file }}.jinja").write_text(
        "{{ _copier_answers|to_nice_yaml -}}\n"
    )
    init_repo(other)
    commit_all(other, "v1")
    git(other, "tag", "v1.0.0")
    return other


def test_o_compromisso_de_custo_e_lido_do_App_de_mesmo_nome(
    runner: CliRunner, template: Path, destination: Path, tmp_path: Path, scope: str
) -> None:
    """A chave entre as duas listas é `services[].name` == `App.metadata.name`.

    Se a função ainda lesse `services[].pode_dormir`, `api` apareceria como não
    respondido (o campo não existe mais) e o teste falharia — que é o que faz
    dele uma medição e não uma formalidade.

    A junção é medida pelo NOME, não pela existência: um `services[]` que
    aponta para um nome sem App cai em "não respondido", e é assim que se prova
    que a leitura casa por nome em vez de devolver a primeira coisa que achar.
    """
    generate(runner, template, destination, service_name="api", can_sleep="false")
    runner.invoke(solution, ["record", str(destination), "--solution", "s"])

    assert solution_kind.unanswered_cost_question(
        solution_spec("s"), scope=scope
    ) == [], "`api` tem App de mesmo nome, e ele respondeu"

    desencontrado = {"services": [{"name": "api-que-nao-existe"}]}
    assert solution_kind.unanswered_cost_question(desencontrado, scope=scope) == [
        "api-que-nao-existe"
    ], "sem App daquele NOME não há resposta — a junção é por nome"


def test_can_sleep_false_e_uma_RESPOSTA_e_ausente_nao_e_false(
    runner: CliRunner, template: Path, template_mudo: Path, destination: Path,
    scope: str,
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
    generate(runner, template, destination, service_name="pago", can_sleep="false")
    generate(runner, template_mudo, destination, service_name="mudo")

    result = runner.invoke(
        solution, ["record", str(destination), "--solution", "s", "--json"]
    )
    unanswered = json.loads(result.output)["unanswered_cost"]

    assert "pago" not in unanswered, "`can_sleep: false` é uma RESPOSTA"
    assert unanswered == ["mudo"], "ausente é `não respondeu`, nunca `false`"


def test_um_servico_cujo_App_nunca_respondeu_nao_presume_o_lado_barato(
    runner: CliRunner, template_mudo: Path, destination: Path, scope: str
) -> None:
    """Um `App` que existe e nunca respondeu cai no lado ALTO.

    A finding fala em TODA execução, como `divergent_answers` e ao contrário de
    `moved_defaults`: uma condição que continua verdadeira tem de continuar
    sendo dita.
    """
    generate(runner, template_mudo, destination, service_name="mudo")

    result = runner.invoke(
        solution, ["record", str(destination), "--solution", "s", "--json"]
    )
    assert json.loads(result.output)["unanswered_cost"] == ["mudo"]

    strict = runner.invoke(
        solution, ["record", str(destination), "--solution", "s", "--strict"]
    )
    assert strict.exit_code == solution_cmd.EXIT_FINDINGS
    assert "US$ 90" in strict.output


def test_gravar_o_App_e_o_que_RESPONDE_a_pergunta_de_custo(
    runner: CliRunner, template: Path, destination: Path, scope: str
) -> None:
    """⭐ O elo que esta fatia acrescenta, medido como elo.

    Antes de `dna solution` gravar o App, um repo gerado ficava com a pergunta
    de custo aberta PARA SEMPRE: o template perguntava, a resposta ficava em
    `answers`, e nada nunca escrevia o compromisso onde a frota o lê. A conta
    ficava respondida no disco e não respondida no registro.

    Este é o teste que ligaria vermelho se alguém removesse a escrita do App
    "porque o descritor já tem os campos".
    """
    generate(runner, template, destination, service_name="api", can_sleep="true")

    result = runner.invoke(
        solution, ["record", str(destination), "--solution", "s", "--json"]
    )

    assert json.loads(result.output)["unanswered_cost"] == [], (
        "o template perguntou e o record gravou o App — a pergunta está "
        "respondida, e nenhum humano teve de reescrever o valor à mão"
    )
    from dna_cli._ctx import open_session

    with open_session(scope) as session:
        assert dict(session.get_doc("App", "api").spec or {})["can_sleep"] is True


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


def test_o_ledger_guarda_a_procedencia_e_nunca_o_custo() -> None:
    """The two halves, and the line between them.

    `services[]` keeps `name` / `answers_file` / `template` / `answers`. The
    cost commitment is NOT written here in any form — not conditionally, not
    "for compatibility". It is `App.can_sleep`, and a `pode_dormir` beside it
    would be the second house `spec-app-e-o-servico` removed: two answers to
    "does this sleep?", free to disagree, with the invoice finding the one that
    did.

    ⚠️ The Copier answer itself is untouched inside `answers` — asserted here,
    because "the cost left services[]" must not be read as "the answer was
    dropped".
    """
    entry = one_layer().to_spec()

    assert entry["name"] == "mcp-ws"
    assert entry["answers_file"] == ".copier-answers.mcp-ws.yml"
    assert entry["template"] == {"src": "/templates/app-container", "ref": "v1.0.0"}
    assert entry["answers"]["can_sleep"] is False, (
        "the template's answer stays verbatim; what ended was its promotion"
    )
    assert "pode_dormir" not in entry
    assert "can_sleep" not in entry, "the commitment is the App's, not the layer's"


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
        answers={"python_module": "api", "port": 8080, "can_sleep": True},
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


def test_uma_resposta_falsa_e_uma_RESPOSTA_e_nao_uma_ausencia() -> None:
    """⚠️ `can_sleep: False` and `port: 0` are falsy, and both are answers.

    A projection written with `if value:` would drop exactly the expensive half
    of the cost question — the ~US$ 90/month half — and the App would come out
    looking as though nobody had been asked. Type-checked, never truth-checked.

    `port: True` is refused for the mirror reason: `isinstance(True, int)` is
    True in Python, so a bool would otherwise be written as a port.
    """
    spec = one_layer(answers={"can_sleep": False, "port": 0}).to_app_spec()
    assert spec["can_sleep"] is False
    assert spec["port"] == 0

    absent = one_layer(answers={}).to_app_spec()
    assert "can_sleep" not in absent and "port" not in absent

    wrong_type = one_layer(answers={"port": True, "can_sleep": "yes"}).to_app_spec()
    assert "port" not in wrong_type, "a bool is not a port"
    assert "can_sleep" not in wrong_type, "a string is not an answer to a bool field"


def test_a_prontidao_do_descritor_e_medida_e_nunca_presumida() -> None:
    """⚠️ Asked of the live descriptor, so it cannot go stale.

    `App` declares `additionalProperties: false`, so a field it does not know is
    a REFUSED write, not a tolerated extra — measured 07/08/2026::

        write vetoed for board/App/api: Additional properties are not allowed
        ('can_sleep', 'port', 'python_module', 'service_name' were unexpected)

    The predicate reads the schema instead of carrying a flag somebody has to
    remember to flip — which is why #351 landing changed the behaviour by
    itself, with this test passing before and after and nobody editing it.

    ⭐ It also asserts the descriptor DOES carry them now, so this cannot decay
    into a tautology: a predicate compared only against itself would agree with
    an empty `APP_SERVICE_FIELDS` just as happily.
    """
    from dna.kernel import Kernel

    port = Kernel.auto()._kinds[("github.com/ruinosus/dna/v1", "App")]
    properties = set((port.schema() or {}).get("properties") or {})
    absent = set(solution_kind.app_kind_absent_fields())

    assert absent == {f for f in solution_kind.APP_SERVICE_FIELDS if f not in properties}
    assert solution_kind.app_is_the_deployment() is not bool(absent)

    # …and the four are really there, so the comparison above is not vacuous.
    assert {"service_name", "python_module", "port", "can_sleep"} <= properties
    assert solution_kind.app_is_the_deployment() is True


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


def test_um_cli_mais_novo_que_o_sdk_DIZ_que_nao_gravou_App(
    runner: CliRunner, template: Path, destination: Path, scope: str, monkeypatch
) -> None:
    """⭐ A bridge announces itself; a fallback goes quiet.

    ⚠️ Not a hypothetical, and not dead code now that #351 landed: `dna-cli`
    and `dna-sdk` are SEPARATE WHEELS with independent floors, so an install
    can carry a CLI that knows these fields and an SDK whose descriptors do
    not. There the App write is refused by schema, and what must not happen is
    that the run looks successful.

    The skew is simulated at the only honest seam — the descriptor probe — so
    this runs on every CI instead of skipping forever on a green descriptor. A
    permanent skip would be a test that stopped measuring the day it started
    mattering.
    """
    monkeypatch.setattr(
        solution_kind, "app_kind_absent_fields", lambda: ("can_sleep", "port")
    )

    generate(runner, template, destination, service_name="api", can_sleep="false")
    result = runner.invoke(
        solution, ["record", str(destination), "--solution", "s", "--json"]
    )
    report = json.loads(result.output)

    assert "can_sleep" in report["app_kind_missing_fields"]
    assert report["unanswered_cost"] == ["api"], (
        "no App was written, so nothing answers the cost question — and that "
        "must read as UNANSWERED, never as an assumed `can_sleep: true`"
    )
    # ⚠️ The provenance is still recorded. An announcement is not permission to
    # drop the run's work on the floor.
    assert layer_of("s", "api")["answers"]["can_sleep"] is False
    assert "apps" not in solution_spec("s"), (
        "`apps` is enforced — naming an App this run could not write would be a "
        "dangling pointer, which the kernel vetoes"
    )

    prose = runner.invoke(solution, ["record", str(destination), "--solution", "s"])
    assert "dna-sdk" in prose.output, "the fix is a version floor — say so"
    assert "can_sleep" in prose.output


@pytest.mark.skipif(
    not solution_kind.app_is_the_deployment(),
    reason="the installed App descriptor cannot hold the service identity "
    "(a dna-cli newer than its dna-sdk)",
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
    # …and the cost question is ANSWERED, which is the whole point of writing
    # the App: before this it read every service as unanswered forever.
    assert solution_kind.unanswered_cost_question(stored, scope=scope) == []


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
    # ⚠️ 07/08/2026, `Spec/spec-campo-opcional-por-evidencia`: `services` saiu
    # do `required` — o dna-cloud nunca foi gerado por template, e o
    # `required` transformava "este repo não tem procedência de render" em
    # "falta um campo". O que este teste sempre mediu continua de pé: a
    # propriedade tem de EXISTIR, porque `upsert_solution` grava nela sob
    # `additionalProperties: false`. Opcional foi o que a evidência comprou;
    # REMOVER a propriedade segue quebrando `dna solution` inteiro.
    assert "services" in port.schema()["properties"]
    assert port.schema()["required"] == ["title"]
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
