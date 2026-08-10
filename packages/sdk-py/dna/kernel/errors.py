"""Kernel error vocabulary — boot-time registration failures, and the marker
base every deliberate REFUSAL shares.

H1 — Boot-time validation. The Kernel's `kind/reader/writer/load`
registration methods used to be `self._x.append(y)` no-ops with zero
validation. Result: a typo in `detect()` made the Reader silently
ignored; two bundle Readers using the same marker file collided
(first-registered wins, depending on entry-point alphabetical order);
duplicate `(api_version, kind)` registrations silently overwrote.

These errors surface those problems at boot time instead of as silent
runtime drift. They subclass ``ValueError`` so existing code that
broadly catches ``ValueError`` still works.
"""
from __future__ import annotations


class KernelRefusal(Exception):
    """Marker base for a DELIBERATE kernel refusal — "no, and here is why".

    Not an error class in the usual sense: it says nothing about what went
    wrong, only that the kernel *decided*. A schema veto, a LayerPolicy veto, a
    tenancy rule, a read-only source, a retired Kind — each is a verdict the
    caller can act on, and each therefore has to REACH the caller with its
    reason intact.

    It exists because every face was enumerating them instead, and getting the
    enumeration wrong. The MCP write tool caught
    ``(ValueError, LookupError, PermissionError)``; but
    :class:`~dna.kernel.protocols.LayerPolicyViolationError`,
    :class:`~dna.kernel.protocols.TenantNotAllowed`,
    :class:`~dna.kernel.protocols.TenantRequired` and
    :class:`~dna.kernel.protocols.InvalidTenantSlug` are plain ``Exception`` and
    :class:`~dna.kernel.NotWritableError` is a ``RuntimeError``, so not one of
    them matched — the likeliest refusal on a tenant write reached the client as
    an unexplained failure. A marker base turns "catch the right N types" into
    "catch one", and a refusal declared tomorrow is relayed by every face that
    already exists.

    **Additive, never a re-parenting.** Each refusal keeps the base it always
    had (``ValueError`` for the schema veto, ``RuntimeError`` for the read-only
    source), so code that catches them the old way is untouched. Guarded by
    ``packages/sdk-py/tests/test_kernel_refusal_base.py``, which also pins the
    kernel exceptions that are deliberately NOT refusals — so a new exception
    type in these modules forces the decision instead of defaulting to
    "uncaught".
    """


class CapabilityRefusal(Exception):
    """Marker base for *the STORE wired into this deployment cannot answer that*.

    Sibling of :class:`KernelRefusal`, and the distinction between the two is
    the reason there are two. ``KernelRefusal`` is a **verdict about the
    request**: policy looked at what you asked for and said no, so the remedy is
    a different request (fix the instance, take another name, obtain the grant).
    This one is not about the request at all — it was well formed and the caller
    was entitled to it. What is missing is a capability of the ADAPTER, and the
    remedy is a different deployment, never a different call. Relaying one as
    the other sends the caller hunting for an entitlement they already have.

    Every member exists to refuse a **confident lie**, because in each case the
    plausible fallback is an answer no store in that state may give:

    ==============================  =========  ================================
    refusal                         REST       the lie it exists to refuse
    ==============================  =========  ================================
    ``AsOfUnsupported``             **501**    today's instance under a past
                                               timestamp
    ``AsOfTruncated``               **410**    a bare ``LookupError`` — *"it did
                                               not exist yet"* is a different
                                               statement from *"I no longer hold
                                               the record"*
    ``GraphUnsupported``            **501**    ``[]`` — reads as *nothing points
                                               at this instance*
    ``InstanceIdLookupUnsupported`` **501**    an empty result set
    ``ValidTimeUnsupported``        **501**    the instance UNFILTERED — which
                                               asserts *"yes, it was true
                                               then"* from a store with no
                                               world-time column
    ==============================  =========  ================================

    ⚠️ ``AsOfUnsupported`` and ``ValidTimeUnsupported`` are two axes, not two
    spellings: the first is TRANSACTION time (*what did you believe at T*), the
    second is WORLD time (*when was it true*). A deployment can have either
    without the other, and the SQLite binding of ``SqlAlchemySource`` is exactly
    that case — full version history, no validity column.

    **Why a base and not a tuple.** There was a tuple:
    ``dna_cli._mcp_refusals.CAPABILITY_REFUSALS`` listed the four by hand and
    said so in its own docstring, because the four inherit from
    ``RuntimeError`` / ``NotImplementedError`` / ``LookupError`` and scatter
    across the builtin hierarchy — no ``except`` reached them as a family, and
    only the one that happened to be a ``LookupError`` fell inside a tuple the
    MCP face already caught. So ``recall(as_of=…)`` against a store with no
    version history reached the client as FastMCP's ``Error calling tool
    'recall'``: the documented refusal, delivered in the shape of a crash. This
    house has measured what per-face enumeration costs — it is the same defect
    ``KernelRefusal`` was created to end, one category over. A face catches one
    name now, and a capability refusal declared tomorrow is relayed by every
    face written today.

    **Additive, never a re-parenting.** Each member keeps the builtin base it
    always had (``RuntimeError`` for the two "this adapter cannot",
    ``LookupError`` for the pruned history, ``NotImplementedError`` for the id
    lane), so ``except LookupError`` around an as-of read keeps behaving exactly
    as it did. Guarded by ``packages/sdk-py/tests/test_capability_refusal_base.py``
    (the family, its bases, and the fact that the two marker bases stay
    disjoint) and by ``packages/cli/tests/test_face_refusal_parity.py``, which
    derives from the REST face's own source that anything it answers 501/410
    carries this base.

    ⚠️ **Not a ``KernelRefusal``, and the ratchet says so on purpose.**
    ``tests/test_kernel_refusal_base.py`` lists ``GraphUnsupported`` and
    ``InstanceIdLookupUnsupported`` under ``_NOT_REFUSALS`` with a paragraph
    each explaining that they are statements about the deployment. That
    classification does not change here; it acquires a name.
    """


class StoreUnavailable(CapabilityRefusal, FileNotFoundError):
    """The STORE this adapter is configured against is not there at all.

    The fifth member of the capability family, and it exists to separate two
    absences a face could not tell apart (i-142).

    ⚠️ **"Absent because it never existed" and "absent because the store is
    gone" are different facts, and only the ADAPTER can tell them apart.**

    * A **SCOPE** that holds nothing is EMPTY. Every store says so by
      answering ``[]`` — measured on SQLite and on a real Postgres — and the
      filesystem adapter was the only one that raised, because on disk a scope
      is a DIRECTORY and an absent directory looks like an error. It is not:
      the first write auto-creates it, so nothing is wrong and nothing needs
      provisioning. That case answers ``[]`` now, like everywhere else.
    * A **STORE ROOT** that is not a directory is a DEPLOYMENT fault — a
      wrong ``DNA_BASE_DIR``, an unmounted volume, a path that was never
      created. The request was well formed and the caller was entitled to it;
      what is missing is the deployment. That is this class, and it is the
      definition of :class:`CapabilityRefusal`.

    WHAT IT COST TO NOT HAVE THIS. ``assign_namespace`` READS the
    ``KindNamespace`` claim registry in ``_lib`` before it mints, so on a
    brand-new ``.dna`` the very first Kind authored anywhere failed with
    ``FileNotFoundError: Scope not found: <base>/_lib`` — and **four** places
    grew a handler for it: ``dna new kind``'s ``_no_registry`` (names the fix),
    ``dna_cli._mcp_kinds.NO_REGISTRY`` (tells the agent to ask an operator),
    the REST face's four ``except (NamespaceRegistryUnreadable,
    FileNotFoundError)`` arms (503), and ``dna.application.sdlc.existing_or_none``
    (treats it as an absent instance). Every one of them is RIGHT for a store
    that LOST its ``_lib`` and WRONG for a store that never had one — and none
    of them could tell, because a builtin ``FileNotFoundError`` carries no such
    distinction and is also what an absent bundle entry and an absent template
    file raise. A fifth handler would have been a fifth guess.

    ⚠️ **The honest limit, written down rather than implied.** Once a scope
    directory is gone, this adapter cannot tell "deleted" from "never created",
    and neither can Postgres once the rows are deleted. No store can date an
    absence. What a store CAN report is whether the store itself is reachable,
    and that is exactly the line drawn here.

    A ``CapabilityRefusal`` so a face relays it as a deployment problem rather
    than a denial the caller may appeal, and — additive, never a re-parenting —
    still a ``FileNotFoundError``, so every handler listed above keeps working
    unchanged. What changed is that they now fire ONLY for the case they
    describe.
    """


class InstanceNameTaken(KernelRefusal, FileExistsError):
    """An ``if_absent`` write lost the race: the name was already taken.

    The ATOMIC half of "create is never an update". ``refuse_if_exists`` closed
    the whole class of NON-concurrent overwrites — the guessed name, the retry,
    the stale board — by reading before writing, and said in its own docstring
    that the genuinely concurrent race stayed open because the kernel had no
    unique-name constraint to lean on. It does now: both shipped adapters can
    claim a name atomically (a composite primary key on the SQL side,
    ``O_CREAT|O_EXCL`` / ``mkdir`` on the filesystem), so an ``if_absent`` write
    either creates the instance or raises this — never overwrites.

    A ``KernelRefusal`` so every face relays it as an honest denial, and a
    ``FileExistsError`` so a caller allocating a name (``create_issue``) can
    catch the standard exception and try the next one.
    """


class StaleInstanceWrite(KernelRefusal, ValueError):
    """An ``if_match`` write lost the race: the stored instance is no longer the
    one the caller read, so the write would have been a LOST UPDATE.

    The UPDATE half of what :class:`InstanceNameTaken` is for creates.
    ``if_absent`` answers "this create must not become an update"; this answers
    "this update must not become somebody else's erasure". Both are arbitrated
    by the adapter against the STORE, which is the only thing that makes either
    of them true: a read-modify-write guarded in application code re-reads
    through the very cache that made the read stale (i-083 — a reviewer's 60s
    granular instance cache on one replica, an author's edit on another), and
    so compares a stale value against itself and agrees.

    The token is the ``spec`` content digest :func:`dna.kernel.etag.spec_etag`
    computes — see that function for why it is a content hash and not the
    adapter's version id.

    A ``KernelRefusal`` so every face relays it as an honest denial rather than
    a 500, and a ``ValueError`` so the doors that already map write-path vetoes
    to a client refusal surface it with no new wiring. The remedy is always the
    same and the message says it: re-read the instance and re-apply the change
    to the fresh etag.
    """


class InvalidInstanceName(KernelRefusal, ValueError):
    """An instance ``name`` is not a single, safe path component.

    An instance reaches a source adapter as a PATH COMPONENT — it is stored at
    ``<scope>/<container>/<name>/…`` or ``<container>/<name>.yaml`` — and
    nothing on the kernel write path used to say so. A caller-supplied
    ``"../../../../ESCAPED"`` was accepted end to end and wrote a file two
    levels ABOVE the store root, with the store itself left empty. The
    tenant-facing route it was measured on was never the bug: ``create_story``
    and every other application-layer writer take a raw caller ``name`` exactly
    the same way, so the guard belongs at the kernel facade every door
    inherits — beside the retired-Kind block and the tenant-slug check.

    The rule is "cannot escape or address a directory", NOT "looks like an
    identifier". No charset is imposed, because legitimate names in the wild
    include ``s-foo-bar``, ``i-065-layerpolicy-missing``,
    ``ws-1a2b3c.dna.local`` and ``ws-1a2b3c.dna.local--Contrato`` — ``.``,
    ``-`` and ``--`` are all legal. See :func:`validate_instance_name`.

    A ``KernelRefusal`` so every face relays it as an honest denial, and ALSO a
    ``ValueError`` — deliberately, for a security refusal — so a face that
    predates the marker base and still catches
    ``(ValueError, LookupError, PermissionError)`` reports it instead of
    letting it escape as a masked failure.
    """


class InvalidScopeName(KernelRefusal, ValueError):
    """A ``scope`` is not a single, safe path component.

    The twin of :class:`InvalidInstanceName`, and for the same reason: the
    filesystem adapter builds ``base_dir / scope`` (and
    ``base_dir / "tenants" / <t> / "scopes" / scope``) with no validation at
    all, and ``scope`` IS caller-supplied on the generic write door whenever
    the deployment's scope-binding regime is the permissive one — an
    unauthenticated/local caller, a single-workspace deployment, or a token
    carrying the ``*`` grant. Those regimes intend "any scope you like"; they
    do not intend "any directory you like".

    ``kind`` needs no such guard and deliberately has none: it never reaches a
    path. The adapter routes it through ``Kernel.storage_for_kind`` →
    ``StorageDescriptor.container``, a registry-DECLARED value, and an
    unregistered kind resolves to ``None`` (write at the scope root) rather
    than to the caller's string.
    """


class InvalidBundleEntry(KernelRefusal, ValueError):
    """A bundle ``entry`` is not a safe RELATIVE path inside its bundle.

    The third member of the family, and the one the first two did not cover.
    ``name`` and ``scope`` are single path COMPONENTS; an ``entry`` is a
    relative PATH — see the ``entry`` vs ``name`` note on
    ``FilesystemSource._bundle_root``. Same concept, two doors, and for a while
    only one of them was guarded.

    The hole this closes was NOT a caller passing a crafted ``entry`` to a
    bundle-entry door — ``606812c`` guarded those. It was that a bundle entry
    path is ALSO derived from instance CONTENT. ``spec.source_files``,
    ``spec.root_files``, ``spec.scripts|references|assets``, ``spec.extras`` and
    ``spec.instruction_file`` are all turned into ``relativePath`` values by the
    registered writers, and ``spec`` is copied verbatim from the caller by
    ``apply_definition_impl`` and taken as an untyped body by
    ``PUT /v1/definitions/{kind}/{name}``. Measured at HEAD through
    ``Kernel.write_instance`` on the default ``Agent`` Kind: each of those five
    fields wrote a file OUTSIDE the store root, on the base lane and on the
    tenant lane alike, and an ABSOLUTE entry wrote to an arbitrary absolute path
    (``pathlib`` joins discard the anchor when the right operand is absolute).
    An arbitrary-file-write through the kernel's own documented write facade.

    ``spec.source_files`` is a kind-AGNOSTIC documented convention
    (``pop_source_files_as_entries``, used by Tenant and TenantMembership too),
    so this was never one Kind's quirk — which is why the closing guard lives on
    the HANDLE every writer must go through (``FilesystemBundleHandle``) rather
    than on each writer. Eight of the in-repo writers call
    ``bundle.write_text(f["relativePath"], …)`` directly instead of the shared
    ``write_entries_to_handle`` sink; guarding the sink alone would have
    repeated the enumeration mistake that caused the miss.

    The rule is measured, not felt: 492 distinct real bundle entry paths across
    both repos' ``.dna/`` trees and fixtures — 482 of them carry a ``/``, the
    deepest is 8 segments, the longest 96 bytes, every one of them carries a
    dot, and ZERO have a ``..`` or ``.`` segment, are absolute, carry a
    backslash or a NUL, or exceed the bound. Subdirectories and dots stay legal
    (``skills/foo/SKILL.md`` must round-trip); escaping and directory-addressing
    do not. See :func:`validate_bundle_entry`.

    A ``KernelRefusal`` + ``ValueError`` for the same two reasons as its
    siblings.
    """


class PathEscapesStoreRoot(KernelRefusal, ValueError):
    """A path a store adapter built from caller-supplied segments resolved
    OUTSIDE that adapter's base directory.

    The SECOND layer, deliberately redundant with :class:`InvalidInstanceName`
    / :class:`InvalidScopeName`. Those guard the kernel facade — the primary
    seam, because it is the door every writer and reader goes through and it
    can name WHICH input was wrong. This one guards the filesystem adapter
    itself, which builds ``<base>/<scope>/<container>/<name>/<…>`` and until now
    trusted every segment it was handed. The kernel guard cannot help a caller
    that does not go through the kernel, and there already is one
    (``dna.kernel.source.sync`` calls ``save_instance`` directly — benignly
    today, since its names come from the source being copied rather than from a
    request), plus the public conformance kit, which drives adapters on purpose.

    Both layers are load-bearing and NEITHER is dead code: delete the kernel
    guard and a traversing name reaches disk-adjacent code before anything
    notices; delete this one and the next writer that reaches the adapter
    directly re-opens the hole. If a reviewer is about to remove one as
    redundant — that redundancy IS the design.

    Reported as a ``KernelRefusal`` (so every face relays it as an honest
    denial) and a ``ValueError`` (so a face that predates the marker base still
    reports it), exactly like its two kernel-side siblings.
    """


class RevokedKindWrite(KernelRefusal, ValueError):
    """A write was refused because its Kind has been REVOKED (i-085).

    The third state of the registration gate, and the reason it had to BE a
    state rather than the absence of approval. Approval is what confers schema
    validation and storage routing, so withdrawing it looks like it should
    simply un-register the Kind — but an unregistered Kind's instances are
    accepted with NO validation at all (measured), so un-registering LOOSENS the
    gate instead of closing it. A revoked Kind therefore stays registered,
    marked, and refuses new instances outright:

        state            existing instances      new instances
        ---------------- ---------------------- ---------------------------
        never approved   —                       accepted WITHOUT validation
        approved         valid, routed           validated against the schema
        revoked          INVALID                 REFUSED

    Refused, not "vetoed for its shape": a CONFORMING instance is refused too,
    because what was withdrawn is the Kind, not a schema. That is also why this
    is its own type and not a
    :class:`~dna.kernel.protocols.SpecValidationError` — a caller told its
    instance failed validation would go and fix the instance, and no instance
    passes.

    Deliberately NOT governed by ``DNA_WRITE_VALIDATION``. That knob trades
    strictness for the ability to load legacy data; this refusal is a
    workspace's decision about its own Kind, and an environment variable must
    not be able to overrule it.

    Existing instances are untouched — never deleted, never unreadable. They
    read back MARKED invalid (``status.valid == false``), because erasing them
    or refusing the read would destroy the ability to audit what existed, and
    the data did nothing wrong: the workspace changed its mind. Reversible in
    one act — approving again restores validity, since validity follows the
    Kind's CURRENT state and is never a stamp on the instance.

    A ``KernelRefusal`` so every face relays it as an honest denial, and a
    ``ValueError`` so a face that predates the marker base and still catches
    ``(ValueError, LookupError, PermissionError)`` reports it rather than
    letting it escape as a masked failure.
    """


class DeleteRefused(KernelRefusal, PermissionError):
    """A delete was refused because the KIND may not be removed that way.

    A verdict about the REQUEST — the remedy is a different request, never a
    different deployment — so a :class:`KernelRefusal` and emphatically not a
    :class:`CapabilityRefusal`: the store could have removed the row, and that
    is exactly the problem. It keeps ``PermissionError``, the base it was born
    with in ``dna.application.instances``, where every face already maps it to
    an honest client denial.

    It MOVED here (i-130) rather than being declared here, and the move is half
    the fix. Two refusal categories already lived on the application side and
    were consulted by exactly ONE caller — the generic MCP delete — while the
    REST memory delete, the CLI and the internal callers went straight to
    :meth:`dna.kernel.Kernel.delete_instance` and never asked. That is adequate
    for a rule about a TOOL (*"never deletable through a generic tool"*, which
    is what ``record.append-only`` says, with the purpose-built path left open).
    It is not adequate for a rule about the DATA: an Engram promises in its own
    descriptor that it is *never hard-deleted*, and a promise about the row has
    to hold at the one place every door crosses — otherwise it is a promise
    about whichever door somebody happened to guard.

    So the type lives beside :class:`TargetDeleteRestricted`, the other refusal
    on the delete path, and is raised from the same chokepoint
    (``WritePipeline.delete``). ``dna.application.instances`` re-exports the
    name, so ``D.DeleteRefused`` and ``from dna.application import
    DeleteRefused`` keep resolving to this class.
    """


class TargetDeleteRestricted(KernelRefusal, ValueError):
    """A delete was refused because something still points at the instance, and
    the relation that points at it declares ``on_target_delete: restrict``.

    The other half of referential integrity, and the half a store like ours can
    actually have. The spec that recommended this design also wrote down what
    it costs: integrity imposed by the DATABASE is not available to us, because
    everyone who has it does DDL per type in an RDBMS and that is incompatible
    with a type created at runtime. What is available is integrity of
    APPLICATION, per field — this — and every system in our group (Kubernetes,
    Foundry, Backstage, DataHub) settled in the same place.

    A :class:`KernelRefusal` and emphatically **not** a
    :class:`CapabilityRefusal`, because the distinction between the two is
    exactly the distinction between the two things that can go wrong here. This
    is a verdict about the REQUEST: the store could have deleted the row, the
    caller was entitled to ask, and policy said no. The remedy is a different
    request — delete the referrers first, or repoint them. A capability refusal
    would send the caller looking for a different deployment, which would not
    help, since the same policy is declared in the data and would travel with
    it.

    ``ValueError`` for the reason every other kernel refusal keeps a builtin
    base: a face written before the marker base existed still catches it.

    :attr:`referrers` carries the list rather than only the count, because the
    remedy IS the list. A refusal that says "47 things point at this" and makes
    the caller run a second query to find out which ones has told them they
    cannot proceed without telling them how to.
    """

    def __init__(self, message: str, *, referrers: list[dict] | None = None):
        super().__init__(message)
        #: ``{kind, name, relation}`` per referring instance — what the caller
        #: has to deal with before this delete can succeed.
        self.referrers: list[dict] = list(referrers or [])


#: Longest path component the kernel will hand an adapter, in UTF-8 BYTES.
#:
#: ``NAME_MAX`` is 255 bytes on every filesystem DNA writes to, and the
#: adapters append to the component they are given (``.yaml``, ``.md``, bundle
#: entry paths), so a bound at the ceiling would still produce ENAMETOOLONG
#: deep inside the adapter. 200 leaves that headroom and is ~3x the longest
#: name that exists in any DNA scope measured (68 bytes — a slugified insight
#: title; ``dna.extensions.intel.engine._slug`` caps its own output at 48+24).
#: Bytes, not characters, because the filesystem limit is a byte limit.
MAX_PATH_COMPONENT_BYTES = 200

#: Characters that make a string stop being ONE path component. ``/`` and
#: ``\`` split it (POSIX and Windows/UNC respectively); a NUL truncates the C
#: string the OS is eventually handed, so what gets created is not what was
#: validated.
_PATH_COMPONENT_SEPARATORS = (("/", "'/'"), ("\\", "'\\'"), ("\x00", "a NUL byte"))


def _path_component_fault(value: object) -> str | None:
    """Return why ``value`` is not a single, safe path component, or ``None``.

    Split out from the two public validators so the RULE is written once and
    the two refusals cannot drift apart.
    """
    if not isinstance(value, str):
        return f"is not a str (got {type(value).__name__})"
    if not value.strip():
        return "is empty or whitespace-only"
    for char, label in _PATH_COMPONENT_SEPARATORS:
        if char in value:
            return f"contains {label}"
    if value in (".", ".."):
        return "addresses a directory instead of naming an instance"
    size = len(value.encode("utf-8", "surrogatepass"))
    if size > MAX_PATH_COMPONENT_BYTES:
        return f"is {size} bytes (max {MAX_PATH_COMPONENT_BYTES})"
    return None


_COMPONENT_RULE = (
    "a single, safe path component: not empty or whitespace-only, no '/', "
    "'\\' or NUL, not '.' or '..', at most "
    f"{MAX_PATH_COMPONENT_BYTES} bytes. Dots, hyphens and double hyphens are "
    "fine — the rule is that it cannot escape or address a directory, not "
    "that it looks like an identifier"
)


def validate_instance_name(name: object) -> None:
    """Raise :class:`InvalidInstanceName` unless ``name`` is a safe component.

    Called by ``Kernel.write_instance`` / ``Kernel.delete_instance`` before any
    adapter is touched, so every writer — the SDLC verbs, the generic MCP write
    tool, the REST routes, an extension — inherits it without knowing it exists.
    """
    fault = _path_component_fault(name)
    if fault is not None:
        raise InvalidInstanceName(
            f"instance name {name!r} {fault} — an instance name must be "
            f"{_COMPONENT_RULE}. It is written to disk as a path component "
            f"(<scope>/<container>/<name>), so a name that traverses would "
            f"place the instance outside the store."
        )


def validate_scope_name(scope: object) -> None:
    """Raise :class:`InvalidScopeName` unless ``scope`` is a safe component.

    A NOTE ON THE ASYMMETRY, so the next reader does not mistake it for a bug:
    the WRITE and BUNDLE facades refuse ``scope=""``, ``"."`` and ``"a/b"``
    through this validator, but the READ path never calls it — reads are held to
    CONTAINMENT only (``FilesystemSource._contained``), which fires on a genuine
    escape and lets those three through. So ``list_instances(scope="a/b")``
    works today while ``write_instance(scope="a/b")`` refuses. Deliberate and
    measured, not overlooked: 12 on-disk scopes exist across both repos and not
    one contains a slash, so nothing real depends on either behaviour, and
    tightening the read path would be a change in what a scope IS rather than a
    security fix. Left as-is on purpose; if it is ever unified, unify it toward
    this validator, not away from it.
    """
    fault = _path_component_fault(scope)
    if fault is not None:
        raise InvalidScopeName(
            f"scope {scope!r} {fault} — a scope must be {_COMPONENT_RULE}. "
            f"It is written to disk as a path component "
            f"(<base>/<scope>, <base>/tenants/<tenant>/scopes/<scope>), so a "
            f"scope that traverses would place the write outside the store."
        )


#: Longest whole bundle ENTRY path the kernel will hand a handle, in UTF-8
#: BYTES. An entry is a relative PATH, not a component, so it has its own bound:
#: each SEGMENT is still held to ``MAX_PATH_COMPONENT_BYTES`` (the ``NAME_MAX``
#: argument), and the assembled path to this. 1000 leaves headroom under the
#: smallest ``PATH_MAX`` DNA writes to (1024 on macOS) once the bundle root
#: prefix is counted, and is ~10x the longest entry that exists anywhere
#: measured (96 bytes — an XSD buried in a Skill's ``scripts/`` tree).
MAX_BUNDLE_ENTRY_BYTES = 1000

_ENTRY_RULE = (
    "a RELATIVE path inside the bundle: not empty or whitespace-only, not "
    "absolute, no '\\' or NUL, no '.' or '..' segment, no empty segment (a "
    "leading, trailing or doubled '/'), each segment at most "
    f"{MAX_PATH_COMPONENT_BYTES} bytes and the whole path at most "
    f"{MAX_BUNDLE_ENTRY_BYTES}. Subdirectories and dots are FINE — "
    "'skills/foo/SKILL.md' and 'scripts/office/schemas/opc-digSig.xsd' are "
    "real entries; the rule is that it cannot escape the bundle or address a "
    "directory"
)


def _bundle_entry_fault(value: object) -> str | None:
    """Return why ``value`` is not a safe relative bundle path, or ``None``.

    Split out from :func:`validate_bundle_entry` for symmetry with
    :func:`_path_component_fault`, so the two RULES stay visibly different
    things: a ``name``/``scope`` is ONE component, an ``entry`` is a PATH.
    """
    if not isinstance(value, str):
        return f"is not a str (got {type(value).__name__})"
    if not value.strip():
        return "is empty or whitespace-only"
    if "\x00" in value:
        return "contains a NUL byte"
    if "\\" in value:
        return "contains '\\' (a path separator on Windows/UNC)"
    if value.startswith("/"):
        return "is an absolute path"
    if len(value) > 1 and value[1] == ":":
        return "carries a Windows drive prefix"
    size = len(value.encode("utf-8", "surrogatepass"))
    if size > MAX_BUNDLE_ENTRY_BYTES:
        return f"is {size} bytes (max {MAX_BUNDLE_ENTRY_BYTES})"
    for segment in value.split("/"):
        if segment == "":
            return "has an empty path segment (a leading, trailing or doubled '/')"
        if segment == ".":
            return "has a '.' segment — it addresses a directory, not a file"
        if segment == "..":
            return "has a '..' segment — it escapes the bundle"
        seg_size = len(segment.encode("utf-8", "surrogatepass"))
        if seg_size > MAX_PATH_COMPONENT_BYTES:
            return (
                f"has a segment {segment!r} of {seg_size} bytes "
                f"(max {MAX_PATH_COMPONENT_BYTES} per segment)"
            )
    return None


def validate_bundle_entry(entry: object, *, where: str = "bundle entry") -> None:
    """Raise :class:`InvalidBundleEntry` unless ``entry`` is a safe relative path.

    ``where`` names the door for the message — ``"bundle entry"`` at the handle,
    a writer's field name (``"spec.root_files key"``) when the caller knows it.

    Called by ``FilesystemBundleHandle`` on EVERY method that builds a path from
    an entry, by ``write_entries_to_handle`` before any writer's output reaches
    a handle, and by ``Kernel.serialize_instance`` on every ``relativePath`` it
    hands back. The handle is the closing layer — it is the one door every
    writer must pass — and the other two are the named, early ones that can say
    WHICH field was wrong.
    """
    fault = _bundle_entry_fault(entry)
    if fault is not None:
        raise InvalidBundleEntry(
            f"{where} {entry!r} {fault} — an entry must be {_ENTRY_RULE}. "
            f"It is joined onto the bundle root (<scope>/<container>/<name>/"
            f"<entry>), so an entry that traverses — or is absolute, which "
            f"makes a pathlib join DISCARD the bundle root entirely — would "
            f"place the write outside the bundle and outside the store."
        )


class KernelRegistrationError(ValueError):
    """Base class for kernel registration validation failures."""


class KindRegistrationError(KernelRegistrationError):
    """A KindPort failed Protocol conformance, uniqueness, or marker
    collision checks at ``kernel.kind(port)`` time.

    Examples:
      - Duplicate ``(api_version, kind)`` tuple
      - Duplicate ``alias`` across registered Kinds
      - Two BUNDLE-pattern Kinds declaring the same
        ``(storage.container, storage.marker)`` pair
      - Object passed doesn't satisfy the ``KindPort`` Protocol
    """


class ReaderRegistrationError(KernelRegistrationError):
    """A ReaderPort failed Protocol conformance or owner-binding checks
    at ``kernel.reader(r)`` time.

    Examples:
      - Object missing ``detect`` or ``read`` methods
      - Reader claims a ``(container, marker)`` pair already owned by
        another reader (only enforced for BUNDLE-pattern Kinds)
    """


class WriterRegistrationError(KernelRegistrationError):
    """A WriterPort failed Protocol conformance checks at
    ``kernel.writer(w)`` time. Object missing ``can_write`` or
    ``write`` methods is the typical case."""


class ExtensionLoadError(KernelRegistrationError):
    """An Extension failed structural checks at ``kernel.load(ext)``
    time. Object missing ``register`` callable, or its ``register``
    raised an unexpected exception that wasn't routed through the
    ``extension_error`` hook."""


class AgentNotFound(LookupError):
    """``build_prompt(agent=X)`` was asked for an agent that no prompt-target
    instance in the loaded manifest declares (missing, renamed, or unparseable).

    Fail-loud contract (s-dx-build-prompt-fail-loud): the builder used to
    RETURN the string ``"Agent 'X' not found"`` instead of raising — which
    sailed straight through a consumer's ``if not text`` check and became the
    LITERAL agent instruction. Every consumer therefore wrote the same
    defensive guard (``mi.one("Agent", x) is None``) before every call. Raising
    a typed error deletes that guard: the miss is now impossible to ignore.

    Subclasses ``LookupError`` (not ``ValueError``) — semantically a
    lookup miss, and narrow enough that a caller can ``except AgentNotFound``
    (or the broader ``except LookupError``) without swallowing unrelated
    failures. Exported publicly from the ``dna`` package.
    """

    def __init__(self, agent: str | None) -> None:
        self.agent = agent
        super().__init__(f"Agent '{agent}' not found")


class RuntimeBindingNotFound(LookupError):
    """A named RuntimeBinding does not exist in the selected DNA scope."""

    def __init__(self, binding: str) -> None:
        self.binding = binding
        super().__init__(f"RuntimeBinding '{binding}' not found")


class InstanceIdLookupUnsupported(CapabilityRefusal, NotImplementedError):
    """The wired source cannot resolve a ``metadata.id`` prefix (i-114).

    Raised rather than answering with an empty list, for the same reason
    ``graph_refs`` answers 501 instead of ``[]`` when no edge store is
    configured: "this adapter cannot answer" and "no instance has that id" are
    different facts, and a caller handed silence for the first will read it as
    the second.

    A :class:`CapabilityRefusal` so every face relays it by name, and still a
    ``NotImplementedError`` so nothing that caught it the old way changes.
    """


class KeyLookupUnsupported(CapabilityRefusal, NotImplementedError):
    """The wired source cannot find instances by a spec KEY (fatia 5).

    The sibling of :class:`InstanceIdLookupUnsupported`, and it exists for the
    identical reason: ``None`` from a store that never looked reads exactly
    like ``None`` from a store that looked and found nothing. A relation
    declared ``by: workspace_id`` would then be reported as dangling on every
    deployment whose adapter simply cannot ask the question — an accusation
    against data that may be perfectly sound.

    ⚠️ The write path CATCHES this rather than propagating it, and records the
    edge with reason ``unsupported``. That is deliberate: a capability the
    store lacks must never fail a write that did nothing wrong. It propagates
    to whoever asks ``Kernel.find_instance_by_key`` directly, where the caller
    wanted an answer and silence would be the lie.
    """


class AmbiguousInstanceKey(LookupError):
    """Two or more instances of one Kind carry the same spec key value.

    A refusal and never a choice, and for a stronger reason than its twin
    :class:`~dna.kernel.identity.AmbiguousInstanceId`: nothing in the schema
    makes a spec key unique, and fatia 5 does not make it unique either. A
    UNIQUE index would refuse a tenant overlay that legitimately carries the
    same key as the base instance it forks. So ambiguity is not a corrupt state
    to be prevented at write time — it is a LEGAL state the read has to refuse
    to guess about. Picking the first row would be indistinguishable from
    picking the right one, in the diff and on the screen.

    ⚠️ **NEITHER marker base, and the twin is the reason.** It is not a
    :class:`CapabilityRefusal` — the store answered perfectly well, and what it
    answered was "two". It is not a :class:`KernelRefusal` either, on exactly
    the argument ``AmbiguousInstanceId`` is classified by: a refusal marks a
    verdict about the CALLER, who asked for something policy will not give.
    This is a fact about the QUESTION — two instances match, so there is no
    single answer — and the remedy is in the data rather than in permission.
    Relayed as a denial it would send somebody hunting for an entitlement they
    already have. ``tests/test_kernel_refusal_base.py`` holds that decision.

    ``LookupError`` because that is what a lookup with no single answer is, and
    what the sibling already is.
    """

    def __init__(
        self, kind: str, key: str, value: str,
        *, matches: "list[Any] | None" = None,
    ) -> None:
        self.kind = kind
        self.key = key
        self.value = value
        #: The candidates, because the remedy IS the list — the same reasoning
        #: that makes ``TargetDeleteRestricted`` record its referrers instead
        #: of counting them.
        self.matches: list[Any] = list(matches or [])
        shown = ", ".join(
            str((m or {}).get("name") or "?")
            for m in self.matches[:8] if isinstance(m, dict)
        )
        super().__init__(
            f"{len(self.matches) or 2} {kind} instances carry "
            f"{key}={value!r} — refusing to guess which one a relation "
            f"addressed `by: {key}` means"
            + (f" ({shown})" if shown else "")
        )


class UnknownLayout(ValueError):
    """``build_prompt`` hit an Agent whose ``layout:`` names a preset the
    Kind does not offer (s-dx-named-layouts).

    Fail-loud DX: a typo'd layout (``persona_first`` for ``persona-first``)
    must not silently fall through to the Kind default and compose in the
    wrong order — it raises with the valid names listed. Subclasses
    ``ValueError``. Exported publicly from the ``dna`` package.
    """

    def __init__(
        self, layout: str, available: list[str] | None = None,
        agent: str | None = None,
    ) -> None:
        self.layout = layout
        self.available = list(available or [])
        self.agent = agent
        where = f" on agent '{agent}'" if agent else ""
        hint = (
            f" — available: {', '.join(self.available)}"
            if self.available else ""
        )
        super().__init__(f"Unknown layout '{layout}'{where}{hint}")


class ToolNotFound(LookupError):
    """``load_tools(scope)[name]`` was asked for a Tool that no ``Tool``
    instance in the scope declares (missing, renamed, or in another scope).

    Fail-loud contract (s-load-tools-helper), the twin of
    :class:`AgentNotFound`: the agent-facing tool surface is data, so a miss
    must raise a typed, ignorable-only-on-purpose error — never return an
    empty surface that would silently reach a model as a tool with no
    description. Subclasses ``LookupError`` (a lookup miss); callers can
    ``except ToolNotFound`` (or the broader ``LookupError``) without
    swallowing unrelated failures. Exported publicly from the ``dna`` package.
    """

    def __init__(
        self, name: str | None, scope: str | None = None,
        available: list[str] | None = None,
    ) -> None:
        self.name = name
        self.scope = scope
        self.available = list(available or [])
        where = f" in scope '{scope}'" if scope else ""
        hint = (
            f" — available: {', '.join(self.available)}"
            if self.available else ""
        )
        super().__init__(f"Tool '{name}' not found{where}{hint}")


class SourceRegistrationError(KernelRegistrationError):
    """A source failed the SourcePort boot gate at ``kernel.source(src)``
    time (s-dna-source-conformance-kit).

    The gate checks that the CORE SourcePort surface exists BY NAME
    (``runtime_checkable`` semantics — names only, not behavior). A
    source that passes the gate can still misbehave; run the public
    conformance kit (``dna.testing.source_conformance_suite``)
    against your adapter to verify actual behavior. See
    docs/PORT-CONTRACT.md."""
