# Hosting ao-copilot on Agno AgentOS (documented, no managed runtime)

`hosting.target: agentos` is emitted **documented, lower v1 priority**: Agno
AgentOS has **no managed runtime**. `hosting.mode: hosted` for agentos ≈
**self-host** (the emitted `AgentOS(...)` app + `compose.yaml`) **+ an optional
control-plane REGISTRATION** step — there is no Foundry-style hosted agent
(design §2/§6). Be honest about it: the abstraction does not fully hold.

## What this emit gives you

- `main.py` — the `AgentOS(agents=[...])` app serving REST / AG-UI on `:7777`.
- `compose.yaml` — a THIN single-service scaffold (build + port + JWT env).

## What you still do (not this emit)

1. Provision compute + managed **Postgres/pgvector** + registry + the
   `AGENTOS_JWT_SECRET` + ingress — via `f-copilot-infra-binding`, not the thin
   `compose.yaml`.
2. Register the running service with your control plane (the "hosted" half that
   is a convention, not a managed runtime).
