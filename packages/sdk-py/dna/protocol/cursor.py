"""Cursors — opaque to the client, and pinned to one snapshot (spec §6.2).

    *"``cursor``, never offset. Offset pagination is ``OFFSET n`` in SQL and
    degrades quadratically. A cursor MAY expire; an expired cursor MUST answer
    ``-32005 CURSOR_EXPIRED`` so the client restarts rather than silently
    skipping."*

Two things the cursor buys that an offset cannot:

1. **Opacity is what makes the offset replaceable.** The store underneath still
   pages by offset today (``list_instances_impl`` → ``kernel.query(offset=…)``,
   and the SQL adapter really does emit ``OFFSET n``). Because the client never
   sees that number, moving to a keyset cursor is an implementation change, not
   a wire change. Shipping the offset as the wire contract is what makes the
   quadratic cost permanent — that is the difference this module exists for,
   and the underlying pagination is a named follow-up, not a claim.

2. **The cursor carries the listing's identity**, so a page cannot be
   reinterpreted. It pins the channel, the Kind, the ``select`` shape and the
   snapshot ``revision``. A page-2 request that changes any of them is not a
   continuation of that listing:

   * a **different shape or address** is the caller's mistake → ``-32602``;
   * a **moved snapshot** is nobody's mistake → ``-32005``, restart.

   Rule 3 (*``revision`` is constant across a paginated read*) is enforced by
   this pin rather than promised by it: page N returns the revision recorded at
   page 1, and the moment that revision stops matching the store, the listing
   is over instead of quietly continuing against a different state.

The encoding is base64url of compact JSON — no padding, URL-safe, and
deliberately not a format a client is invited to read. Nothing secret travels
in it, so it is not signed; it is opaque, not confidential.
"""
from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any

from dna.protocol.errors import DnapError

__all__ = ["Cursor", "decode_cursor", "encode_cursor"]

#: Bumped whenever the payload's meaning changes. An unrecognised version is
#: ``-32005``, not ``-32602``: a cursor minted by another build of this server
#: is a valid cursor the server can no longer honour, and "restart the listing"
#: is exactly the right remedy.
_VERSION = 1


@dataclass(frozen=True, slots=True)
class Cursor:
    """The state one listing carries from page to page."""

    channel: str
    kind: str
    select: str
    offset: int
    revision: str | None

    def encode(self) -> str:
        payload = {
            "v": _VERSION, "c": self.channel, "k": self.kind,
            "s": self.select, "o": self.offset, "r": self.revision,
        }
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def encode_cursor(
    *, channel: str, kind: str, select: str, offset: int, revision: str | None,
) -> str:
    return Cursor(
        channel=channel, kind=kind, select=select, offset=offset,
        revision=revision,
    ).encode()


def decode_cursor(
    raw: object, *, channel: str, kind: str, select: str,
) -> Cursor:
    """Decode and validate a cursor against the request that presented it.

    Raises ``-32602`` when the cursor belongs to a different listing and
    ``-32005`` when it cannot be honoured at all.
    """
    if not isinstance(raw, str) or not raw:
        raise DnapError.invalid_params(
            "`cursor` must be the opaque string a previous page returned",
        )
    try:
        pad = "=" * (-len(raw) % 4)
        payload = json.loads(base64.urlsafe_b64decode(raw + pad))
    except (ValueError, binascii.Error) as exc:
        raise DnapError.cursor_expired(
            f"this cursor cannot be read ({exc}) — restart the listing without "
            f"a cursor. A cursor is opaque: it is only ever a value a previous "
            f"page handed you."
        ) from exc
    if not isinstance(payload, dict) or payload.get("v") != _VERSION:
        raise DnapError.cursor_expired(
            "this cursor was minted by a different version of this server — "
            "restart the listing without a cursor."
        )
    got_channel, got_kind, got_select = (
        payload.get("c"), payload.get("k"), payload.get("s"),
    )
    if (got_channel, got_kind, got_select) != (channel, kind, select):
        raise DnapError.invalid_params(
            "this cursor belongs to a different listing "
            f"(cursor: channel={got_channel!r} kind={got_kind!r} "
            f"select={got_select!r}; request: channel={channel!r} "
            f"kind={kind!r} select={got_select and select!r}). All pages of one "
            "listing share one address and one shape — start a new listing "
            "instead of continuing this one under different terms.",
            cursor_channel=got_channel, cursor_kind=got_kind,
        )
    offset = payload.get("o")
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise DnapError.cursor_expired(
            "this cursor carries no usable position — restart the listing."
        )
    revision = payload.get("r")
    if revision is not None and not isinstance(revision, str):
        raise DnapError.cursor_expired(
            "this cursor carries no usable revision — restart the listing."
        )
    return Cursor(
        channel=channel, kind=kind, select=select, offset=offset,
        revision=revision,
    )


def require_same_snapshot(cursor: Cursor, current: str | None) -> None:
    """Rule 3, enforced: the pages of one listing belong to one snapshot.

    When the store serves a watermark and it has moved, the listing is over:
    ``-32005``. When the store serves none, both values are ``None`` and there
    is nothing to check — the ``revision: null`` the listing reports already
    says the server cannot date the snapshot, so this is not a check that
    silently passed, it is a check with nothing to compare.
    """
    if cursor.revision is None and current is None:
        return
    if cursor.revision != current:
        raise DnapError.cursor_expired(
            f"the channel moved while you were paging (listing snapshot "
            f"{cursor.revision!r}, store now {current!r}) — restart the "
            f"listing. Continuing would hand you pages from two different "
            f"states and no way to tell which row came from which."
        )
