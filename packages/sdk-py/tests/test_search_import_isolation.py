"""rec-embeddable-provider — the core stays free of the sqlite-vec dependency.

The sqlite-vec RecordSearchProvider is an OPT-IN extra (``dna-sdk[search-sqlite]``).
Importing the SDK, the adapters namespace, booting a kernel, and running the
lexical fallback (``kernel.search``) must NEVER pull ``sqlite_vec``. Mirrors
``test_embedding_import_isolation.py`` and the sqlalchemy isolation guard.
"""
from __future__ import annotations

import subprocess
import sys


def test_default_import_and_lexical_search_never_pull_sqlite_vec():
    code = (
        "import sys, asyncio\n"
        "import dna\n"
        "import dna.adapters\n"
        "from dna.kernel import Kernel\n"
        "k = Kernel.auto()\n"
        # exercise the degraded lexical search path — still no sqlite-vec. No
        # source is registered, so the scan raises; that's fine — we only care
        # that reaching search() imported nothing from the extra.
        "try:\n"
        "    asyncio.run(k.search('nope', 'hello', kind='Story'))\n"
        "except Exception:\n"
        "    pass\n"
        "assert 'sqlite_vec' not in sys.modules, \\\n"
        "    'default import/lexical search pulled sqlite_vec'\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_importing_rrf_is_cheap():
    """The pure RRF core carries no sqlite-vec dependency."""
    code = (
        "import sys\n"
        "from dna.adapters.search.rrf import reciprocal_rank_fusion\n"
        "assert 'sqlite_vec' not in sys.modules\n"
        "assert reciprocal_rank_fusion([['a','b'],['b','a']])\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
