# `dna eval`

Run EvalSuites locally (offline, deterministic) and compare runs
against a pinned EvalBaseline.

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna eval --help`.

## `dna eval list`

List EvalSuites, saved EvalRuns and pinned EvalBaselines.

```text
dna eval list [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output. |
| `--scope` | Scope to list (default: resolved from the source). |

## `dna eval pin`

Pin RUN_NAME as the EvalBaseline for its suite.

Future ``dna eval run <suite> --baseline <name>`` executions are
compared against the pinned run (regressions exit non-zero).

```text
dna eval pin [OPTIONS] RUN_NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `RUN_NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--label` | Why this run is the reference. |
| `--name` | Baseline document name (default: baseline-<suite>). |
| `--scope` | Scope to write in (default: resolved from the source). |

## `dna eval run`

Execute SUITE offline and report per-case results.

Without ``--baseline`` the exit code reflects the run itself (1 when
any case failed/errored). With ``--baseline`` it reflects the DIFF:
only a regression (a case the baseline passed, now failing) exits 1.

```text
dna eval run [OPTIONS] SUITE
```

**Arguments**

| Argument | Required |
| --- | --- |
| `SUITE` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--baseline` | Compare against the EvalBaseline document NAME; exit 1 on regressions. |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output. |
| `--save` | Persist the result as an EvalRun document. |
| `--scope` | Scope to run in (default: resolved from the source). |

## `dna eval show`

Show one saved EvalRun with per-case detail.

```text
dna eval show [OPTIONS] RUN_NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `RUN_NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output. |
| `--scope` | Scope to read (default: resolved from the source). |

