"""Channels — DNAP's addressing (spec §3).

::

    dnap-root://                    connection-level operations
    dnap-scope:/<scope>             one scope's instances
    dnap-scope:/<scope>#<tenant>    the tenant overlay of that scope

⭐ **Scope is an ADDRESS, not a parameter**, and this module exists to make the
difference mechanical. The defect it corrects was measured on DNA's REST face:
``?scope=`` was accepted and silently ignored, so one scope's content came back
under another scope's name. A parameter can be dropped by a framework and
nobody notices; an address cannot be dropped, because a request without one
does not parse — and a request naming a channel this server does not serve is
:data:`~dna.protocol.errors.CHANNEL_NOT_SERVED`, **never** answered from a
channel the server does serve.

The refusal is the load-bearing half. :meth:`ChannelSet.require` has no
fallback branch by construction: there is no code path from "you asked for
``dnap-scope:/acme``" to "here is ``dnap-scope:/dna-cloud``".

## The tenant overlay (§3, added by the clean-room revision — gap A12)

``dnap-scope:/<scope>#<tenant>`` was *"an address with no semantics at all —
one line of text, three rules invented"*. The three rules the spec now states,
and where each is satisfied here:

**read-through** — an instance absent from the overlay resolves to the base
channel's. This is the DNA kernel's layer resolution, unchanged: the tenant is
threaded to ``kernel.get_instance`` / ``kernel.query`` and the base layer
answers what the overlay does not carry.

**write-local** — a write on the overlay lands in the overlay and never touches
the base. Also the kernel's, via ``_write_tenant`` in
:mod:`dna.application.instances`; the one exception is a ``TenantScope.GLOBAL``
Kind, for which the kernel refuses a tenant outright rather than writing to the
base under a tenant's name.

**no tombstones** — a delete on the overlay removes the tenant's own version
and reveals the base one again; it cannot hide a base instance. *"Hiding would
make 'this tenant has no X' and 'this tenant deleted X' indistinguishable to
every reader, which is §7's rule wearing another face."*

**Each channel carries its own ``revision`` sequence** — a base write does not
advance the overlay's. :func:`dna.protocol.revision.channel_revision` is keyed
on ``(scope, tenant)`` for exactly this reason; whether a given store honours
the separation is the store's to answer, and one that cannot serve a watermark
at all reports ``null`` rather than borrowing the base's.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from dna.protocol.errors import DnapError

__all__ = ["ROOT", "Channel", "ChannelSet", "parse_channel"]

ROOT_URI = "dnap-root://"
SCOPE_PREFIX = "dnap-scope:/"

#: A scope or tenant segment. Deliberately narrow: DNA scopes are directory
#: names and SQL key parts (``dna-cloud``, ``tenant-acme``), and a permissive
#: grammar here would push escaping decisions onto every adapter below.
_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True, slots=True)
class Channel:
    """A parsed channel URI. ``scope is None`` iff this is the root channel."""

    scope: str | None
    tenant: str | None = None

    @property
    def is_root(self) -> bool:
        return self.scope is None

    @property
    def uri(self) -> str:
        if self.scope is None:
            return ROOT_URI
        return (
            f"{SCOPE_PREFIX}{self.scope}"
            + (f"#{self.tenant}" if self.tenant else "")
        )

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.uri


#: The connection-level channel (``initialize``, and the default for ``kinds/*``).
ROOT = Channel(scope=None)


def parse_channel(raw: object) -> Channel:
    """Parse a channel URI, or raise ``-32602``.

    ⚠️ A **malformed** URI and an **unserved** one are different failures and
    get different codes on purpose. ``-32602`` says *"that is not a channel"*;
    ``-32004`` says *"that is a channel, and not mine"*. A client that cannot
    tell them apart cannot tell a typo from a wrong server.
    """
    if not isinstance(raw, str) or not raw:
        raise DnapError.invalid_params(
            "`channel` must be a channel URI string "
            f"({ROOT_URI!r} or {SCOPE_PREFIX + '<scope>[#<tenant>]'!r})",
            got=None if not isinstance(raw, str) else raw,
        )
    if raw == ROOT_URI:
        return ROOT
    if not raw.startswith(SCOPE_PREFIX):
        raise DnapError.invalid_params(
            f"unknown channel scheme in {raw!r} — DNAP addresses are "
            f"{ROOT_URI!r} and {SCOPE_PREFIX + '<scope>[#<tenant>]'!r}",
            channel=raw,
        )
    body = raw[len(SCOPE_PREFIX):]
    scope, sep, tenant = body.partition("#")
    if not _SEGMENT.match(scope):
        raise DnapError.invalid_params(
            f"{raw!r} has no usable scope segment — expected "
            f"{SCOPE_PREFIX + '<scope>'!r} with <scope> matching "
            f"{_SEGMENT.pattern}",
            channel=raw,
        )
    if sep and not _SEGMENT.match(tenant):
        raise DnapError.invalid_params(
            f"{raw!r} has an empty or malformed tenant segment after '#'",
            channel=raw,
        )
    return Channel(scope=scope, tenant=tenant if sep else None)


class ChannelSet:
    """The channels one server serves — and the refusal for everything else.

    A server is constructed with the scopes it serves. A tenant overlay
    (``…#acme``) is served iff its scope is; the tenant is a layer *of* that
    scope, and refusing it separately would require this class to know the
    tenant registry, which is the kernel's job and not addressing's.
    """

    def __init__(self, scopes: Iterable[str], *, default: str | None = None) -> None:
        self._scopes = tuple(dict.fromkeys(str(s) for s in scopes))
        if not self._scopes:
            raise ValueError("a DNAP server must serve at least one scope")
        for s in self._scopes:
            if not _SEGMENT.match(s):
                raise ValueError(f"not a usable scope name: {s!r}")
        self._default = default or self._scopes[0]
        if self._default not in self._scopes:
            raise ValueError(
                f"default scope {self._default!r} is not among the served "
                f"scopes {self._scopes!r}"
            )

    @property
    def scopes(self) -> tuple[str, ...]:
        return self._scopes

    @property
    def default_scope(self) -> str:
        return self._default

    def advertised(self) -> list[str]:
        """The ``channels`` member of the ``initialize`` result."""
        return [f"{SCOPE_PREFIX}{s}" for s in self._scopes]

    def serves(self, channel: Channel) -> bool:
        return channel.is_root or channel.scope in self._scopes

    def require(self, channel: Channel) -> Channel:
        """``channel`` if served, else ``-32004``. There is no third branch."""
        if self.serves(channel):
            return channel
        raise DnapError.channel_not_served(channel.uri, self.advertised())

    def require_scope(self, channel: Channel) -> Channel:
        """Like :meth:`require`, and additionally refuses the ROOT channel.

        ``instances/*`` acts on instances, and the root channel holds none.
        Answering it from the default scope would be exactly the substitution
        §3 forbids — so root is refused with ``-32004`` naming the scope
        channels that would work.
        """
        if channel.is_root:
            raise DnapError.channel_not_served(ROOT_URI, self.advertised())
        return self.require(channel)
