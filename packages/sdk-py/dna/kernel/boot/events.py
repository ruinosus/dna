"""Derive the post_save event_type from the Kind's OWN declaration.

i-107 slice 3. This module used to hold the event vocabulary of Kinds the
kernel does not own::

    _FIXED_EVENTS = {"EvalRun": "eval_run_completed", "EvalBaseline": "baseline_pinned"}
    _SPLIT_EVENTS = {"Finding": ("finding_created", "finding_status_changed")}

Three names, in the kernel, for three Kinds that live in extensions. The cost
was not tidiness: ``EvidencePolicy`` selects which writes to capture BY
event_type, so a Kind whose event_type could only ever be ``document_created``
could not be named by any policy written against a meaningful event. A
tenant-authored Kind therefore could not participate in evidence capture at
all, and there was no way to ask for it.

Now the Kind declares ``post_save_event`` (a ``KindPort`` attribute, or
``spec.post_save_event`` in a ``.kind.yaml`` descriptor) and this module only
reads it.

⚠️ ``"Finding"`` was one of the three and is NOT a registered Kind (measured
12/08/2026). A dict can hold a key for a Kind that does not exist and nothing
ever complains; a declaration has to live ON something. Its entry is gone with
no replacement, which is the correct outcome and not a regression — see
``tests/test_events.py``.
"""
from __future__ import annotations

from typing import Any

DELETE_EVENT_TYPE = "document_deleted"

#: What a Kind that declares nothing gets.
GENERIC_CREATED = "document_created"
GENERIC_MODIFIED = "document_modified"


def event_type_for_port(port: Any, *, is_update: bool) -> str:
    """The event_type declared by ``port``, else the generic pair.

    ``post_save_event`` is read permissively on purpose — a descriptor-declared
    Kind arrives through YAML, where a two-element pair is a ``list`` and not a
    ``tuple``, and refusing that would make the descriptor path behave
    differently from the class path for no reason a Kind author could see.
    """
    declared = getattr(port, "post_save_event", None) if port is not None else None
    if declared is None:
        return GENERIC_MODIFIED if is_update else GENERIC_CREATED
    if isinstance(declared, str):
        # One name for both transitions: an EvalRun is "completed" whether the
        # row is new or rewritten.
        return declared
    if isinstance(declared, (tuple, list)) and len(declared) == 2:
        create_evt, update_evt = declared
        return str(update_evt if is_update else create_evt)
    # Malformed declaration: fall back to generic rather than raise. This runs
    # inside post_save emission, where raising would fail the WRITE because its
    # notification is misdeclared — the write already succeeded and the row is
    # good, so degrading the event name is the proportionate response.
    return GENERIC_MODIFIED if is_update else GENERIC_CREATED


def derive_event_type(
    kind: str, *, is_update: bool, kernel: Any = None,
) -> str:
    """Map a Kind name + update flag to a post_save event_type string.

    ``kernel`` is how the declaration is reached; without it there is no
    registry to ask and every Kind gets the generic pair. That is deliberately
    NOT a fallback to the old three-name table: a silent fallback would let a
    caller that forgot to pass the kernel keep working against a closed list,
    which is the failure this change removes.
    """
    port = None
    if kernel is not None:
        try:
            port = kernel.kind_port_for(kind)
        except Exception:  # noqa: BLE001 — a broken registry must not fail a write
            port = None
    return event_type_for_port(port, is_update=is_update)
