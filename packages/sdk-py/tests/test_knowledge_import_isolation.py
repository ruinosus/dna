"""i-154 — o core segue livre do ``chonkie``.

O cortador é um EXTRA (``dna-sdk[knowledge]``), e a razão é peso: ele é leve
HOJE (seis dependências obrigatórias) e só continua sendo a escolha certa
enquanto continuar leve. Um extra que o install padrão importa não é um extra —
é uma dependência com outro nome, e o custo dela aparece na imagem de quem só
queria compor um prompt.

Espelha ``test_search_import_isolation.py`` e ``test_embedding_import_isolation.py``.
Cada caso roda num subprocesso porque ``sys.modules`` do processo de teste já
carregou meio mundo — perguntar nele responderia sobre a suíte, não sobre um
install.
"""
from __future__ import annotations

import subprocess
import sys


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)


def test_import_padrao_e_a_porta_de_busca_nao_puxam_chonkie():
    """Importar o SDK, subir um kernel e ATRAVESSAR a porta de busca de
    conhecimento não pode tocar o extra. A busca entra aqui de propósito: é o
    caminho que roda em toda conversa, e é o que ficaria caro se o import
    subisse junto."""
    code = (
        "import sys, asyncio\n"
        "import dna\n"
        "from dna.kernel import Kernel\n"
        "from dna.application import knowledge\n"
        "from dna.application.live import LiveDna\n"
        "k = Kernel.auto()\n"
        "live = LiveDna(base_scope='nope', kernel=k, provider=None)\n"
        "try:\n"
        "    asyncio.run(knowledge.search_knowledge_impl(live, query='oi'))\n"
        "except Exception:\n"
        "    pass\n"
        "assert 'chonkie' not in sys.modules, 'o import padrão puxou chonkie'\n"
        # As funções de NOME são o que a leitura usa, e elas não podem custar
        # o cortador — é por isso que elas moram fora de `chunk_markdown`.
        "assert knowledge.chunk_name('c', 'a'*64, 1)\n"
        "assert 'chonkie' not in sys.modules\n"
    )
    proc = _run(code)
    assert proc.returncode == 0, proc.stderr


def test_o_extra_esta_instalado_no_ambiente_de_teste():
    """⚠️ A guarda-sobre-a-guarda. Sem ela, o teste acima passaria por um motivo
    que nada tem a ver com o que ele afirma: um ambiente onde o ``chonkie``
    simplesmente não existe também nunca o tem em ``sys.modules``. Um universo
    vazio não é prova de isolamento.

    Este caso PULA quando o extra genuinamente não está instalado, e nesse caso
    o teste acima também não prova nada — que é a leitura honesta."""
    import pytest

    pytest.importorskip(
        "chonkie",
        reason="extra `knowledge` não instalado (pip install 'dna-sdk[knowledge]')",
    )
    code = "import chonkie, sys; assert 'chonkie' in sys.modules\n"
    proc = _run(code)
    assert proc.returncode == 0, proc.stderr


def test_o_corte_puxa_o_cortador():
    """O outro lado da guarda: ``chunk_markdown`` DEVE importar o ``chonkie``.
    Se este teste passar sem ele em ``sys.modules``, alguém escreveu um
    cortador à mão — exatamente o que a regra da casa proíbe."""
    import pytest

    pytest.importorskip("chonkie")
    code = (
        "import sys\n"
        "from dna.application.knowledge import chunk_markdown\n"
        "assert 'chonkie' not in sys.modules, 'o módulo importou chonkie no topo'\n"
        "pedacos = chunk_markdown('# T\\n\\n' + ('frase de teste. ' * 80), chunk_size=200)\n"
        "assert len(pedacos) > 1\n"
        "assert 'chonkie' in sys.modules, 'o corte não passou pelo chonkie'\n"
    )
    proc = _run(code)
    assert proc.returncode == 0, proc.stderr
