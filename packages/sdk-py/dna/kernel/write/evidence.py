"""Evidence auto-capture handler for HookRegistry post_save.

The microkernel must work with ZERO extensions loaded, so this module
imports NOTHING from ``dna.extensions`` (boundary ratchet:
``tests/test_kernel_extension_boundary.py``). The three helpers below —
``compute_content_hash``, ``build_evidence`` and ``should_capture`` — are
fully generic (stdlib + plain dicts only), so they live here in the kernel
exactly like the TS twin keeps ``computeContentHash``/``buildEvidenceDoc``/
``shouldCapture`` in ``kernel/evidence-capture.ts`` (s-invert-layer-resolver-dep
pattern; s-invert-evidence-capture-dep). ``EvidenceExtension`` re-exports them
for its public API (the gaia worker + existing callers keep their imports).

Capture is OFF by default: the ``post_save`` handler is only wired when
``EvidenceExtension.register()`` calls ``kernel.on("post_save", ...)``. A
kernel booted without the extension never registers the handler, so nothing
is captured and nothing crashes.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Collection
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

#: Traits that replaced the three literal Kind-name checks this module carried
#: (i-107). Named here rather than inline so they are greppable together — they
#: only make sense as a set: one marks the SOURCE, one breaks the recursion the
#: source would otherwise cause, and one is the GATE that decides.
#:
#: ⚠️ The third arrived a day after the first two, and the gap is the lesson: a
#: reader of this module on 12/08 would have said the evidence path was
#: translated, because the two visible `kind == "..."` comparisons were gone.
#: The `kernel.query(scope, "EvidencePolicy")` on the line below was the same
#: knowledge in a different syntactic shape, and it meant a tenant could declare
#: which Kind produces evidence and which Kind IS evidence, and still not
#: declare which Kind decides. Half a translation reads as a whole one.
TRAIT_PRODUCES_EVIDENCE = "record.produces-evidence"
TRAIT_IS_EVIDENCE = "record.is-evidence"
TRAIT_EVIDENCE_POLICY = "record.evidence-policy"


# ───────────────────────────────────────────────────────────────────────
# Generic evidence helpers (moved from extensions/evidence — kernel-owned)
# ───────────────────────────────────────────────────────────────────────

def compute_content_hash(content: Any) -> str:
    """Return the SHA-256 hex digest of *content* serialized as canonical JSON.

    Keys are sorted and no extra whitespace is added so that logically
    identical objects always produce the same hash regardless of
    insertion order.
    """
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_evidence(
    event_type: str,
    document_ref: str,
    content: Any,
    *,
    author: str = "system",
    notes: str | None = None,
    suite: str | None = None,
    kind: str = "Evidence",
    api_version: str = "github.com/ruinosus/dna/evidence/v1",
) -> dict[str, Any]:
    """Build an evidence instance dict.

    Parameters
    ----------
    event_type:
        One of the allowed event_type enum values (e.g. ``eval_run_completed``).
    document_ref:
        Reference to the instance that triggered the event (e.g. ``eval-evalrun/my-run``).
    content:
        The content to hash — typically the instance spec or a serializable snapshot.
    author:
        Who (or what) captured the evidence.  Defaults to ``"system"``.
    notes:
        Optional free-text annotation.
    kind / api_version:
        Which Kind this evidence instance IS. Defaults keep the historical
        shape for the existing public callers (``EvidenceExtension``
        re-exports this helper); the capture handler passes the Kind that
        DECLARES ``record.is-evidence`` instead, so the kernel no longer
        decides the name. Kept as parameters rather than a lookup because
        this helper is deliberately pure — stdlib and plain dicts only, no
        kernel — which is what lets it live in the kernel at all
        (``tests/test_kernel_extension_boundary.py``).

        ⛔ i-107 — the ``"Evidence"`` DEFAULT stays, and the argument is
        different from every other literal this issue removed. It is not the
        kernel deciding anything: the sole production caller (the capture
        handler, ~150 lines down) passes ``kind=`` explicitly from the trait,
        measured 13/08/2026, so this value never decides a real write. It is a
        published default in a re-exported public signature, and changing it
        would break callers to buy nothing — the derivation is already in place
        above it. A pure function cannot ask a registry, so the only honest
        alternatives are "keep the default" or "make the argument required",
        and the second is an API break dressed as a cleanup.

    Returns
    -------
    dict
        A dict with ``api_version``, ``kind``, ``metadata``, and ``spec`` ready
        to be written by the kernel's WriterPort.
    """
    spec: dict[str, Any] = {
        "event_type": event_type,
        "sha256": compute_content_hash(content),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "author": author,
        "document_ref": document_ref,
        "snapshot": content if isinstance(content, dict) else {"value": content},
    }
    if notes is not None:
        spec["notes"] = notes
    if suite is not None:
        spec["suite"] = suite

    return {
        "api_version": api_version,
        "kind": kind,
        "metadata": {
            "name": f"ev-{event_type}-{spec['sha256'][:12]}",
        },
        "spec": spec,
    }


def should_capture(policy_spec: dict, event_type: str) -> bool:
    """Check whether *event_type* should be auto-captured per *policy_spec*."""
    if not policy_spec.get("auto_capture", True):
        return False
    return event_type in policy_spec.get("events", [])


def extract_suite(
    kind: str,
    spec: dict[str, Any],
    explicit: str | None,
    *,
    producing_kinds: Collection[str] | None = None,
) -> str | None:
    """Extract the suite name for a Kind that PRODUCES evidence.

    The spec may be flat ({"suite": "x"}) or nested ({"spec": {"suite": "x"}})
    depending on whether the caller passed the raw doc or just the spec field.

    ``producing_kinds`` is the set of Kinds declaring
    ``record.produces-evidence`` — normally
    ``kernel.kinds_with_trait(TRAIT_PRODUCES_EVIDENCE)``, passed in by
    :func:`make_evidence_capture_handler`. It used to be a literal
    ``{"EvalRun", "EvalBaseline", "Finding"}`` in this module, which meant a
    tenant-authored Kind could not produce evidence at all — not "was not
    configured to", but had no way to say so.

    ⚠️ ``None`` means "no registry to ask" and yields ``None``, i.e. no suite.
    It does NOT fall back to the old literal set: a silent fallback would let a
    caller that forgot to pass the set keep working while quietly reverting to
    a closed list, which is the failure this change exists to remove.
    """
    if explicit:
        return explicit
    if not producing_kinds or kind not in producing_kinds:
        return None
    # Handle both flat and nested structures
    inner = spec.get("spec", spec) if isinstance(spec.get("spec"), dict) else spec
    return inner.get("suite") or inner.get("source")


def make_evidence_capture_handler(kernel: Any):
    """Create a post_save handler bound to a kernel instance."""
    _policy_cache: dict[str, list] = {}

    async def handler(ctx) -> None:
        data = ctx.data
        event_type = data.get("event_type", "")
        kind = ctx.kind or ""
        name = ctx.name or ""

        # Resolved per call, never cached: extensions may register Kinds after
        # this handler is wired, and a tenant KindDefinition can be approved
        # while the process is up. A snapshot taken at wiring time would make
        # a newly-approved Kind silently unable to produce evidence until
        # restart — the closed-set behaviour this replaced.
        is_evidence = kernel.kinds_with_trait(TRAIT_IS_EVIDENCE)
        producing = kernel.kinds_with_trait(TRAIT_PRODUCES_EVIDENCE)

        # Break the recursion: capturing a write of the evidence Kind would
        # re-trigger this handler on what it just wrote. Declared by the Kind
        # (`record.is-evidence`), not spelled `kind == "Evidence"` here.
        if kind in is_evidence:
            return

        # No Kind declares `record.is-evidence` → nowhere to write. Returning is
        # correct and not a silent skip: capture is opt-in (this handler is only
        # wired by EvidenceExtension.register), and a deployment that wires it
        # without an evidence Kind registered has a wiring bug, not a policy.
        if not is_evidence:
            logger.warning(
                "evidence capture is wired but no registered Kind declares %r "
                "— nothing can be captured; register the Evidence Kind or "
                "declare the trait on your own.",
                TRAIT_IS_EVIDENCE,
            )
            return

        # Which Kinds GATE capture — declared (`record.evidence-policy`), and
        # resolved per call for the same reason the two sets above are: a tenant
        # KindDefinition can be approved while the process is up.
        policy_kinds = kernel.kinds_with_trait(TRAIT_EVIDENCE_POLICY)

        scope = ctx.scope
        # Writing a gate instance invalidates the cached policies for its scope,
        # or an edit would not take effect until restart. Derived rather than
        # spelled `kind == "EvidencePolicy"`: a tenant Kind that declares the
        # trait would otherwise be read once and cached forever.
        if kind in policy_kinds or scope not in _policy_cache:
            # MUST be async — this handler runs from inside post_save
            # emission (which is invoked via `await emit_async` on the
            # caller's event loop). Using sync `kernel.instance(scope)`
            # here drops to `_run_sync_helper`, which spawns a new loop
            # in a ThreadPoolExecutor when `kernel._main_loop` isn't
            # registered (CLI / standalone tests). The new loop then
            # tries to use the asyncpg pool bound to the caller's loop
            # → `RuntimeError: Future attached to a different loop`
            # → `ConnectionDoesNotExistError`. Fixed 2026-05-03.
            _policy_cache[scope] = [
                raw.get("spec") or {}
                for policy_kind in sorted(policy_kinds)
                async for raw in kernel.query(scope, policy_kind)
            ]
        if not any(should_capture(p, event_type) for p in _policy_cache.get(scope, [])):
            return

        suite = extract_suite(
            kind, data.get("spec", {}), data.get("suite"),
            producing_kinds=producing,
        )

        # The Kind to WRITE is the one declaring `record.is-evidence`. Sorted so
        # a deployment that registers more than one (legal — see the trait's
        # description) picks deterministically rather than by dict order.
        evidence_kind = sorted(is_evidence)[0]
        evidence_port = kernel.kind_port_for(evidence_kind)
        evidence_api = (
            getattr(evidence_port, "api_version", None)
            or "github.com/ruinosus/dna/evidence/v1"
        )

        doc = build_evidence(
            event_type,
            f"{kind}:{name}",
            data.get("spec", {}),
            author=data.get("author", "unknown"),
            suite=suite,
            kind=evidence_kind,
            api_version=evidence_api,
        )

        try:
            evidence_name = doc["metadata"]["name"]
            raw_evidence = {
                "apiVersion": doc.get("api_version", evidence_api),
                "kind": evidence_kind,
                "metadata": doc.get("metadata", {}),
                "spec": doc.get("spec", {}),
            }
            # skip_hooks=True prevents the Evidence write from re-triggering
            # post_save → infinite recursion. Source persists via the registered
            # WriterPort — works for FS, Postgres, SQLite, or any backend.
            await kernel.write_instance(
                scope, evidence_kind, evidence_name, raw_evidence,
                skip_hooks=True,
            )
            logger.debug("Evidence captured: %s for %s:%s", event_type, kind, name)
        except Exception as e:
            logger.warning("Evidence capture failed for %s:%s: %s", kind, name, e)

    return handler
