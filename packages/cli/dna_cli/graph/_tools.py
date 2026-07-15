"""``dna_cli.graph._tools`` — the built-in OBO Graph tools.

Stories ``s-mcp-obo-calendar-tool`` (``ms_calendar_list``) and
``s-mcp-obo-files-group`` (``ms_files_search`` + ``ms_file_read``), ADR-mcp-obo §6.
Each is a THIN adapter, exactly like the other MCP tools: the tenancy/quota
``_guard`` seam → resolve the inbound Entra assertion → OBO exchange for the
group's scope (:func:`dna_cli.graph._obo`) → one or two Microsoft Graph calls → a
shaped, token-free result.

Two properties matter:

* **The surface is DATA.** ``description`` + ``input_schema`` come from the governed
  Tool docs ``tools/<name>.yaml`` (:func:`tool_surface`) — not hardcoded — so the
  model's view is overlayable like any Tool.
* **Token B never leaves.** The Graph token is acquired per request, used on the
  outbound Graph ``Authorization`` header, and dropped. The tools return domain
  fields only; the ``shape_*`` helpers copy named fields (never the token, never a
  preauth download URL, never the raw Graph body). ``ms_file_read`` additionally
  fetches file content from the driveItem's *preauth* download URL with NO auth
  header, so token B is confined to the single ``graph.microsoft.com`` metadata call.
"""
from __future__ import annotations

import functools
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from dna.tools import ToolSurface

from . import _config as C
from . import _obo as O
from .errors import OboError

_TOOLS_DIR = Path(__file__).resolve().parent / "tools"
_GRAPH_BASE = "https://graph.microsoft.com/v1.0"

#: Injectable Graph transport: ``(url, token, params) -> json dict``. Default does
#: a real httpx GET; tests inject a fake so no network/token is needed.
GraphCall = Callable[..., Awaitable[dict[str, Any]]]


@functools.lru_cache(maxsize=None)
def _load_doc(name: str) -> dict[str, Any]:
    import yaml

    path = _TOOLS_DIR / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"graph Tool doc not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def tool_surface(name: str) -> ToolSurface:
    """The governed agent-facing surface (description + parameters) of a graph
    Tool doc — the SAME projection ``dna.load_tools`` serves, read from the
    packaged Tool YAML so the built-in tool's description is data, not code."""
    doc = _load_doc(name)
    meta = doc.get("metadata") or {}
    spec = doc.get("spec") or {}
    return ToolSurface(
        description=str(meta.get("description") or "").strip(),
        parameters=dict(spec.get("input_schema") or {}),
    )


# ── Graph response shaping (pure) ──────────────────────────────────────────


def shape_calendar(raw: dict[str, Any]) -> dict[str, Any]:
    """Shape a Graph ``calendarView`` / ``events`` response into a compact,
    token-free result. Copies only named fields — tolerant of missing ones."""
    events = []
    for ev in (raw or {}).get("value") or []:
        events.append({
            "id": ev.get("id"),
            "subject": ev.get("subject") or "(no subject)",
            "start": ((ev.get("start") or {}).get("dateTime")),
            "end": ((ev.get("end") or {}).get("dateTime")),
            "location": ((ev.get("location") or {}).get("displayName")),
            "organizer": (((ev.get("organizer") or {}).get("emailAddress") or {}).get("name")),
            "web_link": ev.get("webLink"),
        })
    return {"count": len(events), "events": events}


# ── Files (OneDrive/SharePoint) shaping + classification (pure) ─────────────

#: Extensions we treat as text-extractable inline (decoded UTF-8). Deliberately
#: conservative: plain text + common structured/markup formats. Binary Office
#: (docx/xlsx/pptx) and images are NOT here — they get metadata + a web link.
_TEXT_EXTS = frozenset({
    "txt", "text", "md", "markdown", "mdx", "rst", "csv", "tsv", "json",
    "jsonl", "ndjson", "yaml", "yml", "toml", "ini", "cfg", "conf", "properties",
    "xml", "html", "htm", "svg", "log", "tex", "srt", "vtt", "sql", "sh", "bash",
    "zsh", "py", "js", "mjs", "cjs", "ts", "tsx", "jsx", "css", "scss", "less",
    "env", "gitignore", "dockerfile", "makefile", "gradle", "kt", "java", "go",
    "rs", "rb", "php", "c", "h", "cpp", "hpp", "cs", "swift", "r", "pl", "lua",
})


def _ext(name: str) -> str:
    """The lower-cased extension of ``name`` (without the dot), or ``""``."""
    base = (name or "").rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[-1].lower() if "." in base else ""


def _file_type(name: str, mime: str, is_folder: bool) -> str:
    """A short, human/agent-friendly type tag for a driveItem: ``folder``, the
    file extension when present (``docx``/``xlsx``/``pdf``/…), else the MIME
    subtype, else ``file``."""
    if is_folder:
        return "folder"
    ext = _ext(name)
    if ext:
        return ext
    if mime and "/" in mime:
        return mime.rsplit("/", 1)[-1]
    return "file"


def _is_text_mime(mime: str) -> bool:
    m = (mime or "").split(";", 1)[0].strip().lower()
    if m.startswith("text/"):
        return True
    return m in {
        "application/json", "application/xml", "application/xhtml+xml",
        "application/yaml", "application/x-yaml", "application/javascript",
        "application/typescript", "application/toml", "application/sql",
    }


def is_text_extractable(name: str, mime: str) -> bool:
    """Whether a file's content can be returned as inline text in this slice.

    True for text/* (and a few structured ``application/*`` text formats) or a
    known text extension; False for binary Office (docx/xlsx/pptx), images, PDFs,
    and anything else — those get metadata + a web link instead of a byte dump."""
    return _is_text_mime(mime) or _ext(name) in _TEXT_EXTS


def shape_files(raw: dict[str, Any]) -> dict[str, Any]:
    """Shape a Graph drive ``search`` response into a compact, token-free result.

    Copies only named fields (name, id, web URL, last-modified, size, type) — never
    the preauthenticated ``@microsoft.graph.downloadUrl`` (a leak-surface), never a
    token, never the raw Graph body. Tolerant of missing fields."""
    files = []
    for it in (raw or {}).get("value") or []:
        is_folder = "folder" in (it or {})
        mime = ((it.get("file") or {}).get("mimeType")) or ""
        files.append({
            "id": it.get("id"),
            "name": it.get("name") or "(unnamed)",
            "web_url": it.get("webUrl"),
            "last_modified": it.get("lastModifiedDateTime"),
            "size": it.get("size"),
            "type": _file_type(it.get("name") or "", mime, is_folder),
        })
    return {"count": len(files), "files": files}


def shape_file_meta(raw: dict[str, Any]) -> dict[str, Any]:
    """Shape a single driveItem's metadata (from a ``$select`` GET) into the
    token-free named fields shared by both file result modes."""
    is_folder = "folder" in (raw or {})
    mime = ((raw.get("file") or {}).get("mimeType")) or ""
    return {
        "id": raw.get("id"),
        "name": raw.get("name") or "(unnamed)",
        "web_url": raw.get("webUrl"),
        "last_modified": raw.get("lastModifiedDateTime"),
        "size": raw.get("size"),
        "type": _file_type(raw.get("name") or "", mime, is_folder),
    }


def _escape_odata_quote(value: str) -> str:
    """Escape a value for embedding inside an OData ``search(q='…')`` string: a
    single quote is doubled (OData literal escaping), so a query can never break
    out of the quoted string."""
    return (value or "").replace("'", "''")


def _default_window(start: str | None, end: str | None) -> tuple[str, str]:
    """Default the calendarView window to [today 00:00 UTC, +7d) when omitted."""
    if not start:
        now = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        start = now.isoformat().replace("+00:00", "Z")
    if not end:
        try:
            base = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            base = datetime.now(timezone.utc)
        end = (base + timedelta(days=7)).isoformat().replace("+00:00", "Z")
    return start, end


async def _default_graph_call(
    url: str, token: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """A real Microsoft Graph GET (httpx). Sends token B on the Authorization
    header; returns the JSON body. Never logs the token."""
    try:
        import httpx
    except ModuleNotFoundError as exc:  # pragma: no cover — exercised via CLI
        from .errors import OboExchangeError

        raise OboExchangeError(
            "the Microsoft Graph call needs the optional 'httpx' dependency — "
            "install it with: pip install 'dna-cli[graph]'"
        ) from exc

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            url, params=params or {},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        if resp.status_code >= 400:
            # Map to an honest, sanitized tool error — never echo the raw body.
            from .errors import OboExchangeError

            raise OboExchangeError(
                f"Microsoft Graph returned HTTP {resp.status_code} for the request."
            )
        return resp.json()


#: Injectable content transport for the preauthenticated download URL:
#: ``(url) -> bytes``. Default does a real httpx GET with NO Authorization header
#: (the download URL is preauth — token B never leaves ``graph.microsoft.com``).
FetchBytes = Callable[[str], Awaitable[bytes]]


async def _default_fetch_bytes(url: str) -> bytes:
    """Fetch a driveItem's preauthenticated download URL as raw bytes.

    Sends NO Authorization header: the ``@microsoft.graph.downloadUrl`` is already
    preauthenticated and short-lived, so token B stays on the single ``graph``
    metadata call and is never sent to the file CDN host. Follows the redirect."""
    try:
        import httpx
    except ModuleNotFoundError as exc:  # pragma: no cover — exercised via CLI
        from .errors import OboExchangeError

        raise OboExchangeError(
            "reading file content needs the optional 'httpx' dependency — "
            "install it with: pip install 'dna-cli[graph]'"
        ) from exc

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url)
        if resp.status_code >= 400:
            from .errors import OboExchangeError

            raise OboExchangeError(
                f"downloading the file content returned HTTP {resp.status_code}."
            )
        return resp.content


async def calendar_list_impl(
    *,
    assertion: str | None,
    tid: str | None,
    client_id: str | None,
    client_secret: str | None,
    scopes: list[str],
    start: str | None = None,
    end: str | None = None,
    top: int = 25,
    acquire: O.Acquirer = O._default_acquire,
    graph_call: GraphCall = _default_graph_call,
) -> dict[str, Any]:
    """The calendar-list use-case: OBO exchange → Graph ``calendarView`` → shape.

    Fully injectable (``acquire`` + ``graph_call``) so it is unit-testable with no
    live Entra / Graph. Raises the honest :mod:`dna_cli.graph.errors` on any edge."""
    token_b = O.exchange_on_behalf_of(
        assertion=assertion, tid=tid, client_id=client_id,
        client_secret=client_secret, scopes=scopes, allowed_scopes=scopes,
        acquire=acquire,
    )
    win_start, win_end = _default_window(start, end)
    raw = await graph_call(
        f"{_GRAPH_BASE}/me/calendarView", token_b,
        {
            "startDateTime": win_start, "endDateTime": win_end,
            "$top": max(1, min(int(top or 25), 100)),
            "$select": "id,subject,start,end,location,organizer,webLink",
            "$orderby": "start/dateTime",
        },
    )
    # token_b goes out of scope here — never returned, never logged.
    return shape_calendar(raw)


async def files_search_impl(
    *,
    assertion: str | None,
    tid: str | None,
    client_id: str | None,
    client_secret: str | None,
    scopes: list[str],
    query: str,
    top: int = 25,
    acquire: O.Acquirer = O._default_acquire,
    graph_call: GraphCall = _default_graph_call,
) -> dict[str, Any]:
    """The files-search use-case: OBO exchange → Graph drive ``search`` → shape.

    Searches the signed-in user's OneDrive/SharePoint via
    ``GET /me/drive/root/search(q='…')`` with the delegated ``Files.Read`` scope
    only. Fully injectable (``acquire`` + ``graph_call``) so it is unit-testable
    with no live Entra / Graph. Raises the honest :mod:`dna_cli.graph.errors` on
    any edge."""
    token_b = O.exchange_on_behalf_of(
        assertion=assertion, tid=tid, client_id=client_id,
        client_secret=client_secret, scopes=scopes, allowed_scopes=scopes,
        acquire=acquire,
    )
    q = _escape_odata_quote(query or "")
    raw = await graph_call(
        f"{_GRAPH_BASE}/me/drive/root/search(q='{q}')", token_b,
        {
            "$top": max(1, min(int(top or 25), 100)),
            "$select": "id,name,webUrl,size,lastModifiedDateTime,file,folder",
        },
    )
    # token_b goes out of scope here — never returned, never logged.
    return shape_files(raw)


#: The note returned instead of bytes when a file is not text-extractable inline.
_BINARY_NOTE = (
    "This file type is not text-extractable inline in this slice — open it in the "
    "browser via web_url. (Rich Office .docx/.xlsx/.pptx text extraction is a "
    "tracked follow-up.)"
)


async def file_read_impl(
    *,
    assertion: str | None,
    tid: str | None,
    client_id: str | None,
    client_secret: str | None,
    scopes: list[str],
    item_id: str,
    max_bytes: int = 1_048_576,
    acquire: O.Acquirer = O._default_acquire,
    graph_call: GraphCall = _default_graph_call,
    fetch_bytes: FetchBytes = _default_fetch_bytes,
) -> dict[str, Any]:
    """The file-read use-case: OBO exchange → Graph driveItem metadata → (for a
    text-convertible file) fetch + decode its content; otherwise return metadata
    plus an honest note.

    Token hygiene: the OBO token B is used ONLY on the ``graph.microsoft.com``
    metadata call; the content is then fetched from the driveItem's *preauth*
    ``@microsoft.graph.downloadUrl`` with NO Authorization header, so token B never
    leaves the Graph host. Delegated ``Files.Read`` only. Fully injectable for
    unit tests."""
    token_b = O.exchange_on_behalf_of(
        assertion=assertion, tid=tid, client_id=client_id,
        client_secret=client_secret, scopes=scopes, allowed_scopes=scopes,
        acquire=acquire,
    )
    meta = await graph_call(
        f"{_GRAPH_BASE}/me/drive/items/{item_id}", token_b,
        {"$select": "id,name,size,webUrl,lastModifiedDateTime,file,"
                    "@microsoft.graph.downloadUrl"},
    )
    # token_b is done after the metadata call — never sent to the file CDN below.
    shaped = shape_file_meta(meta)
    name = meta.get("name") or ""
    mime = ((meta.get("file") or {}).get("mimeType")) or ""
    download_url = meta.get("@microsoft.graph.downloadUrl")
    is_folder = "folder" in (meta or {})

    if not is_folder and download_url and is_text_extractable(name, mime):
        data = await fetch_bytes(download_url)
        cap = max(0, int(max_bytes))
        truncated = len(data) > cap
        text = data[:cap].decode("utf-8", errors="replace")
        return {**shaped, "mode": "text", "text": text, "truncated": truncated}

    # Binary Office / image / PDF / folder → honest metadata, never a byte dump.
    return {**shaped, "mode": "metadata", "note": _BINARY_NOTE}


# ── registration into the FastMCP server ───────────────────────────────────


def register_graph_tools(
    server: Any,
    cfg: C.GraphConfig,
    *,
    guard: Callable[..., Awaitable[Any]],
    obo_context: Callable[[], tuple[str | None, str | None]],
) -> list[str]:
    """Register the active ``graph.*`` tools on ``server`` (ADR §5 — built-in
    execution, config enablement).

    Only groups the config marks ACTIVE (block enabled AND group enabled) get
    their tools — each group is independent (``calendar``, ``files``, …), so a
    deployment can opt into any subset. With OBO off (``cfg is None`` handled by the
    caller) nothing is registered — the OSS/stdio path is untouched. ``guard`` is the
    tenancy/quota seam every tool passes through; ``obo_context`` yields the current
    request's (raw Entra assertion, tid) or ``(None, None)`` for a non-Entra identity.

    Returns the list of registered tool names (for the boot log / tests)."""
    from fastmcp.exceptions import ToolError

    registered: list[str] = []
    if cfg is None:
        return registered

    def _creds() -> tuple[str, str]:
        """Read the confidential-client id + secret from the env-var NAMES the
        config declares (never stored in config)."""
        return (
            os.environ.get(cfg.client_id_env or "") or "",
            os.environ.get(cfg.credential_env or "") or "",
        )

    def _require_entra(tool_name: str) -> tuple[str, str]:
        """The Entra gate shared by every graph tool: a non-Entra identity is an
        honest capability gap, not a crash."""
        assertion, tid = obo_context()
        if not assertion or not tid:
            raise ToolError(
                f"Microsoft Graph is not available for this identity — the "
                f"{tool_name} tool needs a Microsoft Entra sign-in (On-Behalf-Of has "
                f"no assertion to exchange for this token)."
            )
        return assertion, tid

    # ── calendar group ──────────────────────────────────────────────────────
    if cfg.is_active("calendar"):
        cal_surface = tool_surface("ms_calendar_list")
        cal_scopes = cfg.scopes_for("calendar")

        @server.tool(name="ms_calendar_list", description=cal_surface.description,
                     run_in_thread=False)
        async def ms_calendar_list(
            start: str | None = None, end: str | None = None, top: int = 25,
        ) -> dict[str, Any]:
            # Tenancy + quota (auth gating) — same seam as every other tool.
            await guard("definitions")
            assertion, tid = _require_entra("ms_calendar_list")
            client_id, client_secret = _creds()
            try:
                return await calendar_list_impl(
                    assertion=assertion, tid=tid, client_id=client_id,
                    client_secret=client_secret, scopes=cal_scopes,
                    start=start, end=end, top=top,
                )
            except OboError as exc:
                # unavailable / consent / interaction / scope / exchange — honest.
                raise ToolError(str(exc)) from None

        registered.append("ms_calendar_list")

    # ── files group (OneDrive / SharePoint, read-only) ──────────────────────
    if cfg.is_active("files"):
        files_scopes = cfg.scopes_for("files")
        search_surface = tool_surface("ms_files_search")
        read_surface = tool_surface("ms_file_read")

        @server.tool(name="ms_files_search", description=search_surface.description,
                     run_in_thread=False)
        async def ms_files_search(query: str, top: int = 25) -> dict[str, Any]:
            await guard("definitions")
            assertion, tid = _require_entra("ms_files_search")
            client_id, client_secret = _creds()
            try:
                return await files_search_impl(
                    assertion=assertion, tid=tid, client_id=client_id,
                    client_secret=client_secret, scopes=files_scopes,
                    query=query, top=top,
                )
            except OboError as exc:
                raise ToolError(str(exc)) from None

        registered.append("ms_files_search")

        @server.tool(name="ms_file_read", description=read_surface.description,
                     run_in_thread=False)
        async def ms_file_read(item_id: str) -> dict[str, Any]:
            await guard("definitions")
            assertion, tid = _require_entra("ms_file_read")
            client_id, client_secret = _creds()
            try:
                return await file_read_impl(
                    assertion=assertion, tid=tid, client_id=client_id,
                    client_secret=client_secret, scopes=files_scopes,
                    item_id=item_id,
                )
            except OboError as exc:
                raise ToolError(str(exc)) from None

        registered.append("ms_file_read")

    return registered
