"""`dna copilot install` (F3) — o kit inteiro pela PORTA.

Instala o kit de vitrine REAL do repo (copilot-kits/contrato-intake) num
store temporário: cada doc passa pelo kernel.write_document com todos os
guards; o Kind entra INERTE sem --approve e aprovado com; --dry-run não
escreve nada."""

from __future__ import annotations

import pathlib

from click.testing import CliRunner

from dna_cli import main

_KIT = pathlib.Path(__file__).resolve().parents[3] / "copilot-kits" / "contrato-intake"


def _run(tmp_path, *args):
    (tmp_path / "kitscope").mkdir(exist_ok=True)
    runner = CliRunner()
    return runner.invoke(
        main,
        ["copilot", "install", str(_KIT), "--scope", "kitscope", *args],
        env={"DNA_BASE_DIR": str(tmp_path)},
        catch_exceptions=False,
    )


def test_dry_run_lista_o_plano_e_escreve_nada(tmp_path):
    out = _run(tmp_path, "--dry-run")
    assert out.exit_code == 0, out.output
    assert "Copilot/contrato-copiloto" in out.output
    assert "KindDefinition/contrato-de-servico" in out.output
    # nada escrito
    assert not [p for p in (tmp_path / "kitscope").rglob("*") if p.is_file()]


def test_instala_o_kit_inteiro_com_kind_inerte(tmp_path):
    out = _run(tmp_path)
    assert out.exit_code == 0, out.output
    assert "3 documento(s)" in out.output
    assert "INERTES" in out.output  # o humano fica no circuito
    escritos = {str(p.relative_to(tmp_path / "kitscope")) for p in (tmp_path / "kitscope").rglob("*") if p.is_file()}
    # cada Kind no SEU storage declarado: o copilot em YAML, o Agent em
    # markdown (AGENT.md), o KindDefinition em kinds/<nome>/KIND.yaml —
    # prova de que a escrita passou pelo roteamento do kernel, não por cópia.
    assert "copilots/contrato-copiloto.yaml" in escritos
    assert "agents/contrato-agent/AGENT.md" in escritos
    assert "kinds/contrato-de-servico/KIND.yaml" in escritos


def test_approve_carimba_o_operador(tmp_path):
    out = _run(tmp_path, "--approve")
    assert out.exit_code == 0, out.output
    assert "INERTES" not in out.output
    import yaml

    kind_doc = next((tmp_path / "kitscope").rglob("KIND.yaml"))
    raw = yaml.safe_load(kind_doc.read_text())
    assert raw["spec"].get("approved_by")  # o ato humano, carimbado
