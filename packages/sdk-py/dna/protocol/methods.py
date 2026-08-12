"""The built-in DNAP methods — ``initialize``, ``kinds/*``, ``instances/*``.

⭐ **This module is COLA.** Every read and every write goes through the
use-cases in :mod:`dna.application.instances` that the MCP and REST faces
already use (``list_kinds_impl``, ``list_instances_impl``, ``get_instance_impl``,
``write_instance_impl``, ``delete_instance_impl``). Nothing about the kernel,
the layer policy, the schema gate or the tenant resolution is re-implemented
here. What this module adds is the part that is *protocol* rather than
behaviour: addressing, the Kind vocabulary, the ``select`` contract, cursors,
revisions, and the error table.

``resolve/*`` and ``search/*`` (spec §6.3/§6.4) are **deliberately absent** —
they register into the same :class:`~dna.protocol.registry.MethodRegistry` from
their own module, and this one does not need to know they exist.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dna.protocol.channels import Channel
from dna.protocol.cursor import (
    decode_cursor,
    encode_cursor,
    require_same_snapshot,
)
from dna.protocol.errors import (
    INVALID_PARAMS,
    NOT_FOUND,
    NOT_WRITABLE,
    REFUSED,
    REVISION_CONFLICT,
    VALIDATION_FAILED,
    DnapError,
)
from dna.protocol.kinddef import KIND_DEFINITION, validate_kind_definition
from dna.protocol.registry import ChannelRequirement, MethodRegistry
from dna.protocol.revision import (
    channel_revision,
    digest_revision,
    store_supports_channel_revision,
)
from dna.protocol.select import parse_select
from dna.protocol.server import PROTOCOL_VERSION, RequestContext

__all__ = ["builtin_registry"]

#: The Kind vocabulary a client is allowed to name is the one the server
#: advertised. ``list_kinds_impl`` is that vocabulary's single source, so both
#: ``initialize`` and the ``-32003`` gate read it — never two lists.
_APIVERSION_KEY = "api_version"

#: §6.2 rule 4: *"Order is lexicographic by ``metadata.name``, ascending. Rules
#: 2 and 3 are both meaningless without a total order, and ``metadata.name`` is
#: the only member §5 guarantees unique within (channel, kind)."* Pushed down
#: to ``kernel.query`` so the order is the STORE's, not the page's.
_ORDER_BY = "metadata.name"


# ── shared helpers ──────────────────────────────────────────────────────────


async def _catalog(ctx: RequestContext, channel: Channel) -> list[dict[str, Any]]:
    from dna.application.instances import list_kinds_impl

    result = await list_kinds_impl(
        ctx.live, scope=ctx.scope, tenant=ctx.tenant,
    )
    return list(result.get("kinds") or [])


async def _require_kind(ctx: RequestContext, params: Mapping[str, Any]) -> dict[str, Any]:
    """The catalog entry for ``params["kind"]``, or ``-32003``.

    ⭐ Checked against the **advertised vocabulary**, not merely resolved
    against the registry. Spec §4: *"A client that names an unadvertised Kind
    gets ``-32003 KIND_NOT_SERVED``."* Those are different tests — a Kind can
    exist in the process-wide registry and not govern this channel — and
    resolving without the vocabulary check would serve a Kind the client was
    never told about, which is the mirror image of the channel substitution §3
    forbids.
    """
    kind = params.get("kind")
    if not isinstance(kind, str) or not kind:
        raise DnapError.invalid_params("`kind` is required and must be a string")
    for entry in await _catalog(ctx, ctx.channel):
        if entry.get("kind") == kind or entry.get("alias") == kind:
            return entry
    raise DnapError.kind_not_served(kind, ctx.channel.uri)


def _instance_revision(raw: Any) -> str:
    """``metadata.revision`` for one instance — see :mod:`dna.protocol.revision`."""
    from dna.kernel.etag import spec_etag

    spec = raw.get("spec") if isinstance(raw, dict) else None
    return spec_etag(spec)


def _as_document(raw: Any, *, revision: str | None = None) -> dict[str, Any]:
    """The kernel's stored instance, shaped as the DNAP document (spec §5).

    Unknown ``metadata`` members are **preserved** — §5 requires clients to
    round-trip them, which is meaningless if the server drops them first.
    ``metadata.id`` is emitted only when the store actually has one: §5 calls it
    "server-minted", and a server with no id mechanism omits the member rather
    than minting a number that is stable only until the next process.
    """
    if not isinstance(raw, dict):
        raise DnapError(
            -32603, f"the store returned {type(raw).__name__}, not an instance",
        )
    doc = dict(raw)
    metadata = dict(doc.get("metadata") or {})
    metadata["revision"] = revision if revision is not None else _instance_revision(raw)
    doc["metadata"] = metadata
    return doc


def _translate(exc: Exception) -> DnapError:
    """One exception → one code. The whole §7 table lives here.

    Ordering is load-bearing in the same way the MCP face's is: several of
    these subclass ``LookupError`` or ``ValueError``, so the specific test must
    come before the general one or a precise failure gets reported as a vague
    one.
    """
    from dna.application import instances as D
    from dna.kernel.errors import CapabilityRefusal, KernelRefusal
    from dna.kernel.protocols import SpecValidationError

    if isinstance(exc, DnapError):
        return exc
    if isinstance(exc, D.UnknownKindError):
        return DnapError.kind_not_served(str(exc), "the requested channel")
    if isinstance(exc, D.AmbiguousKindError):
        return DnapError.invalid_params(
            f"{exc} — name the Kind's apiVersion to disambiguate",
        )
    if isinstance(exc, SpecValidationError):
        # §6.2: "-32010 VALIDATION_FAILED carries the failing path and the
        # rule, never a bare 'invalid'." ``path``/``rule`` are attributes on
        # the exception (added for exactly this); either may be None when the
        # raise site genuinely does not know it, and None travels as null
        # rather than as a guess.
        return DnapError(
            VALIDATION_FAILED, str(exc),
            path=getattr(exc, "path", None), rule=getattr(exc, "rule", None),
        )
    if isinstance(exc, D.ConcurrentWriteError):
        return DnapError(REVISION_CONFLICT, str(exc))
    if isinstance(exc, D.UnknownInstanceError):
        return DnapError(NOT_FOUND, str(exc))
    if isinstance(exc, D.BootstrapKindWriteRefused | D.DeleteRefused):
        # The Kind is served and not writable/deletable — §7's own code. This
        # is normally caught up front from the catalog (``_require_writable``);
        # arriving here means the kernel refused for a reason the catalog did
        # not report, and it still gets the code that names the condition.
        return DnapError(NOT_WRITABLE, str(exc), refusal=type(exc).__name__)
    if isinstance(exc, KernelRefusal | CapabilityRefusal):
        # ⛔ A refusal is NOT an internal error. Both marker bases are caught
        # non-enumeratively and on purpose: a Kind trait, a layer policy or a
        # tenant rule added later refuses through the same bases, and a list of
        # concrete classes here would go stale silently — this repo's own
        # "guardas: enumeração vs. derivação" lesson, applied to an error
        # table. ``refusal`` names the class so a client can tell a
        # write-refusal from a delete-refusal without reading the sentence.
        return DnapError(REFUSED, str(exc), refusal=type(exc).__name__)
    raise exc


# ── the registry ────────────────────────────────────────────────────────────

_REGISTRY = MethodRegistry()


@_REGISTRY.method(
    "initialize", channel=ChannelRequirement.NONE, requires_session=False,
)
async def initialize(ctx: RequestContext, params: Mapping[str, Any]) -> dict[str, Any]:
    """Spec §4 — the client states what it can do; the server answers with what
    it serves.

    The answer is **derived**: ``channels`` from the served scopes,
    ``capabilities`` from the registered method table, ``kinds`` from
    ``list_kinds_impl``. Nothing here is a list a human keeps in step — which
    is what makes "the client takes its vocabulary from ``initialize``"
    (conformance rule 1 for clients) a mechanism rather than an aspiration.
    """
    requested = params.get("protocolVersion")
    if requested is not None and requested != PROTOCOL_VERSION:
        raise DnapError.invalid_params(
            f"unsupported protocolVersion {requested!r}",
            supported=[PROTOCOL_VERSION],
        )
    client = params.get("client")
    caps = params.get("capabilities")
    session = ctx.session
    session.initialized = True
    session.protocol_version = PROTOCOL_VERSION
    session.client = dict(client) if isinstance(client, dict) else {}
    session.client_capabilities = dict(caps) if isinstance(caps, dict) else {}

    kinds = sorted({e["kind"] for e in await _catalog(ctx, ctx.channel)})
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "server": dict(ctx.server.server_info),
        "channels": ctx.server.channels.advertised(),
        "capabilities": ctx.server.capabilities(ctx),
        "kinds": kinds,
        # A DNAP-1.0 extension, and the honest half of §5's "monotonic per
        # channel". See dna.protocol.revision: this store has no port that
        # exposes a channel watermark, so listings report `revision: null`
        # instead of a minted one — and the client learns that once, here,
        # rather than inferring it from a null it did not expect.
        # A DNAP-1.0 extension: WHICH of the two revision mechanisms this
        # connection is getting. Both are honest; one is O(1) and the other is
        # O(n) per listing (see dna.protocol.revision), and a client is better
        # served learning that once here than inferring it from a latency
        # graph.
        "revisions": {
            "instance": "content-hash",
            "channel": (
                "store-sequence"
                if store_supports_channel_revision(
                    getattr(ctx.live, "kernel", None))
                else "content-digest"
            ),
        },
    }


@_REGISTRY.method("kinds/list", channel=ChannelRequirement.ROOT_OR_SCOPE)
async def kinds_list(ctx: RequestContext, params: Mapping[str, Any]) -> dict[str, Any]:
    """Spec §6.1 — the Kinds this channel serves, with the shape of each."""
    entries = await _catalog(ctx, ctx.channel)
    return {
        # The channel answered for is ECHOED, so a root request never leaves
        # the client guessing which scope's vocabulary it received.
        "channel": ctx.channel.uri if not ctx.channel.is_root
        else f"dnap-scope:/{ctx.scope}",
        "kinds": [
            {
                "kind": e["kind"],
                "apiVersion": e[_APIVERSION_KEY],
                "plane": e.get("plane"),
                "promptTarget": bool(e.get("prompt_target", False)),
                "writable": bool(e.get("writable")),
            }
            for e in entries
        ],
    }


@_REGISTRY.method("kinds/describe", channel=ChannelRequirement.ROOT_OR_SCOPE)
async def kinds_describe(
    ctx: RequestContext, params: Mapping[str, Any],
) -> dict[str, Any]:
    """Spec §6.1 — the JSON Schema of ``spec``, plus declared relations.

    *"The schema travels because a client that cannot see it must guess, and a
    guessing client writes documents the server will reject."*

    A Kind with **no** declared schema reports ``schema: null``, which is a
    fact about that Kind (the kernel stays permissive for it) and not a failure
    to look one up — an empty ``{}`` would read as "no constraints declared and
    verified", which is a different claim.
    """
    from dna.application.instances import resolve_kind_port_live

    entry = await _require_kind(ctx, params)
    try:
        port = await resolve_kind_port_live(
            ctx.live, entry["kind"], entry[_APIVERSION_KEY], scope=ctx.scope,
        )
    except Exception as exc:  # noqa: BLE001 — translated, never swallowed
        raise _translate(exc) from exc
    schema = port.schema() if callable(getattr(port, "schema", None)) else None
    relations = (
        port.dependencies() if callable(getattr(port, "dependencies", None))
        else None
    )
    return {
        "kind": entry["kind"],
        "apiVersion": entry[_APIVERSION_KEY],
        "plane": entry.get("plane"),
        "promptTarget": bool(entry.get("prompt_target", False)),
        "writable": bool(entry.get("writable")),
        "writeRefusal": entry.get("write_refusal"),
        "deletable": bool(entry.get("deletable")),
        "deleteRefusal": entry.get("delete_refusal"),
        "schema": schema,
        "relations": relations or {},
    }


@_REGISTRY.method("instances/list")
async def instances_list(
    ctx: RequestContext, params: Mapping[str, Any],
) -> dict[str, Any]:
    """Spec §6.2 — and its **five** rules, each corrected here rather than hoped
    for.

    1. ``select`` is validated **before** the store is read
       (:mod:`dna.protocol.select`); an unhonourable projection is ``-32602``
       and never a narrower shape with the request echoed back.
    2. Pagination is by opaque ``cursor``; the offset underneath is invisible
       and therefore replaceable.
    3. The snapshot ``revision`` is pinned in the cursor and re-checked on
       every page; a store that moved answers ``-32005``.
    4. **Order is lexicographic by ``metadata.name``, ascending** — pushed down
       to the store as ``order_by=["metadata.name"]``, never sorted per page.
       A page-local sort would look identical on a one-page listing and be
       wrong on every other: rules 2 and 3 are *"both meaningless without a
       total order"*, and a per-page sort is not one.
    5. The result SHAPE of each ``select`` — plain strings for ``"names"``,
       whole documents for ``"full"``, exactly the requested paths for a path
       list (:meth:`~dna.protocol.select.Selection.shape`).
    """
    from dna.application.instances import list_instances_impl

    entry = await _require_kind(ctx, params)
    kind = entry["kind"]
    selection = parse_select(params.get("select"))
    limit = _positive_int(params.get("limit"), "limit")

    current = await _slice_revision(ctx, entry)
    raw_cursor = params.get("cursor")
    if raw_cursor is None:
        offset, snapshot = 0, current
    else:
        cursor = decode_cursor(
            raw_cursor, channel=ctx.channel.uri, kind=kind,
            select=selection.fingerprint,
            generation=ctx.server.cursor_generation,
        )
        require_same_snapshot(cursor, current)
        offset, snapshot = cursor.offset, cursor.revision

    try:
        result = await list_instances_impl(
            ctx.live, kind=kind, scope=ctx.scope, tenant=ctx.tenant,
            api_version=entry[_APIVERSION_KEY],
            limit=limit, offset=offset,
            fields=list(selection.paths) if selection.mode == "paths" else None,
            envelope=selection.mode == "full",
            order_by=[_ORDER_BY],
        )
    except Exception as exc:  # noqa: BLE001 — translated, never swallowed
        raise _translate(exc) from exc

    rows = list(result.get("instances") or [])
    out: dict[str, Any] = {
        "instances": (
            [_as_document(r) for r in rows] if selection.mode == "full"
            else selection.shape(rows)
        ),
        "revision": snapshot,
        "selected": selection.echo,
    }
    if result.get("has_more"):
        # ⚠️ ABSENT when exhausted (§6.2), not null. A null cursor and a missing
        # cursor read the same to a careless client and differently to a
        # careful one; the spec's example omits it, so it is omitted.
        out["cursor"] = encode_cursor(
            channel=ctx.channel.uri, kind=kind,
            select=selection.fingerprint,
            offset=offset + len(rows), revision=snapshot,
            generation=ctx.server.cursor_generation,
        )
    return out


@_REGISTRY.method("instances/get")
async def instances_get(
    ctx: RequestContext, params: Mapping[str, Any],
) -> dict[str, Any]:
    """Spec §6.2 — the document verbatim, including ``metadata.revision``.

    ``ifNoneMatch`` gives the conditional read: a match answers
    ``{"notModified": true}`` **with no body**.
    """
    from dna.application.instances import get_instance_impl

    entry = await _require_kind(ctx, params)
    name = _require_name(params)
    try:
        result = await get_instance_impl(
            ctx.live, kind=entry["kind"], name=name, scope=ctx.scope,
            tenant=ctx.tenant, api_version=entry[_APIVERSION_KEY],
        )
    except LookupError as exc:
        # "no such instance" is an ANSWER about the world, and it is reported
        # as an error rather than as an empty document — the §7 rule at the
        # single-instance layer. ``-32002 NOT_FOUND`` is the spec's own code
        # for it as of the clean-room revision (gap A2: the most common failure
        # of `get`/`delete` had no code at all).
        raise DnapError(
            NOT_FOUND, str(exc), kind=entry["kind"], name=name,
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc) from exc

    revision = result.get("etag")
    if_none_match = params.get("ifNoneMatch")
    if if_none_match is not None and if_none_match == revision:
        return {"notModified": True, "revision": revision}
    return {
        "instance": _as_document(result.get("instance"), revision=revision),
        "revision": revision,
    }


@_REGISTRY.method("instances/write", capability="write")
async def instances_write(
    ctx: RequestContext, params: Mapping[str, Any],
) -> dict[str, Any]:
    """Spec §6.2 — ``{channel, document, ifMatch}`` → ``{instance, created}``.

    ⭐ **The Kind is read from ``document.kind``, and there is no ``kind``
    param.** *"A separate `kind` param would be a second spelling that can
    disagree with the first."* One of the twelve gaps the clean room found
    (A1): this method had no documented params at all, so two honest readers
    would have built two shapes.

    ``metadata.id`` / ``metadata.revision`` supplied by the client are
    ``-32010``, not ``-32602`` — the spec assigns that code here, and it is the
    better one: the document is malformed against the rules of §5, which is a
    validation failure about content rather than a bad argument.

    ``ifMatch`` is optimistic concurrency: a stored revision that moved answers
    ``-32011 REVISION_CONFLICT`` **carrying the current revision**, so the
    client can re-read and decide rather than retry blindly. Getting that
    number costs one extra read, on the conflict path only.
    """
    from dna.application.instances import write_instance_impl

    document = params.get("document")
    if not isinstance(document, dict):
        raise DnapError.invalid_params(
            "`document` is required and must be the whole instance "
            "({apiVersion, kind, metadata, spec}) — spec §6.2",
        )
    entry = await _require_kind(ctx, {"kind": document.get("kind")})
    metadata = document.get("metadata")
    if not isinstance(metadata, dict):
        raise DnapError(
            VALIDATION_FAILED, "`document.metadata` must be an object",
            path="metadata", rule="type",
        )
    _refuse_derived_metadata(metadata)
    name = metadata.get("name")
    if not isinstance(name, str) or not name:
        raise DnapError(
            VALIDATION_FAILED,
            "`document.metadata.name` is required and must be a string",
            path="metadata.name", rule="required",
        )
    spec = document.get("spec")
    if not isinstance(spec, dict):
        raise DnapError(
            VALIDATION_FAILED, "`document.spec` must be an object",
            path="spec", rule="type",
        )
    if entry["kind"] == KIND_DEFINITION:
        # §6.1's two rules, checked before the store — see dna.protocol.kinddef
        # (and the conflict with the SDK's authoring gate documented there).
        validate_kind_definition(document)
    # ⚠️ Writability is checked LAST of the preconditions, and the order is a
    # decision. A malformed document is malformed whatever the target's policy
    # is, and 400-before-403 is the order every validating API settles on: a
    # client told only "not writable" would fix nothing, resubmit the same
    # broken document to a channel that does accept the Kind, and be refused
    # again for a reason it was never told the first time.
    _require_writable(entry)

    try:
        result = await write_instance_impl(
            ctx.live, kind=entry["kind"], name=name, spec=spec,
            scope=ctx.scope, tenant=ctx.tenant,
            api_version=entry[_APIVERSION_KEY],
            merge=bool(params.get("merge", True)),
            if_match=params.get("ifMatch"),
        )
    except Exception as exc:  # noqa: BLE001
        err = _translate(exc)
        if err.code == REVISION_CONFLICT:
            err.data["revision"] = await _current_revision(ctx, entry, name)
        raise err from exc

    stored = await _current_document(ctx, entry, name)
    return {"instance": stored, "created": bool(result.get("created", False))}


@_REGISTRY.method("instances/delete", capability="write")
async def instances_delete(
    ctx: RequestContext, params: Mapping[str, Any],
) -> dict[str, Any]:
    """Spec §6.2 — ``{channel, kind, name, ifMatch}`` →
    ``{deleted, revision}``.

    ``revision`` is *"the revision the channel advanced to, so a watcher can
    order the delete against its own reads"*. Where the store serves no channel
    watermark it is ``null`` — the same honesty as a listing's, and for the
    same reason (:mod:`dna.protocol.revision`): a delete that reported a minted
    number would let a watcher order events against a sequence the server
    invented.
    """
    from dna.application.instances import delete_instance_impl

    entry = await _require_kind(ctx, params)
    _require_deletable(entry)
    name = _require_name(params)
    try:
        await delete_instance_impl(
            ctx.live, kind=entry["kind"], name=name,
            api_version=entry[_APIVERSION_KEY],
            scope=ctx.scope, tenant=ctx.tenant,
            if_match=params.get("ifMatch"),
        )
    except Exception as exc:  # noqa: BLE001
        err = _translate(exc)
        if err.code == REVISION_CONFLICT:
            err.data["revision"] = await _current_revision(ctx, entry, name)
        raise err from exc
    return {"deleted": True, "revision": await _slice_revision(ctx, entry)}


# ── small validators ────────────────────────────────────────────────────────


def _require_name(params: Mapping[str, Any]) -> str:
    name = params.get("name")
    if not isinstance(name, str) or not name:
        raise DnapError.invalid_params("`name` is required and must be a string")
    return name


def _require_writable(entry: Mapping[str, Any]) -> None:
    """§7 ``-32006 NOT_WRITABLE`` — *"the Kind is served but writable: false"*.

    Answered from the CATALOG, before the store is touched. The same refusal
    would eventually arrive from the kernel, but as a generic policy refusal
    with no code of its own; asking the catalog first means a client is refused
    for the reason it could have predicted from ``kinds/list``, in the code the
    spec assigns to it.
    """
    if entry.get("writable"):
        return
    raise DnapError(
        NOT_WRITABLE,
        entry.get("write_refusal")
        or f"the Kind {entry['kind']!r} is served but not writable",
        kind=entry["kind"],
    )


def _require_deletable(entry: Mapping[str, Any]) -> None:
    """The delete twin of :func:`_require_writable`.

    ⚠️ It needs its own check rather than riding on ``writable``: the two
    refusals do not coincide (an AuditLog is writable and never deletable), and
    a face that inferred one from the other would be guessing about the more
    destructive of the two. ``-32006`` is the nearest code the spec gives —
    reported, because §7 names no separate NOT_DELETABLE.
    """
    if entry.get("deletable"):
        return
    raise DnapError(
        NOT_WRITABLE,
        entry.get("delete_refusal")
        or f"the Kind {entry['kind']!r} is served but not deletable",
        kind=entry["kind"], operation="delete",
    )


def _positive_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise DnapError.invalid_params(f"`{field}` must be a positive integer")
    return value


def _refuse_derived_metadata(metadata: Mapping[str, Any]) -> None:
    """§5/§6.2: *"``metadata.id`` and ``metadata.revision`` supplied by the
    client MUST be rejected with ``-32010``."*

    Refused rather than ignored. A write that carried a revision and had it
    dropped would look to its author exactly like a write whose revision was
    honoured — which is how a client comes to believe it has optimistic
    concurrency it never had. ``ifMatch`` is the member that means that, and it
    is the only one.
    """
    derived = sorted(k for k in ("id", "revision") if k in metadata)
    if not derived:
        return
    raise DnapError(
        VALIDATION_FAILED,
        f"metadata.{', metadata.'.join(derived)} "
        f"{'is' if len(derived) == 1 else 'are'} derived by the server and "
        f"must not be supplied on write (spec §5). For optimistic concurrency "
        f"use `ifMatch`.",
        path=f"metadata.{derived[0]}", rule="derived-not-supplied",
        fields=derived,
    )


async def _slice_revision(
    ctx: RequestContext, entry: Mapping[str, Any],
) -> str:
    """The snapshot token for one ``(channel, kind)`` slice (§6.2 rule 3).

    The store's own sequence when it has one; otherwise a content digest — see
    :mod:`dna.protocol.revision` for why the third option (minting a token) is
    the one that is not on the table.

    ⚠️ The digest branch reads every name+etag of the slice, so it is O(n) per
    listing. That cost is the honest price of a store with no sequence, and it
    disappears the moment one is exposed.
    """
    from dna.application.instances import list_instances_impl

    kernel = getattr(ctx.live, "kernel", None)
    supplied = await channel_revision(kernel, ctx.scope, tenant=ctx.tenant)
    if supplied is not None:
        return supplied

    from dna.kernel.etag import spec_etag

    pairs: list[tuple[str, str]] = []
    offset = 0
    while True:
        page = await list_instances_impl(
            ctx.live, kind=entry["kind"], scope=ctx.scope, tenant=ctx.tenant,
            api_version=entry[_APIVERSION_KEY],
            envelope=True, order_by=[_ORDER_BY], offset=offset,
        )
        rows = list(page.get("instances") or [])
        for row in rows:
            metadata = row.get("metadata") if isinstance(row, dict) else None
            name = (metadata or {}).get("name")
            if isinstance(name, str):
                pairs.append((name, spec_etag(row.get("spec"))))
        if not page.get("has_more") or not rows:
            break
        offset += len(rows)
    return digest_revision(pairs)


async def _read(
    ctx: RequestContext, entry: Mapping[str, Any], name: str,
) -> dict[str, Any] | None:
    from dna.application.instances import get_instance_impl

    try:
        return await get_instance_impl(
            ctx.live, kind=entry["kind"], name=name, scope=ctx.scope,
            tenant=ctx.tenant, api_version=entry[_APIVERSION_KEY],
        )
    except LookupError:
        return None


async def _current_revision(
    ctx: RequestContext, entry: Mapping[str, Any], name: str,
) -> str | None:
    result = await _read(ctx, entry, name)
    # The instance being gone IS the current state; reporting "revision
    # unknown" would be a guess. None means "there is none".
    return None if result is None else result.get("etag")


async def _current_document(
    ctx: RequestContext, entry: Mapping[str, Any], name: str,
) -> dict[str, Any]:
    """The stored document, for ``instances/write``'s result (§6.2).

    The write use-case returns a summary, not the instance, so the document the
    result carries is re-read. ⚠️ If that read finds nothing, the server does
    **not** answer with the document the client sent: a write that reported
    back its own input as "stored" is the §7 collapse in its most convincing
    disguise, because the response looks exactly like a success.
    """
    result = await _read(ctx, entry, name)
    if result is None:
        raise DnapError(
            -32603,
            f"{entry['kind']} {name!r} was written and could not be read back "
            f"— refusing to echo your own document as if it were stored.",
        )
    return _as_document(result.get("instance"), revision=result.get("etag"))


_REGISTRY.declare_capability("write", lambda ctx: {"validate": True})
_REGISTRY.frozen()


def builtin_registry() -> MethodRegistry:
    """The frozen registry of DNAP's built-in methods.

    Call :meth:`~dna.protocol.registry.MethodRegistry.extended` on it to add
    ``resolve/*``, ``search/*`` or anything else — see
    :mod:`dna.protocol.registry`.
    """
    return _REGISTRY
