"""f-cli-session-injection — the session port itself.

Three guarantees, each of which used to be impossible or silently wrong
under the module-global seam:

1. A fake injected through the click context (``obj={SESSION_PROVIDER_KEY:
   fake}``) is what commands use — no module reached into.
2. The injection survives a CUSTOM click.Group dispatch (``_KaizenGroup``
   overrides resolve_command), because the port reads the context, not a
   module attribute.
3. A patch aimed at the OLD seam (``sdlc_cmd.dna_session``) fails LOUDLY
   with AttributeError instead of silently letting the test hit the real
   session — the failure mode that blocked splitting sdlc_cmd.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from click.testing import CliRunner

from dna_cli import sdlc_cmd
from dna_cli._ctx import SESSION_PROVIDER_KEY
from dna_cli.sdlc_cmd import sdlc


class _FakeDocView:
    def __init__(self, raw: dict):
        self._raw = raw
        self.name = raw.get("metadata", {}).get("name")
        self.kind = raw.get("kind")
        self.spec = raw.get("spec") or {}


class _FakeKernel:
    def __init__(self, store: dict):
        self._store = store
        self._kinds: dict = {}

    def with_tenant(self, tenant):
        return self

    async def write_document(self, scope, kind, name, raw, **_):
        self._store[(scope, kind, name)] = raw
        return "v1"


class _FakeSession:
    def __init__(self, store: dict, scope: str):
        self._store = store
        self.scope = scope
        self.kernel = _FakeKernel(store)
        self.holder = type("_H", (), {"reload": lambda self: None})()

    def get_doc(self, kind, name, *, tenant=None):
        raw = self._store.get((self.scope, kind, name))
        return _FakeDocView(raw) if raw is not None else None

    def query_list(self, kind, *, tenant=None):
        return [
            _FakeDocView(raw)
            for (sc, kd, _nm), raw in self._store.items()
            if sc == self.scope and kd == kind
        ]

    def run(self, coro):
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _obj_over(store: dict) -> dict:
    @contextmanager
    def _fake(scope=None, *, tenant=None, timeout=30.0):
        yield _FakeSession(store, scope or "dna-development")

    return {SESSION_PROVIDER_KEY: _fake}


def test_injected_session_is_used_end_to_end():
    """The obj-injected fake receives the write — front-door injection."""
    store: dict = {}
    r = CliRunner().invoke(
        sdlc, ["spec", "create", "spec-di", "--title", "DI"],
        obj=_obj_over(store),
    )
    assert r.exit_code == 0, r.output
    assert ("dna-development", "Spec", "spec-di") in store


def test_injection_survives_custom_group_dispatch():
    """_KaizenGroup overrides resolve_command (default-subcommand fallback);
    the port must not care. Uses the HISTORICAL form `kaizen <wi> --body`,
    which routes through the override itself, not just a normal lookup."""
    store: dict = {}
    store[("dna-development", "Story", "s-di")] = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
        "kind": "Story",
        "metadata": {"name": "s-di"},
        "spec": {"status": "in-progress", "title": "T", "timeline": []},
    }
    r = CliRunner().invoke(
        sdlc, ["kaizen", "s-di", "--body", "melhorar o porto de sessão"],
        obj=_obj_over(store),
    )
    assert r.exit_code == 0, r.output
    kaizen_keys = [k for k in store if k[1] == "Kaizen"]
    assert kaizen_keys, f"no Kaizen doc written; store keys: {list(store)}"


def test_patching_the_old_seam_fails_loud(monkeypatch):
    """The category-killer: sdlc_cmd no longer HAS a dna_session global, so
    the legacy patch raises instead of silently passing against the real
    session. (raising=True is monkeypatch's default; spelled out because
    this loudness is the point.)"""
    with pytest.raises(AttributeError):
        monkeypatch.setattr(
            sdlc_cmd, "dna_session", lambda scope: None, raising=True,
        )
