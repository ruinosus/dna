"""``dna solution new|update`` — driven against REAL Copier and REAL git repos.

Nothing here is faked. A scaffolder proven against a stub proves that the stub
behaves as imagined, and every finding this command reports exists because
Copier's ACTUAL behaviour was measured and found surprising. The tests
therefore render real trees, evolve real templates, tag real commits and read
the answers files back off disk.

The guards are written to the granularity of the defect, and the defects are
the four traps an adversarial experiment measured before a line of this was
written:

1. **An `update` does not move a version floor, and says nothing.** Copier
   keeps a recorded answer forever; a template that bumps its default reaches
   nobody. ``test_o_piso_que_nao_se_moveu_e_reportado`` is the loud tier and
   ``test_o_piso_continua_visivel_depois_que_o_commit_avancou`` is the quiet
   one — the second exists because the first CANNOT fire twice, and an answer
   left behind by update N is invisible to update N+1 by construction. That
   hole was found by running the command, not by reading it.
2. **A `when:`-gated answer is erased in silence.** ``true`` → *(absent)* →
   ``false`` in one round trip. ``test_a_resposta_gated_perdida_e_nomeada``.
3. **A per-instance answers file breaks `copier update` with a bare
   `TypeError`.** ``test_dois_answers_files_recusam_sem_escolha`` and
   ``test_type_error_do_copier_vira_recusa_legivel``.
4. **A template with no tags updates a fleet anyway**, under a synthesised
   pseudo-version. ``test_template_sem_tag_recusa_o_update``.

⭐ THE MUTANT this file exists for is
``test_toda_resposta_gravada_e_repassada_ao_copier``. It captures the ``data``
dict at the seam and asserts every recorded answer is in it. Delete
``{**before, ...}`` from ``update`` and it goes red — and it is the only thing
that would, which is exactly why it is written as a SEAM guard and labelled as
one: measured against copier 9.17, re-passing recorded answers is behaviourally
indistinguishable from not passing them, because Copier's own memory already
keeps them. Asserting on rendered output would therefore have been a test that
passes for the wrong reason. What the seam buys is that the answer set becomes
this command's to state — which is what makes the report above trustworthy, and
what a recorded ``Solution`` will fill from the other side.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from dna_cli import solution_cmd
from dna_cli.solution_cmd import solution

copier = pytest.importorskip("copier", reason="needs dna-cli[scaffold]")

REPO_ROOT = Path(__file__).resolve().parents[3]
REFERENCE_TEMPLATE = REPO_ROOT / "templates" / "app-container"

# ⚠️ The code files carry a CONDITIONAL path segment (`{% if owns_code %}…`),
# which is how one directory serves N services without regenerating anybody's
# source — Copier skips a file or directory whose rendered name is empty
# (measured against 9.17). Named here rather than spelled at four call sites so
# the next rename is one edit.
SERVER_SKELETON = (
    "apps/{{ service_name }}/{% if owns_code %}src{% endif %}"
    "/{{ python_module }}/server.py.jinja"
)


# ── helpers ──────────────────────────────────────────────────────────────────


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    ).stdout


def commit_all(repo: Path, message: str) -> None:
    git(repo, "add", "-A")
    git(
        repo,
        "-c",
        "user.email=t@example.com",
        "-c",
        "user.name=t",
        "commit",
        "-qm",
        message,
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
    """A git-tracked, TAGGED copy of the repo's reference template at v1.0.0."""
    dst = tmp_path / "template"
    subprocess.run(["cp", "-R", str(REFERENCE_TEMPLATE), str(dst)], check=True)
    init_repo(dst)
    commit_all(dst, "v1")
    git(dst, "tag", "v1.0.0")
    return dst


@pytest.fixture
def destination(tmp_path: Path) -> Path:
    return init_repo(tmp_path / "repo")


def bump_template(template: Path, *, tag: str, **edits: str) -> None:
    """Evolve the template: rewrite `copier.yml` fragments, then tag."""
    text = (template / "copier.yml").read_text()
    for old, new in edits.items():
        replacement = new
        old_text = old.replace("__", " ")
        assert old_text in text, f"fragment not in copier.yml: {old_text!r}"
        text = text.replace(old_text, replacement)
    (template / "copier.yml").write_text(text)
    commit_all(template, tag)
    git(template, "tag", tag)


def generate(runner: CliRunner, template: Path, destination: Path, **answers: object):
    args = ["new", str(template), str(destination), "--defaults"]
    for key, value in answers.items():
        args += ["--data", f"{key}={value}"]
    result = runner.invoke(solution, args)
    assert result.exit_code == 0, result.output
    return result


def answers_of(destination: Path, service: str) -> dict:
    return yaml.safe_load((destination / f".copier-answers.{service}.yml").read_text())


# ── the extra is optional, and stays optional ────────────────────────────────


def test_base_import_never_pulls_copier() -> None:
    """Importing the CLI must not import Copier.

    The whole point of `dna-cli[scaffold]` being an extra is that the base
    install — every `dna sdlc` invocation, every container that only serves MCP
    — does not carry jinja2, pydantic, plumbum, dunamai and questionary. An
    eager `import copier` at module scope would make the extra a lie while
    every test still passed, because the test environment installs it.
    """
    source = (Path(solution_cmd.__file__)).read_text()
    module_level = [
        line
        for line in source.splitlines()
        if line.startswith("import copier") or line.startswith("from copier")
    ]
    assert module_level == [], (
        "copier must be imported inside a function, never at module scope: "
        f"{module_level}"
    )


def test_copier_private_surface_we_depend_on_still_exists() -> None:
    """The private attributes `solution_cmd` reads, asserted by name.

    `copier._template.Template` is private API. It is used for READING only —
    the resolved version, whether the template has tags, and the questions'
    declared defaults at a given ref — because Copier publishes no public
    equivalent and the alternative is re-deriving template resolution by hand.

    This guard is what makes that dependency honest rather than hidden: a
    Copier release that renames any of these fails here, in CI, instead of
    failing a user mid-scaffold. It is paired with the `<10` ceiling in
    `pyproject.toml`; neither is decoration.
    """
    template_cls = solution_cmd._copier_template_class()
    for attribute in ("version", "commit", "vcs", "local_abspath", "questions_data",
                      "config_data", "tasks", "jinja_extensions", "_cleanup"):
        assert hasattr(template_cls, attribute), (
            f"copier._template.Template lost `{attribute}` — `dna solution` reads it. "
            "Re-check the private surface before raising the ceiling."
        )


# ── new: the shape the design is about ───────────────────────────────────────


def test_new_renders_an_app_and_records_the_answers(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    generate(runner, template, destination, service_name="api", identity="workos")

    assert (destination / "apps/api/pyproject.toml").is_file()
    assert (destination / "apps/api/wiring/containerapp.bicep").is_file()
    recorded = answers_of(destination, "api")
    assert recorded["service_name"] == "api"
    assert recorded["_commit"] == "v1.0.0"
    assert recorded["_src_path"] == str(template)


def test_o_mesmo_template_sobreposto_duas_vezes_da_dois_apps_independentes(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """One template, N apps, N answers files — the whole architecture in one test.

    This is the property that makes "nine services over four images" fit the
    tool at all: a second app is another LAYER, not a regeneration, and each
    layer updates alone. If the answers file were not per-instance, the second
    `new` would overwrite the first's record and the first app would become
    un-updatable — silently, since its files would still be there.
    """
    generate(runner, template, destination, service_name="api", identity="workos")
    generate(runner, template, destination, service_name="mcp", identity="entra")

    assert sorted(p.name for p in destination.glob(".copier-answers*")) == [
        ".copier-answers.api.yml",
        ".copier-answers.mcp.yml",
    ]
    assert answers_of(destination, "api")["identity"] == "workos"
    assert answers_of(destination, "mcp")["identity"] == "entra"
    assert (destination / "apps/api/Dockerfile").is_file()
    assert (destination / "apps/mcp/Dockerfile").is_file()


def test_new_nomeia_os_dois_lugares_que_nenhum_template_alcanca(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """The closing note, asserted by content and not by presence.

    Wiring a new app touches seven places; a Copier template renders files, so
    two of them — a block inside `azure.yaml` and the module invocation in the
    root bicep — are mechanically out of reach. A scaffolder that generated
    five sevenths of the wiring and implied seven would be worse than one that
    generated nothing, because the operator would stop checking.
    """
    result = generate(runner, template, destination, service_name="api")

    assert "azure.yaml" in result.output
    assert "bicep" in result.output
    assert "guard" in result.output.lower()


def test_new_recusa_sem_defaults_e_sem_terminal(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """No prompting is possible off a terminal, so say so instead of hanging."""
    result = runner.invoke(solution, ["new", str(template), str(destination)])

    assert result.exit_code == solution_cmd.EXIT_REFUSED
    assert "--defaults" in result.output


# ── ⭐ `can_sleep`: the cost gate, from the answer to the bicep to the screen ──


def bicep_of(destination: Path, service: str) -> str:
    return (destination / f"apps/{service}/wiring/containerapp.bicep").read_text()


def test_can_sleep_false_chega_ao_bicep_como_min_replicas_1(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """⭐ The assertion the whole story is about, made on the RENDERED file.

    `can_sleep` is the one answer that is not a render detail: `false` means a
    fixed replica, and a fixed replica is ~US$ 90/month for as long as the app
    exists. Asserting it on the copier.yml — "the question is declared" — would
    have proven the question exists, which is not the same claim as the number
    reaching the resource that bills.

    Both sides, in one test, because the mutant is the interesting half: with
    only the `false` case frozen, a template that hardcoded `minReplicas: 1`
    would be green and would put every generated app on a permanent replica.
    """
    generate(runner, template, destination, service_name="worker", can_sleep="false")
    generate(runner, template, destination, service_name="sleepy", can_sleep="true")

    assert "minReplicas: 1" in bicep_of(destination, "worker")
    assert "minReplicas: 0" in bicep_of(destination, "sleepy")


def test_a_geracao_imprime_o_custo_quando_o_app_nao_dorme(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """⭐ The dna-cloud gate says: ask "can it sleep?" WITH THE NUMBER ON SCREEN.

    Generation is the moment that question is actually being answered, so this
    is where the number goes. Before this, the answer existed in the tree and
    the price existed in a CLAUDE.md, and nothing put the two in the same place
    at the same time.
    """
    result = generate(
        runner, template, destination, service_name="worker", can_sleep="false"
    )

    assert "COST" in result.output
    assert "worker" in result.output
    assert "US$ 90" in result.output
    assert "minReplicas: 1" in result.output
    assert "94.43" in result.output, "the measured invoice line, not a round guess"


def test_um_app_que_dorme_nao_paga_o_aviso(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """The other half: a warning that fires always is a warning nobody reads."""
    result = generate(
        runner, template, destination, service_name="api", can_sleep="true"
    )

    assert "COST" not in result.output
    assert "US$ 90" not in result.output


def test_o_custo_aparece_sem_registro_nenhum(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """No `--solution`, no scope, no `.dna` — and the number still appears.

    `dna solution` runs against somebody else's repo, where there is no kernel
    to talk to. Making the cost line depend on a recorded `Solution` would have
    hidden it in exactly the case where the person generating has least context
    about this house's bill.
    """
    result = runner.invoke(
        solution,
        ["new", str(template), str(destination), "--defaults",
         "--data", "service_name=worker", "--data", "can_sleep=false", "--json"],
    )
    report = json.loads(result.output)

    assert report["solution"] is None
    assert report["no_sleep"] == ["worker"]


def test_uma_camada_muda_de_ideia_e_o_update_diz(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """The cost is re-stated by `update`, not only by `new`.

    An app that starts sleeping and stops is the same ~US$ 90 decision, taken
    later and more quietly — the update is the only place that can say so.
    """
    generate(runner, template, destination, service_name="worker", can_sleep="true")
    commit_all(destination, "generated")

    result = runner.invoke(
        solution,
        ["update", str(destination), "--service", "worker",
         "--data", "can_sleep=false"],
    )

    assert result.exit_code == 0, result.output
    assert "COST" in result.output
    assert "minReplicas: 1" in bicep_of(destination, "worker")


def test_uma_resposta_de_custo_ausente_nao_vira_custo(
    runner: CliRunner, tmp_path: Path
) -> None:
    """⚠️ Absent is not `false`, and it is not `true` either.

    A template that never asks the question produces no cost line — presuming
    the expensive side would cry wolf on every unrelated template, and
    presuming the cheap side is the failure the field exists to prevent. The
    absence is reported by `unanswered_cost`, which is a different sentence.
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

    result = CliRunner().invoke(
        solution, ["new", str(silent), str(tree), "--defaults", "--json"]
    )

    assert json.loads(result.output)["no_sleep"] == []


# ── ⭐ 1 code directory : N services ──────────────────────────────────────────


def code_fingerprint(destination: Path, service: str) -> dict[str, str]:
    """Every non-wiring file under `apps/<service>/`, by content."""
    root = destination / "apps" / service
    return {
        str(p.relative_to(root)): p.read_text(encoding="utf-8")
        for p in sorted(root.rglob("*"))
        if p.is_file() and "wiring" not in p.relative_to(root).parts
    }


def test_um_segundo_servico_sobre_a_mesma_imagem_gera_so_a_fiacao(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """⭐ Measured in dna-cloud, 07/08/2026: NINE services over FOUR directories.

        apps/mcp/  →  mcp, mcp-entra, mcp-ws     (one image, three doors)

    So EIGHT of the nine services are another deployment of an image that
    already exists, and for those, generating `Dockerfile`/`src`/`tests` would
    OVERWRITE PRODUCTION CODE because somebody declared a new door. This is the
    test that says it does not: the owner's tree is compared byte for byte
    across the second generation, and what the second run leaves behind is
    exactly the three wiring fragments.

    Asserted on CONTENT, not on mtime or on "the command exited 0": a rewrite
    that produced identical bytes did not damage anything, and one that produced
    different bytes is the defect, whatever the exit code said.
    """
    generate(runner, template, destination, service_name="mcp", identity="workos")
    before = code_fingerprint(destination, "mcp")
    assert "Dockerfile" in before, "precondition: the owner really did get code"

    result = runner.invoke(
        solution,
        ["new", str(template), str(destination), "--defaults",
         "--data", "service_name=mcp-ws", "--data", "image_name=mcp",
         "--data", "owns_code=false", "--data", "identity=workos"],
    )
    assert result.exit_code == 0, result.output

    assert code_fingerprint(destination, "mcp") == before, (
        "declaring a second door over the mcp image rewrote the mcp image's code"
    )
    assert sorted(p.name for p in (destination / "apps/mcp-ws").rglob("*") if p.is_file()) == [
        "azure.service.yaml",
        "compose.fragment.yml",
        "containerapp.bicep",
    ]
    assert not (destination / "apps/mcp-ws/Dockerfile").exists()
    assert not (destination / "apps/mcp-ws/src").exists()


def test_a_fiacao_do_segundo_servico_aponta_para_a_imagem_do_primeiro(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """Wiring-only is useless if the wiring points at an empty directory.

    `apps/mcp-ws/` holds no Dockerfile, so a fragment that said `build:
    ./apps/mcp-ws` would be a file that renders, passes every file-set
    assertion, and fails at `docker compose build` — the shape of failure this
    template exists to remove.
    """
    generate(runner, template, destination, service_name="mcp")
    generate(
        runner, template, destination,
        service_name="mcp-ws", image_name="mcp", owns_code="false",
    )

    compose = (destination / "apps/mcp-ws/wiring/compose.fragment.yml").read_text()
    azure = (destination / "apps/mcp-ws/wiring/azure.service.yaml").read_text()

    assert "context: ./apps/mcp\n" in compose
    assert "project: ./apps/mcp\n" in azure
    assert "mcp-ws:" in compose, "the SERVICE is still mcp-ws — only the code is shared"


def test_port_e_can_sleep_sao_do_servico_e_nunca_da_imagem(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """⭐ Two doors over one image may disagree about both, and often do.

    `port` and `can_sleep` are `App` fields, and an App is a service — so the
    answers file that carries them is per service. A template that derived them
    from the image would give the whole fleet one sleep answer, which is exactly
    how a fixed replica gets into the bill without anybody choosing it.
    """
    generate(runner, template, destination, service_name="mcp", port="8080",
             can_sleep="true")
    generate(
        runner, template, destination,
        service_name="mcp-ws", image_name="mcp", owns_code="false",
        port="8001", can_sleep="false",
    )

    assert "targetPort: 8080" in bicep_of(destination, "mcp")
    assert "minReplicas: 0" in bicep_of(destination, "mcp")
    assert "targetPort: 8001" in bicep_of(destination, "mcp-ws")
    assert "minReplicas: 1" in bicep_of(destination, "mcp-ws")


def test_owns_code_false_sem_outra_imagem_para_apontar_e_recusado(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """`owns_code: false` means "somebody else has the code" — so name them.

    Left unchecked, `owns_code=false` with the default `image_name` renders a
    fragment whose build context is its own empty directory: a tree that looks
    complete and cannot build. The validator turns that into a refusal at the
    only moment it is cheap to fix.
    """
    result = runner.invoke(
        solution,
        ["new", str(template), str(destination), "--defaults",
         "--data", "service_name=mcp-ws", "--data", "owns_code=false"],
    )

    assert result.exit_code == solution_cmd.EXIT_REFUSED
    assert "image_name" in result.output
    assert not (destination / "apps").exists()


def test_um_validator_do_template_vira_recusa_legivel(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """⚠️ Copier raises a PLAIN `ValueError` for a `validator:` — not a CopierError.

    Measured while adding `owns_code`, and true of `service_name`'s validator
    since the day it was written: the failure arrived as a bare traceback with
    neither the command nor the answer name near the top, and `CliRunner` shows
    it as EMPTY output. Driven through a real validator rather than asserted
    against the prefix constant, so a Copier release that rewords the message
    fails here instead of silently restoring the traceback.
    """
    result = runner.invoke(
        solution,
        ["new", str(template), str(destination), "--defaults",
         "--data", "service_name=Not A Service"],
    )

    assert result.exit_code == solution_cmd.EXIT_REFUSED
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "service_name" in result.output
    assert "Traceback" not in result.output


def test_os_tres_fragmentos_de_fiacao_saem_nos_dois_casos(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """The three wiring files are the point of the template, in both shapes.

    ⚠️ And they are only THREE of the seven places a service needs. The other
    two remain unreachable by any template (`azure.yaml`, the root bicep
    invocation) — this test asserts what is emitted, never that a service is
    wired. The guard in the consuming repo is what asserts arrival; see
    `_echo_unreachable_note`.
    """
    fragments = ["compose.fragment.yml", "azure.service.yaml", "containerapp.bicep"]
    generate(runner, template, destination, service_name="mcp")
    generate(
        runner, template, destination,
        service_name="mcp-ws", image_name="mcp", owns_code="false",
    )

    for service in ("mcp", "mcp-ws"):
        for name in fragments:
            assert (destination / f"apps/{service}/wiring/{name}").is_file(), (
                f"apps/{service}/wiring/{name} was not emitted"
            )


# ── the question names ARE the App's field names ─────────────────────────────


def test_as_perguntas_do_template_sao_os_campos_do_App() -> None:
    """⭐ One vocabulary, asserted against the template rather than remembered.

    `App` IS the service (`Spec/spec-app-e-o-servico`), so the answers that
    describe the service are spelled exactly as the descriptor spells them. The
    old name `container_port` is asserted GONE, not merely "port is present":
    with both accepted, a tree would render from one and a record would be
    written from the other, and the two would agree only by luck.
    """
    from dna._yaml import safe_load

    questions = safe_load((REFERENCE_TEMPLATE / "copier.yml").read_text())

    for field in ("service_name", "python_module", "port", "can_sleep"):
        assert field in questions, f"the App declares `{field}`; the template must ask it"
    assert "container_port" not in questions, (
        "`container_port` was renamed to `port` to match the App field. Two "
        "spellings of one fact is how a record and a tree drift apart."
    )


# ── trap 4: `_tasks` and the door with no handle ─────────────────────────────


def test_template_com_tasks_e_recusado_sem_flag_de_escape(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """Exit 4, no `--trust`, and nothing written.

    Two independent reasons, either sufficient: `_tasks` is arbitrary code from
    a template author running on this machine, and it is unreliable even when
    benign (three executions per update, two of them in temp directories with
    no git repo). The refusal happens BEFORE anything is rendered, so a refused
    template does not leave a half-built tree behind.
    """
    config = template / "copier.yml"
    config.write_text(config.read_text() + '\n_tasks:\n  - "echo pwned > /tmp/pwned"\n')
    commit_all(template, "tasks")
    git(template, "tag", "v1.1.0")

    result = runner.invoke(
        solution, ["new", str(template), str(destination), "--defaults"]
    )

    assert result.exit_code == solution_cmd.EXIT_UNSAFE_TEMPLATE
    assert "_tasks" in result.output
    assert "--trust" in result.output  # named only to say it does not exist
    assert not (destination / "apps").exists()


def test_a_recusa_de_tasks_nao_e_contornavel_por_nenhuma_opcao() -> None:
    """No option on either command opens the unsafe door.

    Derived from the parameter list rather than asserted as prose: a future
    `--trust`, `--unsafe` or `--UNSAFE` added for convenience fails here, which
    is the only place that would notice.
    """
    for command in (solution.commands["new"], solution.commands["update"]):
        names = {
            opt
            for param in command.params
            for opt in getattr(param, "opts", [])
        }
        assert not (names & {"--trust", "--unsafe", "--UNSAFE"}), (
            f"`dna solution {command.name}` grew an escape hatch: {names}"
        )


# ── trap 3: the per-instance answers file ────────────────────────────────────


def test_dois_answers_files_recusam_sem_escolha(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """Never guess between apps — a wrong guess updates the wrong one."""
    generate(runner, template, destination, service_name="api")
    generate(runner, template, destination, service_name="mcp")
    commit_all(destination, "generated")

    result = runner.invoke(solution, ["update", str(destination)])

    assert result.exit_code == solution_cmd.EXIT_REFUSED
    assert ".copier-answers.api.yml" in result.output
    assert ".copier-answers.mcp.yml" in result.output
    assert "--service" in result.output


def test_type_error_do_copier_vira_recusa_legivel() -> None:
    """`TypeError: Template not found` is translated, not relayed.

    Discovery upstream should make it unreachable. It is translated anyway:
    "should be unreachable" is precisely how a bare traceback reaches a user,
    and this one names neither the answers file nor the fix.
    """
    translated = solution_cmd._translate(TypeError("Template not found"), Path("/tmp"))

    assert isinstance(translated, solution_cmd.SolutionError)
    assert "--service" in translated.message
    assert "Traceback" not in translated.message


def test_uma_arvore_sem_answers_file_recusa_dizendo_por_que(
    runner: CliRunner, destination: Path
) -> None:
    result = runner.invoke(solution, ["update", str(destination)])

    assert result.exit_code == solution_cmd.EXIT_REFUSED
    assert "never updated" in result.output


def test_um_destino_sem_git_recusa_antes_de_tentar(
    runner: CliRunner, tmp_path: Path
) -> None:
    """`update` is a three-way merge; with no history there is nothing to merge."""
    plain = tmp_path / "plain"
    plain.mkdir()

    result = runner.invoke(solution, ["update", str(plain)])

    assert result.exit_code == solution_cmd.EXIT_REFUSED
    assert "git" in result.output


# ── trap 4: the untagged template ────────────────────────────────────────────


def test_template_sem_tag_recusa_o_update(
    runner: CliRunner, tmp_path: Path, destination: Path
) -> None:
    """The measured precondition is *git*, not *a tag* — so this refusal is ours.

    Copier synthesises `0.0.0.post1.dev0+<hash>` and proceeds, exit 0. Rolling
    a whole fleet forward to a HEAD nobody named is not a release, and the
    failure mode is that afterwards no one can say what version anything is on.
    """
    untagged = tmp_path / "untagged"
    subprocess.run(["cp", "-R", str(REFERENCE_TEMPLATE), str(untagged)], check=True)
    init_repo(untagged)
    commit_all(untagged, "no tags here")

    generate(runner, untagged, destination, service_name="api")
    commit_all(destination, "generated")

    refused = runner.invoke(solution, ["update", str(destination), "--service", "api"])
    assert refused.exit_code == solution_cmd.EXIT_REFUSED
    assert "tag" in refused.output

    allowed = runner.invoke(
        solution,
        ["update", str(destination), "--service", "api", "--allow-untagged"],
    )
    assert allowed.exit_code == 0, allowed.output


def test_template_sem_tag_apenas_avisa_no_new(
    runner: CliRunner, tmp_path: Path, destination: Path
) -> None:
    """`new` warns and proceeds: there is no fleet to roll forward yet.

    The asymmetry is deliberate. Generating from an untagged template costs
    nothing that is not immediately visible; updating from one costs the
    ability to name what the fleet is running.
    """
    untagged = tmp_path / "untagged"
    subprocess.run(["cp", "-R", str(REFERENCE_TEMPLATE), str(untagged)], check=True)
    init_repo(untagged)
    commit_all(untagged, "no tags here")

    result = runner.invoke(
        solution, ["new", str(untagged), str(destination), "--defaults"]
    )

    assert result.exit_code == 0, result.output
    assert "NO git tags" in result.output


# ── trap 1: the floor that does not move, and does not say so ────────────────


def test_um_update_sem_data_realmente_nao_move_o_piso(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """The measurement this whole design rests on, re-measured here.

    Not a test of our code — a test of Copier's, pinned. If a future Copier
    started taking the new default, the loud report would become a lie and this
    test is what would say so first.
    """
    generate(runner, template, destination, service_name="api")
    commit_all(destination, "generated")
    bump_template(template, tag="v2.0.0", **{'default:__"0.74"': 'default: "0.75"'})

    result = runner.invoke(solution, ["update", str(destination), "--service", "api"])

    assert result.exit_code == 0, result.output
    assert answers_of(destination, "api")["dna_floor"] == "0.74"
    assert '>=0.74,<0.75' in (destination / "apps/api/pyproject.toml").read_text()


def test_o_piso_que_nao_se_moveu_e_reportado(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """The loud tier: the default moved between the two refs and the answer did not.

    This is the silent failure of the design made audible. Delete the
    `moved_defaults` report and this goes red — it is the only thing standing
    between "your version floor did not move" and no output at all.
    """
    generate(runner, template, destination, service_name="api")
    commit_all(destination, "generated")
    bump_template(template, tag="v2.0.0", **{'default:__"0.74"': 'default: "0.75"'})

    result = runner.invoke(solution, ["update", str(destination), "--service", "api"])

    assert "dna_floor" in result.output
    assert "0.75" in result.output
    # The ready-made line, not a description of one: `--adopt-new-defaults`
    # only works in the run that DETECTS the move, and by the time a human has
    # read this the run is over.
    assert "--data dna_floor=0.75" in result.output


def test_o_piso_continua_visivel_depois_que_o_commit_avancou(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """⭐ The quiet tier, and the hole it plugs.

    The loud report compares two refs, so it can only speak at the update where
    the default moves. One update later `_commit` has advanced, both refs agree,
    and an answer that was left behind becomes indistinguishable from one a
    human pinned on purpose — the warning goes quiet while the floor stays
    stale forever. That is the original silent failure returning by the back
    door, and it was found by running the command rather than reading it.

    The second tier asks a question that needs no history: is this answer what
    the template says today? Delete `divergent_answers` and this goes red.
    """
    generate(runner, template, destination, service_name="api")
    commit_all(destination, "generated")
    bump_template(template, tag="v2.0.0", **{'default:__"0.74"': 'default: "0.75"'})

    runner.invoke(solution, ["update", str(destination), "--service", "api"])
    commit_all(destination, "first update")
    second = runner.invoke(solution, ["update", str(destination), "--service", "api"])

    assert second.exit_code == 0, second.output
    assert "dna_floor" in second.output
    assert "0.75" in second.output


def test_adopt_new_defaults_move_o_piso_de_verdade(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """The flag has to reach the rendered file, not just the answers file."""
    generate(runner, template, destination, service_name="api")
    commit_all(destination, "generated")
    bump_template(template, tag="v2.0.0", **{'default:__"0.74"': 'default: "0.75"'})

    result = runner.invoke(
        solution,
        ["update", str(destination), "--service", "api", "--adopt-new-defaults"],
    )

    assert result.exit_code == 0, result.output
    assert answers_of(destination, "api")["dna_floor"] == "0.75"
    assert '>=0.75,<0.75' in (destination / "apps/api/pyproject.toml").read_text()


def test_uma_resposta_customizada_nao_e_reportada_como_default_perdido(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """The clause that keeps the loud tier worth reading.

    A human who answered `0.90` on purpose is not "behind"; reporting them
    would train everyone to skip the warning, which is how a loud report
    becomes indistinguishable from no report at all.
    """
    generate(runner, template, destination, service_name="api", dna_floor="0.90")
    commit_all(destination, "generated")
    bump_template(template, tag="v2.0.0", **{'default:__"0.74"': 'default: "0.75"'})

    result = runner.invoke(
        solution, ["update", str(destination), "--service", "api", "--json"]
    )
    report = json.loads(result.output)

    assert report["moved_defaults"] == []
    assert [d["name"] for d in report["divergent_answers"]] == ["dna_floor"]


def test_um_default_jinja_nunca_e_comparado() -> None:
    """A templated default cannot be compared without rendering it.

    Rendering it to produce a WARNING would risk being wrong in a message whose
    entire value is being right, so templated defaults are skipped. Every
    version floor this house actually bumps is a literal, which is the case
    that matters.
    """
    literal = solution_cmd.literal_defaults(
        {
            "dna_floor": {"type": "str", "default": "0.74"},
            "python_module": {"type": "str", "default": "{{ image_name }}"},
            "loud": {"type": "str", "default": "{% if x %}a{% endif %}"},
            "no_default": {"type": "str"},
        }
    )

    assert literal == {"dna_floor": "0.74"}


# ── trap 2: the answer erased by `when:` ─────────────────────────────────────


def test_a_resposta_gated_perdida_e_nomeada(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """`graph_obo: true` → *(absent)*, and the value is printed before it is gone.

    The loss cannot be undone from inside this command — the answers file was
    the only place holding it, and the update rewrites that file. What it can
    do is refuse to let it happen quietly, and print the value so a human (or
    a recorded `Solution`) can carry it forward.
    """
    generate(
        runner, template, destination, service_name="mcp", identity="entra",
        graph_obo="true",
    )
    commit_all(destination, "generated")
    assert answers_of(destination, "mcp")["graph_obo"] is True

    result = runner.invoke(
        solution,
        ["update", str(destination), "--service", "mcp", "--data", "identity=workos"],
    )

    assert result.exit_code == 0, result.output
    assert "graph_obo" not in answers_of(destination, "mcp")
    assert "graph_obo" in result.output
    assert "absent" in result.output
    assert "True" in result.output  # the value itself, not just its name


def test_a_ida_e_volta_devolve_o_default_e_nao_a_resposta_humana(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """The full round trip, measured: true → absent → **false**.

    This is the honest statement of what fatia 3 cannot fix. The value comes
    back as the template's default, not as what the human said, and no amount
    of reporting changes that — only a record that outlives the answers file
    can. The test exists so the claim in the guide is a measurement and not a
    recollection.
    """
    generate(
        runner, template, destination, service_name="mcp", identity="entra",
        graph_obo="true",
    )
    commit_all(destination, "generated")

    runner.invoke(
        solution,
        ["update", str(destination), "--service", "mcp", "--data", "identity=workos"],
    )
    commit_all(destination, "to workos")
    runner.invoke(
        solution,
        ["update", str(destination), "--service", "mcp", "--data", "identity=entra"],
    )

    assert answers_of(destination, "mcp")["graph_obo"] is False


def test_uma_resposta_que_o_operador_mudou_nao_e_reportada_como_perda(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """Asking for a change is not losing one."""
    generate(runner, template, destination, service_name="api", ingress="internal")
    commit_all(destination, "generated")

    result = runner.invoke(
        solution,
        ["update", str(destination), "--service", "api", "--data", "ingress=external",
         "--json"],
    )
    report = json.loads(result.output)

    assert report["lost_answers"] == []
    assert answers_of(destination, "api")["ingress"] == "external"


# ── ⭐ the seam: every recorded answer is re-passed ───────────────────────────


def test_toda_resposta_gravada_e_repassada_ao_copier(
    runner: CliRunner, template: Path, destination: Path, monkeypatch
) -> None:
    """⭐ THE MUTANT. Delete `{**before, ...}` from `update` and this goes red.

    Written as a SEAM guard and labelled as one, because honesty about what it
    measures is the whole point: against copier 9.17 re-passing the recorded
    answers is behaviourally indistinguishable from not passing them — Copier's
    own memory keeps them either way — so an assertion on rendered output would
    have passed for the wrong reason and stayed green through the deletion.

    What the seam buys is not a different render today. It is that the answer
    set becomes THIS command's to state rather than Copier's to remember: the
    report can say "we passed these and they still did not move", the overrides
    are the only path by which an answer changes, and a recorded `Solution`
    has one place to plug into.
    """
    generate(
        runner, template, destination, service_name="mcp", identity="entra",
        graph_obo="true", ingress="external", max_replicas="7",
    )
    commit_all(destination, "generated")
    recorded = {
        k: v for k, v in answers_of(destination, "mcp").items() if not k.startswith("_")
    }

    captured: dict = {}
    real_run_update = copier.run_update

    def spy(*args, **kwargs):
        captured.update(kwargs.get("data") or {})
        return real_run_update(*args, **kwargs)

    monkeypatch.setattr(copier, "run_update", spy)

    result = runner.invoke(
        solution,
        ["update", str(destination), "--service", "mcp", "--data", "max_replicas=9"],
    )
    assert result.exit_code == 0, result.output

    missing = {k: v for k, v in recorded.items() if k not in captured}
    assert not missing, f"recorded answers never reached copier: {missing}"
    assert captured["max_replicas"] == 9, "the explicit override must win"
    for key, value in recorded.items():
        if key == "max_replicas":
            continue
        assert captured[key] == value, f"{key} was re-passed changed"


# ── conflicts, and counting them without lying ───────────────────────────────


def test_um_conflito_e_reportado_e_contado_uma_vez_so(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """A real three-way conflict, counted with `status` and not `ls-files`.

    ⚠️ With a path in conflict `git ls-files` lists it THREE times (stages
    1/2/3), so a change-set counted that way overstates by two per conflict —
    it is how a first reading of the adversarial measurement reported 9.1 %
    instead of 11.1 %. This asserts the path appears once, which is the
    granularity the mistake actually happened at.
    """
    generate(runner, template, destination, service_name="api")
    commit_all(destination, "generated")

    # The human edits the line the template is about to rewrite.
    server = destination / "apps/api/src/api/server.py"
    server.write_text(server.read_text().replace('IDENTITY = "workos"', 'IDENTITY = "workos"  # pinned by a security review'))
    commit_all(destination, "human edit")

    skeleton = template / SERVER_SKELETON
    skeleton.write_text(
        skeleton.read_text().replace(
            'IDENTITY = "{{ identity }}"',
            'IDENTITY = "{{ identity }}"  # v2: stated explicitly',
        )
    )
    commit_all(template, "v2")
    git(template, "tag", "v2.0.0")

    result = runner.invoke(
        solution, ["update", str(destination), "--service", "api", "--json"]
    )
    report = json.loads(result.output)

    assert report["conflicted_paths"] == ["apps/api/src/api/server.py"]
    assert report["changed_paths"].count("apps/api/src/api/server.py") == 1
    assert "<<<<<<<" in server.read_text()


def test_strict_falha_quando_ha_conflito(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """`--strict` is what makes this usable from a script.

    Without it a conflicted tree exits 0 and a pipeline moves on to a checkout
    that does not compile — conflict markers are not valid source.
    """
    generate(runner, template, destination, service_name="api")
    commit_all(destination, "generated")
    server = destination / "apps/api/src/api/server.py"
    server.write_text(server.read_text().replace('IDENTITY = "workos"', 'IDENTITY = "w"'))
    commit_all(destination, "human edit")
    skeleton = template / SERVER_SKELETON
    skeleton.write_text(
        skeleton.read_text().replace(
            'IDENTITY = "{{ identity }}"', 'IDENTITY = "{{ identity }}"  # v2'
        )
    )
    commit_all(template, "v2")
    git(template, "tag", "v2.0.0")

    result = runner.invoke(
        solution, ["update", str(destination), "--service", "api", "--strict"]
    )

    assert result.exit_code == solution_cmd.EXIT_FINDINGS


def test_a_dica_do_conflito_de_wiring_e_uma_pergunta_faltando(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """The conflict report has to distinguish wiring from logic.

    A conflict in `wiring/` means a human expressed STRUCTURE the template
    never asked about, and the fix is a new question in `copier.yml`, not a
    merge. Resolving it by hand papers over a missing field and guarantees the
    same conflict at the next update, forever.
    """
    generate(runner, template, destination, service_name="api")
    commit_all(destination, "generated")
    bicep = destination / "apps/api/wiring/containerapp.bicep"
    bicep.write_text(bicep.read_text().replace("maxReplicas: 2", "maxReplicas: 4"))
    commit_all(destination, "human edit")
    wiring = template / "apps/{{ service_name }}/wiring/containerapp.bicep.jinja"
    wiring.write_text(
        wiring.read_text().replace(
            "maxReplicas: {{ max_replicas }}", "maxReplicas: {{ max_replicas }} // v2"
        )
    )
    commit_all(template, "v2")
    git(template, "tag", "v2.0.0")

    result = runner.invoke(solution, ["update", str(destination), "--service", "api"])

    assert "wiring/" in result.output
    assert "question" in result.output.lower()


def test_uma_edicao_humana_na_fiacao_torna_a_linha_invisivel(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """Measured, and recorded here so nobody re-discovers it in production.

    `maxReplicas: 2 → 4` by hand: the update keeps the 4 and does not conflict
    and does not warn. Copier has no "skipped, and here is what I skipped" —
    it skips, and says nothing. Every wiring line a human touches is invisible
    to the template from then on, and this test is the statement of that limit.
    """
    generate(runner, template, destination, service_name="api")
    commit_all(destination, "generated")
    bicep = destination / "apps/api/wiring/containerapp.bicep"
    bicep.write_text(bicep.read_text().replace("maxReplicas: 2", "maxReplicas: 4"))
    commit_all(destination, "human edit")
    wiring = template / "apps/{{ service_name }}/wiring/containerapp.bicep.jinja"
    wiring.write_text(
        wiring.read_text().replace(
            "// azd overwrites this with the image it builds", "// v2 comment"
        )
    )
    commit_all(template, "v2")
    git(template, "tag", "v2.0.0")

    result = runner.invoke(
        solution, ["update", str(destination), "--service", "api", "--json"]
    )
    report = json.loads(result.output)

    assert report["conflicted_paths"] == []
    assert "maxReplicas: 4" in bicep.read_text()


# ── the dirty tree ───────────────────────────────────────────────────────────


def test_arvore_suja_recusa_com_a_mensagem_do_copier(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    """Copier's message is already clear and correct — relay it, do not rewrite it.

    A message measured to be good is not improved by paraphrase, and a
    paraphrase is one more thing that can drift from the behaviour it
    describes.
    """
    generate(runner, template, destination, service_name="api")
    commit_all(destination, "generated")
    (destination / "scratch.txt").write_text("uncommitted\n")
    git(destination, "add", "-A")

    result = runner.invoke(solution, ["update", str(destination), "--service", "api"])

    assert result.exit_code == solution_cmd.EXIT_REFUSED
    assert "dirty" in result.output
    assert "commit or stash" in result.output


# ── list ─────────────────────────────────────────────────────────────────────


def test_list_mostra_uma_camada_por_app(
    runner: CliRunner, template: Path, destination: Path
) -> None:
    generate(runner, template, destination, service_name="api")
    generate(runner, template, destination, service_name="mcp")

    result = runner.invoke(solution, ["list", str(destination), "--json"])
    rows = json.loads(result.output)

    assert [row["answers_file"] for row in rows] == [
        ".copier-answers.api.yml",
        ".copier-answers.mcp.yml",
    ]
    assert {row["ref"] for row in rows} == {"v1.0.0"}


# ── the small parsers, at the granularity they fail ──────────────────────────


def test_data_e_lido_como_yaml_para_um_bool_ser_um_bool() -> None:
    """`--data graph_obo=true` must reach a `type: bool` question as a bool.

    Handing a bool question the string `"true"` is the kind of near-miss that
    renders subtly wrong output instead of failing — `{% if graph_obo %}` is
    true for the string `"false"` as well.
    """
    parsed = solution_cmd.parse_data(
        ("graph_obo=true", "max_replicas=4", "identity=entra", "empty=")
    )

    assert parsed == {
        "graph_obo": True,
        "max_replicas": 4,
        "identity": "entra",
        "empty": None,
    }


def test_data_sem_igual_e_recusado() -> None:
    with pytest.raises(solution_cmd.SolutionError):
        solution_cmd.parse_data(("graph_obo",))


def test_o_bookkeeping_do_copier_nunca_volta_como_resposta(tmp_path: Path) -> None:
    """`_commit` and `_src_path` are Copier telling itself where it was.

    Feeding them back as answers would hand the template its own bookkeeping as
    data, and — worse — pin `_src_path` as an answer, which is how a recorded
    template path becomes un-relocatable.
    """
    (tmp_path / ".copier-answers.api.yml").write_text(
        "_commit: v1.0.0\n_src_path: /somewhere\nservice_name: api\n"
    )

    assert solution_cmd.recorded_answers(tmp_path, Path(".copier-answers.api.yml")) == {
        "service_name": "api"
    }


# ── _external_data: inheritance between layers, without template inheritance ──


@pytest.fixture
def layered_templates(tmp_path: Path) -> tuple[Path, Path]:
    """A `base` template and a `leaf` that reads the base's answers as defaults.

    Copier has no template-inherits-template (issue #934). `_external_data` is
    the third way, and the only one running in production anywhere: a layer
    declares the answers file of the layer above and reads it. It is what lets
    three MCP doors inherit one base and answer only what differs — which is,
    field for field, what actually varies between them.
    """
    base = tmp_path / "base-template"
    base.mkdir()
    (base / "copier.yml").write_text(
        '_answers_file: ".copier-answers.base.yml"\n'
        '_templates_suffix: ".jinja"\n'
        "org:\n  type: str\n  default: acme\n"
    )
    (base / "{{ _copier_conf.answers_file }}.jinja").write_text(
        "{{ _copier_answers|to_nice_yaml -}}\n"
    )
    init_repo(base)
    commit_all(base, "base")
    git(base, "tag", "v1.0.0")

    leaf = tmp_path / "leaf-template"
    leaf.mkdir()
    (leaf / "copier.yml").write_text(
        '_answers_file: ".copier-answers.{{ service_name }}.yml"\n'
        '_templates_suffix: ".jinja"\n'
        "_external_data:\n  base: .copier-answers.base.yml\n"
        "service_name:\n  type: str\n  default: api\n"
    )
    (leaf / "{{ _copier_conf.answers_file }}.jinja").write_text(
        "{{ _copier_answers|to_nice_yaml -}}\n"
    )
    (leaf / "owner.txt.jinja").write_text("{{ _external_data.base.org }}\n")
    init_repo(leaf)
    commit_all(leaf, "leaf")
    git(leaf, "tag", "v1.0.0")
    return base, leaf


def test_external_data_herda_a_resposta_da_camada_de_cima(
    runner: CliRunner, layered_templates: tuple[Path, Path], destination: Path
) -> None:
    base, leaf = layered_templates
    generate(runner, base, destination, org="ruinosus")

    generate(runner, leaf, destination, service_name="api")

    assert (destination / "owner.txt").read_text().strip() == "ruinosus"


def test_external_data_ausente_e_reportado_em_vez_de_render_vazio(
    runner: CliRunner, layered_templates: tuple[Path, Path], destination: Path
) -> None:
    """The failure mode that looks like success.

    With the upper layer's answers file absent, Copier warns and renders the
    inherited values as EMPTY — it does not fail. An app generated that way is
    missing everything it was meant to inherit and looks fine, which is the
    worst shape a defect can take. The warning is surfaced as a named finding
    so it is a decision instead of a discovery.
    """
    _, leaf = layered_templates

    result = runner.invoke(
        solution,
        ["new", str(leaf), str(destination), "--defaults", "--json"],
    )
    report = json.loads(result.output)

    assert report["missing_external_data"], (
        "a missing inherited layer rendered silently as empty: "
        + (destination / "owner.txt").read_text()
    )
    assert (destination / "owner.txt").read_text().strip() == ""


def test_external_data_ausente_falha_com_strict(
    runner: CliRunner, layered_templates: tuple[Path, Path], destination: Path
) -> None:
    _, leaf = layered_templates

    result = runner.invoke(
        solution, ["new", str(leaf), str(destination), "--defaults", "--strict"]
    )

    assert result.exit_code == solution_cmd.EXIT_FINDINGS
    assert "external-data" in result.output
