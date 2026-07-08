---
kind: SafetyPolicy
metadata:
  name: pii-ml-filter
spec:
  engine: ml-privacy-filter
  model: openai/privacy-filter
  backend: auto
  threshold: 0.8
  categories:
    - private_person
    - private_email
    - private_phone
    - secret
  scope: input
  action: mask
  severity: warn
  mask_char: "[REDACTED]"
  budget_ms: 1000
---

# ML Privacy Filter Policy

This policy applies the [openai/privacy-filter](https://huggingface.co/openai/privacy-filter)
model (Apache 2.0, 8 entity categories) to mask PII in **agent input**
context strings.

> **Output-scope** (`scope: output` / `both`) is **not yet supported** in
> this release — the kernel's `post_build_prompt` event is read-only.
> Setting `scope: output` here will log a warning and be ignored at
> registration time.

## Categories enabled by this template

| Category          | Examples                              |
|-------------------|---------------------------------------|
| `private_person`  | "Alice Smith", "Dr. João"             |
| `private_email`   | "alice@company.com"                   |
| `private_phone`   | "+55 11 99999-9999", "555-1234"       |
| `secret`          | passwords, API keys, tokens           |

Edit `spec.categories` to add or remove categories. Set `spec.action: block`
to reject turns containing PII rather than masking them. Set
`spec.budget_ms` to tune the per-call wall-clock budget — over-budget
scans log-and-continue with the original text (never block the turn).

## Install

```bash
cd python-harness
uv sync --extra ml-privacy
```

The model downloads on the first agent turn (~1.5 GB; cached locally
under `~/.cache/huggingface/`). Subsequent calls are warm: p50≈48 ms
(ONNX backend) on a modern laptop.
