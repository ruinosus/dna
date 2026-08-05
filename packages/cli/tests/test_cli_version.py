"""`dna --version` diz a versão INSTALADA — nunca um literal.

O "0.1.0" cravado no scaffold sobreviveu até a 0.70.0: toda release mentia
no --version enquanto o `pip show` dizia a verdade. A fonte é o metadado da
distribuição `dna-cli`; este teste quebra se alguém voltar a cravar."""
from importlib.metadata import version as dist_version

from click.testing import CliRunner

from dna_cli import main


def test_version_matches_installed_metadata():
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert dist_version("dna-cli") in result.output
    assert "0.1.0" not in result.output or dist_version("dna-cli").startswith("0.1.")
