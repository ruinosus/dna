"""O extra `a2a` é OPCIONAL — e a garantia é estrutural, não documental.

`a2a-sdk` traz oito dependências base (protobuf, google-api-core,
googleapis-common-protos e a árvore de auth do Google), herança do transporte
gRPC que nem usamos. Quem não serve A2A não pode pagar por elas. Um import
solto no topo de um módulo do kernel converteria "extra opcional" em
"dependência de todo mundo" sem que ninguém percebesse — este teste é o que
percebe.
"""
from __future__ import annotations

import subprocess
import sys


def test_o_import_base_do_dna_nunca_puxa_a2a():
    codigo = (
        "import dna, dna.application.a2a_transport, dna.application.a2a_ingest, "
        "dna.emit.agent_card, dna.extensions.a2a; "
        "import sys; "
        "vazados = sorted(m for m in sys.modules if m == 'a2a' or m.startswith('a2a.')); "
        "print(','.join(vazados))"
    )
    saida = subprocess.run(
        [sys.executable, "-c", codigo], capture_output=True, text=True, check=True
    )
    vazados = [m for m in saida.stdout.strip().split(",") if m]
    assert not vazados, (
        f"importar o DNA puxou {vazados} — o extra `a2a` deixou de ser opcional"
    )
