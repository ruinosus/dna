"""A deliberately conformant DNAP server, and a dial of deliberate defects.

⚠️ **This is test scaffolding, not the product.** It stores dicts in a dict and
knows nothing about the kernel, the registry or any real Kind. It exists for one
job: to let the conformance suite be run against a server whose behaviour is
known, INCLUDING when that behaviour is wrong.

A conformance suite that has never failed is a suite nobody has tested. So this
stub takes a set of ``mutations`` — each one a defect the specification names,
several of them defects the specification names because they were MEASURED in
the reference implementation — and ``tests/test_dnap_conformance_kit.py``
asserts that each mutation makes its case, by name, fail. That is what separates
a suite that checks the contract from a suite that merely runs.

The vocabulary here is invented (``ConformanceWidget``, ``ConformanceGadget``)
precisely so it collides with no registered Kind: the suite must not need to
know a single real type name to test a server, and neither must this fixture.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# mutations — every one of them is a sentence in the spec, negated
# ---------------------------------------------------------------------------

#: §3 — answer an unserved channel with an empty collection instead of -32004.
EMPTY_ON_UNSERVED_CHANNEL = "empty_on_unserved_channel"
#: §3 — the measured REST defect: accept the address and serve another one.
SUBSTITUTE_CHANNEL = "substitute_channel"
#: §3 — fall back to the base scope when a tenant overlay is not served.
SUBSTITUTE_TENANT = "substitute_tenant"
#: §7 — answer an unadvertised Kind with `[]` instead of -32003.
EMPTY_ON_UNSERVED_KIND = "empty_on_unserved_kind"
#: §6.2 rule 1 — the measured defect: echo the projection, return less.
ECHO_SELECT_BUT_NARROW = "echo_select_but_narrow"
#: §6.2 rule 1 — accept any `select` and quietly ignore it.
SELECT_IS_A_HINT = "select_is_a_hint"
#: §6.2 rule 3 — let the snapshot move under a paginated read.
REVISION_MOVES_BETWEEN_PAGES = "revision_moves_between_pages"
#: §6.2 rule 2 — read an uninterpretable cursor as "the end".
FOREIGN_CURSOR_IS_EXHAUSTION = "foreign_cursor_is_exhaustion"
#: §6.2 — accept a write whose ifMatch is stale.
IGNORE_IFMATCH = "ignore_ifmatch"
#: §6.2 — "invalid", with no path and no rule.
BARE_VALIDATION_ERROR = "bare_validation_error"
#: §5 — accept authored values for the derived metadata members.
ACCEPT_DERIVED_METADATA = "accept_derived_metadata"
#: §7/§8.5 — the whole point: a store that answers `[]` come what may.
LIST_ALWAYS_EMPTY = "list_always_empty"
#: The tautology probe: everything after initialize is an error. Every
#: "must refuse" case in the suite would pass against this.
ERROR_ON_EVERYTHING = "error_on_everything"
#: §8.2 — answer an unknown method with a result.
UNKNOWN_METHOD_IS_A_RESULT = "unknown_method_is_a_result"
#: §4 — serve a Kind on a channel that initialize never advertised.
HIDDEN_KIND_ON_CHANNEL = "hidden_kind_on_channel"
#: §6.3 — leak the host's concerns into the definition contract.
RESOLVE_LEAKS_HOST_CONCERNS = "resolve_leaks_host_concerns"
#: §6.3 — a vendor client id where a coordinate belongs.
MODEL_IS_A_VENDOR_ID = "model_is_a_vendor_id"
#: §7 — a blank definition where "no such definition" belongs.
RESOLVE_BLANK_ON_MISSING = "resolve_blank_on_missing"
#: §6.4 rule 1 — a silent relevance floor.
SEARCH_HAS_A_RELEVANCE_FLOOR = "search_has_a_relevance_floor"
#: §6.4 rule 4 — the measured defect: narrow after the candidates are chosen.
NARROW_IS_A_POST_FILTER = "narrow_is_a_post_filter"
#: §6.4 rule 3 — one note, not two.
SEARCH_ONE_NOTE_ONLY = "search_one_note_only"
#: §6.4 rule 1 — no relevanceNotice at all.
SEARCH_HIDES_THE_NOTICE = "search_hides_the_notice"
#: §6.4 rule 5 — degraded, with a shrug for a reason.
DEGRADED_WITHOUT_REASON = "degraded_without_reason"
#: §6.5 — push the body to every watcher.
NOTIFICATION_CARRIES_THE_BODY = "notification_carries_the_body"
#: §2 — answer a notification.
ANSWER_NOTIFICATIONS = "answer_notifications"
#: §2 — no batch support.
NO_BATCH = "no_batch"
#: §6.2 — a paginated walk that silently skips a row.
PAGES_DROP_ROWS = "pages_drop_rows"

CHANNEL = "dnap-scope:/conformance"
API_VERSION = "example.test/dnap/v1"

#: How many candidates a plane over-fetches before ranking. Small on purpose:
#: §6.4 rule 4's defect is only VISIBLE when the budget is smaller than the
#: corpus, which is the condition it describes in production.
CANDIDATE_BUDGET = 8

_SCHEMAS: dict[str, dict[str, Any]] = {
    "ConformanceWidget": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "weight": {"type": "integer"},
            "model": {"type": "string"},
        },
        "required": ["title"],
    },
    "ConformanceGadget": {
        "type": "object",
        "properties": {"note": {"type": "string"}},
        "required": [],
    },
}

_DESCRIPTORS = [
    {"kind": "ConformanceWidget", "apiVersion": API_VERSION,
     "plane": "composition", "promptTarget": True, "writable": True},
    {"kind": "ConformanceGadget", "apiVersion": API_VERSION,
     "plane": "record", "promptTarget": False, "writable": True},
]


def _err(code: int, message: str, data: Any = None) -> dict:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return error


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t}


class DnapStubServer:
    """An in-memory DNAP 1.0 server. ``mutations`` turns obligations off."""

    def __init__(self, mutations: Iterable[str] = (), *, capabilities: Iterable[str] =
                 ("resolve", "search", "watch", "write")) -> None:
        self.mutations = frozenset(mutations)
        self.families = frozenset(capabilities)
        self.revision = 1000
        self.store: dict[tuple[str, str, str], dict] = {}
        self.notifications: list[dict] = []
        self.store_broken = False
        self.search_broken = False
        self.cursors_expired = False
        self._seed()

    def has(self, mutation: str) -> bool:
        return mutation in self.mutations

    # -- fixture ---------------------------------------------------------

    def _seed(self) -> None:
        """A corpus with two groups: a large one that ranks for the suite's
        query, and a small one that does not. §6.4 rule 4 is only observable
        when the narrowed rows are the ones the unnarrowed budget leaves out."""
        for i in range(10):
            self._put("ConformanceWidget", f"bulk-{i}",
                      {"title": f"conformance conformance widget bulk {i}",
                       "weight": i, "model": "openai/gpt-5.5"})
        for i in range(3):
            self._put("ConformanceWidget", f"alpha-{i}",
                      {"title": f"alpha unrelated vocabulary {i}", "weight": i,
                       "model": "openai/gpt-5.5"})
        self.notifications.clear()

    def _put(self, kind: str, name: str, spec: dict) -> dict:
        self.revision += 1
        doc = {
            "apiVersion": API_VERSION, "kind": kind,
            "metadata": {"name": name, "id": f"01J{name}", "revision": str(self.revision)},
            "spec": spec,
        }
        self.store[(CHANNEL, kind, name)] = doc
        note_params = {"channel": CHANNEL, "kind": kind, "name": name,
                       "change": "updated", "revision": str(self.revision)}
        if self.has(NOTIFICATION_CARRIES_THE_BODY):
            note_params["instance"] = copy.deepcopy(doc)
        self.notifications.append(
            {"jsonrpc": "2.0", "method": "notifications/instances/changed",
             "params": note_params})
        return doc

    # -- hooks the harness exposes --------------------------------------

    async def break_store(self) -> None:
        self.store_broken = True

    async def break_search(self) -> None:
        self.search_broken = True

    async def expire_cursors(self) -> None:
        self.cursors_expired = True

    async def break_resolution(self) -> str:
        name = "half-resolved"
        self._put("ConformanceWidget", name, {"title": "conformance half"})
        return name

    async def drain_notifications(self) -> list[dict]:
        drained, self.notifications = list(self.notifications), []
        return drained

    # -- wire ------------------------------------------------------------

    async def handle(self, request: Any) -> Any:
        if isinstance(request, list):
            if self.has(NO_BATCH):
                return _envelope(None, _err(-32600, "batch not supported"))
            out = [await self.handle(r) for r in request]
            return [r for r in out if r is not None]
        if not isinstance(request, dict):
            return _envelope(None, _err(-32600, "not a request object"))
        rid = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        is_notification = "id" not in request
        if is_notification and not self.has(ANSWER_NOTIFICATIONS):
            await self._dispatch(method, params)
            return None
        try:
            result = await self._dispatch(method, params)
        except _Refusal as refusal:
            return _envelope(rid, refusal.error)
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    async def _dispatch(self, method: str, params: dict) -> Any:
        if method == "initialize":
            return self._initialize()
        if self.has(ERROR_ON_EVERYTHING):
            raise _Refusal(_err(-32603, "internal error (mutation)"))
        handler = {
            "kinds/list": self._kinds_list,
            "kinds/describe": self._kinds_describe,
            "instances/list": self._instances_list,
            "instances/get": self._instances_get,
            "instances/write": self._instances_write,
            "instances/delete": self._instances_delete,
            "resolve/agent": self._resolve_agent,
            "resolve/copilot": self._resolve_copilot,
            "search/instances": self._search,
        }.get(method)
        if handler is None or not self._family_of(method) <= self.families:
            if self.has(UNKNOWN_METHOD_IS_A_RESULT):
                return {"instances": []}
            raise _Refusal(_err(-32601, f"method not found: {method}"))
        return handler(params)

    @staticmethod
    def _family_of(method: str) -> frozenset[str]:
        if method.startswith("resolve/"):
            return frozenset({"resolve"})
        if method.startswith("search/"):
            return frozenset({"search"})
        if method in ("instances/write", "instances/delete"):
            return frozenset({"write"})
        return frozenset()

    # -- methods ---------------------------------------------------------

    def _initialize(self) -> dict:
        caps: dict[str, Any] = {}
        if "resolve" in self.families:
            caps["resolve"] = {"agent": True, "copilot": True}
        if "search" in self.families:
            caps["search"] = {"planes": ["lexical", "semantic"]}
        if "watch" in self.families:
            caps["watch"] = {}
        if "write" in self.families:
            caps["write"] = {"validate": True}
        kinds = [d["kind"] for d in _DESCRIPTORS]
        if self.has(HIDDEN_KIND_ON_CHANNEL):
            kinds = kinds[:1]
        return {
            "protocolVersion": "1.0",
            "server": {"name": "dnap-stub", "version": "1.0"},
            "channels": [CHANNEL],
            "capabilities": caps,
            "kinds": kinds,
        }

    def _channel(self, params: dict) -> str:
        channel = params.get("channel")
        if channel == CHANNEL:
            return channel
        if isinstance(channel, str) and channel.startswith(CHANNEL + "#"):
            if self.has(SUBSTITUTE_TENANT):
                return CHANNEL
            raise _Refusal(_err(-32004, f"tenant overlay not served: {channel}"))
        if self.has(SUBSTITUTE_CHANNEL):
            return CHANNEL
        if self.has(EMPTY_ON_UNSERVED_CHANNEL):
            raise _Empty()
        raise _Refusal(_err(-32004, f"channel not served: {channel}"))

    def _kind(self, params: dict) -> str:
        kind = params.get("kind")
        if kind in _SCHEMAS:
            return kind
        if self.has(EMPTY_ON_UNSERVED_KIND):
            raise _Empty()
        raise _Refusal(_err(-32003, f"kind not served: {kind}"))

    def _kinds_list(self, params: dict) -> dict:
        self._channel(params)
        return {"kinds": copy.deepcopy(_DESCRIPTORS)}

    def _kinds_describe(self, params: dict) -> dict:
        self._channel(params)
        kind = self._kind(params)
        return {"kind": kind, "schema": copy.deepcopy(_SCHEMAS[kind]),
                "relations": []}

    def _rows(self, channel: str, kind: str) -> list[dict]:
        if self.store_broken:
            raise _Refusal(_err(-32603, "the store could not be read"))
        return [doc for (c, k, _), doc in self.store.items()
                if c == channel and k == kind]

    def _instances_list(self, params: dict) -> dict:
        try:
            channel = self._channel(params)
            kind = self._kind(params)
        except _Empty:
            return {"instances": [], "revision": str(self.revision), "selected": "full"}
        rows = sorted(self._rows(channel, kind),
                      key=lambda d: d["metadata"]["name"])
        if self.has(LIST_ALWAYS_EMPTY):
            return {"instances": [], "revision": str(self.revision), "selected": "full"}

        select = params.get("select", "full")
        if select not in ("full", "names") and not isinstance(select, list):
            if not self.has(SELECT_IS_A_HINT):
                raise _Refusal(_err(-32602, f"select cannot be honoured: {select!r}"))
            select = "full"

        cursor = params.get("cursor")
        snapshot = str(self.revision)
        offset = 0
        if cursor is not None:
            parsed = _parse_cursor(cursor)
            if parsed is None or self.cursors_expired:
                if self.has(FOREIGN_CURSOR_IS_EXHAUSTION):
                    return {"instances": [], "revision": snapshot, "selected": select}
                raise _Refusal(_err(-32005, "cursor expired; restart the listing"))
            snapshot, offset = parsed
            if self.has(REVISION_MOVES_BETWEEN_PAGES):
                self.revision += 1        # the snapshot moves under the read
                snapshot = str(self.revision)

        limit = params.get("limit") or len(rows) or 1
        if self.has(PAGES_DROP_ROWS) and cursor is not None:
            offset += 1
        window = rows[offset:offset + limit]
        out: dict[str, Any] = {
            "instances": [_project(doc, select, self.has(ECHO_SELECT_BUT_NARROW))
                          for doc in window],
            "revision": snapshot,
            "selected": select,
        }
        if offset + limit < len(rows):
            out["cursor"] = f"cur:{snapshot}:{offset + limit}"
        return out

    def _instances_get(self, params: dict) -> dict:
        channel = self._channel(params)
        kind = self._kind(params)
        doc = self.store.get((channel, kind, params.get("name")))
        if doc is None:
            raise _Refusal(_err(-32602, f"no such instance: {params.get('name')!r}"))
        if params.get("ifNoneMatch") == doc["metadata"]["revision"]:
            return {"notModified": True}
        return {"instance": copy.deepcopy(doc)}

    def _instances_write(self, params: dict) -> dict:
        channel = self._channel(params)
        instance = params.get("instance") or {}
        kind = self._kind(instance)
        metadata = instance.get("metadata") or {}
        name = metadata.get("name")
        if not isinstance(name, str) or not name:
            raise _Refusal(_err(-32602, "metadata.name is required"))
        if not self.has(ACCEPT_DERIVED_METADATA):
            supplied = [m for m in ("id", "revision") if m in metadata]
            if supplied:
                raise _Refusal(_err(
                    -32602, f"metadata {supplied!r} is derived and must not be supplied"))
        problem = _validate(_SCHEMAS[kind], instance.get("spec") or {})
        if problem is not None:
            path, rule = problem
            if self.has(BARE_VALIDATION_ERROR):
                raise _Refusal(_err(-32010, "invalid"))
            raise _Refusal(_err(-32010, f"{path}: {rule}",
                                {"path": path, "rule": rule}))
        if_match = params.get("ifMatch")
        existing = self.store.get((channel, kind, name))
        if if_match is not None and not self.has(IGNORE_IFMATCH):
            current = existing["metadata"]["revision"] if existing else None
            if current != if_match:
                raise _Refusal(_err(
                    -32011, "the stored revision moved",
                    {"revision": current}))
        doc = self._put(kind, name, copy.deepcopy(instance.get("spec") or {}))
        return {"instance": copy.deepcopy(doc)}

    def _instances_delete(self, params: dict) -> dict:
        channel = self._channel(params)
        kind = self._kind(params)
        self.store.pop((channel, kind, params.get("name")), None)
        self.revision += 1
        return {"deleted": True, "revision": str(self.revision)}

    # -- resolution ------------------------------------------------------

    def _resolve_agent(self, params: dict) -> dict:
        return self._resolve(params, source_kind="ConformanceWidget")

    def _resolve_copilot(self, params: dict) -> dict:
        return self._resolve(params, source_kind="ConformanceGadget")

    def _resolve(self, params: dict, *, source_kind: str) -> dict:
        channel = self._channel(params)
        name = params.get("name")
        doc = self.store.get((channel, "ConformanceWidget", name))
        if doc is None:
            if self.has(RESOLVE_BLANK_ON_MISSING):
                return {"resolved": {"name": name, "instructions": "", "tools": [],
                                     "revision": str(self.revision)}}
            raise _Refusal(_err(-32602, f"no such definition: {name!r}"))
        if name == "half-resolved":
            raise _Refusal(_err(-32020, "a referenced part could not be resolved"))
        resolved: dict[str, Any] = {
            "name": name,
            "instructions": f"You are {name}. {doc['spec'].get('title', '')}",
            "model": ("gpt-5.5-turbo-0125" if self.has(MODEL_IS_A_VENDOR_ID)
                      else doc["spec"].get("model", "openai/gpt-5.5")),
            "tools": [],
            "mcpServers": [],
            "toolsRequiringConfirmation": [],
            "knowledge": [],
            "sourceKind": source_kind,
            "sourceName": name,
            "revision": doc["metadata"]["revision"],
        }
        if self.has(RESOLVE_LEAKS_HOST_CONCERNS):
            resolved["checkpointer"] = {"kind": "postgres", "dsn": "…"}
            resolved["telemetrySink"] = "otlp://…"
        return {"resolved": resolved}

    # -- search ----------------------------------------------------------

    def _search(self, params: dict) -> dict:
        channel = self._channel(params)
        kind = self._kind(params)
        if self.search_broken:
            raise _Refusal(_err(-32030, "no plane could run"))
        rows = self._rows(channel, kind)
        query = _tokens(str(params.get("query") or ""))
        narrow = params.get("narrow") or {}
        prefix = narrow.get("namePrefix") or ""

        def scored(docs: list[dict]) -> list[tuple[float, dict]]:
            out = []
            for doc in docs:
                text = _tokens(doc["metadata"]["name"] + " " +
                               str(doc["spec"].get("title") or ""))
                overlap = len(query & text)
                similarity = overlap / max(len(query | text), 1)
                out.append((similarity, doc))
            return sorted(out, key=lambda t: (-t[0], t[1]["metadata"]["name"]))

        if self.has(NARROW_IS_A_POST_FILTER):
            # The measured defect: over-fetch a fixed budget, THEN narrow.
            candidates = scored(rows)[:CANDIDATE_BUDGET]
            candidates = [c for c in candidates
                          if c[1]["metadata"]["name"].startswith(prefix)]
        else:
            eligible = [d for d in rows if d["metadata"]["name"].startswith(prefix)]
            candidates = scored(eligible)[:CANDIDATE_BUDGET]

        if self.has(SEARCH_HAS_A_RELEVANCE_FLOOR):
            candidates = [c for c in candidates if c[0] >= 0.15]
        floor = params.get("minSimilarity")
        if floor is not None:
            candidates = [c for c in candidates if c[0] >= floor]

        k = params.get("k") or len(candidates)
        hits = []
        for rank, (similarity, doc) in enumerate(candidates[:k]):
            hit: dict[str, Any] = {
                "kind": doc["kind"], "name": doc["metadata"]["name"],
                "score": round(1.0 / (60 + rank), 6),
                "title": doc["spec"].get("title"),
                "snippet": str(doc["spec"].get("title") or "")[:80],
            }
            if not self.has(SEARCH_ONE_NOTE_ONLY):
                hit["similarity"] = round(similarity, 6)
            hits.append(hit)
        envelope: dict[str, Any] = {
            "hits": hits, "mode": "hybrid",
            "degraded": bool(self.has(DEGRADED_WITHOUT_REASON)),
            "degradedReason": None,
            "revision": str(self.revision),
        }
        if not self.has(SEARCH_HIDES_THE_NOTICE):
            envelope["relevanceNotice"] = "RANKED_NOT_FILTERED"
        return envelope


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class _Refusal(Exception):
    def __init__(self, error: dict) -> None:
        self.error = error


class _Empty(Exception):
    """Internal: the mutation that turns a refusal into an empty collection."""


def _envelope(rid: Any, error: dict) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "error": error}


def _parse_cursor(cursor: Any) -> tuple[str, int] | None:
    if not isinstance(cursor, str) or not cursor.startswith("cur:"):
        return None
    try:
        _, snapshot, offset = cursor.split(":", 2)
        return snapshot, int(offset)
    except ValueError:
        return None


def _project(doc: dict, select: Any, lie: bool) -> Any:
    if lie:
        return {"name": doc["metadata"]["name"]}   # echo `selected`, return less
    if select == "names":
        return {"metadata": {"name": doc["metadata"]["name"]}}
    if isinstance(select, list):
        out: dict[str, Any] = {}
        for path in select:
            cursor: Any = doc
            for part in str(path).split("."):
                cursor = cursor.get(part) if isinstance(cursor, dict) else None
            target = out
            parts = str(path).split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = cursor
        return out
    return copy.deepcopy(doc)


def _validate(schema: dict, spec: Any) -> tuple[str, str] | None:
    if not isinstance(spec, dict):
        return "spec", "type: object"
    props = schema.get("properties") or {}
    for key in schema.get("required") or ():
        if key not in spec:
            return f"spec.{key}", "required"
    types = {"string": str, "integer": int, "number": (int, float), "boolean": bool}
    for key, value in spec.items():
        expected = (props.get(key) or {}).get("type")
        py = types.get(expected)
        if py and not isinstance(value, py):
            return f"spec.{key}", f"type: {expected}"
    return None


def stub_harness(*mutations: str, capabilities: Iterable[str] =
                 ("resolve", "search", "watch", "write"), hooks: bool = True):
    """An async factory the conformance suite can consume directly."""
    from dna.testing import DnapHarness

    async def factory():
        server = DnapStubServer(mutations, capabilities=capabilities)
        return DnapHarness(
            endpoint=server.handle,
            break_store=server.break_store if hooks else None,
            break_search=server.break_search if hooks else None,
            break_resolution=server.break_resolution if hooks else None,
            expire_cursors=server.expire_cursors if hooks else None,
            drain_notifications=server.drain_notifications if hooks else None,
        )

    return factory
