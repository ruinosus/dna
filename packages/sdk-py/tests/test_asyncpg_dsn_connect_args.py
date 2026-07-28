"""i-091 — a DSN query param that is a CONNECTION argument is not a server setting.

The failing shape, seen live: a source URL ending in ``?ssl=require``. Two
consumers read the same URL and disagree about what that query param MEANS:

  * SQLAlchemy's asyncpg dialect folds ``url.query`` into the **connect
    kwargs** — ``asyncpg.connect(ssl="require")``. Ordinary queries work.
  * asyncpg's OWN DSN parser knows a fixed libpq-ish vocabulary
    (``sslmode``, ``host``, ``user``, …) and forwards everything ELSE, blindly,
    into ``server_settings`` — so the driver puts ``ssl=require`` in the startup
    packet and Postgres answers ``CantChangeRuntimeParamError: parameter "ssl"
    cannot be changed now`` (``ssl`` is a real PGC_SIGHUP GUC).

Anything in the SDK that hands a DSN to asyncpg directly (the pgvector search
provider's pool, the LISTEN/NOTIFY event bus) took the second path, so the
search index could never be refreshed on such a deployment — and ``recall``
stopped being read-your-writes.

These cases pin the translation itself, plus the external fact it rests on
(asyncpg's blind forwarding), so a future asyncpg that starts/stops parsing a
param cannot silently re-open the hole.
"""
from __future__ import annotations

import inspect

import pytest

asyncpg = pytest.importorskip(
    "asyncpg",
    reason="postgres extra not installed (pip install 'dna-sdk[search-pgvector]')",
)

from dna.adapters.asyncpg_dsn import asyncpg_connect_args  # noqa: E402

_DSN = "postgresql://u:p@db.example:5432/app"


def _server_settings(dsn: str, **connect_kwargs) -> dict[str, str]:
    """What asyncpg's own parser would send as startup parameters.

    Calls the driver's private DSN parser — deliberately, because the fact
    under test is the driver's behavior, not our opinion of it. The call is
    built from its live signature (defaults ``None``) so a signature change
    across asyncpg versions surfaces as a normal failure, not a false green.
    """
    from asyncpg import connect_utils

    sig = inspect.signature(connect_utils._parse_connect_dsn_and_args)
    kwargs = {name: None for name in sig.parameters if name != "dsn"}
    # Only the connection arguments this parser itself takes (the rest — e.g.
    # command_timeout — are consumed further down asyncpg's connect path and
    # can never be startup parameters).
    kwargs.update({k: v for k, v in connect_kwargs.items() if k in kwargs})
    _, params = connect_utils._parse_connect_dsn_and_args(dsn=dsn, **kwargs)
    return dict(params.server_settings or {})


def test_asyncpg_forwards_an_unknown_query_param_as_a_server_setting():
    """The external fact the bug rests on — asserted against the real driver."""
    assert _server_settings(f"{_DSN}?ssl=require") == {"ssl": "require"}


def test_a_connection_argument_is_lifted_out_of_the_dsn():
    dsn, kwargs = asyncpg_connect_args(f"{_DSN}?ssl=require")

    assert kwargs == {"ssl": "require"}
    assert dsn == _DSN
    # …and the driver now sends NOTHING extra in the startup packet.
    assert _server_settings(dsn, **kwargs) == {}


def test_a_genuine_server_setting_stays_in_the_dsn():
    """The fix is not "strip the query" — a real GUC must still reach the server."""
    dsn, kwargs = asyncpg_connect_args(f"{_DSN}?application_name=dna&ssl=require")

    assert kwargs == {"ssl": "require"}
    assert dsn == f"{_DSN}?application_name=dna"
    assert _server_settings(dsn, **kwargs) == {"application_name": "dna"}


def test_asyncpgs_own_dsn_vocabulary_is_left_for_asyncpg_to_parse():
    """``sslmode`` IS understood by the driver's parser — lifting it would be a
    second translation of the same thing."""
    for param in ("sslmode=require", "target_session_attrs=primary", "passfile=/x"):
        dsn, kwargs = asyncpg_connect_args(f"{_DSN}?{param}")
        assert kwargs == {}, param
        assert dsn == f"{_DSN}?{param}", param


def test_every_asyncpg_connection_argument_is_covered_not_just_ssl():
    """General by construction: the lifted set is derived from ``asyncpg.connect``'s
    own signature, so the NEXT connection argument someone puts in a URL does not
    repeat this bug."""
    dsn, kwargs = asyncpg_connect_args(
        f"{_DSN}?command_timeout=30&statement_cache_size=0&direct_tls=false"
    )
    assert kwargs == {
        "command_timeout": 30,
        "statement_cache_size": 0,
        "direct_tls": False,
    }, "URL strings are coerced to the types asyncpg expects"
    assert dsn == _DSN
    assert _server_settings(dsn, **kwargs) == {}


def test_a_sqlalchemy_driver_suffix_is_dropped():
    """``postgresql+asyncpg://`` is a SQLAlchemy spelling; asyncpg rejects the
    scheme outright. The same config URL feeds both."""
    dsn, kwargs = asyncpg_connect_args("postgresql+asyncpg://u:p@db.example:5432/app?ssl=require")
    assert dsn == _DSN
    assert kwargs == {"ssl": "require"}


def test_a_dsn_with_nothing_to_translate_is_returned_untouched():
    assert asyncpg_connect_args(_DSN) == (_DSN, {})
    # …including the libpq keyword/value form, which is not a URL at all.
    kv = "host=db.example port=5432 dbname=app sslmode=require"
    assert asyncpg_connect_args(kv) == (kv, {})
