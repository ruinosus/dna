"""Hermetic test contract for the dna-sdk SDK suite (s-pysuite-conftest-hermetic).

One place that:

1. **Caps every test's wall-clock** via a default ``--timeout`` (set in
   ``pyproject.toml`` ``[tool.pytest.ini_options]``), so a hung async test can
   never run to the CI job limit again (the python-sdk job that stuck for 1h on
   2026-05-29). Heavy-but-real tests override with ``@pytest.mark.timeout(N)``.

2. **Skips tests that need a real external resource** — Postgres, network, or a
   real LLM key — when that resource is absent, from a single ``requires_*``
   marker instead of the per-file ``skipif`` guards that had drifted
   (``DATABASE_URL`` vs ``DNA_PG_TEST_URL`` vs ``DNA_PG_TEST_DSN``; ad-hoc
   ``_has_internet()`` copies; ``OPENAI_API_KEY`` truthiness that didn't exclude
   fake keys). Mark a test ``@pytest.mark.requires_postgres`` /
   ``requires_network`` / ``requires_llm`` and it auto-skips offline; provide the
   resource (env set / online) to exercise it. The suite is green with zero
   external resources.
"""
from __future__ import annotations

import os
import socket

import pytest

# --- resource availability — single source of truth ------------------------


def _postgres_available() -> bool:
    """A Postgres DSN is configured under any of the env names the suite has
    historically used."""
    return any(
        os.environ.get(k)
        for k in ("DATABASE_URL", "DNA_PG_TEST_URL", "DNA_PG_TEST_DSN")
    )


def _llm_available() -> bool:
    """A *real* OpenAI key is set. Fake/test keys land on the deterministic
    fallback path (no real call), so they don't count as 'available'."""
    key = os.environ.get("OPENAI_API_KEY", "")
    return bool(key) and not key.lower().startswith(("sk-fake", "sk-test", "test", "fake"))


_NETWORK_CACHE: bool | None = None


def _network_available() -> bool:
    """Real outbound network (probe github.com:443 once, cached).

    ``DNA_OFFLINE=1`` forces False regardless of real connectivity — CI runners
    DO have network, but CI must never clone external repos (s-public-ci), so
    the workflows export DNA_OFFLINE=1 and ``requires_network`` tests skip with
    an explicit reason."""
    if os.environ.get("DNA_OFFLINE"):
        return False
    global _NETWORK_CACHE
    if _NETWORK_CACHE is None:
        try:
            conn = socket.create_connection(("github.com", 443), timeout=2)
            conn.close()
            _NETWORK_CACHE = True
        except OSError:
            _NETWORK_CACHE = False
    return _NETWORK_CACHE


# marker name -> (availability check, skip reason)
_RESOURCES = {
    "requires_postgres": (
        _postgres_available,
        "no Postgres DSN (DATABASE_URL / DNA_PG_TEST_URL / DNA_PG_TEST_DSN) set",
    ),
    "requires_network": (
        _network_available,
        "no network / GitHub access (or DNA_OFFLINE=1 set)",
    ),
    "requires_llm": (_llm_available, "no real OPENAI_API_KEY set"),
}


def pytest_configure(config: pytest.Config) -> None:
    for name in _RESOURCES:
        config.addinivalue_line(
            "markers",
            f"{name}: skip unless the resource is available (see tests/conftest.py)",
        )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        for marker_name, (check, reason) in _RESOURCES.items():
            if item.get_closest_marker(marker_name) and not check():
                item.add_marker(pytest.mark.skip(reason=reason))
