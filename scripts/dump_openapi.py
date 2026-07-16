#!/usr/bin/env python3
"""Deterministically dump the DNA REST read-API's OpenAPI schema.

The DNA REST API (``dna_cli._rest_api``) is a FastAPI app; FastAPI auto-emits an
OpenAPI document from its routes. That document is the GENERATION SOURCE for the
official DNA API clients (``packages/client-ts`` + ``packages/client-py``): the
clients are generated from it, so they never drift from the live routes.

This script re-dumps the schema and writes it to ``docs/openapi.json`` with
STABLE, SORTED keys so the committed file is byte-deterministic (a route change
produces a minimal, reviewable diff). The client drift test
(``packages/client-py/tests/test_openapi_drift.py``) calls :func:`dump` and
fails if the committed file is stale — that is the guard that keeps the client
in sync with the API.

Usage::

    python scripts/dump_openapi.py           # rewrite docs/openapi.json
    python scripts/dump_openapi.py --check    # exit 1 if it would change

Needs the optional ``fastapi`` dependency (``pip install 'dna-cli[api]'``).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# The canonical, committed spec — the single generation source for both clients.
SPEC_PATH = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"


def build_schema() -> dict:
    """Build the FastAPI app and return its OpenAPI document (a plain dict)."""
    from dna_cli._rest_api import build_app

    return build_app().openapi()


def render(schema: dict) -> str:
    """Serialize the schema deterministically (sorted keys, 2-space indent,
    trailing newline) so the committed file is stable across runs/machines."""
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def dump() -> str:
    """Return the deterministic serialization of the live OpenAPI schema."""
    return render(build_schema())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the committed docs/openapi.json is stale (do not write)",
    )
    args = parser.parse_args(argv)

    current = dump()
    if args.check:
        existing = SPEC_PATH.read_text(encoding="utf-8") if SPEC_PATH.exists() else ""
        if existing != current:
            print(
                "::error::docs/openapi.json is stale — the DNA REST API changed "
                "without regenerating the client spec. Run "
                "`python scripts/dump_openapi.py` and commit.",
                file=sys.stderr,
            )
            return 1
        print("docs/openapi.json is in sync with the live DNA REST API.")
        return 0

    SPEC_PATH.write_text(current, encoding="utf-8")
    print(f"wrote {SPEC_PATH.relative_to(SPEC_PATH.parent.parent)} "
          f"({len(current)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
