"""DNA → **Terraform infra inputs** for a servable Copilot (the IaC closure).

Where the backend emitters (agno / MS Agent Framework) materialize the servable
*agent* and the frontend emit materializes its *console*, this module materializes
the **infrastructure inputs** those artifacts need to actually run: the declared
``persistence`` backends + ``knowledge.store`` + ``hosting`` target of a Copilot
become **input to the Terraform migration modules** (the accepted Terraform
migration ADR in ``dna-cloud``). It is the concrete form of the design's §3 —
*"the Copilot definition drives the infra — declarative all the way down"*.

Shape of the emit (ONE artifact, ``role="infra"``):

    <agent>.tfvars.json    a Terraform-native ``.tfvars.json`` declaring, per the
                           design §3 table, the resources the declared backends /
                           hosting target need (Postgres + pgvector, Mongo Atlas,
                           Redis, Foundry account/project/ACR/RBAC, LangGraph /
                           AgentOS compute + stores), PLUS the ``env_injection``
                           map — each resource's Terraform OUTPUT (connection
                           string / endpoint + secret) → the env var the emitted
                           copilot reads. This is the seam the dna-cloud module
                           implementations consume downstream.

**The two rules from design §3:**

1. ``ref`` → the TF module's output (connection string / endpoint + secret)
   injected into the emitted copilot's env. So every store resource carries an
   ``output_env`` and rides in ``env_injection``.
2. **Dedup by ``ref``** — multiple persistence/knowledge slots sharing one ``ref``
   (one physical Postgres, distinct tables per framework) collapse to ONE
   resource. ``used_by`` records every slot the resource backs.

**What this emit does NOT do:** it does not implement the ``.tf`` modules — that
is the Terraform-ADR execution, downstream in ``dna-cloud``. It emits the INPUTS
those modules consume, against the module variable contract the ADR §8 fixes
(``azurerm`` + ``azuread`` providers, the ``ref``/output pattern). The
module-interface contract is documented in
``docs/guides/copilot-infra-binding.md``.

**The agent version is NOT an ARM resource** (design §3): for a Foundry hosting
target the emit declares the account / project / ACR / model deployment / RBAC —
but the agent version itself is a post-provision ``azd deploy`` / SDK step, not a
Terraform resource. The emit records that as a ``note``.

This is NOT a registered :class:`~dna.emit.EmitterPort` — infra inputs carry no
byte-equal instruction and are outside the ``build_prompt`` contract; it is a
standalone surface a consumer calls alongside the backend emit (mirrors
:func:`~dna.emit.frontend.emit_frontend_console`). The emitted JSON is
byte-identical across the Py/TS SDKs (``infra.py`` ↔ ``infra.ts``).
"""
from __future__ import annotations

import json
from typing import Any

from dna.emit import EmitArtifact, EmitContext, EmitError, EmitResult

__all__ = ["has_infra", "emit_infra"]

#: Persistence backends that map to a managed Postgres (design §3 row 1).
_POSTGRES_BACKENDS = frozenset({"postgres"})
#: Knowledge-store backends that map to Postgres + the ``vector`` extension.
_PGVECTOR_BACKENDS = frozenset({"pgvector"})
#: Backends that map to a Mongo Atlas cluster (design §3 row 2).
_MONGO_BACKENDS = frozenset({"mongo", "mongo-atlas", "atlas"})
#: Backends that map to a managed Redis (design §3 row 3).
_REDIS_BACKENDS = frozenset({"redis"})

#: Hosting targets that consume the ``hosting.stores`` block. Foundry is a true
#: managed runtime — it provisions its own state, so its ``stores`` is ignored
#: (design §2 note: ``stores`` is "langgraph/agentos only").
_STORE_HOSTS = frozenset({"langgraph-platform", "agentos"})

#: Default serve port per hosting target (design §2: 8088 / 8123 / 7777).
_DEFAULT_PORT = {"foundry": 8088, "langgraph-platform": 8123, "agentos": 7777}


def has_infra(ctx: EmitContext) -> bool:
    """Whether ``ctx`` carries any declared infra — ``persistence`` OR
    ``knowledge.store`` OR ``hosting``. A copilot that declares none (in-memory,
    no-RAG, self-hosted) has no infra to provision (back-compat)."""
    return (
        ctx.persistence is not None
        or ctx.knowledge_store is not None
        or ctx.hosting is not None
    )


def _env_slug(ref: str) -> str:
    """``primary-pg`` → ``PRIMARY_PG`` — a stable UPPER_SNAKE env-var suffix so a
    per-``ref`` output env var is deterministic (and disambiguates when a copilot
    binds more than one physical store)."""
    out = []
    for ch in str(ref).strip():
        out.append(ch if (ch.isalnum() or ch == "_") else "_")
    slug = "".join(out).strip("_") or "STORE"
    return slug.upper()


def _slot_iter(ctx: EmitContext):
    """Yield ``(label, backend, ref)`` for every declared persistence slot +
    the knowledge store — the raw signals the resource grouping reads."""
    persistence = ctx.persistence or {}
    for slot in ("checkpoint", "memory", "cache"):
        node = persistence.get(slot)
        if node and node.get("backend"):
            yield (f"persistence.{slot}", node["backend"], node.get("ref"))
    store = ctx.knowledge_store
    if store and store.get("backend"):
        yield ("knowledge.store", store["backend"], store.get("ref"))


def _group_stores(ctx: EmitContext) -> tuple[list[dict], list[dict], list[dict], list[str]]:
    """Group the declared slots into deduped Postgres / Mongo / Redis resource
    lists (keyed by ``ref``), plus the honest de-para losses for any backend with
    no infra mapping. This is the **dedup-by-ref** rule (design §3)."""
    pg: dict[str, dict[str, Any]] = {}
    mongo: dict[str, dict[str, Any]] = {}
    redis: dict[str, dict[str, Any]] = {}
    losses: list[str] = []

    for label, backend, ref in _slot_iter(ctx):
        key = ref or label  # a store with no ref keys on its slot label
        if backend in _POSTGRES_BACKENDS or backend in _PGVECTOR_BACKENDS:
            entry = pg.setdefault(
                key,
                {"ref": ref, "database": "dna", "pgvector": False, "used_by": []},
            )
            if backend in _PGVECTOR_BACKENDS:
                entry["pgvector"] = True
            entry["used_by"].append(label)
        elif backend in _MONGO_BACKENDS:
            entry = mongo.setdefault(
                key,
                {"ref": ref, "atlas": True, "vector_search": False, "used_by": []},
            )
            if label == "knowledge.store":
                entry["vector_search"] = True
            entry["used_by"].append(label)
        elif backend in _REDIS_BACKENDS:
            entry = redis.setdefault(
                key, {"ref": ref, "redisearch": True, "used_by": []}
            )
            entry["used_by"].append(label)
        else:
            losses.append(
                f"{label} backend {backend!r} has no Terraform infra mapping "
                f"(design §3 covers postgres/pgvector, mongo/atlas, redis) — "
                f"provision it out-of-band or extend the binding doc"
            )

    def _finish(coll: dict, prefix: str) -> list[dict]:
        out = []
        for entry in coll.values():
            entry["used_by"] = sorted(entry["used_by"])
            ref = entry["ref"]
            entry["output_env"] = f"{prefix}_{_env_slug(ref)}" if ref else None
            entry["secret"] = True
            out.append(entry)
        return sorted(out, key=lambda e: (e["ref"] or "", e["output_env"] or ""))

    return (
        _finish(pg, "DNA_PG_URI"),
        _finish(mongo, "DNA_MONGO_URI"),
        _finish(redis, "DNA_REDIS_URL"),
        losses,
    )


def _hosting_inputs(
    ctx: EmitContext, pg: list[dict], redis: list[dict]
) -> tuple[dict | None, list[str]]:
    """Build the hosting module input from ``ctx.hosting`` + roll a store-host's
    ``hosting.stores`` into the Postgres/Redis resource lists. Returns
    ``(hosting_block_or_None, extra_losses)``."""
    hosting = ctx.hosting
    if hosting is None:
        return None, []
    target = hosting.get("target")
    losses: list[str] = []
    resources = hosting.get("resources") or {}
    image = hosting.get("image") or {}
    port = image.get("port") or _DEFAULT_PORT.get(target)
    block: dict[str, Any] = {
        "target": target,
        "mode": hosting.get("mode"),
        "resources": {"cpu": resources.get("cpu"), "memory": resources.get("memory")},
        "image": {
            "registry_hint": image.get("registry_hint"),
            "remote_build": image.get("remote_build"),
            "base_image": image.get("base_image"),
            "container_port": port,
        },
    }

    if target == "foundry":
        # A true managed runtime — Foundry provisions its own state, so the
        # declared `stores` is ignored here (design §2: stores = langgraph/agentos
        # only). CognitiveServices account + project + ACR + model deployment +
        # RBAC. The agent VERSION is NOT an ARM resource (post-provision azd/SDK).
        block["foundry"] = {
            "account": True,
            "project": True,
            "acr": True,
            "app_insights": True,
            "log_analytics": True,
            "connections": True,
            "identity": "system_assigned",
            "model_deployment": ctx.model,
            "rbac": [
                {"principal": "project_identity", "role": "AcrPull"},
                {"principal": "agent_identity", "role": "Azure AI User"},
            ],
        }
        block["note"] = (
            "the agent version is NOT an ARM resource — it is a post-provision "
            "`azd deploy` / SDK step, not a Terraform resource (design §3)"
        )
        if hosting.get("stores"):
            losses.append(
                "hosting.stores is ignored for target 'foundry' — Foundry is a "
                "managed runtime that provisions its own state (design §2)"
            )
    elif target in _STORE_HOSTS:
        # Self-host + optional control plane: compute + registry + managed
        # Postgres/Redis (from `stores`) + the control-plane secret env.
        stores = hosting.get("stores") or {}
        secret_env = (
            ["LANGGRAPH_CLOUD_LICENSE_KEY"]
            if target == "langgraph-platform"
            else ["AGENTOS_JWT_SECRET"]
        )
        block[target.replace("-", "_")] = {
            "compute": True,
            "registry": True,
            "ingress": True,
            "secret_env": secret_env,
        }
        # Roll a required store into the resource lists IF the persistence refs did
        # not already declare it (design §3 hosting rows). No ref is declared on a
        # `stores` requirement → synthesize one from the agent slug.
        from dna.emit.scaffold import py_identifier

        base = py_identifier(ctx.name)
        if stores.get("postgres") == "required" and not pg:
            ref = f"{base}-pg"
            pgvector = target == "agentos"  # AgentOS wants Postgres/pgvector
            pg.append(
                {
                    "ref": ref,
                    "database": "dna",
                    "pgvector": pgvector,
                    "used_by": ["hosting.stores.postgres"],
                    "output_env": f"DNA_PG_URI_{_env_slug(ref)}",
                    "secret": True,
                }
            )
        if stores.get("redis") == "required" and not redis:
            ref = f"{base}-redis"
            redis.append(
                {
                    "ref": ref,
                    "redisearch": True,
                    "used_by": ["hosting.stores.redis"],
                    "output_env": f"DNA_REDIS_URL_{_env_slug(ref)}",
                    "secret": True,
                }
            )
    elif target is not None:
        losses.append(
            f"hosting target {target!r} has no infra mapping (design §3 covers "
            f"foundry, langgraph-platform, agentos)"
        )

    return block, losses


def _env_injection(
    pg: list[dict], mongo: list[dict], redis: list[dict], hosting: dict | None
) -> dict[str, dict[str, Any]]:
    """The **env-injection contract** (design §3 key rule): each store's Terraform
    OUTPUT → the env var the emitted copilot reads. This is the seam the scaffold
    emitters bind against — a ``ref``'s connection string arrives as ``output_env``."""
    out: dict[str, dict[str, Any]] = {}
    for entry in pg:
        if entry.get("output_env"):
            out[entry["output_env"]] = {
                "from": f"postgres[{entry['ref']!r}].connection_string",
                "secret": True,
            }
    for entry in mongo:
        if entry.get("output_env"):
            out[entry["output_env"]] = {
                "from": f"mongo[{entry['ref']!r}].connection_string",
                "secret": True,
            }
    for entry in redis:
        if entry.get("output_env"):
            out[entry["output_env"]] = {
                "from": f"redis[{entry['ref']!r}].connection_string",
                "secret": True,
            }
    if hosting is not None:
        for key in ("langgraph_platform", "agentos"):
            sub = hosting.get(key)
            if sub:
                for env in sub.get("secret_env", []):
                    out[env] = {"from": f"hosting.{hosting['target']}.{env}", "secret": True}
    return out


def _module_inputs(ctx: EmitContext) -> tuple[dict[str, Any], list[str]]:
    """Assemble the full ``.tfvars.json`` object + the aggregate de-para losses."""
    pg, mongo, redis, store_losses = _group_stores(ctx)
    hosting, host_losses = _hosting_inputs(ctx, pg, redis)
    # re-sort in case hosting.stores appended a synthesized resource
    pg.sort(key=lambda e: (e["ref"] or "", e["output_env"] or ""))
    redis.sort(key=lambda e: (e["ref"] or "", e["output_env"] or ""))
    inputs = {
        "dna_agent": ctx.name,
        "scope": ctx.scope,
        "postgres": pg,
        "mongo": mongo,
        "redis": redis,
        "hosting": hosting,
        "env_injection": _env_injection(pg, mongo, redis, hosting),
    }
    return inputs, store_losses + host_losses


def _mapping() -> dict[str, str]:
    """The field-level de-para for the report."""
    return {
        "Copilot.persistence.{checkpoint,memory,cache}": "postgres[]/mongo[]/redis[] module inputs (deduped by ref)",
        "Copilot.knowledge.store": "postgres[].pgvector / mongo[].vector_search",
        "Copilot.hosting.target=foundry": "hosting.foundry (account/project/acr/model_deployment/rbac)",
        "Copilot.hosting.target=langgraph-platform|agentos": "hosting.<target> (compute/registry/stores/secret_env)",
        "ref → TF output": "env_injection[<ENV_VAR>] = {from: <kind>[ref].connection_string, secret}",
    }


def emit_infra(ctx: EmitContext) -> EmitResult:
    """Render the Terraform infra inputs (``<agent>.tfvars.json``) for a Copilot.

    ``ctx`` is an enriched copilot context (:func:`~dna.emit.build_copilot_context`)
    carrying ``persistence`` / ``knowledge.store`` / ``hosting``. Returns an
    :class:`~dna.emit.EmitResult` with ONE ``role="infra"`` artifact — the
    ``.tfvars.json`` the dna-cloud Terraform modules consume. Raises
    :class:`~dna.emit.EmitError` when the copilot declares no infra at all.
    """
    if not has_infra(ctx):
        raise EmitError(
            f"copilot {ctx.name!r} declares no `persistence`/`knowledge.store`/"
            "`hosting` — nothing to provision (an in-memory, no-RAG, self-hosted "
            "copilot has no infra inputs)"
        )
    from dna.emit.scaffold import py_identifier

    inputs, losses = _module_inputs(ctx)
    # `.tfvars.json` — Terraform reads this natively. 2-space indent, no trailing
    # spaces; byte-identical to the TS twin's `JSON.stringify(x, null, 2)`.
    content = json.dumps(inputs, indent=2, ensure_ascii=False) + "\n"
    filename = f"{py_identifier(ctx.name)}.tfvars.json"

    return EmitResult(
        target="terraform",
        artifacts=[EmitArtifact(path=filename, content=content, role="infra")],
        losses=losses,
        mapping=_mapping(),
    )
