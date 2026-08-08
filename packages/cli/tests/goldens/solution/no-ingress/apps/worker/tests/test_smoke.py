"""The one test the template ships: the package imports and reads its knobs.

Anything richer would be behaviour, and behaviour is yours — see `server.py`.
"""
from __future__ import annotations

from worker import server


def test_this_app_does_not_serve() -> None:
    """`ingress: none` all the way down — no port anywhere, not even a default.

    The assertion is an ABSENCE, and it is the one worth shipping: `port` is
    not an answer this app HAS (the `App` Kind refuses `ingress: none` beside
    a `port`), so a `PORT` reappearing here would mean something invented one.
    """
    assert not hasattr(server, "PORT")


def test_identity_authority_is_the_one_that_was_declared() -> None:
    assert server.IDENTITY == "none"
