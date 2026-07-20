"""The shape of a generated ``workspace_id`` — decision **D5**.

The id stopped being the Azure ``tid`` and became a server-minted value. That
makes its FORMAT load-bearing in four independent places, each of which can be
broken by an innocent-looking change to the generator:

* the kernel ``tenant`` column value;
* a filename — ``_lib/workspaces/<id>.yaml``;
* a scope name — ``tenant-<id>`` (``LiveDna.default_scope``);
* a URL path segment — ``/w/<id>/mcp``.

And one security property: it must be UNGUESSABLE. That is not decoration — the
post-D5 anti-takeover argument rests on it. The old guard prevented takeover by
comparing tids; the new one prevents it by making the id un-nameable. If ids
became sequential or derived, "you can't claim what you can't name" would stop
being true and the guard would have nothing behind it.
"""
from __future__ import annotations

import re

from dna.application.runtime import new_workspace_id, slugify

_ID_RE = re.compile(r"^ws-[a-z2-7]{24}$")


def test_the_id_is_url_file_and_scope_safe():
    """Lowercase base32 only. No ``/``, no ``.``, no uppercase (which would
    collide on a case-insensitive filesystem), nothing needing percent-encoding."""
    for _ in range(50):
        wid = new_workspace_id()
        assert _ID_RE.match(wid), wid
        assert wid == wid.lower()
        assert not (set(wid) - set("abcdefghijklmnopqrstuvwxyz234567-"))


def test_the_id_carries_no_meaning():
    """OPAQUE. It must not embed a counter, a timestamp, an email or a tid — an
    id that encodes tenancy facts leaks them to everyone who sees a URL."""
    ids = [new_workspace_id() for _ in range(20)]
    bodies = [i[len("ws-"):] for i in ids]
    # No shared prefix beyond the literal namespace tag (a timestamp or counter
    # prefix would make consecutive ids share leading characters).
    assert len({b[:6] for b in bodies}) == len(bodies)


def test_ids_are_unguessable_and_do_not_repeat():
    """120 bits of entropy per id. Sampling cannot prove randomness, but a
    generator that has silently become sequential/constant fails here."""
    ids = {new_workspace_id() for _ in range(2000)}
    assert len(ids) == 2000


def test_the_id_never_contains_the_membership_key_separator():
    """WorkspaceMembership docs are named ``{workspace_id}--{email}``. An id
    containing ``--`` would make that key ambiguous."""
    for _ in range(200):
        assert "--" not in new_workspace_id()


# ── slug: presentation over a stable id (the GitHub model) ──────────────────


def test_slugify_folds_a_display_name_to_a_handle():
    assert slugify("Barnabé Labs") == "barnabe-labs"
    assert slugify("  ACME   Corp.  ") == "acme-corp"
    assert slugify("a/b\\c") == "a-b-c"
    assert slugify("Ünïcôdé Ñämè") == "unicode-name"


def test_slugify_returns_empty_rather_than_inventing_a_name():
    """Data honesty: when nothing usable survives, say so. The caller falls back
    to the id — this function never fabricates a handle."""
    assert slugify("") == ""
    assert slugify("   ") == ""
    assert slugify("!!!") == ""
    assert slugify("日本語") == ""
