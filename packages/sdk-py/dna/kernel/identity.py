"""``metadata.id`` — the instance's identity, separate from its address.

Until i-114 an instance had exactly ONE identifier: its ``name``, which was
also its address. That made every rename a deletion: the Tier→PricingPlan
rename left dead names in three places for months, LessonLearned→Engram left a
``lessons-learned/`` container behind, and the ``dna-cloud-dev``→``dna-cloud``
scope rename orphaned a Genome and three Engrams that nobody found until six
weeks later. In each case *changing the address erased the identity*, because
there was no identity underneath it.

The fix is NOT "reference things by id". That is the trade the issue almost
made, and it is the wrong one: the whole differential of keeping definitions in
git is that a human reads the diff, and ``01JQZX7K3M...`` in a diff is a
regression disguised as rigour. Logseq is the measured counter-example — it
writes ``((1e514c8c-a6d4-…))`` into authored text, and the same file opened in
Obsidian shows the raw UUID, because only Logseq can resolve it. Durability
bought with legibility and portability.

**The rule comes from Kubernetes**, whose ``apiVersion/kind/metadata/spec``
grammar this project already speaks, so it is doctrine rather than analogy:
identity and reference are not a choice between name and id — they are
**separated by who writes them**.

* A reference a HUMAN authors (``configMapRef``, ``secretRef``,
  ``serviceAccountName``) carries **only the name**. Their stated reason is
  ours: the API exists "for humans to author and read directly as declarative
  configuration".
* A reference a MACHINE writes (``ownerReferences``, posted by a controller)
  carries **name AND uid** — because deleting and recreating under the same
  name is a DIFFERENT object, and a controller must not re-attach to the wrong
  one.

Translated here, with no strain:

* the ``.dna/`` YAML that is authored and reviewed in a PR keeps the **name**;
* ``dna_edges``, which the write path DERIVES, keeps **id and name**
  (``to_id`` beside ``to_name``).

The two house principles that looked like they contradicted each other — "the
diff must stay legible" and "a rename must not break anything" — do not: they
hold in different LAYERS. "Legible" is about what is authored. "Unbroken" is
about what is derived.

``metadata.id`` itself DOES live in the file, and that is not an exception to
the rule. An id in the frontmatter is the instance saying what it *is*; it is
not a reference to anything, so it costs the reader nothing (one opaque line on
an instance they were reading anyway) and it is what lets a re-seed of ``.dna/``
carry the identity across instead of reinventing it. What never enters an
authored file is the id of the TARGET of a reference.

Shape of the id
---------------

Short, lowercase, typable, and resolvable by **unique prefix** — the model git,
jujutsu and git-bug all converged on for the same reason: an identifier a human
must occasionally quote should be quotable in six characters even though it is
twelve. The alphabet is RFC-4648 lowercase base32 ``[a-z2-7]``, which is
already this house's id alphabet (``new_workspace_id`` in
``dna.application.runtime``) and excludes ``0`` and ``1``, the two characters
that get confused with ``o`` and ``l``.

An ambiguous prefix is a REFUSAL, never a silent pick. That is the one rule
this module exists to make impossible to get wrong, so the arbitration lives
HERE — in the kernel, as a pure function over candidates — and not in each
store, where a second adapter would eventually round it differently.

Prior art, and what was and was not adopted
-------------------------------------------

Searched before writing (the house rule): the already-installed dependency
tree, then GitHub. ``python-ulid`` is present in the sdk-py venv but only
transitively (via ``redisvl``, an optional extra) and absent from the CLI venv
entirely, so it is not a dependency this package may lean on; ``shortuuid``
(2.2k★) and ``base32-crockford`` (51★) generate ids but neither resolves a
prefix. Nothing packages prefix resolution, and the reason is structural:
resolving a prefix is a query against YOUR OWN index, so a library cannot own
it. What WAS adopted is the design — git/jujutsu/git-bug's unique-prefix
convention, and Kubernetes' who-writes-it separation — plus the alphabet and
entropy convention already used by ``new_workspace_id``. Generation is
``secrets`` from the standard library; adding a dependency to draw twelve
random characters would be worse than writing them.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

__all__ = [
    "INSTANCE_ID_ALPHABET",
    "INSTANCE_ID_LENGTH",
    "MIN_PREFIX_LENGTH",
    "AmbiguousInstanceId",
    "InstanceRef",
    "PrefixTooShort",
    "UnknownInstanceId",
    "derived_instance_id",
    "instance_id_of",
    "is_instance_id",
    "is_instance_id_prefix",
    "mint_instance_id",
    "resolve_unique_prefix",
    "stamp_instance_id",
]

#: RFC-4648 base32, lowercased — the alphabet ``new_workspace_id`` already
#: uses. No ``0``/``1`` (confusable with ``o``/``l``), no case to get wrong on
#: a case-insensitive filesystem, no character that needs percent-encoding in
#: a URL path segment.
INSTANCE_ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"

#: 12 characters × 5 bits = 60 bits. Long enough that a full id never collides
#: (birthday probability below 1e-9 at a million instances), short enough to
#: read aloud and retype. The *prefix* is what anyone actually quotes.
INSTANCE_ID_LENGTH = 12

#: Below this, a prefix is a typo rather than a question. Four characters is
#: 20 bits — one in a million against a store of a thousand instances — and
#: refusing shorter is kinder than answering "ambiguous" to ``a``.
MIN_PREFIX_LENGTH = 4

_ALPHABET_SET = frozenset(INSTANCE_ID_ALPHABET)


class UnknownInstanceId(LookupError):
    """No instance in the searched space has an id with this prefix."""


class AmbiguousInstanceId(LookupError):
    """More than one instance matches the prefix.

    A refusal, never a choice. Picking the first match would be the failure
    mode this whole feature exists to prevent: a reference that silently
    resolves to the wrong object reads exactly like one that resolved to the
    right one.
    """

    def __init__(self, prefix: str, matches: "list[InstanceRef]") -> None:
        self.prefix = prefix
        self.matches = matches
        shown = ", ".join(
            f"{m.id} ({m.kind} {m.name!r} in {m.scope!r})"
            for m in sorted(matches, key=lambda m: m.id)[:8]
        )
        more = "" if len(matches) <= 8 else f" … and {len(matches) - 8} more"
        super().__init__(
            f"instance id prefix {prefix!r} matches {len(matches)} instances "
            f"— refusing to guess which. Lengthen the prefix: {shown}{more}"
        )


class PrefixTooShort(ValueError):
    """The prefix is shorter than :data:`MIN_PREFIX_LENGTH`, or empty."""


@dataclass(frozen=True)
class InstanceRef:
    """The coordinates an id resolves TO — everything needed to read the
    instance, plus the id that got you here.

    ``api_version`` is part of it because it is part of the storage key
    (revision 0003): two workspaces may each own a Kind called ``Deal``, and a
    ref that omitted it would name two rows.
    """

    id: str
    scope: str
    kind: str
    api_version: str
    name: str
    tenant: str | None = None


def mint_instance_id() -> str:
    """A fresh, random instance id.

    RANDOM, not derived from the content, and the reason is that a content
    hash destroys the property this feature is bought for. An id derived from
    content changes when the content changes — so editing an instance would
    give it a new identity, which is precisely the breakage a rename causes
    today, moved to a new trigger. (git-bug hashes, but it hashes the
    IMMUTABLE creation operation, not the current state; there is no such
    frozen first act here to hash.)

    Random also gets the delete-and-recreate case right for free: recreating
    under the same name yields a DIFFERENT id, which is exactly what
    Kubernetes' uid says about the same event, and what makes a stale
    ``dna_edges.to_id`` legible as "that object is gone" instead of silently
    correct.

    ``secrets.choice`` over the alphabet rather than base32-encoding random
    bytes: it gives exactly 60 uniform bits with no padding to strip and no
    truncation to reason about.
    """
    return "".join(secrets.choice(INSTANCE_ID_ALPHABET)
                   for _ in range(INSTANCE_ID_LENGTH))


def derived_instance_id(
    *, tenant: str | None, scope: str, api_version: str, kind: str, name: str,
) -> str:
    """The id an instance that predates this feature gets — DERIVED from its
    natural key, and used by the backfill ONLY.

    This does not contradict :func:`mint_instance_id`. The migration has a
    problem a new write does not: the same instances exist in TWO stores that
    must agree — the Postgres rows and the ``.dna/`` YAML in git — and they are
    migrated by different code at different times. A random mint would give the
    same instance one id in the database and another on disk, and the ``to_id``
    column would then be right in one store and wrong in the other from the
    first day. Deriving from the natural key makes the backfill *convergent*:
    run it against the database, run it against the files, run it again after a
    re-seed, and get the same ids.

    The obvious objection — "derived from the name means a rename changes the
    id, which is the bug" — does not apply, because derivation happens ONCE, at
    the moment of migration, for instances that exist then. The value is stored
    from that point on and never recomputed. Every id minted afterwards is
    random. What is derived here is a starting value, not a rule.

    BLAKE2b with a domain-separated key: the fields are joined with ``\\x00``,
    which no field may contain, so no two different keys can produce the same
    input string.
    """
    key = "\x00".join((
        "dna.instance.v1",
        tenant or "",
        scope,
        api_version or "",
        kind,
        name,
    ))
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=16).digest()
    value = int.from_bytes(digest, "big")
    out: list[str] = []
    for _ in range(INSTANCE_ID_LENGTH):
        out.append(INSTANCE_ID_ALPHABET[value & 31])
        value >>= 5
    return "".join(out)


def is_instance_id(value: object) -> bool:
    """Is this a well-formed, FULL instance id?"""
    return (
        isinstance(value, str)
        and len(value) == INSTANCE_ID_LENGTH
        and _ALPHABET_SET.issuperset(value)
    )


def is_instance_id_prefix(value: object) -> bool:
    """Could this be the beginning of an instance id? (Length is not checked
    against :data:`MIN_PREFIX_LENGTH` — that is a policy the resolver applies,
    not a fact about the string.)"""
    return (
        isinstance(value, str)
        and 0 < len(value) <= INSTANCE_ID_LENGTH
        and _ALPHABET_SET.issuperset(value)
    )


def instance_id_of(raw: object) -> str | None:
    """The ``metadata.id`` of a raw instance envelope, or ``None``.

    Tolerant of both shapes the getters hand back (a raw dict, a parsed
    instance object) for the same reason ``_spec_of`` in
    ``dna.kernel.query.references`` is: reading through only one of them turns
    a check into something that is silently always ``None`` on the other.
    Anything that is not a well-formed id reads as absent — a malformed value
    must not be mistaken for identity.
    """
    if raw is None:
        return None
    meta: object
    if isinstance(raw, dict):
        meta = raw.get("metadata")
    else:
        meta = getattr(raw, "metadata", None)
    if not isinstance(meta, dict):
        meta = getattr(meta, "__dict__", None) if meta is not None else None
        if not isinstance(meta, dict):
            return None
    value = meta.get("id")
    return value if is_instance_id(value) else None


def stamp_instance_id(raw: dict, instance_id: str) -> dict:
    """Write ``metadata.id`` into a raw envelope, in place, and return it.

    ``id`` is inserted so it sits FIRST in ``metadata`` on a freshly built
    envelope, which is where a reader expects identity — but an existing
    ``metadata`` is never reordered, because rewriting key order on every save
    would put noise in every diff, which is the cost this design is spending
    everything to avoid.
    """
    meta = raw.get("metadata")
    if not isinstance(meta, dict):
        raw["metadata"] = {"id": instance_id}
        return raw
    if meta.get("id") == instance_id:
        return raw
    if "id" in meta:
        meta["id"] = instance_id
        return raw
    # Fresh key: rebuild so ``id`` leads, then ``name``, then the rest as
    # authored.
    rebuilt = {"id": instance_id}
    rebuilt.update(meta)
    raw["metadata"] = rebuilt
    return raw


def resolve_unique_prefix(
    prefix: str, candidates: "list[InstanceRef]",
) -> InstanceRef:
    """Arbitrate a prefix against the candidates a store found.

    The whole point of this being a pure function in the kernel: there is ONE
    rule, and every store gets it. A store that did its own arbitration would
    eventually round the tie differently, and the two would disagree exactly
    when it mattered.

    Exact-id wins over prefix: if one candidate's id IS the query, it is not
    ambiguous no matter how many other ids start with it — that case cannot
    arise at a fixed id length, but stating it here keeps the rule from
    changing meaning if the length ever does.
    """
    if not isinstance(prefix, str) or len(prefix) < MIN_PREFIX_LENGTH:
        raise PrefixTooShort(
            f"instance id prefix {prefix!r} is too short — give at least "
            f"{MIN_PREFIX_LENGTH} characters. A prefix this short would match "
            f"most of the store, and answering 'ambiguous' to it would hide "
            f"that the real problem is the query."
        )
    if not is_instance_id_prefix(prefix):
        raise PrefixTooShort(
            f"{prefix!r} is not an instance id prefix — ids use only "
            f"[a-z2-7] and are {INSTANCE_ID_LENGTH} characters long."
        )
    if not candidates:
        raise UnknownInstanceId(
            f"no instance has an id starting with {prefix!r}"
        )
    exact = [c for c in candidates if c.id == prefix]
    if len(exact) == 1:
        return exact[0]
    if len(candidates) > 1:
        raise AmbiguousInstanceId(prefix, list(candidates))
    return candidates[0]
