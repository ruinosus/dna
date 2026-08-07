"""The one test the template ships: the package imports and reads its knobs.

Anything richer would be behaviour, and behaviour is yours — see `server.py`.
"""
from __future__ import annotations

from mcp import server


def test_port_comes_from_the_declared_default() -> None:
    assert server.PORT == 8000


def test_identity_authority_is_the_one_that_was_declared() -> None:
    assert server.IDENTITY == "entra"
