"""``dna rename`` — change an instance's NAME and repoint what authored it.

The operation i-114 left behind, and it is a consequence of that decision
rather than a gap in it. i-114 settled how a reference is written by
**separating the two layers by who writes them** (Kubernetes' rule, which this
project's ``apiVersion/kind/metadata/spec`` grammar already comes from):

* the ``.dna/`` a HUMAN authors and reviews in a PR carries **only the name**,
  because the diff has to stay legible;
* ``dna_edges``, which the write path DERIVES, carries **id and name**, because
  a machine must survive a rename.

The derived half therefore needs nothing from this command — a rename that
preserves ``metadata.id`` (this one does; see :func:`_renamed_envelope`) leaves
every ``to_id`` still pointing at the same identity, and the edges are
recomputed from the instances the moment they are written. What breaks is the
AUTHORED half: a YAML that says ``feature: f-old-name`` after ``f-old-name``
became ``f-new-name``. Kubernetes' answer to that is honest and unhelpful — it
simply breaks, and a human fixes it, like an import in code. This command is
that fix, promoted from ritual to operation: on 06/08/2026 it was performed by
hand, with ``sed``, twice in one day.

⚠️ Why it is emphatically NOT ``sed``
=====================================
The same day, a vocabulary rename run with ``sed`` over 650 files produced four
defects that no test saw, and every one of them is a property of TOKEN
REPLACEMENT rather than of carelessness:

1. a verb became a non-word, because replacing a token also rewrites the longer
   word that CONTAINS it;
2. the right word was replaced where it meant something else;
3. pt-BR gender agreement broke, on screen;
4. a label drifted away from the value of the data underneath it.

A ``dna rename`` implemented as ``str.replace`` over a store reproduces all
four. So this one never looks at text. It reads the field a Kind DECLARED as a
relation, compares the whole value, and writes the whole value back. There is
no substring, no regular expression, and no word to be inside of.

How it finds the references — and why not the reverse edge index
================================================================
The issue that filed this proposed reading ``dna_edges``' reverse index
(``edges_in_idx`` over ``scope, tenant, to_kind, to_name``), which returns
exactly ``(from_kind, from_name, source_field, ordinal)``. That is the right
SHAPE of answer and the wrong SOURCE, for three measured reasons:

* **It is derived, so it can be stale — silently.** Instances written before
  the edge producer existed have no rows at all; ``dna graph backfill`` exists
  for precisely that population, and its module docstring names the trap. A
  rename driven by the index would report *"0 references rewritten"* over a
  store whose edges were never filled, which is the confident-empty-answer
  this codebase treats as a defect (the same one ``GraphUnsupported`` refuses
  to commit).
* **The store this command exists for keeps no edges at all.** The measured use
  case is renumbering an Issue in a git-tracked ``.dna/`` — the filesystem
  adapter, which declares no ``edge_graph``. An index-driven rename would
  refuse in exactly the case that motivated it.
* **The index is a CACHE of the declarations**, not an independent fact: the
  producer writes it from ``spec.relations`` through
  :func:`dna.kernel.query.references.resolve_relations`. Reading the cache when
  the source is available adds a second mechanism that can disagree with the
  first — the disagreement ``references.py`` was deliberately written as ONE
  function to prevent.

So the set is derived from the DECLARATIONS, the same way ``dna graph
backfill`` derives its work:

1. walk the in-memory Kind registry for every ``(source Kind, relation)`` whose
   ``rel.to`` names the Kind being renamed and whose ``rel.resolved`` is true —
   pure, no I/O, the same shape as
   :func:`dna.kernel.write.target_delete.enforcers_for`;
2. for each such pair, enumerate the candidate instances — through
   ``list_instances_with_spec_field`` when the adapter has it (a JSONB
   key-existence query the GIN index serves), else through ``kernel.query``
   over the Kind;
3. read ``spec.<relation>`` with
   :func:`dna.kernel.kinds.relations.relation_values` — the DECLARED field —
   and compare each value, whole, against the old name.

The result is exact, it carries the field AND the ordinal, and it works on
every adapter.

What it will not touch, and why
===============================
**Another scope.** ``dna_edges`` rows are keyed by scope and so is everything
else here. A reference from a sibling scope belongs to another owner, and
rewriting another owner's file inside a PR is worse than the breakage: the
reader can fix a dangling name, and cannot un-review an edit they never saw.
Those are LISTED — the list is the deliverable there.

**A polymorphic relation that resolves elsewhere.** ``spec_refs`` on a Kind
declared ``to: [Spec, ADR]`` may hold a name that resolves to the ADR. The
resolution order the write path uses is replayed exactly (see
:func:`_resolves_to_target`), and a value that lands on another Kind is
reported, never rewritten.

**Prose.** A name quoted in a ``description``, a docstring or a markdown body
is not a reference; it is text that mentions a name. It is not rewritten — that
is defect (2) above — and it is also not SEARCHED, which is the less obvious
half of the decision. A substring report would hand a human a list of hits
whose obvious next step is the ``sed`` this command exists to replace, and the
list would carry the false positives that make ``sed`` wrong. What the summary
does instead is name the territory and hand over the right tool
(``git grep``), so the gap is known rather than papered over.

**A reference-shaped field nobody declared.** ``Issue.related_feature`` points
at a Feature by name and is declared only as a ``dep_filters`` alias, so the
kernel does not resolve it and this command cannot reach it. Those ARE reported
— derived from the registry, never guessed — because the remedy is one line of
``spec.relations`` and a re-run, and a silent miss would leave the caller
believing the rename was complete.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Any

import click

from dna_cli._ctx import fail, open_session, print_json

__all__ = ["rename", "referring_relations", "undeclared_reference_fields"]


@dataclass(frozen=True)
class Hit:
    """One authored reference to the instance being renamed.

    ``field``/``ordinal`` come from the DECLARATION and the value's position in
    it — the same two columns ``dna_edges`` stores — so applying the rewrite is
    an index assignment, never a search-and-replace over the instance.
    """

    scope: str
    kind: str
    name: str
    field: str
    ordinal: int
    #: ``None`` when the value resolves to this instance. Otherwise the reason
    #: it was left alone, in the words the report prints.
    skipped: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out = {
            "scope": self.scope, "kind": self.kind, "name": self.name,
            "field": self.field, "ordinal": self.ordinal,
        }
        if self.skipped:
            out["skipped"] = self.skipped
        return out


@dataclass
class RenamePlan:
    """Everything the rename found, before anything is written.

    Built whole and only then acted on, for the reason
    :func:`dna.kernel.write.target_delete.plan_target_delete` builds its
    cascade whole: a plan that discovered its refusal halfway through would
    already have written half the store on the way to refusing, and a refusal
    that costs data is not a refusal.
    """

    kind: str = ""
    old: str = ""
    new: str = ""
    scope: str = ""
    #: Pairs consulted — ``(source Kind, relation)`` from the registry.
    pairs: list[tuple[str, str]] = field(default_factory=list)
    #: Home-scope references that WILL be rewritten.
    rewrite: list[Hit] = field(default_factory=list)
    #: Home-scope references left alone, each carrying why.
    skipped: list[Hit] = field(default_factory=list)
    #: References from another scope. Reported, never touched.
    foreign: list[Hit] = field(default_factory=list)
    #: ``(Kind, field)`` that point at this Kind without declaring a relation.
    undeclared: list[tuple[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "old": self.old, "new": self.new,
            "scope": self.scope,
            "pairs": [{"kind": k, "relation": f} for k, f in self.pairs],
            "rewrite": [h.as_dict() for h in self.rewrite],
            "skipped": [h.as_dict() for h in self.skipped],
            "foreign": [h.as_dict() for h in self.foreign],
            "undeclared": [
                {"kind": k, "field": f} for k, f in self.undeclared
            ],
        }


def referring_relations(kernel: Any, target_kind: str) -> list[tuple[str, Any]]:
    """``(source Kind, Relation)`` for every declaration that can name
    ``target_kind`` by instance name.

    Two conditions, and the second is the one that is easy to lose: the
    relation has to be one the kernel RESOLVES (``rel.resolved`` — concrete
    targets, addressed ``by: name``), AND it has to name ``target_kind`` among
    its targets. A ``Story.feature`` says nothing about renaming an ``Epic``.

    Derived from the live registry on every call, never cached and never
    enumerated by hand, for the reason
    :func:`dna.kernel.write.target_delete.registry_relations` gives: Kinds are
    registered at RUNTIME (``author_kind``), so a cache here would rewrite
    yesterday's model.

    An unresolved relation (``by: workspace_id``, ``to: "*"``) is deliberately
    out. The kernel does not follow it, so this command cannot know that its
    value addresses this instance rather than something that merely looks like
    it — and guessing is the whole family of defect being avoided.
    """
    from dna.kernel.kinds.relations import relations_of

    out: list[tuple[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for port in _kind_ports(kernel):
        source_kind = getattr(port, "kind", None)
        if not isinstance(source_kind, str):
            continue
        for rel in relations_of(port).values():
            if not rel.resolved or target_kind not in rel.to:
                continue
            key = (source_kind, rel.name)
            if key in seen:
                continue
            seen.add(key)
            out.append((source_kind, rel))
    return sorted(out, key=lambda p: (p[0], p[1].name))


def undeclared_reference_fields(
    kernel: Any, target_kind: str,
) -> list[tuple[str, str]]:
    """``(Kind, field)`` that address ``target_kind`` WITHOUT declaring it.

    Derived from ``dep_filters()`` — the older, alias-keyed way a Kind says
    "this field points at that Kind" — intersected against the target's own
    ``alias``. It is not a second resolution mechanism and is never used to
    rewrite anything: it exists so the report can distinguish *"nothing points
    at this"* from *"three things point at this and none of them said so"*.

    The distinction is real and currently costs: ``Issue.related_feature`` and
    ``RiskRegister.related_features`` both hold Feature names, and neither is a
    declared relation, so a rename of a Feature leaves them dangling. Naming
    them turns a silent miss into a one-line fix (declare the relation, re-run).
    """
    target_alias: str | None = None
    for port in _kind_ports(kernel):
        if getattr(port, "kind", None) == target_kind:
            alias = getattr(port, "alias", None)
            if isinstance(alias, str) and alias:
                target_alias = alias
            break
    if not target_alias:
        return []

    declared = {(k, r.name) for k, r in referring_relations(kernel, target_kind)}
    out: list[tuple[str, str]] = []
    for port in _kind_ports(kernel):
        source_kind = getattr(port, "kind", None)
        if not isinstance(source_kind, str):
            continue
        getter = getattr(port, "dep_filters", None)
        if not callable(getter):
            continue
        try:
            filters = getter() or {}
        except Exception:  # noqa: BLE001 — a broken declaration must not be
            # able to take a rename down; it simply is not reported.
            continue
        if not isinstance(filters, dict):
            continue
        for name, alias in sorted(filters.items()):
            if alias != target_alias or (source_kind, name) in declared:
                continue
            out.append((source_kind, name))
    return sorted(set(out))


def _kind_ports(kernel: Any) -> list[Any]:
    """Every registered Kind port.

    Raises rather than returning ``[]`` when the registry is unreachable, for
    the reason :func:`dna.kernel.query.backfill._registry_items` does: an empty
    list here produces a rename that reports "0 references" and looks like a
    clean run, which is the exact failure this whole operation exists to end.
    """
    ports = getattr(kernel, "kind_ports", None)
    if not callable(ports):
        raise RuntimeError(
            "cannot enumerate registered Kinds on this kernel (no "
            "kind_ports()), so the declarations that point at the instance "
            "cannot be derived — refusing to report a rename with no "
            "references, which would look like a complete one."
        )
    return list(ports())


def _is_bundle(port: Any) -> bool:
    """Is this Kind stored as a bundle DIRECTORY (``SKILL.md`` & friends)?"""
    storage = getattr(port, "storage", None)
    pattern = getattr(storage, "pattern", None)
    return str(getattr(pattern, "value", pattern) or "").lower() == "bundle"


def _renamed_envelope(
    raw: dict, new_name: str, *,
    scope: str, kind: str, old_name: str, tenant: str | None,
) -> dict:
    """A copy of ``raw`` addressed by ``new_name``, carrying the OLD identity.

    Preserving the id is not a nicety, it is the entire point: it is what makes
    the DERIVED half of i-114 survive the rename with nothing to fix — every
    ``dna_edges.to_id`` keeps pointing at the same identity while the names
    move. The write pipeline's stamper short-circuits on an envelope that
    already carries one (``if instance_id_of(raw) is not None: return raw``),
    so copying the metadata forward is sufficient there.

    ⚠️ **An instance with no id needs the derived one stamped HERE**, and
    leaving that to the pipeline is a silent identity loss rather than a
    cosmetic gap. The pipeline reads the store under the name it is WRITING —
    ``f-new``, which does not exist yet — so it takes its "genuinely new
    instance" branch and mints a fresh random id. The rename would then delete
    the old row and leave behind an instance with a different identity: exactly
    the "changing the address erased the identity" failure i-114 was filed to
    end, arriving through the command built to fix it.

    So the id is derived from the instance's own OLD coordinates, with
    :func:`dna.kernel.identity.derived_instance_id` — the same function the
    Postgres backfill and the pipeline's migration branch use, which is what
    makes the three converge instead of each inventing a value. What is derived
    is a starting identity for an instance that predates the id, never a rule:
    it is stamped once, here, and every later write carries it forward.

    A deep copy, because the source envelope is served from the kernel's
    granular cache and mutating it in place would edit what the next reader
    sees.
    """
    from dna.kernel.identity import (
        derived_instance_id, instance_id_of, stamp_instance_id,
    )

    out = copy.deepcopy(raw)
    meta = out.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
        out["metadata"] = meta
    if instance_id_of(out) is None:
        api_version = out.get("apiVersion")
        stamp_instance_id(out, derived_instance_id(
            tenant=tenant, scope=scope,
            api_version=api_version if isinstance(api_version, str) else "",
            kind=kind, name=old_name,
        ))
    meta = out["metadata"]
    meta["name"] = new_name
    return out


async def _candidates(
    kernel: Any, source_kind: str, rel_name: str, tenant: str | None,
) -> list[dict[str, Any]]:
    """Instances of ``source_kind`` that HAVE ``spec.<rel_name>`` set.

    Two lanes, and the fast one is opportunistic rather than required. An
    adapter that offers ``list_instances_with_spec_field`` (the SQL one) answers
    with a key-existence query the ``dna_insts_spec_gin_idx`` index serves —
    the same narrowing ``dna graph backfill`` uses. An adapter that does not
    (the filesystem, which is where ``.dna/`` lives) is walked per Kind, which
    is a directory listing of one container and not a scan of the store.

    Both lanes read the SAME declared field and return the same rows, so the
    answer does not depend on which store is wired. That is the property the
    edge index could not offer.

    ⚠️ ``origin="local"`` on the walking lane, and it is load-bearing. The
    default is ``all``, which folds instances INHERITED from a parent scope
    into a child scope's listing — so the same referrer would be found once per
    descendant scope, each time attributed to a scope it does not live in, and
    the sibling-scope partition below would then refuse to rewrite the file in
    its own home. Scope inheritance is the default regime
    (``_DenylistInheritable``), so this is the ordinary case rather than an
    exotic one.
    """
    source = getattr(kernel, "_source", None)
    reader = getattr(source, "list_instances_with_spec_field", None)
    if callable(reader):
        rows = await reader(source_kind, rel_name, scope=None)
        return [
            {
                "scope": r["scope"], "kind": r["kind"], "name": r["name"],
                "tenant": r.get("tenant") or None, "raw": r["raw"],
            }
            for r in rows
        ]

    out: list[dict[str, Any]] = []
    for one in await source.list_scopes():
        async for row in kernel.query(
            one, source_kind, tenant=tenant, origin="local",
        ):
            meta = row.get("metadata") if isinstance(row, dict) else None
            name = (meta or {}).get("name") if isinstance(meta, dict) else None
            if not name:
                continue
            out.append({
                "scope": one, "kind": source_kind, "name": name,
                "tenant": tenant, "raw": row,
            })
    return out


async def build_plan(
    kernel: Any, *, scope: str, kind: str, old: str, new: str,
    tenant: str | None = None,
) -> RenamePlan:
    """Find every authored reference to ``kind/old``, partitioned by verdict.

    Reads only. Nothing here writes, so a refusal raised by the caller after
    this returns has cost nothing but time.
    """
    from dna.kernel.kinds.relations import relation_values

    plan = RenamePlan(kind=kind, old=old, new=new, scope=scope)
    pairs = referring_relations(kernel, kind)
    plan.pairs = [(k, r.name) for k, r in pairs]
    plan.undeclared = undeclared_reference_fields(kernel, kind)

    port_for = getattr(kernel, "kind_port_for", None)

    for source_kind, rel in pairs:
        for row in await _candidates(kernel, source_kind, rel.name, tenant):
            raw = row["raw"]
            spec = raw.get("spec") if isinstance(raw, dict) else None
            values = relation_values(rel, spec if isinstance(spec, dict) else {})
            for ordinal, value in enumerate(values):
                if value != old:
                    continue
                hit = Hit(
                    scope=row["scope"], kind=row["kind"], name=row["name"],
                    field=rel.name, ordinal=ordinal,
                )
                if row["scope"] != scope:
                    # Another owner's file. The list IS the deliverable.
                    plan.foreign.append(hit)
                    continue
                if rel.polymorphic:
                    targets = list(rel.to)
                    if callable(port_for):
                        targets = [
                            t for t in rel.to if port_for(t) is not None
                        ] or targets
                    winner = await _first_match(
                        kernel, scope, targets, value, tenant,
                    )
                    if winner is not None and winner != kind:
                        plan.skipped.append(replace(hit, skipped=(
                            f"the value resolves to {winner}/{value}, not to "
                            f"{kind}/{value} — a polymorphic relation "
                            f"pointing somewhere else"
                        )))
                        continue
                plan.rewrite.append(hit)
    plan.rewrite.sort(key=lambda h: (h.kind, h.name, h.field, h.ordinal))
    plan.skipped.sort(key=lambda h: (h.kind, h.name, h.field, h.ordinal))
    plan.foreign.sort(key=lambda h: (h.scope, h.kind, h.name, h.field))
    return plan


async def _first_match(
    kernel: Any, scope: str, targets: list[str], value: str,
    tenant: str | None,
) -> str | None:
    """Which declared target Kind a value lands on FIRST — the write path's
    own rule, replayed. ``None`` when nothing resolves."""
    for target in targets:
        try:
            doc = await kernel.get_instance(scope, target, value, tenant=tenant)
        except Exception:  # noqa: BLE001 — a read failure is not a verdict;
            # treat it as "cannot tell", which keeps the value out of the
            # rewrite set rather than guessing it in.
            return None
        if doc is not None:
            return target
    return None


async def apply_plan(
    kernel: Any, plan: RenamePlan, *, tenant: str | None = None,
) -> None:
    """Execute a plan, in the ONE order that never leaves the store lying.

    1. **write the new name first.** Its ``metadata.id`` is the old one's, so
       the identity is carried rather than reissued.
    2. **repoint the referrers.** They now name an instance that exists, so a
       deployment running ``DNA_REF_VALIDATION=enforce`` does not veto the
       write and no intermediate state has a dangling reference.
    3. **delete the old name last.** By then nothing in this scope points at
       it, so ``on_target_delete: restrict`` — which would otherwise refuse the
       delete on behalf of the very references this command just fixed — has
       nothing to hold.

    Reversing any pair of these produces a window in which the store contradicts
    itself, and on the filesystem that window is a commit.
    """
    old_raw = await kernel.get_instance_local(
        plan.scope, plan.kind, plan.old, tenant=tenant,
    )
    if old_raw is None:  # pragma: no cover — build_plan's caller checked
        raise LookupError(f"{plan.kind}/{plan.old} disappeared mid-rename")

    # ``if_absent`` is the ATOMIC half of "a rename never merges two
    # instances". The command already read the new name and refused if it was
    # taken — that is the readable refusal, and it closes every NON-concurrent
    # case. What it cannot close is the race, because a read-then-write in
    # application code re-reads through the granular cache that made the read
    # stale. The adapter arbitrates against the STORE instead (``O_CREAT|O_EXCL``
    # on the filesystem, the composite primary key on SQL) and raises
    # ``InstanceNameTaken``. Same two-layer split ``refuse_if_exists`` and
    # ``InstanceNameTaken`` already are for creates.
    await kernel.write_instance(
        plan.scope, plan.kind, plan.new,
        _renamed_envelope(
            old_raw, plan.new,
            scope=plan.scope, kind=plan.kind, old_name=plan.old, tenant=tenant,
        ),
        tenant=tenant, if_absent=True,
    )

    # ⚠️ ``hit.scope == plan.scope`` is asserted a SECOND time here, and the
    # redundancy is the design — the same argument
    # :class:`~dna.kernel.errors.PathEscapesStoreRoot` makes for guarding both
    # the facade and the adapter. ``build_plan`` already partitioned the
    # sibling scopes out; this line means that a future edit which loses that
    # partition produces an incomplete REPORT rather than a write into somebody
    # else's file. A reviewer about to delete it as dead code: it is the layer
    # that decides which of those two failures happens.
    by_instance: dict[tuple[str, str], list[Hit]] = {}
    for hit in plan.rewrite:
        if hit.scope != plan.scope:
            continue
        by_instance.setdefault((hit.kind, hit.name), []).append(hit)

    for (ref_kind, ref_name), hits in sorted(by_instance.items()):
        raw = await kernel.get_instance_local(
            plan.scope, ref_kind, ref_name, tenant=tenant,
        )
        if raw is None:  # pragma: no cover — read between plan and apply
            continue
        raw = copy.deepcopy(raw)
        spec = raw.get("spec")
        if not isinstance(spec, dict):
            continue
        for hit in hits:
            _set_value(spec, hit.field, hit.ordinal, plan.new)
        await kernel.write_instance(
            plan.scope, ref_kind, ref_name, raw, tenant=tenant,
        )

    await kernel.delete_instance(
        plan.scope, plan.kind, plan.old, tenant=tenant,
    )


def _set_value(spec: dict, field_name: str, ordinal: int, new: str) -> None:
    """Replace ONE value, at its position, leaving the container's shape alone.

    A list stays a list and a scalar stays a scalar: ``relation_values`` reads
    both regardless of the declared cardinality (an instance may legally
    contradict its Kind's ``cardinality`` and be caught by schema validation
    instead), so writing back has to preserve whichever shape was authored.
    Normalizing here would put an unrelated change in the diff — and the diff
    is the deliverable.
    """
    value = spec.get(field_name)
    if isinstance(value, list):
        if 0 <= ordinal < len(value):
            value[ordinal] = new
        return
    if isinstance(value, tuple):
        items = list(value)
        if 0 <= ordinal < len(items):
            items[ordinal] = new
        spec[field_name] = items
        return
    spec[field_name] = new


# ── the command ─────────────────────────────────────────────────────────────


@click.command("rename")
@click.argument("kind_name")
@click.argument("old_name")
@click.argument("new_name")
@click.option("--scope", default=None,
              help="Scope holding the instance (default: env / sole scope).")
@click.option("--tenant", default=None, help="Bind to this tenant.")
@click.option("--dry-run", is_flag=True,
              help="Show exactly what would change; write nothing.")
@click.option("--json", "as_json", is_flag=True)
def rename(
    kind_name: str, old_name: str, new_name: str, scope: str | None,
    tenant: str | None, dry_run: bool, as_json: bool,
) -> None:
    """Rename an instance and repoint the AUTHORED references to it.

    The declared relations that name it are rewritten field-by-field — never by
    text substitution, so a longer name that merely CONTAINS the old one is
    untouched. References from another scope are listed and left alone; prose
    is neither rewritten nor searched. ``--dry-run`` prints the same plan
    without writing, because what this operation promises is that the result
    shows up in the diff of a pull request.
    """
    from dna.kernel.errors import (
        InstanceNameTaken, InvalidInstanceName, validate_instance_name,
    )

    try:
        validate_instance_name(new_name)
    except InvalidInstanceName as exc:
        fail(str(exc))
        return

    if old_name == new_name:
        fail(
            f"{kind_name}/{old_name} is already called that — nothing to "
            f"rename. Refused rather than run: a no-op rename that reported "
            f"success would be indistinguishable from one that worked."
        )
        return

    with open_session(scope) as s:
        port = s.kernel.kind_port_for(kind_name, scope=s.scope)
        if port is None:
            fail(
                f"no Kind named {kind_name!r} is registered, so there is no "
                f"model saying what may point at one of its instances. "
                f"Refused rather than renamed: without the declarations this "
                f"would be a file move that leaves every reference behind."
            )
            return
        if _is_bundle(port):
            fail(
                f"{kind_name} is stored as a BUNDLE directory, and this "
                f"command renames through read + write + delete — which "
                f"carries the envelope and not the bundle's files. Refused "
                f"rather than run: it would move the instance and destroy its "
                f"entries. Move the directory with `git mv` and re-run "
                f"`dna rename` once the Kind is stored as YAML."
            )
            return

        existing = s.run(s.kernel.get_instance_local(
            s.scope, kind_name, old_name, tenant=tenant,
        ))
        if existing is None:
            fail(
                f"no {kind_name} named {old_name!r} in scope {s.scope!r}. "
                f"(Read WITHOUT the parent-scope fallback on purpose: an "
                f"instance inherited from a parent scope is not this scope's "
                f"to rename.)"
            )
            return
        taken = s.run(s.kernel.get_instance_local(
            s.scope, kind_name, new_name, tenant=tenant,
        ))
        if taken is not None:
            fail(
                f"{kind_name}/{new_name} already exists in scope {s.scope!r} "
                f"— refusing to rename onto it. This is a verdict about the "
                f"request, not about the store: the write would have "
                f"succeeded, and it would have silently merged two "
                f"instances into one. Pick another name."
            )
            return

        plan = s.run(build_plan(
            s.kernel, scope=s.scope, kind=kind_name,
            old=old_name, new=new_name, tenant=tenant,
        ))
        if not dry_run:
            try:
                s.run(apply_plan(s.kernel, plan, tenant=tenant))
            except InstanceNameTaken as exc:
                fail(str(exc))
                return

    if as_json:
        print_json({**plan.as_dict(), "dry_run": dry_run})
        return
    _report(plan, dry_run=dry_run)


def _report(plan: RenamePlan, *, dry_run: bool) -> None:
    """The human rendering. Never a bare count: every number that could be
    read as "nothing to do" is printed beside the reason it is that number."""
    verb = "would rename" if dry_run else "renamed"
    click.echo(
        f"{verb} {plan.kind}/{plan.old} → {plan.new} in scope {plan.scope} "
        f"(metadata.id preserved)"
    )
    click.echo(
        f"{len(plan.pairs)} declared (Kind, relation) pair(s) can point at "
        f"{plan.kind}"
    )
    verb = "would rewrite" if dry_run else "rewrote"
    if plan.rewrite:
        click.echo(f"{verb} {len(plan.rewrite)} authored reference(s):")
        for h in plan.rewrite:
            click.echo(f"  {h.kind}/{h.name}  spec.{h.field}[{h.ordinal}]")
    else:
        click.echo(
            f"{verb} 0 authored references — no instance in this scope names "
            f"{plan.old!r} through a declared relation."
        )
    for h in plan.skipped:
        click.echo(
            f"⚠ left alone: {h.kind}/{h.name} spec.{h.field}[{h.ordinal}] — "
            f"{h.skipped}"
        )
    if plan.foreign:
        # "MAY now dangle", never "now dangle". A sibling scope can hold its
        # OWN instance under the same name, in which case its reference was
        # never ours and nothing broke. Reporting the weaker, true claim is the
        # point: the reader can check, and a report that overstated would train
        # them to stop checking.
        click.echo(
            f"⚠ {len(plan.foreign)} reference(s) in OTHER scopes name "
            f"{plan.old!r} and MAY now dangle — they resolve in their own "
            f"scope first, so verify before acting. Not touched: another "
            f"scope is another owner, and rewriting their files in this PR "
            f"would be worse than the breakage:"
        )
        for h in plan.foreign:
            click.echo(
                f"  [{h.scope}] {h.kind}/{h.name}  spec.{h.field}[{h.ordinal}]"
            )
    if plan.undeclared:
        click.echo(
            f"⚠ {len(plan.undeclared)} field(s) address {plan.kind} WITHOUT "
            f"declaring a relation, so they are unreachable here and were not "
            f"rewritten. Declare them in spec.relations and re-run:"
        )
        for kind_name, field_name in plan.undeclared:
            click.echo(f"  {kind_name}.spec.{field_name}")
    click.echo(
        f"prose is not a reference: a mention of {plan.old!r} in a "
        f"description or a markdown body was neither rewritten nor searched. "
        f"Review by hand if you want to — `git grep {plan.old}`."
    )
