"""rec-embedding-port — the core stays ML-dependency-free.

The REAL embedder (ONNX all-MiniLM-L6-v2 via fastembed) is an OPT-IN extra
(``dna-sdk[embed-onnx]``). Importing the SDK, the adapters namespace, booting a
kernel, and even using the fake embedding floor must NEVER pull
fastembed/onnxruntime/torch. This guard mirrors the sqlalchemy import-isolation
test (``test_sqlalchemy_source.py::test_default_import_never_pulls_sqlalchemy``).
"""
from __future__ import annotations

import subprocess
import sys

# Heavy ML modules the fastembed extra drags — none may appear in a default
# process, not even after embedding with the fake floor.
_FORBIDDEN = ("fastembed", "onnxruntime", "torch")


def test_default_import_and_fake_embed_never_pull_onnx():
    """Fresh interpreter so this suite's own imports don't contaminate:
    import the SDK, boot a kernel, run the fake embedding floor — assert none
    of the ML modules loaded."""
    code = (
        "import sys, asyncio\n"
        "import dna\n"
        "import dna.adapters\n"
        "from dna.kernel import Kernel\n"
        "k = Kernel.auto()\n"
        "asyncio.run(k.embed(['the quick brown fox']))\n"  # exercise the fake floor
        f"forbidden = {_FORBIDDEN!r}\n"
        "leaked = [m for m in forbidden if m in sys.modules]\n"
        "assert not leaked, f'default install/fake-embed pulled ML deps: {leaked}'\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_importing_onnx_adapter_module_is_cheap():
    """Importing the ONNX adapter MODULE must not eagerly load fastembed —
    the heavy import is deferred to first embed() (lazy-download+cache). This
    holds whether or not the extra is installed."""
    code = (
        "import sys\n"
        "import dna.adapters.embedding.onnx as m\n"
        "assert 'fastembed' not in sys.modules, 'adapter import eagerly loaded fastembed'\n"
        "assert hasattr(m, 'OnnxEmbeddingProvider')\n"
        # Constructing the provider is also cheap (model built on first embed).
        "p = m.OnnxEmbeddingProvider()\n"
        "assert p.model_id and p.dims == 384\n"
        "assert 'fastembed' not in sys.modules, 'constructing provider loaded fastembed'\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
