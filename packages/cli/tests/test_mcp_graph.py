"""Feature ``f-mcp-obo`` — the Microsoft On-Behalf-Of (OBO) graph adapter.

Three stories, all proven here (mirrors ``test_mcp_auth.py``'s pure-core style):

1. **``s-mcp-obo-exchanger``** — the per-request OBO token exchange
   (:mod:`dna_cli.graph._obo`). Security-critical: token B never leaks, the
   scope allow-list is fail-closed (a tool can't escalate), consent-required and
   Conditional-Access challenges are honest errors (not crashes), the exchange
   always targets the assertion's *home tenant* (multi-tenant correctness), and a
   non-Entra identity is an honest capability gap.

2. **``s-mcp-obo-config-gating``** — the ``graph:`` config block
   (:mod:`dna_cli.graph._config`): OFF by default, an explicit fail-closed scope
   allow-list, the confidential-client credential as an ENV-VAR *name* (never a
   secret value in config).

3. **``s-mcp-obo-calendar-tool``** — the ``ms_calendar_list`` surface
   (:mod:`dna_cli.graph._tools`): the governed Tool doc (description +
   input_schema) and the Graph response shaping.

No live Entra and no secret are needed: the exchange seam (``acquire``) is
injected with a fake that returns MSAL-shaped result dicts. The single live smoke
is a documented MANUAL step (see ``docs/guides/mcp-obo.md``), not CI.
"""
from __future__ import annotations

import pytest

from dna_cli.graph import _config as C
from dna_cli.graph import _obo as O
from dna_cli.graph import errors as E


# ── s-mcp-obo-exchanger: the exchange (pure, fake acquirer) ─────────────────

_TID = "11111111-2222-3333-4444-555555555555"
_ASSERTION = "eyJ.inbound-user-token.sig"  # a stand-in bearer (never a real token)
_TOKEN_B = "eyJ.graph-audience-token-B.sig"


def _ok_acquirer(recorder: dict | None = None):
    """A fake MSAL acquirer that succeeds — records what it was called with."""

    def acquire(*, client_id, client_secret, authority, assertion, scopes):
        if recorder is not None:
            recorder.update(
                client_id=client_id, client_secret=client_secret,
                authority=authority, assertion=assertion, scopes=list(scopes),
            )
        return {"access_token": _TOKEN_B, "expires_in": 3600, "token_type": "Bearer"}

    return acquire


def _err_acquirer(result: dict):
    def acquire(*, client_id, client_secret, authority, assertion, scopes):
        return result

    return acquire


def test_exchange_returns_token_b_for_entra_assertion():
    tok = O.exchange_on_behalf_of(
        assertion=_ASSERTION, tid=_TID, client_id="app", client_secret="s",
        scopes=["Calendars.Read"], acquire=_ok_acquirer(),
    )
    assert tok == _TOKEN_B


def test_exchange_targets_the_assertions_home_tenant():
    """Multi-tenant correctness: the authority is the token's OWN ``tid``, never a
    fixed tenant — OBO hits the Graph of the tenant that issued the token."""
    rec: dict = {}
    O.exchange_on_behalf_of(
        assertion=_ASSERTION, tid=_TID, client_id="app", client_secret="s",
        scopes=["Calendars.Read"], acquire=_ok_acquirer(rec),
    )
    assert rec["authority"] == f"https://login.microsoftonline.com/{_TID}"
    assert _TID in rec["authority"]


def test_exchange_requests_exactly_the_asked_scopes():
    rec: dict = {}
    O.exchange_on_behalf_of(
        assertion=_ASSERTION, tid=_TID, client_id="app", client_secret="s",
        scopes=["Calendars.Read"], acquire=_ok_acquirer(rec),
    )
    assert rec["scopes"] == ["Calendars.Read"]  # not `.default`, not broadened.


def test_non_entra_identity_is_capability_gap_not_crash():
    with pytest.raises(E.OboUnavailableError):
        O.exchange_on_behalf_of(
            assertion=None, tid=None, client_id="app", client_secret="s",
            scopes=["Calendars.Read"], acquire=_ok_acquirer(),
        )
    # a tid without an assertion (mis-shaped) is equally unavailable.
    with pytest.raises(E.OboUnavailableError):
        O.exchange_on_behalf_of(
            assertion=None, tid=_TID, client_id="app", client_secret="s",
            scopes=["Calendars.Read"], acquire=_ok_acquirer(),
        )


def test_scope_allow_list_is_fail_closed_a_tool_cannot_escalate():
    """Defense in depth: even if a caller asks for a scope outside the config
    allow-list, the exchanger refuses BEFORE any exchange happens."""
    called = {"n": 0}

    def acquire(**_):
        called["n"] += 1
        return {"access_token": _TOKEN_B}

    with pytest.raises(E.OboScopeNotAllowedError):
        O.exchange_on_behalf_of(
            assertion=_ASSERTION, tid=_TID, client_id="app", client_secret="s",
            scopes=["Mail.Send"], allowed_scopes=["Calendars.Read"], acquire=acquire,
        )
    assert called["n"] == 0  # never reached the exchange — fail closed.


def test_consent_required_is_an_honest_error():
    result = {
        "error": "invalid_grant",
        "error_description": "AADSTS65001: The user or administrator has not "
                             "consented to use the application with ID '...'.",
        "error_codes": [65001],
    }
    with pytest.raises(E.OboConsentRequiredError) as exc:
        O.exchange_on_behalf_of(
            assertion=_ASSERTION, tid=_TID, client_id="app", client_secret="s",
            scopes=["Calendars.Read"], acquire=_err_acquirer(result),
        )
    # the message names the scope so the caller can act — but carries no token.
    assert "Calendars.Read" in str(exc.value)


def test_conditional_access_challenge_is_surfaced_not_swallowed():
    result = {
        "error": "interaction_required",
        "error_description": "AADSTS50076: Due to a configuration change...",
        "claims": '{"access_token":{"acrs":{"essential":true,"value":"c1"}}}',
    }
    with pytest.raises(E.OboInteractionRequiredError) as exc:
        O.exchange_on_behalf_of(
            assertion=_ASSERTION, tid=_TID, client_id="app", client_secret="s",
            scopes=["Calendars.Read"], acquire=_err_acquirer(result),
        )
    # the claims challenge is preserved for the client to step up.
    assert exc.value.claims_challenge == result["claims"]


def test_generic_graph_error_is_mapped_and_sanitized():
    result = {
        "error": "invalid_client",
        "error_description": "AADSTS7000215: Invalid client secret provided.",
        "error_codes": [7000215],
    }
    with pytest.raises(E.OboExchangeError) as exc:
        O.exchange_on_behalf_of(
            assertion=_ASSERTION, tid=_TID, client_id="app", client_secret="s",
            scopes=["Calendars.Read"], acquire=_err_acquirer(result),
        )
    msg = str(exc.value)
    assert "AADSTS7000215" in msg          # the AADSTS code helps diagnose,
    assert "Invalid client secret provided" not in msg  # but not the raw body.


def test_token_b_never_leaks_into_any_error():
    """The single most important security property: no failure path can echo
    token B (or the inbound assertion) into a surfaced error."""
    for result in (
        {"error": "invalid_grant", "error_description": f"boom {_TOKEN_B}",
         "error_codes": [65001]},
        {"error": "interaction_required", "claims": "{}"},
        {"error": "weird", "error_description": f"leak {_TOKEN_B} {_ASSERTION}"},
        {},  # empty / no access_token, no error
    ):
        try:
            O.exchange_on_behalf_of(
                assertion=_ASSERTION, tid=_TID, client_id="app", client_secret="s",
                scopes=["Calendars.Read"], acquire=_err_acquirer(result),
            )
        except E.OboError as exc:
            assert _TOKEN_B not in str(exc)
            assert _ASSERTION not in str(exc)
        else:  # pragma: no cover — every non-success result must raise.
            pytest.fail("a non-success MSAL result must raise, never pass silently")


def test_missing_credential_is_a_clean_error_not_a_none_secret_call():
    with pytest.raises(E.OboExchangeError):
        O.exchange_on_behalf_of(
            assertion=_ASSERTION, tid=_TID, client_id="app", client_secret=None,
            scopes=["Calendars.Read"], acquire=_ok_acquirer(),
        )


def test_audit_line_carries_no_secrets():
    """The structured audit helper records THAT an exchange happened — never the
    assertion, the token, or the secret."""
    line = O.audit_line(tenant="ws-1", tool="ms_calendar_list",
                        scopes=["Calendars.Read"], ok=True)
    assert "ms_calendar_list" in line and "Calendars.Read" in line
    assert _TOKEN_B not in line and _ASSERTION not in line and "secret" not in line.lower()


# ── s-mcp-obo-config-gating: the graph: config block ───────────────────────


def _cfg(**over):
    base = {
        "enabled": True,
        "client_id_env": "DNA_MCP_CLIENT_ID",
        "credential_env": "DNA_MCP_CLIENT_SECRET",
        "groups": {"calendar": {"enabled": True, "scopes": ["Calendars.Read"]}},
    }
    base.update(over)
    return base


def test_graph_absent_means_off():
    assert C.parse_graph_config(None) is None
    assert C.parse_graph_config({}) is None or C.parse_graph_config({}).enabled is False


def test_graph_disabled_by_default_when_enabled_missing():
    gc = C.parse_graph_config({"client_id_env": "X", "credential_env": "Y", "groups": {}})
    assert gc is not None and gc.enabled is False


def test_graph_parses_enabled_block():
    gc = C.parse_graph_config(_cfg())
    assert gc.enabled is True
    assert gc.client_id_env == "DNA_MCP_CLIENT_ID"
    assert gc.credential_env == "DNA_MCP_CLIENT_SECRET"
    assert gc.group_enabled("calendar") is True
    assert gc.scopes_for("calendar") == ["Calendars.Read"]


def test_credential_is_an_env_var_name_never_a_secret_value():
    """The config carries the NAME of the env var, and the parser rejects a value
    that looks like an inline secret (defense against a foot-gun)."""
    # a plausible secret value in the *_env field is refused.
    with pytest.raises(ValueError):
        C.parse_graph_config(_cfg(credential_env="s3cr3t~Value.With/Symbols=="))


def test_scope_allow_list_fail_closed():
    gc = C.parse_graph_config(_cfg())
    # in the list → allowed
    C.assert_scope_allowed(gc, "calendar", "Calendars.Read")
    # not in the list → refused (a tool cannot request it)
    with pytest.raises(E.OboScopeNotAllowedError):
        C.assert_scope_allowed(gc, "calendar", "Calendars.ReadWrite")
    # unknown group → refused
    with pytest.raises(E.OboScopeNotAllowedError):
        C.assert_scope_allowed(gc, "mail", "Mail.Send")


def test_group_disabled_is_not_active():
    gc = C.parse_graph_config(_cfg(groups={"calendar": {"enabled": False, "scopes": ["Calendars.Read"]}}))
    assert gc.group_enabled("calendar") is False


def test_bad_graph_shape_fails_loud():
    with pytest.raises(ValueError):
        C.parse_graph_config({"enabled": True})  # no client_id_env/credential_env
    with pytest.raises(ValueError):
        C.parse_graph_config(_cfg(groups={"calendar": {"enabled": True, "scopes": []}}))  # empty scopes


def test_active_when_enabled_and_group_on():
    gc = C.parse_graph_config(_cfg())
    assert gc.is_active("calendar") is True
    off = C.parse_graph_config(_cfg(enabled=False))
    assert off.is_active("calendar") is False


# ── s-mcp-obo-calendar-tool: the governed Tool surface + shaping ───────────


def test_calendar_tool_doc_is_governed_data():
    from dna_cli.graph import _tools as T

    surface = T.tool_surface("ms_calendar_list")
    assert surface.description and "calendar" in surface.description.lower()
    assert surface.parameters.get("type") == "object"
    props = surface.parameters.get("properties", {})
    assert "start" in props and "end" in props  # the calendarView window


def test_calendar_response_shaping_drops_noise_and_never_carries_a_token():
    from dna_cli.graph import _tools as T

    raw = {
        "value": [
            {"id": "1", "subject": "Standup",
             "start": {"dateTime": "2026-07-15T09:00:00", "timeZone": "UTC"},
             "end": {"dateTime": "2026-07-15T09:15:00", "timeZone": "UTC"},
             "location": {"displayName": "Room 1"},
             "organizer": {"emailAddress": {"name": "Alex", "address": "a@partner-org.test"}},
             "webLink": "https://outlook.office365.com/...", "bodyPreview": "notes"},
        ],
        "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/calendarView?...",
    }
    shaped = T.shape_calendar(raw)
    assert shaped["count"] == 1
    ev = shaped["events"][0]
    assert ev["subject"] == "Standup"
    assert ev["start"] == "2026-07-15T09:00:00"
    assert ev["location"] == "Room 1"
    assert ev["organizer"] == "Alex"
    assert _TOKEN_B not in str(shaped)


def test_calendar_shaping_tolerates_missing_fields():
    from dna_cli.graph import _tools as T

    shaped = T.shape_calendar({"value": [{"id": "x"}]})
    assert shaped["count"] == 1
    assert shaped["events"][0]["subject"] == "(no subject)"


def test_calendar_list_impl_end_to_end_with_fakes():
    """The tool use-case runs OBO → Graph → shape with injected fakes — no live
    Entra, no secret, no network. The Graph token B is used but never surfaced."""
    import asyncio

    from dna_cli.graph import _tools as T

    seen: dict = {}

    async def fake_graph_call(url, token, params=None):
        seen["url"] = url
        seen["token"] = token
        seen["params"] = params
        return {"value": [
            {"id": "1", "subject": "Sync",
             "start": {"dateTime": "2026-07-15T10:00:00"},
             "end": {"dateTime": "2026-07-15T10:30:00"}},
        ]}

    out = asyncio.run(T.calendar_list_impl(
        assertion=_ASSERTION, tid=_TID, client_id="app", client_secret="s",
        scopes=["Calendars.Read"], top=10,
        acquire=_ok_acquirer(), graph_call=fake_graph_call,
    ))
    assert out["count"] == 1 and out["events"][0]["subject"] == "Sync"
    assert seen["url"].endswith("/me/calendarView")
    assert seen["token"] == _TOKEN_B          # token B reached the Graph call,
    assert _TOKEN_B not in str(out)           # but never the shaped result.


# ── s-mcp-obo-files-group: the files config group (fail-closed) ─────────────


def _files_cfg(**over):
    base = {
        "enabled": True,
        "client_id_env": "DNA_MCP_CLIENT_ID",
        "credential_env": "DNA_MCP_CLIENT_SECRET",
        "groups": {"files": {"enabled": True, "scopes": ["Files.Read"]}},
    }
    base.update(over)
    return base


def test_files_group_parses_and_is_active():
    gc = C.parse_graph_config(_files_cfg())
    assert gc.group_enabled("files") is True
    assert gc.scopes_for("files") == ["Files.Read"]
    assert gc.is_active("files") is True
    assert "files" in gc.active_groups()


def test_files_group_scope_allow_list_is_fail_closed():
    """A tool in the files group can only ever request Files.Read — a broader
    scope (Files.ReadWrite / Files.Read.All) is refused, and the exchanger refuses
    it independently too (defense in depth)."""
    gc = C.parse_graph_config(_files_cfg())
    C.assert_scope_allowed(gc, "files", "Files.Read")
    for escalation in ("Files.ReadWrite", "Files.Read.All", "Sites.Read.All"):
        with pytest.raises(E.OboScopeNotAllowedError):
            C.assert_scope_allowed(gc, "files", escalation)


def test_files_group_disabled_is_not_active():
    gc = C.parse_graph_config(
        _files_cfg(groups={"files": {"enabled": False, "scopes": ["Files.Read"]}})
    )
    assert gc.group_enabled("files") is False
    assert gc.is_active("files") is False


# ── s-mcp-obo-files-group: ms_files_search (surface + shaping + impl) ────────


def test_files_search_tool_doc_is_governed_data():
    from dna_cli.graph import _tools as T

    surface = T.tool_surface("ms_files_search")
    assert surface.description and "file" in surface.description.lower()
    assert surface.parameters.get("type") == "object"
    assert "query" in surface.parameters.get("properties", {})


def test_files_search_shaping_keeps_named_fields_and_no_token():
    from dna_cli.graph import _tools as T

    raw = {
        "value": [
            {
                "id": "01ABC",
                "name": "Q3 Plan.docx",
                "webUrl": "https://acme-my.sharepoint.test/…/Q3%20Plan.docx",
                "lastModifiedDateTime": "2026-07-10T12:00:00Z",
                "size": 20480,
                "file": {"mimeType": "application/vnd.openxmlformats-"
                         "officedocument.wordprocessingml.document"},
                "searchResult": {"onClickTelemetryUrl": "https://bing.com/…"},
                "@microsoft.graph.downloadUrl": "https://…files.1drv.test/y23",
            },
            {"id": "02DEF", "name": "Reports", "folder": {"childCount": 3},
             "webUrl": "https://…/Reports", "size": 0},
        ],
        "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/drive/root/search(…)",
    }
    shaped = T.shape_files(raw)
    assert shaped["count"] == 2
    f0 = shaped["files"][0]
    assert f0["name"] == "Q3 Plan.docx"
    assert f0["id"] == "01ABC"
    assert f0["web_url"].endswith("Q3%20Plan.docx")
    assert f0["last_modified"] == "2026-07-10T12:00:00Z"
    assert f0["size"] == 20480
    assert f0["type"] == "docx"
    assert shaped["files"][1]["type"] == "folder"
    # the preauth download URL is NOT surfaced by search (leak-surface hygiene),
    # and nothing token-shaped rides along.
    assert "downloadUrl" not in str(shaped)
    assert _TOKEN_B not in str(shaped)


def test_files_search_shaping_tolerates_missing_fields():
    from dna_cli.graph import _tools as T

    shaped = T.shape_files({"value": [{"id": "x"}]})
    assert shaped["count"] == 1
    assert shaped["files"][0]["name"] == "(unnamed)"


def test_files_search_impl_end_to_end_with_fakes():
    """OBO → Graph search → shape, all injected. Scope is exactly Files.Read; the
    query is quoted into the search function; token B reaches Graph, never the result."""
    import asyncio

    from dna_cli.graph import _tools as T

    seen: dict = {}

    async def fake_graph_call(url, token, params=None):
        seen["url"] = url
        seen["token"] = token
        seen["params"] = params
        return {"value": [
            {"id": "1", "name": "budget.xlsx",
             "webUrl": "https://…/budget.xlsx", "size": 5120,
             "lastModifiedDateTime": "2026-07-01T00:00:00Z",
             "file": {"mimeType": "application/vnd.openxmlformats-"
                      "officedocument.spreadsheetml.sheet"}},
        ]}

    rec: dict = {}
    out = asyncio.run(T.files_search_impl(
        assertion=_ASSERTION, tid=_TID, client_id="app", client_secret="s",
        scopes=["Files.Read"], query="budget", top=10,
        acquire=_ok_acquirer(rec), graph_call=fake_graph_call,
    ))
    assert out["count"] == 1 and out["files"][0]["name"] == "budget.xlsx"
    assert out["files"][0]["type"] == "xlsx"
    assert rec["scopes"] == ["Files.Read"]         # not broadened.
    assert "/me/drive/root/search" in seen["url"]
    assert "budget" in seen["url"]                 # the query is in the function call.
    assert seen["token"] == _TOKEN_B               # token B reached Graph,
    assert _TOKEN_B not in str(out)                # but never the shaped result.


def test_files_search_impl_escapes_single_quote_in_query():
    """A single quote in the query must be escaped so it can't break out of the
    OData search(q='…') string (injection hygiene)."""
    import asyncio

    from dna_cli.graph import _tools as T

    seen: dict = {}

    async def fake_graph_call(url, token, params=None):
        seen["url"] = url
        return {"value": []}

    asyncio.run(T.files_search_impl(
        assertion=_ASSERTION, tid=_TID, client_id="app", client_secret="s",
        scopes=["Files.Read"], query="O'Brien plan",
        acquire=_ok_acquirer(), graph_call=fake_graph_call,
    ))
    # the raw lone quote must not appear unescaped as q='O'Brien…'
    assert "q='O''Brien plan'" in seen["url"] or "O%27%27Brien" in seen["url"]


# ── s-mcp-obo-files-group: ms_file_read (classify + text vs binary) ─────────


def test_classify_text_extractable_vs_binary():
    from dna_cli.graph import _tools as T

    assert T.is_text_extractable("notes.md", "text/markdown") is True
    assert T.is_text_extractable("data.csv", "text/csv") is True
    assert T.is_text_extractable("a.json", "application/json") is True
    assert T.is_text_extractable("readme", "text/plain") is True
    # binary Office → not inline-extractable in this slice.
    assert T.is_text_extractable(
        "plan.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ) is False
    assert T.is_text_extractable("sheet.xlsx", "application/octet-stream") is False
    assert T.is_text_extractable("pic.png", "image/png") is False


def test_file_read_returns_text_for_text_file_token_stays_on_graph():
    """A text file: metadata via Graph (token B), then the preauth downloadUrl is
    fetched WITHOUT any token (token B never leaves graph.microsoft.com)."""
    import asyncio

    from dna_cli.graph import _tools as T

    graph_seen: dict = {}
    fetch_seen: dict = {}

    async def fake_graph_call(url, token, params=None):
        graph_seen["url"] = url
        graph_seen["token"] = token
        return {
            "id": "1", "name": "notes.md", "size": 12,
            "webUrl": "https://…/notes.md",
            "lastModifiedDateTime": "2026-07-01T00:00:00Z",
            "file": {"mimeType": "text/markdown"},
            "@microsoft.graph.downloadUrl": "https://dl.files.1drv.test/notes",
        }

    async def fake_fetch_bytes(url):
        fetch_seen["url"] = url
        return b"# Notes\nhello"

    out = asyncio.run(T.file_read_impl(
        assertion=_ASSERTION, tid=_TID, client_id="app", client_secret="s",
        scopes=["Files.Read"], item_id="1",
        acquire=_ok_acquirer(), graph_call=fake_graph_call,
        fetch_bytes=fake_fetch_bytes,
    ))
    assert out["mode"] == "text"
    assert out["text"] == "# Notes\nhello"
    assert out["truncated"] is False
    assert out["name"] == "notes.md"
    assert graph_seen["token"] == _TOKEN_B                  # metadata used token B,
    assert fetch_seen["url"] == "https://dl.files.1drv.test/notes"
    assert "graph.microsoft.com" in graph_seen["url"]       # only the graph host saw it.
    assert _TOKEN_B not in str(out)


def test_file_read_binary_office_returns_metadata_note_not_bytes():
    """A .docx (binary Office) is NOT dumped inline — the caller gets honest
    metadata + web_url + a not-text-extractable note, and the content is never fetched."""
    import asyncio

    from dna_cli.graph import _tools as T

    fetched = {"n": 0}

    async def fake_graph_call(url, token, params=None):
        return {
            "id": "9", "name": "Q3 Plan.docx", "size": 30720,
            "webUrl": "https://…/Q3%20Plan.docx",
            "lastModifiedDateTime": "2026-07-10T00:00:00Z",
            "file": {"mimeType": "application/vnd.openxmlformats-"
                     "officedocument.wordprocessingml.document"},
            "@microsoft.graph.downloadUrl": "https://dl.files.1drv.test/q3",
        }

    async def fake_fetch_bytes(url):  # must NOT be called for binary Office.
        fetched["n"] += 1
        return b"PK\x03\x04binary"

    out = asyncio.run(T.file_read_impl(
        assertion=_ASSERTION, tid=_TID, client_id="app", client_secret="s",
        scopes=["Files.Read"], item_id="9",
        acquire=_ok_acquirer(), graph_call=fake_graph_call,
        fetch_bytes=fake_fetch_bytes,
    ))
    assert out["mode"] == "metadata"
    assert out["name"] == "Q3 Plan.docx"
    assert out["web_url"].endswith("Q3%20Plan.docx")
    assert out["type"] == "docx"
    assert "note" in out and out["note"]
    assert "text" not in out                    # never dumped bytes.
    assert fetched["n"] == 0                     # content stream never fetched.


def test_file_read_caps_large_text_and_flags_truncated():
    import asyncio

    from dna_cli.graph import _tools as T

    async def fake_graph_call(url, token, params=None):
        return {
            "id": "big", "name": "huge.txt", "size": 10_000_000,
            "webUrl": "https://…/huge.txt", "file": {"mimeType": "text/plain"},
            "@microsoft.graph.downloadUrl": "https://dl.files.1drv.test/huge",
        }

    async def fake_fetch_bytes(url):
        return b"x" * 5000

    out = asyncio.run(T.file_read_impl(
        assertion=_ASSERTION, tid=_TID, client_id="app", client_secret="s",
        scopes=["Files.Read"], item_id="big", max_bytes=1000,
        acquire=_ok_acquirer(), graph_call=fake_graph_call,
        fetch_bytes=fake_fetch_bytes,
    ))
    assert out["mode"] == "text"
    assert out["truncated"] is True
    assert len(out["text"].encode("utf-8")) <= 1000


def test_file_read_requests_exactly_files_read_scope():
    import asyncio

    from dna_cli.graph import _tools as T

    rec: dict = {}

    async def fake_graph_call(url, token, params=None):
        return {"id": "1", "name": "x.txt", "size": 1,
                "file": {"mimeType": "text/plain"},
                "@microsoft.graph.downloadUrl": "https://dl/x"}

    async def fake_fetch_bytes(url):
        return b"x"

    asyncio.run(T.file_read_impl(
        assertion=_ASSERTION, tid=_TID, client_id="app", client_secret="s",
        scopes=["Files.Read"], item_id="1",
        acquire=_ok_acquirer(rec), graph_call=fake_graph_call,
        fetch_bytes=fake_fetch_bytes,
    ))
    assert rec["scopes"] == ["Files.Read"]


# ── server integration: registration gating (real FastMCP protocol) ────────

import asyncio  # noqa: E402
import pathlib  # noqa: E402
import shutil  # noqa: E402

pytest.importorskip("fastmcp", reason="the MCP runtime face needs the optional 'fastmcp' extra")

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_DNA_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"


def _build(dst, graph_cfg):
    from dna_cli._mcp_server import build_server

    return build_server(base_dir=str(dst), graph_config=graph_cfg)


def test_graph_tool_absent_when_obo_off(tmp_path, monkeypatch):
    """No graph config → ms_calendar_list is NOT on the protocol surface (the
    OSS/stdio path is untouched)."""
    from fastmcp import Client

    dst = tmp_path / ".dna"
    shutil.copytree(_DNA_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))

    async def scenario():
        server = _build(dst, None)
        async with Client(server) as client:
            names = {t.name for t in await client.list_tools()}
            assert "ms_calendar_list" not in names
            assert "compose_prompt" in names  # the base tools still present.

    asyncio.run(scenario())


def test_graph_tool_registered_when_active_and_gated_on_entra(tmp_path, monkeypatch):
    """graph active → ms_calendar_list IS advertised; but with no Entra identity
    (in-memory client has no token) calling it is an honest capability error."""
    from fastmcp import Client
    from fastmcp.exceptions import ToolError

    dst = tmp_path / ".dna"
    shutil.copytree(_DNA_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    gc = C.parse_graph_config(_cfg())

    async def scenario():
        server = _build(dst, gc)
        async with Client(server) as client:
            names = {t.name for t in await client.list_tools()}
            assert "ms_calendar_list" in names
            with pytest.raises(ToolError):  # non-Entra → capability gap.
                await client.call_tool("ms_calendar_list", {})

    asyncio.run(scenario())


def test_graph_group_disabled_keeps_tool_absent(tmp_path, monkeypatch):
    from fastmcp import Client

    dst = tmp_path / ".dna"
    shutil.copytree(_DNA_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    gc = C.parse_graph_config(_cfg(groups={"calendar": {"enabled": False, "scopes": ["Calendars.Read"]}}))

    async def scenario():
        server = _build(dst, gc)
        async with Client(server) as client:
            names = {t.name for t in await client.list_tools()}
            assert "ms_calendar_list" not in names

    asyncio.run(scenario())


def test_files_tools_registered_when_active_and_gated_on_entra(tmp_path, monkeypatch):
    """files group active → both file tools are advertised; but with no Entra
    identity, calling either is an honest capability error (never a crash)."""
    from fastmcp import Client
    from fastmcp.exceptions import ToolError

    dst = tmp_path / ".dna"
    shutil.copytree(_DNA_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    gc = C.parse_graph_config(_files_cfg())

    async def scenario():
        server = _build(dst, gc)
        async with Client(server) as client:
            names = {t.name for t in await client.list_tools()}
            assert "ms_files_search" in names
            assert "ms_file_read" in names
            with pytest.raises(ToolError):  # non-Entra → capability gap.
                await client.call_tool("ms_files_search", {"query": "budget"})
            with pytest.raises(ToolError):
                await client.call_tool("ms_file_read", {"item_id": "1"})

    asyncio.run(scenario())


def test_files_group_disabled_keeps_tools_absent(tmp_path, monkeypatch):
    from fastmcp import Client

    dst = tmp_path / ".dna"
    shutil.copytree(_DNA_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    gc = C.parse_graph_config(
        _files_cfg(groups={"files": {"enabled": False, "scopes": ["Files.Read"]}})
    )

    async def scenario():
        server = _build(dst, gc)
        async with Client(server) as client:
            names = {t.name for t in await client.list_tools()}
            assert "ms_files_search" not in names
            assert "ms_file_read" not in names

    asyncio.run(scenario())


def test_files_and_calendar_groups_coexist(tmp_path, monkeypatch):
    """Two groups active at once → all their tools register (groups are
    independent; enabling files does not disturb calendar)."""
    from fastmcp import Client

    dst = tmp_path / ".dna"
    shutil.copytree(_DNA_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    gc = C.parse_graph_config(_cfg(groups={
        "calendar": {"enabled": True, "scopes": ["Calendars.Read"]},
        "files": {"enabled": True, "scopes": ["Files.Read"]},
    }))

    async def scenario():
        server = _build(dst, gc)
        async with Client(server) as client:
            names = {t.name for t in await client.list_tools()}
            assert {"ms_calendar_list", "ms_files_search", "ms_file_read"} <= names

    asyncio.run(scenario())
