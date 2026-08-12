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
#: §6.2 rule 4 — page in an order that is not the name order.
UNORDERED_LISTING = "unordered_listing"
#: §6.2 rule 5 — `"names"` as one-member documents: the narrower shape in a
#: disguise that satisfies every check asking only "did spec come back?".
NAMES_ARE_DOCUMENTS = "names_are_documents"
#: §6.2 rule 5 — helpfully attach identity to a path projection.
SELECT_PATHS_ADD_IDENTITY = "select_paths_add_identity"
#: §4 — treat the client's capability request as decorative.
IGNORE_CLIENT_CAPABILITIES = "ignore_client_capabilities"
#: §6.1 — store a KindDefinition without registering the type.
KIND_DEFINITION_DOES_NOT_REGISTER = "kind_definition_does_not_register"
#: §6.1 — accept metadata.name != spec.kind.
KIND_DEFINITION_NAME_MAY_DRIFT = "kind_definition_name_may_drift"
#: §6.1 — accept a schema keyword outside the bounded fifteen.
KIND_DEFINITION_SCHEMA_UNBOUNDED = "kind_definition_schema_unbounded"
#: §3 — a tenant write lands on the base.
TENANT_WRITE_HITS_THE_BASE = "tenant_write_hits_the_base"
#: §3 — a tenant delete leaves a tombstone that HIDES the base instance.
TENANT_DELETE_TOMBSTONES = "tenant_delete_tombstones"
#: §3 — the overlay does not read through to the base.
TENANT_DOES_NOT_READ_THROUGH = "tenant_does_not_read_through"
#: §7 — a missing instance is not -32002.
MISSING_IS_NOT_NOT_FOUND = "missing_is_not_not_found"
#: §7 — a read-only Kind accepts writes.
READ_ONLY_KIND_ACCEPTS_WRITES = "read_only_kind_accepts_writes"
#: §6.3 — add a member to the closed resolved shape.
RESOLVED_SHAPE_IS_OPEN = "resolved_shape_is_open"
#: §6.3 — knowledge as bare collection names (the pre-revision shape, gap D6).
KNOWLEDGE_IS_A_BARE_NAME = "knowledge_is_a_bare_name"
#: §7 — -32020 reports only the FIRST missing part.
RESOLUTION_REPORTS_ONE_GAP = "resolution_reports_one_gap"
#: §6.4 rule 2 — apply a threshold and say nothing about it.
MIN_SIMILARITY_IS_SILENT = "min_similarity_is_silent"
#: §6.4 rule 2 — report a count for a filter that never ran.
MIN_SIMILARITY_REPORTS_ZERO = "min_similarity_reports_zero"
#: §6.4 rule 3 — report a rank-derived number under the name `similarity`.
SIMILARITY_IS_CORPUS_DEPENDENT = "similarity_is_corpus_dependent"
#: §6.4 — report a mode outside the advertised planes.
MODE_IS_NOT_A_PLANE = "mode_is_not_a_plane"
#: §6.1 — publish a schema keyword the bound forbids through kinds/describe.
DESCRIBE_LEAKS_UNBOUNDED_KEYWORDS = "describe_leaks_unbounded_keywords"

CHANNEL = "dnap-scope:/conformance"
TENANT = "acme"
OVERLAY = f"{CHANNEL}#{TENANT}"
API_VERSION = "example.test/dnap/v1"

#: How many candidates a plane over-fetches before ranking. Small on purpose:
#: §6.4 rule 4's defect is only VISIBLE when the budget is smaller than the
#: corpus, which is the condition it describes in production.
CANDIDATE_BUDGET = 8

_SCHEMAS: dict[str, dict[str, Any]] = {
    "ConformanceLedger": {
        "type": "object",
        "properties": {"entry": {"type": "string"}},
        "required": [],
    },
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
    # §6.1 — the reflexive Kind. Its schema is itself inside the bound.
    "KindDefinition": {
        "type": "object",
        "properties": {
            "kind": {"type": "string"},
            "apiVersion": {"type": "string"},
            "plane": {"type": "string", "enum": ["composition", "record"]},
            "schema": {"type": "object"},
        },
        "required": ["kind", "apiVersion", "plane", "schema"],
    },
}

_DESCRIPTORS = [
    {"kind": "ConformanceWidget", "apiVersion": API_VERSION,
     "plane": "composition", "promptTarget": True, "writable": True},
    {"kind": "ConformanceGadget", "apiVersion": API_VERSION,
     "plane": "record", "promptTarget": False, "writable": True},
    {"kind": "KindDefinition", "apiVersion": "github.com/ruinosus/dna/core/v1",
     "plane": "record", "promptTarget": False, "writable": True},
    # served, and deliberately read-only — the -32006 lane.
    {"kind": "ConformanceLedger", "apiVersion": API_VERSION,
     "plane": "record", "promptTarget": False, "writable": False},
]


def _err(code: int, message: str, data: Any = None) -> dict:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return error


from dna.testing.dnap_conformance import BOUNDED_SCHEMA_KEYWORDS  # noqa: E402


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t}


class DnapStubServer:
    """An in-memory DNAP 1.0 server. ``mutations`` turns obligations off."""

    def __init__(self, mutations: Iterable[str] = (), *, capabilities: Iterable[str] =
                 ("resolve", "search", "watch", "write")) -> None:
        self.mutations = frozenset(mutations)
        self.families = frozenset(capabilities)
        #: §4 — set at initialize from what the CLIENT asked for. The effective
        #: set is the intersection, so this is not decoration.
        self.requested: frozenset[str] = frozenset(capabilities)
        self.revision = {CHANNEL: 1000, OVERLAY: 5000}   # §3 — one per channel
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
            self._put(CHANNEL, "ConformanceWidget", f"bulk-{i}",
                      {"title": f"conformance conformance widget bulk {i}",
                       "weight": i, "model": "openai/gpt-5.5"})
        for i in range(3):
            self._put(CHANNEL, "ConformanceWidget", f"alpha-{i}",
                      {"title": f"alpha unrelated vocabulary {i}", "weight": i,
                       "model": "openai/gpt-5.5"})
        self._put(CHANNEL, "ConformanceLedger", "ledger-0", {"entry": "opening"})
        self.notifications.clear()

    def _put(self, channel: str, kind: str, name: str, spec: dict) -> dict:
        self.revision[channel] = self.revision.get(channel, 0) + 1
        revision = str(self.revision[channel])
        doc = {
            "apiVersion": _api_version_of(kind), "kind": kind,
            "metadata": {"name": name, "id": f"01J{name}", "revision": revision},
            "spec": spec,
        }
        self.store[(channel, kind, name)] = doc
        note_params = {"channel": channel, "kind": kind, "name": name,
                       "change": "updated", "revision": revision}
        if self.has(NOTIFICATION_CARRIES_THE_BODY):
            note_params["instance"] = copy.deepcopy(doc)
        self.notifications.append(
            {"jsonrpc": "2.0", "method": "notifications/instances/changed",
             "params": note_params})
        return doc

    def _notify_kinds(self, kind: str, change: str) -> None:
        self.notifications.append(
            {"jsonrpc": "2.0", "method": "notifications/kinds/changed",
             "params": {"channel": CHANNEL, "kind": kind, "change": change}})

    # -- hooks the harness exposes --------------------------------------

    async def break_store(self) -> None:
        self.store_broken = True

    async def break_search(self) -> None:
        self.search_broken = True

    async def expire_cursors(self) -> None:
        self.cursors_expired = True

    async def break_resolution(self) -> tuple[str, int]:
        """Two holes, and the suite is TOLD there are two — §7 says -32020 reports
        all of them, and a black-box probe cannot count what it did not break."""
        name = "half-resolved"
        self._put(CHANNEL, "ConformanceWidget", name, {"title": "conformance half"})
        return name, 2

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
            try:
                await self._dispatch(method, params)
            except _Refusal:
                pass
            return None
        try:
            result = await self._dispatch(method, params)
        except _Refusal as refusal:
            return _envelope(rid, refusal.error)
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    async def _dispatch(self, method: str, params: dict) -> Any:
        if method == "initialize":
            return self._initialize(params)
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
        # §4 — the EFFECTIVE set is client ∩ server.
        effective = self.families if self.has(IGNORE_CLIENT_CAPABILITIES) else (
            self.families & self.requested)
        if handler is None or not self._family_of(method) <= effective:
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

    def _initialize(self, params: dict) -> dict:
        asked = params.get("capabilities")
        self.requested = frozenset(asked) if isinstance(asked, dict) else frozenset()
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
            "channels": [CHANNEL, OVERLAY],
            "capabilities": caps,
            "kinds": kinds,
        }

    def _channel(self, params: dict) -> str:
        channel = params.get("channel")
        if channel in (CHANNEL, OVERLAY):
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
        if kind in _SCHEMAS or (CHANNEL, "KindDefinition", kind) in self.store:
            return kind
        if self.has(EMPTY_ON_UNSERVED_KIND):
            raise _Empty()
        raise _Refusal(_err(-32003, f"kind not served: {kind}"))

    def _descriptors(self) -> list[dict]:
        out = [copy.deepcopy(d) for d in _DESCRIPTORS]
        if self.has(KIND_DEFINITION_DOES_NOT_REGISTER):
            return out
        for (channel, kind, name), doc in self.store.items():
            if kind != "KindDefinition":
                continue
            out.append({"kind": doc["spec"]["kind"],
                        "apiVersion": doc["spec"]["apiVersion"],
                        "plane": doc["spec"].get("plane", "record"),
                        "promptTarget": False, "writable": True})
        return out

    def _kinds_list(self, params: dict) -> dict:
        self._channel(params)
        return {"kinds": self._descriptors()}

    def _kinds_describe(self, params: dict) -> dict:
        self._channel(params)
        kind = self._kind(params)
        schema = _SCHEMAS.get(kind)
        if schema is None:
            doc = self.store.get((CHANNEL, "KindDefinition", kind))
            schema = (doc or {}).get("spec", {}).get("schema") or {"type": "object"}
        schema = copy.deepcopy(schema)
        if self.has(DESCRIBE_LEAKS_UNBOUNDED_KEYWORDS):
            schema["allOf"] = [{"required": []}]
        return {"kind": kind, "schema": schema, "relations": []}

    # -- the tenant overlay (§3) -----------------------------------------

    def _visible(self, channel: str, kind: str) -> dict[str, dict]:
        """Rows visible on ``channel``: read-through for an overlay."""
        if self.store_broken:
            raise _Refusal(_err(-32603, "the store could not be read"))
        rows: dict[str, dict] = {}
        if channel == OVERLAY and not self.has(TENANT_DOES_NOT_READ_THROUGH):
            for (c, k, name), doc in self.store.items():
                if c == CHANNEL and k == kind:
                    rows[name] = doc
        for (c, k, name), doc in self.store.items():
            if c == channel and k == kind:
                rows[name] = doc
        return rows

    def _instances_list(self, params: dict) -> dict:
        try:
            channel = self._channel(params)
            kind = self._kind(params)
        except _Empty:
            return {"instances": [], "revision": str(self.revision.get(CHANNEL, 0)),
                    "selected": "full"}
        rows = list(self._visible(channel, kind).values())
        # §6.2 rule 4 — lexicographic by metadata.name, ascending.
        if self.has(UNORDERED_LISTING):
            rows.sort(key=lambda d: d["metadata"]["name"], reverse=True)
        else:
            rows.sort(key=lambda d: d["metadata"]["name"])
        if self.has(LIST_ALWAYS_EMPTY):
            return {"instances": [], "revision": str(self.revision.get(channel, 0)),
                    "selected": "full"}

        select = params.get("select", "full")
        if select not in ("full", "names") and not isinstance(select, list):
            if not self.has(SELECT_IS_A_HINT):
                raise _Refusal(_err(-32602, f"select cannot be honoured: {select!r}"))
            select = "full"

        cursor = params.get("cursor")
        snapshot = str(self.revision.get(channel, 0))
        offset = 0
        if cursor is not None:
            parsed = _parse_cursor(cursor)
            if parsed is None or self.cursors_expired:
                if self.has(FOREIGN_CURSOR_IS_EXHAUSTION):
                    return {"instances": [], "revision": snapshot, "selected": select}
                raise _Refusal(_err(-32005, "cursor expired; restart the listing"))
            snapshot, offset = parsed
            if self.has(REVISION_MOVES_BETWEEN_PAGES):
                self.revision[channel] = self.revision.get(channel, 0) + 1
                snapshot = str(self.revision[channel])

        limit = params.get("limit") or len(rows) or 1
        if self.has(PAGES_DROP_ROWS) and cursor is not None:
            offset += 1
        window = rows[offset:offset + limit]
        out: dict[str, Any] = {
            "instances": [self._project(doc, select) for doc in window],
            "revision": snapshot,
            "selected": select,
        }
        if offset + limit < len(rows):
            out["cursor"] = f"cur:{snapshot}:{offset + limit}"
        return out

    def _project(self, doc: dict, select: Any) -> Any:
        if self.has(ECHO_SELECT_BUT_NARROW):
            return {"name": doc["metadata"]["name"]}   # echo `selected`, return less
        if select == "names":
            if self.has(NAMES_ARE_DOCUMENTS):
                return {"metadata": {"name": doc["metadata"]["name"]}}
            return doc["metadata"]["name"]             # §6.2 r5 — a plain string
        if isinstance(select, list):
            out: dict[str, Any] = {}
            for path in select:
                value: Any = doc
                for part in str(path).split("."):
                    value = value.get(part) if isinstance(value, dict) else None
                target, parts = out, str(path).split(".")
                for part in parts[:-1]:
                    target = target.setdefault(part, {})
                target[parts[-1]] = value
            if self.has(SELECT_PATHS_ADD_IDENTITY):
                out.setdefault("metadata", {})["name"] = doc["metadata"]["name"]
            return out
        return copy.deepcopy(doc)

    def _instances_get(self, params: dict) -> dict:
        channel = self._channel(params)
        kind = self._kind(params)
        doc = self._visible(channel, kind).get(params.get("name"))
        if doc is None:
            code = -32602 if self.has(MISSING_IS_NOT_NOT_FOUND) else -32002
            raise _Refusal(_err(code, f"no such instance: {params.get('name')!r}"))
        if params.get("ifNoneMatch") == doc["metadata"]["revision"]:
            return {"notModified": True}
        return {"instance": copy.deepcopy(doc)}

    def _instances_write(self, params: dict) -> dict:
        channel = self._channel(params)
        document = params.get("document") or {}          # §6.2 — `document`
        kind = self._kind(document)
        writable = {d["kind"]: d.get("writable", True) for d in self._descriptors()}
        if not writable.get(kind, True) and not self.has(READ_ONLY_KIND_ACCEPTS_WRITES):
            raise _Refusal(_err(-32006, f"{kind} is served but not writable"))
        metadata = document.get("metadata") or {}
        name = metadata.get("name")
        if not isinstance(name, str) or not name:
            raise _Refusal(_err(-32602, "metadata.name is required"))
        if not self.has(ACCEPT_DERIVED_METADATA):
            supplied = [m for m in ("id", "revision") if m in metadata]
            if supplied:
                raise _Refusal(_err(
                    -32010, f"metadata {supplied!r} is derived and must not be "
                            f"supplied",
                    {"path": f"metadata.{supplied[0]}", "rule": "derived"}))
        if kind == "KindDefinition":
            self._validate_kind_definition(name, document.get("spec") or {})
        problem = _validate(_SCHEMAS.get(kind) or {"type": "object"},
                            document.get("spec") or {})
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
                    -32011, "the stored revision moved", {"revision": current}))
        # §3 — write-local. The mutation lands it on the base instead.
        target = CHANNEL if self.has(TENANT_WRITE_HITS_THE_BASE) else channel
        doc = self._put(target, kind, name, copy.deepcopy(document.get("spec") or {}))
        if kind == "KindDefinition":
            self._notify_kinds(doc["spec"]["kind"], "registered")
        return {"instance": copy.deepcopy(doc), "created": existing is None}

    def _validate_kind_definition(self, name: str, spec: dict) -> None:
        if spec.get("kind") != name and not self.has(KIND_DEFINITION_NAME_MAY_DRIFT):
            raise _Refusal(_err(
                -32010, f"metadata.name {name!r} must equal spec.kind "
                        f"{spec.get('kind')!r}",
                {"path": "metadata.name", "rule": "must equal spec.kind"}))
        schema = spec.get("schema")
        if isinstance(schema, dict) and not self.has(KIND_DEFINITION_SCHEMA_UNBOUNDED):
            outside = sorted(_schema_keywords(schema) - BOUNDED_SCHEMA_KEYWORDS)
            if outside:
                raise _Refusal(_err(
                    -32010, f"spec.schema uses keywords outside the bounded set: "
                            f"{outside!r}",
                    {"path": "spec.schema", "rule": "bounded schema vocabulary"}))

    def _instances_delete(self, params: dict) -> dict:
        channel = self._channel(params)
        kind = self._kind(params)
        name = params.get("name")
        if self.store.pop((channel, kind, name), None) is None and \
                self._visible(channel, kind).get(name) is None:
            raise _Refusal(_err(-32002, f"no such instance: {name!r}"))
        if channel == OVERLAY and self.has(TENANT_DELETE_TOMBSTONES):
            # The defect: a tombstone that HIDES the base instance, making
            # "this tenant has no X" and "this tenant deleted X" one value.
            self.store[(OVERLAY, kind, name)] = {"__tombstone__": True}
        if kind == "KindDefinition":
            self._notify_kinds(name, "revoked")
        self.revision[channel] = self.revision.get(channel, 0) + 1
        return {"deleted": True, "revision": str(self.revision[channel])}

    # -- resolution ------------------------------------------------------

    def _resolve_agent(self, params: dict) -> dict:
        return self._resolve(params, source_kind="ConformanceWidget")

    def _resolve_copilot(self, params: dict) -> dict:
        return self._resolve(params, source_kind="ConformanceGadget")

    def _resolve(self, params: dict, *, source_kind: str) -> dict:
        channel = self._channel(params)
        name = params.get("name")
        doc = self._visible(channel, "ConformanceWidget").get(name)
        if doc is None:
            if self.has(RESOLVE_BLANK_ON_MISSING):
                return {"resolved": {"name": name, "instructions": "", "tools": [],
                                     "revision": str(self.revision.get(channel, 0))}}
            raise _Refusal(_err(-32002, f"no such definition: {name!r}"))
        if name == "half-resolved":
            missing = [{"kind": "ConformanceGadget", "name": "gone-a",
                        "via": "spec.tools[0]"},
                       {"kind": "ConformanceGadget", "name": "gone-b",
                        "via": "spec.tools[1]"}]
            if self.has(RESOLUTION_REPORTS_ONE_GAP):
                missing = missing[:1]
            raise _Refusal(_err(-32020, "a referenced part could not be resolved",
                                {"missing": missing}))
        knowledge: Any = [{"collection": "conformance-corpus",
                           "kind": "ConformanceWidget",
                           "narrow": {"namePrefix": "bulk-"}}]
        if self.has(KNOWLEDGE_IS_A_BARE_NAME):
            knowledge = ["conformance-corpus"]
        resolved: dict[str, Any] = {
            "name": name,
            "instructions": f"You are {name}. {doc['spec'].get('title', '')}",
            "model": ("gpt-5.5-turbo-0125" if self.has(MODEL_IS_A_VENDOR_ID)
                      else doc["spec"].get("model", "openai/gpt-5.5")),
            "tools": [],
            "mcpServers": [],
            "toolsRequiringConfirmation": [],
            "knowledge": knowledge,
            "sourceKind": source_kind,
            "sourceName": name,
            "revision": doc["metadata"]["revision"],
        }
        if self.has(RESOLVE_LEAKS_HOST_CONCERNS):
            resolved["checkpointer"] = {"kind": "postgres", "dsn": "…"}
            resolved["telemetrySink"] = "otlp://…"
        if self.has(RESOLVED_SHAPE_IS_OPEN):
            resolved["vendorHint"] = {"useOurFastPath": True}
        return {"resolved": resolved}

    # -- search ----------------------------------------------------------

    def _search(self, params: dict) -> dict:
        channel = self._channel(params)
        kind = self._kind(params)
        if self.search_broken:
            raise _Refusal(_err(-32030, "no plane could run"))
        rows = list(self._visible(channel, kind).values())
        query = _tokens(str(params.get("query") or ""))
        narrow = params.get("narrow") or {}
        prefix = narrow.get("namePrefix") or ""

        def scored(docs: list[dict]) -> list[tuple[float, dict]]:
            out = []
            for doc in docs:
                text = _tokens(doc["metadata"]["name"] + " " +
                               str(doc["spec"].get("title") or ""))
                # §6.4 rule 3 — a PROPERTY: a function of (query, document)
                # alone, so it cannot move when the candidate set does.
                similarity = len(query & text) / max(len(query | text), 1)
                out.append((similarity, doc))
            return sorted(out, key=lambda t: (-t[0], t[1]["metadata"]["name"]))

        if self.has(NARROW_IS_A_POST_FILTER):
            candidates = scored(rows)[:CANDIDATE_BUDGET]
            candidates = [c for c in candidates
                          if c[1]["metadata"]["name"].startswith(prefix)]
        else:
            eligible = [d for d in rows if d["metadata"]["name"].startswith(prefix)]
            candidates = scored(eligible)[:CANDIDATE_BUDGET]

        if self.has(SEARCH_HAS_A_RELEVANCE_FLOOR):
            candidates = [c for c in candidates if c[0] >= 0.15]
        floor = params.get("minSimilarity")
        removed = 0
        if floor is not None:
            kept = [c for c in candidates if c[0] >= floor]
            removed = len(candidates) - len(kept)
            candidates = kept

        k = params.get("k") or len(candidates)
        chosen = candidates[:k]
        hits = []
        for rank, (similarity, doc) in enumerate(chosen):
            hit: dict[str, Any] = {
                "kind": doc["kind"], "name": doc["metadata"]["name"],
                "score": round(1.0 / (60 + rank), 6),
                "title": doc["spec"].get("title"),
                "snippet": str(doc["spec"].get("title") or "")[:80],
            }
            if not self.has(SEARCH_ONE_NOTE_ONLY):
                if self.has(SIMILARITY_IS_CORPUS_DEPENDENT):
                    # a rank-derived number wearing the name `similarity`
                    hit["similarity"] = round(1.0 - rank / max(len(chosen), 1), 6)
                else:
                    hit["similarity"] = round(similarity, 6)
            hits.append(hit)
        envelope: dict[str, Any] = {
            "hits": hits,
            "mode": "notaplane" if self.has(MODE_IS_NOT_A_PLANE) else "hybrid",
            "degraded": bool(self.has(DEGRADED_WITHOUT_REASON)),
            "degradedReason": None,
            "revision": str(self.revision.get(channel, 0)),
        }
        if not self.has(SEARCH_HIDES_THE_NOTICE):
            envelope["relevanceNotice"] = "RANKED_NOT_FILTERED"
        # §6.4 rule 2 — the count travels, and is ABSENT when nothing was cut.
        if self.has(MIN_SIMILARITY_REPORTS_ZERO):
            envelope["minSimilarityRemoved"] = removed
        elif floor is not None and not self.has(MIN_SIMILARITY_IS_SILENT):
            envelope["minSimilarityRemoved"] = removed
        return envelope


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class _Refusal(Exception):
    def __init__(self, error: dict) -> None:
        self.error = error


class _Empty(Exception):
    """Internal: the mutation that turns a refusal into an empty collection."""


def _api_version_of(kind: str) -> str:
    if kind == "KindDefinition":
        return "github.com/ruinosus/dna/core/v1"
    return API_VERSION


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


def _schema_keywords(schema: Any, *, depth: int = 0) -> set[str]:
    if not isinstance(schema, dict) or depth > 12:
        return set()
    used = {k for k in schema if not k.startswith("$")}
    for sub in (schema.get("properties") or {}).values():
        used |= _schema_keywords(sub, depth=depth + 1)
    if isinstance(schema.get("items"), dict):
        used |= _schema_keywords(schema["items"], depth=depth + 1)
    if isinstance(schema.get("additionalProperties"), dict):
        used |= _schema_keywords(schema["additionalProperties"], depth=depth + 1)
    return used


def _validate(schema: dict, spec: Any) -> tuple[str, str] | None:
    if not isinstance(spec, dict):
        return "spec", "type: object"
    props = schema.get("properties") or {}
    for key in schema.get("required") or ():
        if key not in spec:
            return f"spec.{key}", "required"
    types = {"string": str, "integer": int, "number": (int, float), "boolean": bool,
             "object": dict, "array": list}
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
