# Renaming an instance

An instance is addressed two ways, and only one of them survives a rename.

| who writes the reference | what it holds | why |
| --- | --- | --- |
| **a human, in a file you review** (`spec.relations`) | the **name** | the diff has to be legible — that is the whole reason definitions live in git |
| **the write path, in `dna_edges`** | the **id** *and* the name | renaming must not break the edge |

That split is deliberate, and it is the one Kubernetes made: a
`configMapRef` a person authors carries a name, while an `ownerReference` a
controller writes carries name **and** uid. Putting machine identity into text
humans read trades legibility for durability — the mistake you can watch play
out in tools that print raw UUIDs inside authored notes.

So the honest consequence is: **renaming leaves authored files pointing at the
old name, and that breaks.** It breaks the same way a moved Python module
breaks its importers. `dna rename` is the operation that fixes it, and its
whole promise is that the fix **shows up in the diff of a pull request**.

## Use it

```bash
dna rename Story s-old-name s-new-name --dry-run
```

`--dry-run` prints exactly the plan — which instance moves, which fields on
which referrers get repointed, and what is being left alone — and writes
nothing. Drop the flag to apply it.

## What it rewrites, and what it deliberately does not

**It rewrites declared relations, field by field.** The set is derived from the
registry: every `(Kind, relation)` whose declared target is this Kind, then the
instances that actually carry a value on that field. It is not a search.

⚠️ **It never does text substitution**, and that is the point of the design
rather than a detail. A name that merely *contains* the old one is untouched.
The failure mode being avoided is not hypothetical — a vocabulary rename done
with `sed` across this repository produced, on one afternoon, all four of:

* a **verb turned into a non-word**, because the substitution reached a longer
  word that contained the token;
* the **right word replaced where it was right**, because the same string means
  different things in different sentences;
* **grammatical agreement broken** in Portuguese prose, on screen, with every
  test still green;
* a **UI label drifting away from the data value** it was supposed to mirror,
  so an error message told users to pick a type the backend does not know.

None of the four is catchable by a test, because none of them is a wrong
program — they are wrong *text*. Deriving the set from the declarations makes
them impossible instead of unlikely.

**It does not touch prose — and it does not search prose either.** A substring
report would hand you a list whose obvious next step is the `sed` this command
exists to replace, complete with the false positives that make `sed` wrong.
What the summary does is name the territory and hand you `git grep`.

**It does not touch machine-written edges.** They carry `metadata.id`, so after
the rename every `to_id` still points at the same identity. That is the half of
the split that was already durable.

**It lists cross-scope referrers and leaves them alone.** A referrer in another
scope is reported, never silently rewritten.

## What it reports that you should read

Two things the summary separates on purpose:

* **reference-shaped fields nobody declared.** *"Nothing points at this"* and
  *"three things point at this and none of them said so"* are different facts,
  and only the second is a reason to go look.
* **cross-scope referrers**, above.

## Refusals

Renaming to a name that already exists, or renaming an instance that does not
exist, is refused — a verdict about the request, not a capability the store
lacks.

⚠️ One family is refused outright today: Kinds stored as **bundles**
(`Spec`, `ADR`, `Skill`). Their read, write, and delete carry an envelope
rather than the bundle's files, so renaming one through this path would destroy
its entries. The refusal says so; the fix is a named open end, not a surprise.

## Related

* [How to read instance data](read-instance-data.md) — the id, and how it is
  resolved by prefix
* [Add a Kind](add-a-kind.md) — where `spec.relations` is declared in the first
  place
* [`dna rename` reference](../reference/cli/rename.md) — the generated flag list
