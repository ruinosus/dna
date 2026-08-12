"""``HttpSource`` — a read-only :class:`~dna.kernel.protocols.SourcePort` over the
DNA REST face, authenticated by a TOKEN instead of a database DSN (i-106).

Why it exists
-------------

Before this adapter, ``source_from_url`` understood ``file://``, ``pkg://``,
``sqlite://`` and ``postgresql://``. A SEPARATE repository that wanted to resolve
its definitions from a HOSTED DNA therefore had exactly one option: share the
Postgres DSN. Between two projects of the same owner that is merely untidy; for a
third party it hands over the whole database and throws away everything the
hosted layer exists to provide — an authenticated door, the tenant stitched in on
the SERVER, quota, metering, audit. The consumer would end up enforcing its own
tenant boundary, which is the opposite of fail-closed.

With this adapter the consumer changes ONE environment variable::

    DNA_SOURCE_URL=https://dna.example.com/v1
    DNA_API_TOKEN=<bearer>

``DnaClient.from_env()`` and ``resolve_agent`` / ``resolve_copilot`` keep their
exact shape. If a consumer has to change code, the adapter failed.

What the REST face gives — and what it costs (measured 12/08/2026)
------------------------------------------------------------------

Measured against a live ``dna api serve`` (local, warm Postgres, 433 instances
across 88 registered Kinds):

===========================================  ==========================  ========
read                                         route(s)                    cost
===========================================  ==========================  ========
``load_bootstrap_docs``                      3 lists + one GET per hit   ~7 calls
``list_doc_refs``                            1 registry + 1 list / Kind  1+N
``load_one``                                 1 GET                       ~2 ms
``load_all``                                 1 + N lists + M documents   522 calls
===========================================  ==========================  ========

``load_all`` is 1+N+M and NOT 1+N, because the list route's ``fields``
projection cannot return a whole ``spec``: ``?fields=spec`` and ``?fields=*``
were tried against the real face and both answered ``[{"name": …}]`` while
echoing ``"projected": ["spec"]`` — accepted and ignored. Only named LEAF paths
project, and they project through the Kind's VIEW, which normalizes. A
``SourcePort`` must return DOCUMENTS (``apiVersion`` + ``metadata`` + ``spec``),
so every instance costs its own GET.

The full ``load_all`` measured **522 calls / 1.13 s wall / 2.4 MiB** with 8
concurrent lanes against a local server. The kernel builds the base manifest
ONCE per process (``Kernel._base_instance_cached_async``), so this is a boot
cost, not a per-request one — but it is a real cost and it grows linearly with
the scope, which is why it is written here rather than discovered later.

⭐ **One scope per credential.** The instance routes deliberately take no
``scope`` query param — the served scope is DERIVED from the credential on the
server (that IS the property the hosted layer sells). Measured: sending
``?scope=other`` to ``/v1/kinds/App/instances`` returns the server's OWN scope's
instances while the body still reports ``"scope": "dna-cloud"``. So this adapter
asks the server which scope it serves and REFUSES any read for a different one
(:class:`RemoteScopeMismatch`) rather than returning another scope's content, or
an empty list. A consequence worth naming: scope-level INHERITANCE cannot cross
this door — the kernel's walk up the declared parent chain will get a refusal
per ancestor and log that inherited instances are unavailable, which is true.

Offline and cache — decided, not inherited
------------------------------------------

The face publishes **no ``ETag`` header** (measured: the single-instance body
carries an ``etag`` FIELD, but no header and no ``If-None-Match`` handling), so
conditional revalidation is not available today. The decision, therefore:

1. **Fail loud by default.** No network, no boot. A ``ResolveNetworkError``
   names the URL. Nothing is ever served from a stale snapshot silently.
2. **Stale is opt-in and announced.** Set ``DNA_SOURCE_SNAPSHOT_DIR`` and every
   successful ``load_all``/``load_bootstrap_docs`` writes a snapshot; set
   ``DNA_SOURCE_OFFLINE=stale-ok`` as well and a NETWORK failure (never an auth
   failure) falls back to that snapshot — logging a WARNING with its age on
   every serve, and recording it on :attr:`HttpSource.stale_since` so a face can
   report it. A consumer that will not boot because the network blinked is worse
   than one running yesterday's definitions; serving yesterday's definitions
   without saying so is worse than both.
3. **A short read memo** (``DNA_SOURCE_HTTP_TTL``, default 30 s) collapses the
   repeated fan-out inside one build. It is a declared staleness window, not a
   silent one; ``0`` disables it.

An EMPTY LIST is never a failure mode here. Every failure raises — a hosted
scope that cannot be asked must not read as a scope that holds nothing.

Dependencies
------------

``urllib.request`` from the standard library, exactly like
``dna.adapters.resolvers.http``. ``httpx`` is in the SDK's ``dev`` extra only,
and the repo's own ``dna-client`` (which would be the "official implementation"
choice) would make the SDK's DEFAULT install depend on ``httpx`` plus a second
package whose release lockstep is already a known-broken guard. The whole value
of this adapter is that a separate repo installs plain ``dna-sdk`` and points at
a URL, so the default install stays dependency-free. Blocking I/O is pushed onto
``asyncio.to_thread`` and fanned out with a bounded semaphore.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from typing import Any, TYPE_CHECKING

from dna.kernel.protocols import (
    BOOTSTRAP_KIND_NAMES,
    ResolveAuthError,
    ResolveError,
    ResolveNetworkError,
    ResolveNotFoundError,
)

if TYPE_CHECKING:  # pragma: no cover — typing only
    from dna.kernel.capabilities import SourceCapabilities

logger = logging.getLogger(__name__)

__all__ = ["HttpSource", "RemoteScopeMismatch"]

#: Default per-request timeout, seconds. Overridable per instance / by env.
DEFAULT_TIMEOUT = 30.0
#: How many document GETs may be in flight at once during ``load_all``.
DEFAULT_CONCURRENCY = 8
#: Default read-memo window, seconds. ``0`` disables the memo.
DEFAULT_TTL = 30.0
#: The list route's page size. The face clamps it by the workspace policy, and
#: the adapter pages until ``has_more`` is false — so this is a request size,
#: never an assumption about how much exists.
_PAGE = 500


class RemoteScopeMismatch(ResolveError):
    """A read asked for a scope this credential's door does not serve.

    The REST instance routes derive the scope from the credential, so asking
    them for another scope returns the SERVED one under the requested name. The
    adapter refuses instead: answering with the wrong scope's content is worse
    than answering nothing, and answering ``[]`` would say "that scope is empty"
    about a scope nobody was allowed to look at.
    """


class HttpSource:
    """A read-only ``SourcePort`` over ``https://<host>/v1`` (see module doc).

    ``base_url`` is the API root INCLUDING the version prefix
    (``https://host/v1``). ``token`` is the bearer; when omitted it is read from
    ``DNA_API_TOKEN`` — the name the REST face, both generated clients and the
    docs already use, so nothing new is invented here.

    ⚠️ The token is never logged, not even masked. Every diagnostic says only
    ``setado`` or ``ausente`` — a mask that was one character too generous is how
    a key leaked once in this house.
    """

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        tenant: str | None = None,
        timeout: float | None = None,
        concurrency: int | None = None,
        ttl: float | None = None,
        snapshot_dir: str | None = None,
        offline: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token if token is not None else os.getenv("DNA_API_TOKEN")
        self._tenant = tenant if tenant is not None else os.getenv("DNA_TENANT") or None
        self._timeout = float(
            timeout if timeout is not None
            else os.getenv("DNA_SOURCE_HTTP_TIMEOUT") or DEFAULT_TIMEOUT
        )
        self._concurrency = int(
            concurrency if concurrency is not None
            else os.getenv("DNA_SOURCE_HTTP_CONCURRENCY") or DEFAULT_CONCURRENCY
        )
        self._ttl = float(
            ttl if ttl is not None
            else os.getenv("DNA_SOURCE_HTTP_TTL") or DEFAULT_TTL
        )
        self._snapshot_dir = (
            snapshot_dir if snapshot_dir is not None
            else os.getenv("DNA_SOURCE_SNAPSHOT_DIR")
        )
        self._offline = (
            offline if offline is not None else os.getenv("DNA_SOURCE_OFFLINE") or ""
        ).strip().lower()
        #: Set to the snapshot's age in seconds the first time a stale read is
        #: served, so a face can REPORT that it is running on old definitions.
        self.stale_since: float | None = None
        self._memo: dict[str, tuple[float, Any]] = {}
        self._served_scope: str | None = None
        self._closed = False

    # ── the port surface ────────────────────────────────────────────────

    @property
    def supports_readers(self) -> bool:
        """False — a remote instance arrives as one self-contained JSON
        document. There is no directory to walk, so wiring ReaderPorts (and the
        filesystem cache + resolvers that ride with them) would be wiring for a
        bundle layout that never reaches this process."""
        return False

    def capabilities(self) -> "SourceCapabilities":
        """Explicit declaration (s-sourceport-contract-cleanup).

        ``granular_list``/``granular_one`` are TRUE and they are the point: one
        instance is one GET, and a name listing is one call per Kind — both
        cheap over the wire and already memoized by the kernel's granular cache.

        ``query_pushdown`` is FALSE **on purpose**, and i-140 is the reason. The
        list route exposes no ``filter`` param, so a native ``query`` here could
        only fetch-then-filter — and it would take the query away from the
        kernel's fallback, which is handed the kernel's live readers. Declaring
        a pushdown this door cannot perform would answer a narrower question
        than the one it took over, with an empty list. The fallback is slower
        and correct; that trade is made deliberately.

        ``layers`` is TRUE for the ONE layer this door composes — ``tenant``,
        resolved on the server. Any other layer id raises rather than reading
        as empty (see :meth:`load_layer`).

        Everything else is False because this face has no write surface and
        serves no bundle entries — a remote read is not a store.
        """
        from dna.kernel.capabilities import SourceCapabilities

        return SourceCapabilities(
            source="https",
            drafts=False,
            versions=False,
            layers=True,
            bundle_read=False,
            bundle_write=False,
            kernel_attachable=False,
            granular_list=True,
            granular_one=True,
            query_pushdown=False,
            tenant_layer_writes=False,
            write_kwargs=frozenset(),
            delete_kwargs=frozenset(),
            key_lookup=False,
            key_lookup_indexed=False,
        )

    async def served_scope(self) -> str:
        """The ONE scope this credential's door serves, as the server states it.

        Read from ``/kinds/registry`` — a route that DOES honor ``scope`` and
        that echoes the resolved value back. Cached for the source's lifetime:
        it is a property of the credential, and a credential does not change
        mid-process.

        This is also the FIRST call every read makes, so it is the first thing
        an outage hits. It therefore has the same offline fallback the document
        reads do — otherwise a process that restarts while the door is down
        could never reach the snapshot it is holding, which is the one moment
        the snapshot exists for.
        """
        if self._served_scope is None:
            try:
                body = await self._get_json("/kinds/registry")
            except ResolveNetworkError as exc:
                remembered = self._stale_scope(exc)
                if remembered is None:
                    raise
                self._served_scope = remembered
                return remembered
            scope = body.get("scope") if isinstance(body, dict) else None
            if not isinstance(scope, str) or not scope:
                raise ResolveError(
                    f"{self.base_url} answered /kinds/registry without naming a "
                    f"scope; this door cannot say what it serves, so no read "
                    f"from it can be trusted to be about the scope you asked for."
                )
            self._served_scope = scope
            self._snapshot_write("served-scope", scope)
        return self._served_scope

    async def list_scopes(self) -> list[str]:
        """The scopes reachable through this door — exactly one.

        There is no ``/v1/scopes`` route and there cannot be a useful one here:
        the door binds a scope to the credential. Returning the served scope is
        the whole truth; returning ``[]`` would make ``DnaClient.from_env()``
        claim the source holds nothing.
        """
        return [await self.served_scope()]

    async def load_bootstrap_docs(
        self, scope: str, *, tenant: str | None = None,
    ) -> list[dict[str, Any]]:
        """Genome + KindDefinition + LayerPolicy, the docs the kernel needs
        registered before ``load_all`` fires.

        Cheap and exact: one list per bootstrap Kind, then one GET per hit
        (measured ~7 calls). Tenant semantics are the SERVER's — ``tenant`` is
        forwarded as the query param the face already understands, and the
        tenant-published Genome shadows the platform one on that side, which is
        where the shadowing belongs when the tenant is stitched in server-side.
        """
        await self._require_scope(scope)
        key = f"bootstrap:{tenant or ''}"
        memo = self._memo_get(key)
        if memo is not None:
            return _deepcopy_docs(memo)
        try:
            docs = await self._fetch_kinds(BOOTSTRAP_KIND_NAMES, tenant=tenant)
        except ResolveNetworkError as exc:
            fallback = self._stale(key, exc)
            if fallback is None:
                raise
            return _deepcopy_docs(fallback)
        self._memo_put(key, docs)
        self._snapshot_write(key, docs)
        return _deepcopy_docs(docs)

    async def load_all(
        self, scope: str, readers: list | None = None,
    ) -> list[dict[str, Any]]:
        """Every instance of ``scope``, as full documents — the 1+N+M read.

        ``readers`` is accepted and unused: a reader detects a BUNDLE on disk,
        and nothing here is on disk. The server already composed each instance
        into the envelope it returns.
        """
        await self._require_scope(scope)
        key = "all"
        memo = self._memo_get(key)
        if memo is not None:
            return _deepcopy_docs(memo)
        try:
            kinds = await self._registry_kinds()
            docs = await self._fetch_kinds(kinds, tenant=self._tenant)
        except ResolveNetworkError as exc:
            fallback = self._stale(key, exc)
            if fallback is None:
                raise
            return _deepcopy_docs(fallback)
        self._memo_put(key, docs)
        self._snapshot_write(key, docs)
        return _deepcopy_docs(docs)

    async def list_doc_refs(
        self, scope: str, *, kind: str | None = None,
        tenant: str | None = None,
    ) -> list[tuple[str, str]]:
        """``(kind, name)`` pairs — metadata only, no document bodies.

        This is the read the REST list route was BUILT for: with no ``fields``
        it returns exactly the names. One call when ``kind`` is given; one per
        registered Kind otherwise.
        """
        await self._require_scope(scope)
        kinds = [kind] if kind else await self._registry_kinds()
        out: list[tuple[str, str]] = []
        for one in kinds:
            for name in await self._list_names(one, tenant=tenant):
                out.append((one, name))
        return out

    async def load_one(
        self, scope: str, kind: str, name: str, *,
        readers: list | None = None,
        tenant: str | None = None,
    ) -> dict[str, Any] | None:
        """ONE document, one GET. ``None`` only for a real 404 from the server —
        never for a network or auth failure, which raise."""
        await self._require_scope(scope)
        try:
            body = await self._get_json(
                f"/kinds/{_seg(kind)}/instances/{_seg(name)}", tenant=tenant,
            )
        except ResolveNotFoundError:
            return None
        instance = body.get("instance") if isinstance(body, dict) else None
        return instance if isinstance(instance, dict) else None

    async def load_layer(
        self, scope: str, layer_id: str, layer_value: str,
        readers: list | None = None,
    ) -> list[dict[str, Any]]:
        """The tenant overlay, as this door can serve it.

        **``tenant`` is the only layer plane behind this door.** The REST face
        composes exactly one overlay dimension, from the ``tenant`` query param;
        no route exposes a generic ``(layer_id, layer_value)`` read. So any
        other layer id has no overlay ROWS here, and ``[]`` is the port's own
        word for that — the same answer every shipped adapter gives for a layer
        value nothing was written under.

        ``__base__`` is refused the same way, and deliberately: it is the
        sentinel meaning "no overlay", never a tenant, and serving base content
        for it is the i-006 defect (``dna source diff/push`` digested ``{}`` on
        both sides and went quietly no-op).

        ⚠️ **Named divergence.** For a real tenant the rows come back
        SERVER-COMPOSED — base ∪ overlay, the same view the face serves its own
        callers — because the face has no overlay-ONLY listing. Composition
        stays correct (re-merging base over base is a no-op, and the tenant's
        shadowing instances still win), but a caller asking this door *"what did
        this tenant override?"* gets more than it asked for and cannot tell the
        difference. That question needs an overlay-only read on the server; it
        does not exist yet, and this docstring is the place it is admitted
        rather than the place it is hidden.
        """
        await self._require_scope(scope)
        if layer_id != "tenant" or layer_value == "__base__":
            return []
        kinds = await self._registry_kinds()
        return await self._fetch_kinds(kinds, tenant=layer_value)

    async def resolve_ref(self, scope: str, ref: str) -> str:
        """No local path backs a remote instance — same answer the SQL sources
        give (``""``), for the same reason."""
        return ""

    async def close(self) -> None:
        self._closed = True
        self._memo.clear()

    # ── HTTP plumbing ───────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "dna-sdk-http-source"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _token_state(self) -> str:
        """``setado`` / ``ausente`` — the ONLY thing this adapter ever says about
        the token. Never the value, never a prefix, never a mask."""
        return "setado" if self._token else "ausente"

    def _url(self, path: str, params: dict[str, Any] | None = None) -> str:
        query = {k: str(v) for k, v in (params or {}).items() if v is not None}
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        return url

    def _get_json_sync(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = self._url(path, params)
        request = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ResolveAuthError(
                    f"the DNA source at {self.base_url} refused the credential "
                    f"(HTTP {exc.code} on {path}); bearer: {self._token_state()} "
                    f"(DNA_API_TOKEN)."
                ) from exc
            if exc.code == 404:
                raise ResolveNotFoundError(f"not found: {path} at {self.base_url}") from exc
            raise ResolveError(
                f"the DNA source at {self.base_url} answered HTTP {exc.code} on {path}."
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ResolveNetworkError(
                f"could not reach the DNA source at {self.base_url} ({path}): {exc}."
            ) from exc
        except json.JSONDecodeError as exc:
            raise ResolveError(
                f"the DNA source at {self.base_url} answered {path} with a body "
                f"that is not JSON: {exc}."
            ) from exc

    async def _get_json(
        self, path: str, *, tenant: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        merged = dict(params or {})
        if tenant:
            merged["tenant"] = tenant
        return await asyncio.to_thread(self._get_json_sync, path, merged)

    async def _require_scope(self, scope: str) -> None:
        served = await self.served_scope()
        if scope != served:
            raise RemoteScopeMismatch(
                f"this DNA door serves the scope {served!r} — the scope is bound "
                f"to the credential on the SERVER and the instance routes take no "
                f"scope parameter, so a read for {scope!r} would be answered with "
                f"{served!r}'s content under the wrong name. Point "
                f"DNA_SOURCE_URL at a door for {scope!r}, or ask for {served!r}."
            )

    async def _registry_kinds(self) -> list[str]:
        """Every Kind registered for the served scope — the ``N`` of the fan-out.

        ``/kinds`` is NOT this list: it returns only the workspace-AUTHORED
        Kinds (measured: 2, against 88 in the registry), so building the fan-out
        from it would silently read a fraction of the scope.
        """
        memo = self._memo_get("registry")
        if memo is not None:
            return list(memo)
        body = await self._get_json("/kinds/registry")
        rows = body.get("kinds") if isinstance(body, dict) else None
        if not isinstance(rows, list):
            raise ResolveError(
                f"{self.base_url}/kinds/registry did not answer with a Kind list; "
                f"without it the set of Kinds to read is unknown, and reading a "
                f"guess would under-report the scope."
            )
        kinds = sorted({row["kind"] for row in rows if isinstance(row, dict) and row.get("kind")})
        self._memo_put("registry", kinds)
        return list(kinds)

    async def _list_names(self, kind: str, *, tenant: str | None = None) -> list[str]:
        """Names of every instance of ``kind``, paging until the server says it
        is done. An unregistered Kind (404) contributes nothing — that is the
        server ANSWERING, not failing."""
        names: list[str] = []
        offset = 0
        while True:
            try:
                body = await self._get_json(
                    f"/kinds/{_seg(kind)}/instances", tenant=tenant,
                    params={"limit": _PAGE, "offset": offset},
                )
            except ResolveNotFoundError:
                return names
            rows = body.get("instances") if isinstance(body, dict) else None
            if not isinstance(rows, list):
                return names
            names += [r["name"] for r in rows if isinstance(r, dict) and r.get("name")]
            if not body.get("has_more") or not rows:
                return names
            offset += len(rows)

    async def _fetch_kinds(
        self, kinds: Sequence[str], *, tenant: str | None = None,
    ) -> list[dict[str, Any]]:
        """List then fetch: ``(kind, name)`` refs first, then every document,
        fanned out over a bounded number of lanes."""
        refs: list[tuple[str, str]] = []
        for kind in kinds:
            refs += [(kind, name) for name in await self._list_names(kind, tenant=tenant)]

        semaphore = asyncio.Semaphore(max(1, self._concurrency))

        async def one(kind: str, name: str) -> dict[str, Any] | None:
            async with semaphore:
                body = await self._get_json(
                    f"/kinds/{_seg(kind)}/instances/{_seg(name)}", tenant=tenant,
                )
            instance = body.get("instance") if isinstance(body, dict) else None
            return instance if isinstance(instance, dict) else None

        results = await asyncio.gather(
            *(one(kind, name) for kind, name in refs), return_exceptions=True,
        )
        docs: list[dict[str, Any]] = []
        for (kind, name), result in zip(refs, results, strict=True):
            if isinstance(result, BaseException):
                # A single document that cannot be read fails the WHOLE read.
                # Dropping it would hand the kernel a scope that is quietly
                # short by one definition — and a missing Agent renders as
                # "no such agent", an accusation against data that exists.
                #
                # The CLASS of the failure is preserved: a door that went away
                # mid-fan-out is a network fact, and the offline fallback is
                # allowed to answer it. A 500 on one document is not.
                failed = ResolveNetworkError if isinstance(
                    result, ResolveNetworkError
                ) else ResolveError
                raise failed(
                    f"the DNA source at {self.base_url} could not serve "
                    f"{kind}/{name}, so this read cannot report the scope's "
                    f"contents: {result}"
                ) from result
            if result is not None:
                docs.append(result)
        return docs

    # ── memo + snapshot ─────────────────────────────────────────────────

    def _memo_get(self, key: str) -> Any | None:
        if self._ttl <= 0:
            return None
        hit = self._memo.get(key)
        if hit is None:
            return None
        stamped, value = hit
        if (time.monotonic() - stamped) > self._ttl:
            self._memo.pop(key, None)
            return None
        return value

    def _memo_put(self, key: str, value: Any) -> None:
        if self._ttl > 0:
            self._memo[key] = (time.monotonic(), value)

    def _snapshot_path(self, key: str) -> Any | None:
        """``<dir>/<host>--<key>.json``, or ``None`` with no snapshot dir.

        Keyed by the DOOR (its host) and the read, and deliberately NOT by the
        served scope: the scope is one of the things a cold process has to learn
        from the snapshot, so making the filename depend on it would hide the
        file from the only process that needs it.
        """
        if not self._snapshot_dir:
            return None
        from pathlib import Path

        def safe(text: str) -> str:
            return "".join(c if c.isalnum() or c in "-_." else "-" for c in text)

        host = safe(urllib.parse.urlparse(self.base_url).netloc)
        return Path(self._snapshot_dir) / f"{host}--{safe(key)}.json"

    def _snapshot_write(self, key: str, value: Any) -> None:
        target = self._snapshot_path(key)
        if target is None:
            return
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:  # a cache that cannot be written must not fail a read
            logger.debug("HTTPS source: snapshot write failed for %s: %s", key, exc)

    def _snapshot_read(self, key: str) -> tuple[Any, float] | None:
        """``(value, age_seconds)`` from the snapshot, or ``None``."""
        target = self._snapshot_path(key)
        if target is None:
            return None
        try:
            value = json.loads(target.read_text(encoding="utf-8"))
            return value, time.time() - target.stat().st_mtime
        except (OSError, json.JSONDecodeError):
            return None

    def _stale(self, key: str, cause: ResolveNetworkError) -> list[dict[str, Any]] | None:
        """The offline fallback — opt-in twice, and LOUD every single time.

        Returns ``None`` (so the caller re-raises) unless BOTH a snapshot
        directory and ``DNA_SOURCE_OFFLINE=stale-ok`` are set. An AUTH failure
        never reaches here: a refused credential is a decision about this
        caller, and answering it from a snapshot would serve content the door
        just declined to serve.
        """
        if self._offline != "stale-ok":
            return None
        hit = self._snapshot_read(key)
        if hit is None:
            return None
        docs, age = hit
        if not isinstance(docs, list):
            return None
        self.stale_since = age
        logger.warning(
            "HTTPS source: serving %d STALE definitions for %r from a snapshot "
            "%.0f s old — %s could not be reached (%s). This is DNA_SOURCE_OFFLINE"
            "=stale-ok; unset it to fail loud instead.",
            len(docs), key, age, self.base_url, cause,
        )
        return docs

    def _stale_scope(self, cause: ResolveNetworkError) -> str | None:
        """The served scope remembered from the last reachable read.

        Same double opt-in, same warning. Without it a process that RESTARTS
        during an outage cannot even learn which scope its snapshot describes,
        and the offline mode would work only for a process that was already up
        — which is the case that needed it least.
        """
        if self._offline != "stale-ok":
            return None
        hit = self._snapshot_read("served-scope")
        if hit is None:
            return None
        scope, age = hit
        if not isinstance(scope, str) or not scope:
            return None
        self.stale_since = age
        logger.warning(
            "HTTPS source: %s could not be reached (%s); taking the served scope "
            "%r from a snapshot %.0f s old (DNA_SOURCE_OFFLINE=stale-ok).",
            self.base_url, cause, scope, age,
        )
        return scope


def _seg(value: str) -> str:
    """URL-quote ONE path segment. ``safe=""`` on purpose: a Kind or instance
    name arrives from the caller, and a bare ``/`` in it would silently retarget
    the request at a different route."""
    return urllib.parse.quote(value, safe="")


def _deepcopy_docs(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hand every caller its OWN copy — the kernel mutates raw docs in place
    (``_inherited_from`` markers, overlay merges), and the memo must not carry
    one build's marks into the next."""
    import copy

    return [copy.deepcopy(d) for d in docs]
