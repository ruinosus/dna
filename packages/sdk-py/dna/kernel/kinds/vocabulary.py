"""⚠️ PROPOSED trait vocabulary — authored by an agent, awaiting the founder.

Everything registered here is a PROPOSAL. ``spec-kind-taxonomia-o-que-eu-sou``
§12.4 asks the question this file exists to make answerable rather than
theoretical:

    *"Um trait novo por família (leva B) é vocabulário de quem? ~8 nomes novos,
    permanentes, difíceis de desfazer. Autoria do founder ou proposta do agente
    com aprovação?"*

So the proposal is kept where it can be judged and, if judged badly, UNDONE in
one move: **delete this file and the import in ``__init__``, and the names are
gone.** The Kinds that declare them keep working — an unregistered trait is
legal and simply carries nothing (``traits.register_trait``'s docstring says
so) — so a rejection costs a description, never a boot.

The core vocabulary lives in ``traits.CORE_TRAITS`` and is NOT touched here.
That separation is the point: thirteen names the founder authored, four an
agent proposes, and nobody has to diff a commit to tell which is which.

⚠️ A THIRD dict was added below on 12/08/2026 — ``BEHAVIOURAL_TRAITS`` (i-107).
It is also agent-authored, but it breaks the "rejection costs a description"
promise this docstring makes about ``PROPOSED_TRAITS``: its two names are READ
by the kernel's evidence-capture path, so deleting one changes behaviour. It is
a separate dict for exactly the reason the first two are separate — so the
different cost is visible without diffing a commit. Read its own comment before
touching it.

Why these four and not the eight the spec sketched
--------------------------------------------------
§9.2's leva B guessed at ~8 traits, one per extension family (Eval, Portfolio,
A2A, tenancy, policy, catalog). Measuring the descriptors first — which is what
§7.3 means by *"a fatia 3 mede antes de declarar"* — killed half of them, and
the reason is §9.3's own criterion, from the gist white paper:

    use a category when it is labelling; and *"it's possible to overdo this"*.

**A trait that merely restates the extension a Kind belongs to is that overdo.**
``origin`` and ``target_api_version`` already say "this is an Eval Kind" on
every descriptor, exactly and machine-readably. A trait ``eval.thing`` would be
a third spelling of a fact already declared twice, and it would make the
coverage metric read higher while answering nothing new — which is worse than
not declaring, because the number would then lie upward.

So the test each name below had to pass was NOT "is there a family?" but
**"does it name a role that CUTS ACROSS extensions, and would somebody ask a
registry for the set?"** Four passed. The four that did are all cross-cutting:
the execution pair spans testkit + eval + automation, the policy trait spans
safety + evidence + helix + sdlc, and the grant trait spans a2a + portfolio +
tenant + audit.

What these traits CARRY: nothing, on purpose
--------------------------------------------
Deliberate, and the deliberation is worth writing down because "a trait that
carries nothing is decoration" was the whole complaint slice 2 answered.

These four are the OTHER legitimate shape — the one §1.3 and §10.2 of the spec
name explicitly: Kubernetes' CRD ``categories: [all]``, *"um rótulo de papel,
declarado no tipo, cujo único serviço é agrupar em consulta."* The spec's §10.2
answer to *"k8s ficou plano e deu certo"* is *"estamos concordando com o
Kubernetes, não discordando"* — and this is where that agreement is spent.

Concretely, each was checked against carrying something and declined for a
measured reason:

* a **schema** — the members' fields genuinely differ. A test run stamps
  ``executed_at``; an eval run stamps ``started_at`` + ``finished_at``. A trait
  schema would have to invent one of them onto the other, and inventing a field
  is the failure mode ``spec.relations`` just spent #335 deleting (27 guessed
  edges → 0). Declined.
* **relations** — same reason, one level up: a run points back at its
  declaration through a differently-NAMED field (``suite`` vs ``guide_ref``),
  and a relation is named by the field that holds it.
* **implies** — no implication is true of all members without exception, and
  ``CORE_TRAIT_IMPLIES`` set the bar: both of its entries were MEASURED true of
  every declaring Kind before being written. None of these clears it.
* ⚠️ **``record.append-only``** was the near miss, and the reason it is not
  here is a finding, not an omission. It fits an ``execution.run`` perfectly on
  paper — a TestRun is the proof ``sdlc.test-gated`` refuses a close without,
  so deleting one destroys the evidence of a gate. But that trait's refusal
  message tells the caller to *"use the purpose-built path for this Kind"*, and
  a TestRun HAS no purpose-built delete path. Making it append-only would leave
  somebody who ran a test wrong with no way to remove the bad row except by
  hand against the database — which is precisely what
  ``test_ordinary_kinds_are_deletable`` says the default exists to prevent.
  **A founder question, in the report, with the measurement. Not a silent
  behaviour change riding in on a vocabulary commit.**

So: four names, zero behaviour change, one deletable file. The return is the
one §7.3 nominates for taxonomy — *"consulta e tela"* — and it is real: today
"which Kinds does an authorization decision read?" has no answer that is not a
hand-written list of six names in whoever needed one.
"""

from __future__ import annotations

from dna.kernel.kinds.traits import register_trait

__all__ = [
    "PROPOSED_TRAITS",
    "BEHAVIOURAL_TRAITS",
    "register_proposed_traits",
    "register_behavioural_traits",
]


#: name → description. Same shape as ``traits.CORE_TRAITS``, deliberately, so
#: promoting one is a move between two dicts and nothing else.
PROPOSED_TRAITS: dict[str, str] = {
    "execution.declared": (
        "Declares work a RUNNER executes, and is only ever the script — never "
        "the outcome. A TestGuide's steps, an EvalSuite's cases, an "
        "Automation's trigger and runner: the instance says what should "
        "happen, a host executes it, and what happened is written somewhere "
        "else (see `execution.run`). The pair is the structural difference "
        "that earns both names — a Kind on this side may be edited freely "
        "because it makes no claim about the past."
    ),
    "execution.run": (
        "The record of ONE execution of an `execution.declared` instance: when "
        "it ran, what it ran against, and what came out. It is a claim about "
        "the past, which is what separates it from the declaration it "
        "executed — a run that turns out to be wrong is not corrected, it is "
        "superseded by another run. Every member points back at its "
        "declaration, by a differently-named field, which is why this trait "
        "carries no relation."
    ),
    "governance.policy": (
        "Declarative rules an ENFORCEMENT POINT reads at runtime — not prose "
        "for a human, and not configuration in the ordinary sense. Editing one "
        "changes what the system refuses, immediately, with no deploy. That is "
        "the behavioural commonality: a policy instance is read by a guard, a "
        "scanner, an overlay resolver or a decay function, never by somebody "
        "wanting to know what happened. It is also why `record.append-only` is "
        "wrong for them and right for a run: a policy is MEANT to be rewritten."
    ),
    "tenancy.access-grant": (
        "A row that GRANTS access: a subject, a scope it reaches, and the level "
        "it reaches it at. Read by an authorization decision — which is the "
        "whole role, and the reason the set has to be enumerable rather than "
        "inferable. Revoking is editing (or expiring) a row, so these are "
        "deliberately NOT append-only. Distinct from the Kind that DEFINES the "
        "ladder rather than granting a rung of it: a role definition is a "
        "catalogue entry, not a grant, and conflating the two would make "
        "\"who can reach this?\" return the vocabulary instead of the answer."
    ),
}


#: ⚠️ ALSO agent-authored, but these two are NOT free to reject — read this.
#:
#: ``PROPOSED_TRAITS`` above is safe to delete in one move because it carries
#: nothing: rejecting a name there costs a description. These two are the other
#: case, and they are kept apart precisely so that difference stays visible
#: without diffing a commit — which is the same reason ``CORE_TRAITS`` and
#: ``PROPOSED_TRAITS`` are separate dicts in the first place.
#:
#: They were introduced by i-107 to REPLACE literal Kind-name sets that the
#: kernel's evidence-capture path was carrying:
#:
#:     write/evidence.py:28   _EVAL_KINDS = {"EvalRun", "EvalBaseline", "Finding"}
#:     write/evidence.py:131  if kind == "Evidence"
#:
#: Deleting a name here without first restoring those literals changes
#: behaviour: evidence stops being stamped with its suite, or the recursion
#: guard stops guarding. So a rejection here is a code change, not a
#: description change — hence the separate dict and this comment.
#:
#: ⭐ What the swap BUYS, and the reason it is worth a vocabulary entry: a Kind
#: authored by a tenant through ``KindDefinition`` could not previously produce
#: evidence at all. Not "was not configured to" — there was no way to say it.
#: The kernel knew three names and no Kind outside that set could join, however
#: much it looked like an eval run. Now it declares
#: ``traits: [record.produces-evidence]`` and is in.
#:
#: ⚠️ ``Finding`` was in that literal set and is NOT a registered Kind (measured
#: 12/08/2026: ``kind_port_for("Finding")`` is None). A literal set can name a
#: Kind that does not exist and nothing complains; a declaration cannot, because
#: there is nothing to declare it on. That dead third entry is why the set is
#: two names here and was three there.
BEHAVIOURAL_TRAITS: dict[str, str] = {
    "record.produces-evidence": (
        "Writing an instance of this Kind is an event worth CAPTURING as "
        "Evidence — the evidence handler reads the write and stamps the "
        "suite/source it came from. Distinct from `execution.run`, which says "
        "the instance IS the record of an execution: a run is evidence-worthy "
        "because it is a claim about the past, but a Kind may be "
        "evidence-worthy without being a run (a baseline is pinned, not run). "
        "Capture is still gated by the scope's EvidencePolicy — this trait says "
        "the Kind is ELIGIBLE, never that capture is on."
    ),
    "record.is-evidence": (
        "This Kind IS the evidence record, which the capture path must know so "
        "it does not capture evidence ABOUT evidence — an unguarded write of a "
        "captured record re-triggers the handler that wrote it. The trait "
        "exists as the declarative half of `record.produces-evidence`: without "
        "it the kernel would still need one hard-coded name to break the loop, "
        "and one hard-coded name is the whole problem in miniature. Expected to "
        "be declared by exactly one Kind per deployment, but deliberately not "
        "enforced as such — a tenant that runs its own evidence Kind alongside "
        "the built-in one is not doing anything wrong."
    ),
}


def register_behavioural_traits() -> None:
    """Publish the load-bearing agent-authored names into the trait registry.

    Same mechanism as :func:`register_proposed_traits`, different contract:
    these names are READ by the kernel's evidence-capture path, so removing one
    changes behaviour. See the comment on ``BEHAVIOURAL_TRAITS``.
    """
    for name, description in BEHAVIOURAL_TRAITS.items():
        register_trait(name, description)


def register_proposed_traits() -> None:
    """Publish the proposed names into the live trait registry.

    Idempotent, because ``register_trait`` is. Called once from
    ``dna.kernel.kinds.__init__`` so the vocabulary is populated wherever the
    trait registry is — the same guarantee ``CORE_TRAITS`` gets from its own
    module-level loop, and the reason ``dna kind traits`` and
    ``describe_traits()`` list these alongside the core thirteen instead of
    only after some extension happens to load.

    Registration buys a DESCRIPTION and nothing else: nothing checks a Kind's
    declared trait against the registry, by design, so this function cannot
    refuse a Kind and cannot change one.
    """
    for name, description in PROPOSED_TRAITS.items():
        register_trait(name, description)


register_proposed_traits()
register_behavioural_traits()
