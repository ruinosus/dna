# `dna solution`

Scaffold and update a repo from Copier templates.

`dna solution new` renders one app; running it again with a different
service name overlays a SECOND app from the same template, with its own
answers file. `dna solution update` rolls one of them forward.

Rendering always happens here, on this machine, from a template you point
at — never on a server, and never with `--trust`.

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna solution --help`.

## `dna solution list`

List the template layers recorded in DESTINATION.

One row per answers file — which is one row per app, because the design is
one template overlaid N times, each with its own answers and its own
independent update.

```text
dna solution list [OPTIONS] [DESTINATION]
```

**Arguments**

| Argument | Required |
| --- | --- |
| `DESTINATION` | no |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable listing. |

## `dna solution new`

Render TEMPLATE into DESTINATION, recording the answers.

TEMPLATE is anything Copier accepts: a local path, a git URL, `gh:owner/repo`.
Run it once per app; each run writes its own answers file, and each app is
then updated independently.

```text
dna solution new [OPTIONS] TEMPLATE DESTINATION
```

**Arguments**

| Argument | Required |
| --- | --- |
| `TEMPLATE` | yes |
| `DESTINATION` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--answers-from` | YAML file of answers, applied under --data. The hand-rolled precursor of a recorded Solution. |
| `--defaults` | Take the template's default for every question that was not answered. |
| `--force` | Overwrite files that already exist. |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable report. |
| `--pretend` | Render nothing; report what would happen. |
| `--strict` | Exit 3 when the run has findings (missing inherited data). |
| `--vcs-ref` | Template ref to render (tag, branch or commit). Default: the latest tag. |
| `-d`, `--data` | Answer a question without being asked. Repeatable. |

## `dna solution update`

Roll ONE app in DESTINATION forward to a newer template version.

The recorded answers are always re-passed, so nothing is re-asked and
nothing is silently re-defaulted. Whatever the update leaves behind or drops
is named in the report — that reporting is the reason this command exists
rather than a `copier update` alias.

```text
dna solution update [OPTIONS] [DESTINATION]
```

**Arguments**

| Argument | Required |
| --- | --- |
| `DESTINATION` | no |

**Options**

| Option | Description |
| --- | --- |
| `--adopt-new-defaults` | Take every default that moved since the recorded ref (see the report). |
| `--allow-untagged` | Proceed even though the template publishes no tags. |
| `--answers-from` | YAML file of answers to apply over the recorded ones. |
| `--conflict` | How Copier records a conflict. _(default: `inline`)_ |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable report. |
| `--pretend` | Change nothing; report what would happen. |
| `--strict` | Exit 3 when the run has findings (lost answers, conflicts, defaults left behind). |
| `--vcs-ref` | Update to this ref instead of the latest tag. |
| `-a`, `--answers-file` | The answers file to update, relative to DESTINATION. |
| `-d`, `--data` | Move an answer as part of this update. Repeatable. |
| `-s`, `--service` | Shorthand for -a .copier-answers.<service>.yml. |

