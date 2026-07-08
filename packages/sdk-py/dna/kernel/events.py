# python/dna/kernel/events.py
"""Derive event types from Kind + update status for HookRegistry post_save."""
from __future__ import annotations

DELETE_EVENT_TYPE = "document_deleted"

_FIXED_EVENTS: dict[str, str] = {
    "EvalRun": "eval_run_completed",
    "EvalBaseline": "baseline_pinned",
}

_SPLIT_EVENTS: dict[str, tuple[str, str]] = {
    "Finding": ("finding_created", "finding_status_changed"),
}


def derive_event_type(kind: str, *, is_update: bool) -> str:
    """Map a Kind name + update flag to a post_save event_type string."""
    if kind in _FIXED_EVENTS:
        return _FIXED_EVENTS[kind]
    if kind in _SPLIT_EVENTS:
        create_evt, update_evt = _SPLIT_EVENTS[kind]
        return update_evt if is_update else create_evt
    return "document_modified" if is_update else "document_created"
