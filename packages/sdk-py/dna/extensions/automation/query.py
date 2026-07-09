"""Query helpers a host executor uses to read Automation docs.

The SDK declares and validates automations; the HOST executes them (see
docs/concepts/builtin-kinds.md — the execution extension point). These
helpers are the read side of that contract, built strictly on the blessed
instance query surface (``instance.all``): no kernel method is added —
listing automations is extension domain knowledge, not microkernel
surface.

Usage (host executor)::

    mi = await kernel.instance("my-scope")
    for doc in automations_for(mi, "cron"):
        schedule(trigger_key(doc), doc.spec["runner"], doc.spec)

1:1 parity with ``src/extensions/automation/query.ts``.
"""
from __future__ import annotations

from typing import Any

_KIND = "Automation"

#: The ``on.type`` discriminator vocabulary (mirrors the descriptor enum).
TRIGGER_TYPES: tuple[str, ...] = ("cron", "hook", "tool")


def _spec(doc: Any) -> dict[str, Any]:
    spec = getattr(doc, "spec", None) or {}
    return spec if isinstance(spec, dict) else {}


def automations_for(
    instance: Any,
    trigger_type: str | None = None,
    *,
    enabled_only: bool = True,
) -> list[Any]:
    """List the scope's Automation docs, filtered for a host executor.

    - ``trigger_type`` — keep only automations whose ``on.type`` matches
      (``"cron"`` / ``"hook"`` / ``"tool"``); ``None`` returns all.
    - ``enabled_only`` (default True) — drop docs with ``enabled: false``
      (declared but paused; hosts must not fire them).

    ``instance`` is a ``ManifestInstance`` — the blessed query surface.
    Source order is preserved (inherited ``_lib`` defaults resolve like
    any other Kind; a tenant overlay wins per the layer policy).
    """
    if trigger_type is not None and trigger_type not in TRIGGER_TYPES:
        raise ValueError(
            f"unknown trigger_type {trigger_type!r} — expected one of "
            f"{TRIGGER_TYPES}"
        )
    out: list[Any] = []
    for doc in instance.all(_KIND):
        spec = _spec(doc)
        on = spec.get("on") or {}
        if not isinstance(on, dict):
            on = {}
        if trigger_type is not None and on.get("type") != trigger_type:
            continue
        if enabled_only and spec.get("enabled", True) is False:
            continue
        out.append(doc)
    return out


def trigger_key(doc: Any) -> str | None:
    """The trigger's identifying value: the cron expression (``cron``),
    the hook name (``hook``) or the dispatch tool name (``tool``).
    None when the trigger is missing/unknown."""
    on = _spec(doc).get("on") or {}
    if not isinstance(on, dict):
        return None
    on_type = on.get("type")
    if on_type == "cron":
        return on.get("cron")
    if on_type == "hook":
        return on.get("hook")
    if on_type == "tool":
        return on.get("tool_name")
    return None
