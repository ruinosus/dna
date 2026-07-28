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


class DocumentNameTaken(KernelRefusal, FileExistsError):
    """An ``if_absent`` write lost the race: the name was already taken.

    The ATOMIC half of "create is never an update". ``refuse_if_exists`` closed
    the whole class of NON-concurrent overwrites — the guessed name, the retry,
    the stale board — by reading before writing, and said in its own docstring
    that the genuinely concurrent race stayed open because the kernel had no
    unique-name constraint to lean on. It does now: both shipped adapters can
    claim a name atomically (a composite primary key on the SQL side,
    ``O_CREAT|O_EXCL`` / ``mkdir`` on the filesystem), so an ``if_absent`` write
    either creates the document or raises this — never overwrites.

    A ``KernelRefusal`` so every face relays it as an honest denial, and a
    ``FileExistsError`` so a caller allocating a name (``create_issue``) can
    catch the standard exception and try the next one.
    """


class StaleDocumentWrite(KernelRefusal, ValueError):
    """An ``if_match`` write lost the race: the stored document is no longer the
    one the caller read, so the write would have been a LOST UPDATE.

    The UPDATE half of what :class:`DocumentNameTaken` is for creates.
    ``if_absent`` answers "this create must not become an update"; this answers
    "this update must not become somebody else's erasure". Both are arbitrated
    by the adapter against the STORE, which is the only thing that makes either
    of them true: a read-modify-write guarded in application code re-reads
    through the very cache that made the read stale (i-083 — a reviewer's 60s
    granular document cache on one replica, an author's edit on another), and
    so compares a stale value against itself and agrees.

    The token is the ``spec`` content digest :func:`dna.kernel.etag.spec_etag`
    computes — see that function for why it is a content hash and not the
    adapter's version id.

    A ``KernelRefusal`` so every face relays it as an honest denial rather than
    a 500, and a ``ValueError`` so the doors that already map write-path vetoes
    to a client refusal surface it with no new wiring. The remedy is always the
    same and the message says it: re-read the document and re-apply the change
    to the fresh etag.
    """


class InvalidDocumentName(KernelRefusal, ValueError):
    """A document ``name`` is not a single, safe path component.

    A document reaches a source adapter as a PATH COMPONENT — it is stored at
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
    ``-`` and ``--`` are all legal. See :func:`validate_document_name`.

    A ``KernelRefusal`` so every face relays it as an honest denial, and ALSO a
    ``ValueError`` — deliberately, for a security refusal — so a face that
    predates the marker base and still catches
    ``(ValueError, LookupError, PermissionError)`` reports it instead of
    letting it escape as a masked failure.
    """


class InvalidScopeName(KernelRefusal, ValueError):
    """A ``scope`` is not a single, safe path component.

    The twin of :class:`InvalidDocumentName`, and for the same reason: the
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
    path is ALSO derived from document CONTENT. ``spec.source_files``,
    ``spec.root_files``, ``spec.scripts|references|assets``, ``spec.extras`` and
    ``spec.instruction_file`` are all turned into ``relativePath`` values by the
    registered writers, and ``spec`` is copied verbatim from the caller by
    ``apply_definition_impl`` and taken as an untyped body by
    ``PUT /v1/definitions/{kind}/{name}``. Measured at HEAD through
    ``Kernel.write_document`` on the default ``Agent`` Kind: each of those five
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

    The SECOND layer, deliberately redundant with :class:`InvalidDocumentName`
    / :class:`InvalidScopeName`. Those guard the kernel facade — the primary
    seam, because it is the door every writer and reader goes through and it
    can name WHICH input was wrong. This one guards the filesystem adapter
    itself, which builds ``<base>/<scope>/<container>/<name>/<…>`` and until now
    trusted every segment it was handed. The kernel guard cannot help a caller
    that does not go through the kernel, and there already is one
    (``dna.kernel.source.sync`` calls ``save_document`` directly — benignly
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
    simply un-register the Kind — but an unregistered Kind's documents are
    accepted with NO validation at all (measured), so un-registering LOOSENS the
    gate instead of closing it. A revoked Kind therefore stays registered,
    marked, and refuses new documents outright:

        state            existing documents      new documents
        ---------------- ---------------------- ---------------------------
        never approved   —                       accepted WITHOUT validation
        approved         valid, routed           validated against the schema
        revoked          INVALID                 REFUSED

    Refused, not "vetoed for its shape": a CONFORMING document is refused too,
    because what was withdrawn is the Kind, not a schema. That is also why this
    is its own type and not a
    :class:`~dna.kernel.protocols.SpecValidationError` — a caller told its
    document failed validation would go and fix the document, and no document
    passes.

    Deliberately NOT governed by ``DNA_WRITE_VALIDATION``. That knob trades
    strictness for the ability to load legacy data; this refusal is a
    workspace's decision about its own Kind, and an environment variable must
    not be able to overrule it.

    Existing documents are untouched — never deleted, never unreadable. They
    read back MARKED invalid (``status.valid == false``), because erasing them
    or refusing the read would destroy the ability to audit what existed, and
    the data did nothing wrong: the workspace changed its mind. Reversible in
    one act — approving again restores validity, since validity follows the
    Kind's CURRENT state and is never a stamp on the document.

    A ``KernelRefusal`` so every face relays it as an honest denial, and a
    ``ValueError`` so a face that predates the marker base and still catches
    ``(ValueError, LookupError, PermissionError)`` reports it rather than
    letting it escape as a masked failure.
    """


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
        return "addresses a directory instead of naming a document"
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


def validate_document_name(name: object) -> None:
    """Raise :class:`InvalidDocumentName` unless ``name`` is a safe component.

    Called by ``Kernel.write_document`` / ``Kernel.delete_document`` before any
    adapter is touched, so every writer — the SDLC verbs, the generic MCP write
    tool, the REST routes, an extension — inherits it without knowing it exists.
    """
    fault = _path_component_fault(name)
    if fault is not None:
        raise InvalidDocumentName(
            f"document name {name!r} {fault} — a document name must be "
            f"{_COMPONENT_RULE}. It is written to disk as a path component "
            f"(<scope>/<container>/<name>), so a name that traverses would "
            f"place the document outside the store."
        )


def validate_scope_name(scope: object) -> None:
    """Raise :class:`InvalidScopeName` unless ``scope`` is a safe component.

    A NOTE ON THE ASYMMETRY, so the next reader does not mistake it for a bug:
    the WRITE and BUNDLE facades refuse ``scope=""``, ``"."`` and ``"a/b"``
    through this validator, but the READ path never calls it — reads are held to
    CONTAINMENT only (``FilesystemSource._contained``), which fires on a genuine
    escape and lets those three through. So ``list_documents(scope="a/b")``
    works today while ``write_document(scope="a/b")`` refuses. Deliberate and
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
    a handle, and by ``Kernel.serialize_document`` on every ``relativePath`` it
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
    document in the loaded manifest declares (missing, renamed, or unparseable).

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
    document in the scope declares (missing, renamed, or in another scope).

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
