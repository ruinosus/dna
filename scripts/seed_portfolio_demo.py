#!/usr/bin/env python3
"""Seed the DNA Cloud portfolio-console demo data (tenant ``demo``).

Mirrors how the intel ``IntelSource`` was seeded at ``.dna/tenants/demo/…``:
writes each portfolio doc through ``kernel.write_document`` (so schema
validation + cache invalidation fire, the same funnel every writer uses), bound
to tenant ``demo`` so the FS source routes them into the tenant overlay layout
``.dna/tenants/demo/scopes/dna-development/<container>/``. Those YAMLs are
FS-tracked and must be COMMITTED (the DNA source is the git-tracked ``.dna/``,
not a database).

Idempotent: re-running overwrites the same docs. After seeding it runs one
offline intel pass over the ``dna`` source (the SeedAnalyzer carries the real
DNA positioning insights) so the DNA project has real ``IntelInsight`` docs.

Run from the repo root (the ``.dna/`` FS source):

    packages/cli/.venv/bin/python scripts/seed_portfolio_demo.py
"""
from __future__ import annotations

import asyncio
import os

SCOPE = "dna-development"
TENANT = "demo"
PORTFOLIO_API = "github.com/ruinosus/dna/portfolio/v1"
INTEL_API = "github.com/ruinosus/dna/intel/v1"


def _doc(api: str, kind: str, name: str, spec: dict) -> dict:
    return {
        "apiVersion": api,
        "kind": kind,
        "metadata": {"name": name},
        "spec": {"name": name, **spec} if "name" not in spec else {**spec},
    }


ORGS = [
    _doc(PORTFOLIO_API, "Organization", "barnabe-labs",
         {"slug": "barnabe-labs", "display_name": "Barnabé Labs"}),
]

REPOS = [
    _doc(PORTFOLIO_API, "Repo", "dna",
         {"url": "https://github.com/ruinosus/dna", "provider": "github",
          "default_branch": "main"}),
    _doc(PORTFOLIO_API, "Repo", "dna-cloud",
         {"url": "https://github.com/ruinosus/dna-cloud", "provider": "github",
          "default_branch": "main"}),
    _doc(PORTFOLIO_API, "Repo", "copiloto-medico",
         {"url": "https://github.com/ruinosus/copiloto-medico", "provider": "github",
          "default_branch": "main"}),
]

PROJECTS = [
    _doc(PORTFOLIO_API, "Project", "dna", {
        "slug": "dna",
        "org_ref": "barnabe-labs",
        "board_scope": "dna-development",
        "repo_refs": ["dna", "dna-cloud"],          # multi-repo — the showcase
        "intel_source_refs": ["dna"],
        "visibility": "private",
    }),
    _doc(PORTFOLIO_API, "Project", "copiloto-medico", {
        "slug": "copiloto-medico",
        "org_ref": "barnabe-labs",
        "board_scope": "copiloto-medico-development",
        "repo_refs": ["copiloto-medico"],
        "intel_source_refs": ["copiloto-medico"],
        "visibility": "private",
    }),
]

# IntelSource for the DNA project — type repo, weekly, threshold 0.6, the DNA
# positioning PIRs. The SeedAnalyzer's "dna" registry supplies the candidates.
SOURCES = [
    _doc(INTEL_API, "IntelSource", "dna", {
        "type": "repo",
        "cadence": "weekly",
        "threshold": 0.6,
        "pirs": ["posicionamento", "arquitetura", "mercado"],
        "muted": False,
        "notes": "DNA / DNA Cloud positioning + intelligence-layer experiments.",
    }),
]


async def _run() -> None:
    from dna_cli._mcp_server import boot_live
    from dna.extensions.intel import engine
    from dna.extensions.intel.analyzer import SeedAnalyzer

    live = await boot_live(scope=SCOPE)
    kernel = live.kernel

    async def write(doc: dict) -> None:
        await kernel.write_document(
            SCOPE, doc["kind"], doc["metadata"]["name"], doc, tenant=TENANT,
        )
        print(f"  seeded {doc['kind']}/{doc['metadata']['name']}")

    print(f"Seeding portfolio (scope={SCOPE}, tenant={TENANT}) …")
    for doc in [*ORGS, *REPOS, *PROJECTS, *SOURCES]:
        await write(doc)

    print("\nRunning intel pass over 'dna' (offline SeedAnalyzer) …")
    result = await engine.run_pass(
        kernel, "dna", scope=SCOPE, tenant=TENANT, analyzer=SeedAnalyzer(),
    )
    print(f"  delivered {result.kept_count} insight(s), "
          f"suppressed {result.suppressed_count}, deduped {result.deduped_count}")
    for k in result.kept:
        print(f"    + {k['name']} (score={k['score']})")


if __name__ == "__main__":
    os.environ.setdefault("DNA_BASE_DIR", os.path.join(os.getcwd(), ".dna"))
    asyncio.run(_run())
