"""``asyncpg_connect_args`` — a Postgres URL split into (DSN, connect kwargs).

One configured URL feeds two very different readers, and they disagree about
what a query parameter MEANS:

  * **SQLAlchemy's asyncpg dialect** folds the whole ``url.query`` into the
    driver's **connection arguments** — ``?ssl=require`` becomes
    ``asyncpg.connect(ssl="require")``, a TLS mode. This is the path every
    ordinary source query takes.
  * **asyncpg's own DSN parser** understands a fixed, libpq-ish vocabulary
    (``sslmode``, ``host``, ``user``, ``target_session_attrs``, …) and forwards
    everything else, blindly, into ``server_settings`` — i.e. the startup
    packet. ``?ssl=require`` therefore asks Postgres to SET the ``ssl`` GUC,
    which is ``PGC_SIGHUP``, and the server answers
    ``CantChangeRuntimeParamError: parameter "ssl" cannot be changed now``.
    Every connection fails; nothing about the URL is wrong.

So a URL that works everywhere SQLAlchemy reads it breaks the moment a
component opens its own asyncpg pool from the same string (i-091: the pgvector
search provider's pool, which is what a ``recall`` index refresh runs on — the
refresh failed, and ``recall`` silently stopped being read-your-writes).

This module is that translation, done once and on purpose:

    dsn, kwargs = asyncpg_connect_args(url)
    pool = await asyncpg.create_pool(dsn, **kwargs)

**A connection argument is lifted; a server setting is left alone.** The lifted
set is derived from ``asyncpg.connect``'s own signature minus the vocabulary its
DSN parser already consumes — so it is not a list of one special-cased name, and
the next connection argument someone puts in a URL cannot repeat the bug. Params
the driver does parse (``sslmode`` and friends) stay in the DSN for the driver
to parse; genuine server settings (``application_name``, …) stay in the DSN and
still reach the server, because dropping them would be a different lie.

A SQLAlchemy driver suffix (``postgresql+asyncpg://``) is dropped — asyncpg
rejects that scheme outright — and a DSN that is not a URL at all (libpq's
``host=… port=…`` keyword/value form) is returned untouched.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

__all__ = ["asyncpg_connect_args"]

#: Query params asyncpg's OWN DSN parser consumes (``connect_utils.
#: _parse_connect_dsn_and_args``). Left in the DSN: the driver already knows
#: what they mean, and translating them twice would be its own defect. If a
#: future asyncpg stops parsing one of these, the worst case is that we hand it
#: over as an explicit keyword — which the driver gives precedence to anyway.
_ASYNCPG_DSN_VOCABULARY = frozenset({
    "host", "port", "user", "password", "passfile", "database", "dbname",
    "service", "sslmode", "sslcert", "sslkey", "sslrootcert", "sslcrl",
    "sslpassword", "sslnegotiation", "ssl_min_protocol_version",
    "ssl_max_protocol_version", "target_session_attrs", "krbsrvname", "gsslib",
})

#: ``connect()`` keywords that can never be expressed in a URL (objects, the
#: running loop, or the very dict this split exists to keep clean).
_NOT_FROM_URL = frozenset({
    "dsn", "loop", "connection_class", "record_class", "server_settings",
})

_TRUE = frozenset({"true", "yes", "on"})
_FALSE = frozenset({"false", "no", "off"})


@lru_cache(maxsize=1)
def _connection_params() -> frozenset[str]:
    """The connect-time arguments a URL may carry that asyncpg would otherwise
    mistake for server settings — read from the installed driver's signature."""
    import inspect

    import asyncpg

    names = {p.name for p in inspect.signature(asyncpg.connect).parameters.values()}
    return frozenset(names - _NOT_FROM_URL - _ASYNCPG_DSN_VOCABULARY)


def _coerce(value: str) -> Any:
    """A URL carries strings; asyncpg's connection arguments are typed.

    Booleans first (``direct_tls=false`` must not arrive as the truthy string
    ``"false"``), then integers, then floats; anything else stays the string it
    was (``ssl=require``, a path, …).
    """
    low = value.strip().lower()
    if low in _TRUE:
        return True
    if low in _FALSE:
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def asyncpg_connect_args(dsn: str) -> tuple[str, dict[str, Any]]:
    """Split ``dsn`` into ``(dsn, connect_kwargs)`` safe to hand to asyncpg.

    Returns the URL with its connection arguments removed, plus those arguments
    as keywords. A DSN with nothing to translate is returned unchanged (same
    object identity of content — no normalization side effects).
    """
    if "://" not in dsn:
        return dsn, {}  # libpq keyword/value form — not ours to rewrite
    parsed = urlparse(dsn)
    base_scheme = parsed.scheme.split("+", 1)[0].lower()
    if base_scheme not in ("postgres", "postgresql"):
        return dsn, {}

    lift = _connection_params()
    kept: list[tuple[str, str]] = []
    connect_kwargs: dict[str, Any] = {}
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key in lift:
            connect_kwargs[key] = _coerce(value)
        else:
            kept.append((key, value))

    if not connect_kwargs and parsed.scheme == base_scheme:
        return dsn, {}
    return urlunparse(parsed._replace(
        scheme=base_scheme, query=urlencode(kept),
    )), connect_kwargs
