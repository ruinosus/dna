"""``dna_cli.graph._config`` — the ``graph:`` block of ``dna.config.yaml``.

Story ``s-mcp-obo-config-gating`` (ADR-mcp-obo §5). The declarative enablement
surface for On-Behalf-Of: which tool-groups a deployment opts into and the exact
delegated scopes each may request. Mirrors the ``auth:`` section exactly —
:mod:`dna.config` treats ``graph:`` as an opaque passthrough mapping and this
module owns its schema + validation (the twin of
:func:`dna_cli._mcp_auth.parse_auth_providers`).

Invariants (all fail-closed):

* **OFF by default.** No ``graph:`` block (or an empty one) → :func:`parse_graph_config`
  returns ``None`` → not one ``graph.*`` tool is registered. The OSS / stdio / self-host
  path never touches Microsoft. A present-but-``enabled: false`` block is also inert.
* **Static scope allow-list.** A tool-group declares the exact scopes it may
  request; :func:`assert_scope_allowed` refuses anything else — a tool can never
  escalate to a scope the deployment did not consent.
* **Credential is an env-var NAME, never a value.** ``client_id_env`` /
  ``credential_env`` name the env vars that hold the app-reg id + secret; the
  secret value never lives in a config doc (mirrors ``MCPFederation.auth``). The
  parser rejects a value that is not a valid env-var identifier — a guard against
  pasting a secret inline.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .errors import OboScopeNotAllowedError

# A POSIX-ish env-var NAME: a letter/underscore then letters/digits/underscores.
# A pasted secret (with ``~ . / = @`` etc.) fails this — the inline-secret guard.
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_KNOWN_KEYS = {"enabled", "client_id_env", "credential_env", "groups"}
_KNOWN_GROUP_KEYS = {"enabled", "scopes"}


@dataclass(frozen=True)
class GraphGroup:
    """One tool-group's declarative enablement (e.g. ``calendar``): whether it is
    on, and the exact delegated Graph scopes it may request."""

    name: str
    enabled: bool
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class GraphConfig:
    """The parsed ``graph:`` block — the ceiling on what OBO may do.

    ``client_id_env`` / ``credential_env`` are env-var NAMES (the confidential
    client's app-reg id + secret are read from ``os.environ`` at exchange time,
    never stored here)."""

    enabled: bool
    client_id_env: str | None
    credential_env: str | None
    groups: dict[str, GraphGroup] = field(default_factory=dict)

    def group_enabled(self, name: str) -> bool:
        g = self.groups.get(name)
        return bool(g and g.enabled)

    def scopes_for(self, name: str) -> list[str]:
        g = self.groups.get(name)
        return list(g.scopes) if g else []

    def is_active(self, name: str) -> bool:
        """A group is ACTIVE (its tools should register + may exchange) only when
        the block is enabled AND the group itself is enabled."""
        return self.enabled and self.group_enabled(name)

    def active_groups(self) -> list[str]:
        return [n for n in self.groups if self.is_active(n)]


def parse_graph_config(raw: Any) -> GraphConfig | None:
    """Parse + validate the ``graph:`` block. ``None``/empty → ``None`` (OBO off).

    Fails loud (``ValueError``) on: not-a-mapping, unknown keys, a present block
    missing ``client_id_env`` / ``credential_env``, an env field that is not a
    valid env-var name (an inline-secret guard), a bad ``groups`` shape, or a group
    with no scopes.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(
            f"`graph:` must be a mapping (its `groups:` opt into OBO tool-groups), "
            f"got {type(raw).__name__}."
        )
    if not raw:  # an empty `graph: {}` is the same as absent — OBO off.
        return None

    unknown = sorted(set(raw) - _KNOWN_KEYS)
    if unknown:
        raise ValueError(
            f"`graph:` unknown key(s) {unknown} — supported: {sorted(_KNOWN_KEYS)}."
        )

    enabled = bool(raw.get("enabled", False))
    client_id_env = _env_name(raw.get("client_id_env"), "graph.client_id_env")
    credential_env = _env_name(raw.get("credential_env"), "graph.credential_env")
    if not client_id_env or not credential_env:
        raise ValueError(
            "`graph:` needs both `client_id_env` and `credential_env` (the NAMES of "
            "the env vars holding the confidential-client app-reg id + secret) — the "
            "secret value never lives in config."
        )

    groups: dict[str, GraphGroup] = {}
    raw_groups = raw.get("groups") or {}
    if not isinstance(raw_groups, dict):
        raise ValueError(
            f"`graph.groups:` must be a mapping of group-name → {{enabled, scopes}}, "
            f"got {type(raw_groups).__name__}."
        )
    for gname, graw in raw_groups.items():
        where = f"graph.groups.{gname}"
        if not isinstance(graw, dict):
            raise ValueError(f"{where}: must be a mapping, got {type(graw).__name__}.")
        gunknown = sorted(set(graw) - _KNOWN_GROUP_KEYS)
        if gunknown:
            raise ValueError(
                f"{where}: unknown key(s) {gunknown} — supported: "
                f"{sorted(_KNOWN_GROUP_KEYS)}."
            )
        gscopes = graw.get("scopes")
        if not isinstance(gscopes, list) or not gscopes or not all(
            isinstance(s, str) and s.strip() for s in gscopes
        ):
            raise ValueError(
                f"{where}.scopes: must be a non-empty list of delegated Graph scope "
                f"strings (e.g. ['Calendars.Read'])."
            )
        groups[str(gname)] = GraphGroup(
            name=str(gname),
            enabled=bool(graw.get("enabled", False)),
            scopes=tuple(s.strip() for s in gscopes),
        )

    return GraphConfig(
        enabled=enabled, client_id_env=client_id_env,
        credential_env=credential_env, groups=groups,
    )


def _env_name(value: Any, where: str) -> str | None:
    """Validate that ``value`` is an env-var NAME (or ``None``). Rejects an inline
    secret value (anything that is not a bare identifier)."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if not _ENV_NAME_RE.match(s):
        raise ValueError(
            f"{where}: {value!r} is not a valid environment-variable NAME — this "
            f"field names the env var that holds the secret; it must never contain "
            f"the secret VALUE itself (expected e.g. DNA_MCP_CLIENT_SECRET)."
        )
    return s


def assert_scope_allowed(cfg: GraphConfig, group: str, scope: str) -> None:
    """Fail-closed: raise unless ``scope`` is declared for ``group``.

    The static allow-list check — a tool may only ever request a scope its group
    declared in config. An unknown group, or a scope outside the group's list, is
    :class:`OboScopeNotAllowedError`."""
    allowed = cfg.scopes_for(group)
    if not allowed:
        raise OboScopeNotAllowedError(
            f"tool-group {group!r} is not configured under `graph.groups` — no "
            f"scope may be requested for it (fail-closed)."
        )
    if scope not in allowed:
        raise OboScopeNotAllowedError(
            f"scope {scope!r} is not allowed for group {group!r} (allowed: "
            f"{allowed}) — a tool cannot request an unconsented scope."
        )
