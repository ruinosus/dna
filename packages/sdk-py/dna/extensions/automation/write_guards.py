"""Automation-owned write-path guards (s-tier-a-automation).

One ``pre_save`` VETO hook that makes an Automation write *fully valid or
not persisted*, in two ordered steps:

1. **Normalize the YAML 1.1 ``on`` trap (Python-only).** PyYAML reads a
   bare ``on:`` key as boolean ``True`` (YAML 1.1 booleans), so a
   hand-authored doc silently loses its trigger — the live failure that
   motivated this step: the doc wrote fine and exploded at scan time
   with "'on' is a required property". The guard rewrites a top-level
   ``True`` spec key back to ``"on"`` (mutating ``ctx.raw`` in place —
   the veto-channel contract) before validating; PyYAML's emitter quotes
   ``'on'`` on dump, so the healed doc round-trips. js-yaml keeps ``on``
   a string, so the TS twin has no such step.
2. **Semantics the schema cannot express:**

   - **cron expression** (``on.type: cron``) — parsed by a
     zero-dependency 5-field validator (documented decision: a cron lib
     would be the SDK's only runtime dep for one field; the grammar below
     covers the standard crontab core — ``*``, numbers, ranges, lists,
     steps — and rejects the rest loudly. Name aliases like
     ``JAN``/``MON`` are NOT supported.)
   - **hook name** (``on.type: hook``) — must belong to the kernel's
     typed hook vocabulary ``KNOWN_HOOK_NAMES`` (s-dna-typed-hook-names).
     The HookRegistry itself tolerates custom names (warn-once), but an
     Automation is DATA a host executor dispatches on: a misspelled hook
     would be declared, listed, and silently never fire — so here the
     unknown name is a veto, not a warning.

Schema SHAPE at write time (originally this guard's step 2) is no longer
Automation-specific: ``s-write-path-validation`` (i-008) generalized it —
``WritePipeline.write`` validates every doc's spec against the Kind's
declared ``schema()`` AFTER the veto hooks run, so the YAML-1.1 heal here
lands before the shape check. This guard keeps only what is Automation's
own: the heal and the semantics JSON Schema cannot express.

A raise from the guard vetoes the write (nothing is persisted). The hook
fires for EVERY ``kernel.write_document`` regardless of ``skip_hooks`` —
it is an integrity gate, not a notification. 1:1 parity with
``src/extensions/automation/write-guards.ts``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dna.kernel.hooks import PreSaveContext

_KIND = "Automation"

# After helix (10/20/30) and SDLC bitemporal (40).
PRIORITY_TRIGGER_GUARD = 50

# (label, lo, hi) per cron field, in order. dow accepts 0-7 (0 and 7 both
# mean Sunday, matching crontab).
_CRON_FIELDS: tuple[tuple[str, int, int], ...] = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day-of-month", 1, 31),
    ("month", 1, 12),
    ("day-of-week", 0, 7),
)


def _cron_error(expr: str, detail: str) -> ValueError:
    return ValueError(
        f"invalid cron expression {expr!r}: {detail}. Expected 5 "
        f"whitespace-separated fields 'min hour dom mon dow' (e.g. "
        f"'0 10 * * 1,3,5'); each field is '*', a number, a range 'a-b', "
        f"a list 'a,b,c' or a step '*/n' / 'a-b/n'. Name aliases "
        f"(JAN/MON) are not supported."
    )


def validate_cron_expression(expr: str) -> None:
    """Validate a 5-field cron expression. Raises ``ValueError`` on the
    first problem (didactic message); returns None when valid."""
    fields = expr.split()
    if len(fields) != 5:
        raise _cron_error(expr, f"expected 5 fields, got {len(fields)}")
    for value, (label, lo, hi) in zip(fields, _CRON_FIELDS):
        for item in value.split(","):
            if not item:
                raise _cron_error(expr, f"empty list item in {label} field")
            base, sep, step = item.partition("/")
            if sep:
                if not step.isdigit() or int(step) < 1:
                    raise _cron_error(
                        expr, f"step '/{step}' in {label} field must be a "
                        f"positive integer",
                    )
                if base == "":
                    raise _cron_error(
                        expr, f"step without a base in {label} field",
                    )
            if base == "*":
                continue
            lo_s, dash, hi_s = base.partition("-")
            bounds = (lo_s, hi_s) if dash else (lo_s,)
            for bound in bounds:
                if not bound.isdigit():
                    raise _cron_error(
                        expr, f"{bound!r} in {label} field is not a number",
                    )
                if not lo <= int(bound) <= hi:
                    raise _cron_error(
                        expr, f"{bound} out of range {lo}-{hi} for {label}",
                    )
            if dash and int(lo_s) > int(hi_s):
                raise _cron_error(
                    expr, f"inverted range {base!r} in {label} field",
                )


def automation_trigger_guard(ctx: "PreSaveContext") -> None:
    """Veto an Automation write that is not fully valid.

    Steps (module docstring): normalize the PyYAML ``on``→``True`` key
    trap, then check the semantics JSON Schema cannot express (cron
    grammar, hook-name vocabulary). Schema SHAPE is validated by the
    kernel's generic write-path step (s-write-path-validation, i-008),
    which runs after this guard — so the heal below lands first.
    """
    if ctx.kind != _KIND or not isinstance(ctx.raw, dict):
        return
    spec = ctx.raw.get("spec") or {}
    if not isinstance(spec, dict):
        return
    # 1. YAML 1.1 trap: a bare `on:` key arrives as boolean True from
    #    PyYAML. Heal it in place (the veto channel's documented mutation
    #    contract) so the persisted doc carries the real field.
    if True in spec and "on" not in spec:
        spec["on"] = spec.pop(True)
    # 2. Semantics the schema cannot express (shape itself is the kernel's
    #    generic write-path validation, which runs after the veto hooks).
    on = spec.get("on") or {}
    if not isinstance(on, dict):
        return
    on_type = on.get("type")
    if on_type == "cron":
        cron = on.get("cron")
        if isinstance(cron, str):
            validate_cron_expression(cron)
    elif on_type == "hook":
        hook = on.get("hook")
        if isinstance(hook, str):
            from dna.kernel.hooks import KNOWN_HOOK_NAMES  # noqa: PLC0415
            if hook not in KNOWN_HOOK_NAMES:
                raise ValueError(
                    f"Automation {ctx.name!r} declares on.hook={hook!r}, "
                    f"which is not a kernel lifecycle hook. Known hooks: "
                    f"{sorted(KNOWN_HOOK_NAMES)}. A misspelled hook would "
                    f"be declared but never fire — fix the name (the "
                    f"vocabulary is typed: dna.kernel.hooks.HookName)."
                )


def register_write_guards(kernel: Any) -> None:
    """Wire the Automation write guard as a ``pre_save`` veto hook.

    The key makes the registration idempotent (re-loading the extension
    onto a shared HookRegistry replaces instead of stacking duplicates).
    """
    kernel.hooks.on_veto(
        "pre_save", automation_trigger_guard,
        priority=PRIORITY_TRIGGER_GUARD, key="automation.trigger-guard",
    )
