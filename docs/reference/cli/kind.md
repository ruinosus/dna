# `dna kind`

List + inspect registered Kinds.

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna kind --help`.

## `dna kind describe`

Show the JSON Schema + storage descriptor for a Kind.

```text
dna kind describe [OPTIONS] KIND_NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND_NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope to look up the Kind in (default: env / sole scope). |
| `--tenant` | Route as this tenant. |

## `dna kind list`

List all Kinds registered on the kernel (in the given scope).

```text
dna kind list [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` | JSON output. |
| `--scope` | Scope to enumerate kinds from (default: env / sole scope). |
| `--tenant` | Route as this tenant. |

## `dna kind traits`

List the TRAITS Kinds declare, and which Kinds carry each.

A trait answers "does this Kind take part in X?" for an X the kernel has no
opinion about — ``sdlc.work-item``, ``memory.recallable``,
``record.append-only``. Consumers ask ``kernel.kinds_with_trait(name)``
instead of carrying a literal Kind-name list, so adding a Kind to a family is
a declaration rather than an edit everywhere that family is consulted.

The vocabulary is OPEN: a trait no extension registered a description for is
still perfectly legal and still shows up here (with an empty description),
because an extension that ships a Kind and its one consumer must not have to
patch a core enum. Registration buys documentation, never a veto.

Reads the LOCAL kernel registry — traits are a property of the registered
Kinds, not of any scope's instances.

```text
dna kind traits [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` | JSON output. |
| `--trait` | Show only which Kinds declare this trait. |

