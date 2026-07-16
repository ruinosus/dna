# Copilot persistence — the Mongo path

A `Copilot` declares **where its state lives** in one block — `persistence`
(checkpoint / memory / cache) and `knowledge.store` (the vector store). DNA
0.17.0 emits **Postgres** config for all three runtimes as a first-class,
functional path (see [Emitting to a runtime](emitting-to-a-runtime.md)). The
`backend` enum is **open** — `postgres | mongo | redis | cosmos | azure-ai-search`
— so a Copilot can already *declare* `backend: mongo` today. What this guide
covers is the **Mongo target**: the per-framework configuration you write by hand
until Mongo emit ships, and — just as important — the **honest gaps** where a
framework simply has no Mongo slot.

> **Status.** DNA v1 emits Mongo config for **no** runtime. This is a
> hand-configuration guide, not a `dna emit --target … ` feature. The Postgres
> path is the supported, emitted one; reach for Mongo only when your infra is
> already MongoDB/Atlas and you accept the gaps below.

## The declaration is the same; only the backend changes

```yaml
Copilot:
  persistence:
    checkpoint: { backend: mongo, ref: primary-mongo }   # thread/run state
    memory:     { backend: mongo, ref: primary-mongo }   # cross-session memory
  knowledge:
    collections: [rfp-corpus]
    store:
      backend: mongo-atlas                                # vectors — Atlas only (see gaps)
      ref: primary-mongo
      embed: { model: text-embedding-3-small, dims: 1536 }
```

`ref` points at an infra resource (an Atlas cluster / a self-hosted Mongo). As
with Postgres, the DSN is **never hardcoded** — it is read from an env var keyed
by the ref (e.g. `primary-mongo` → `DNA_PRIMARY_MONGO_URL`), which
`f-copilot-infra-binding` wires from the Terraform module output.

## Per-framework Mongo configuration

### LangGraph

| Slot | Class | Package |
|---|---|---|
| checkpoint | `MongoDBSaver` | `langgraph-checkpoint-mongodb` |
| memory (long-term Store) | **— none —** | *(gap, see below)* |
| vectors | `MongoDBAtlasVectorSearch` | `langchain-mongodb` (Atlas only) |

```python
from langgraph.checkpoint.mongodb import MongoDBSaver

# checkpoint — thread/run state in Mongo
checkpointer = MongoDBSaver.from_conn_string(os.environ["DNA_PRIMARY_MONGO_URL"])
graph = builder.compile(checkpointer=checkpointer)

# vectors — retrieval only, Atlas $vectorSearch
from langchain_mongodb import MongoDBAtlasVectorSearch
store = MongoDBAtlasVectorSearch.from_connection_string(
    os.environ["DNA_PRIMARY_MONGO_URL"],
    namespace="dna.rfp_corpus",
    embedding=embeddings,          # text-embedding-3-small, 1536-dim
    index_name="vector_index",
)
```

**Gap — no Mongo memory Store.** LangGraph's long-term memory (`BaseStore`, the
`store=` on `compile`) has a Postgres and an in-memory implementation but **no
Mongo one**. There is no `MongoStore`. If you declare `memory: { backend: mongo }`
you get checkpointing but must either (a) keep long-term memory on Postgres /
in-memory, or (b) write your own `BaseStore` over a Mongo collection. Declare it
honestly — do not pretend a Mongo Store exists.

### Agno

| Slot | Class | Package |
|---|---|---|
| checkpoint + memory (`db=`) | `MongoDb` | `agno` (+ `pymongo`) |
| vectors | `MongoVectorDb` | `agno` (+ `pymongo`, Atlas vector search) |

```python
from agno.db.mongo import MongoDb
from agno.knowledge.knowledge import Knowledge
from agno.vectordb.mongodb import MongoVectorDb

db = MongoDb(db_url=os.environ["DNA_PRIMARY_MONGO_URL"])   # session + user memories
knowledge = Knowledge(
    vector_db=MongoVectorDb(                                # NOT `MongoDb` — a distinct class
        collection_name="rfp_corpus",
        db_url=os.environ["DNA_PRIMARY_MONGO_URL"],
    ),
)
agent = Agent(db=db, enable_user_memories=True, knowledge=knowledge, search_knowledge=True, ...)
```

> **Name hazard.** The vector class is **`MongoVectorDb`**, not `MongoDb`.
> `MongoDb` is the session/memory store (`db=`); `MongoVectorDb` is the vector
> store (`vector_db=`). Mixing them is the classic Agno Mongo mistake.

**Gap — Atlas-only vectors.** `MongoVectorDb` uses Atlas `$vectorSearch`; a
self-hosted community MongoDB has no `$vectorSearch` operator, so the vector
store needs an **Atlas** cluster (or Atlas Local) even if checkpoint/memory run
on self-hosted Mongo.

### Microsoft Agent Framework (MS-AF)

MS-AF's managed-Mongo story is **Cosmos DB (Mongo vCore)**, not community Mongo.

| Slot | Class | Notes |
|---|---|---|
| checkpoint / memory (thread state) | **serialize-yourself** | no native Mongo/Cosmos thread-store |
| vectors | `CosmosMongoCollection` | Cosmos DB for MongoDB vCore `$vectorSearch` |

```python
# vectors — Cosmos DB for MongoDB (vCore) vector search, as a context provider
from agent_framework.cosmos import CosmosMongoCollection   # verify import at wire-up

vector_store = CosmosMongoCollection(
    connection_string=os.environ["DNA_PRIMARY_MONGO_URL"],
    collection_name="rfp_corpus",
    embedding_model="text-embedding-3-small",
    embedding_dimensions=1536,
)
agent = client.as_agent(..., context_providers=[vector_store])
```

**Gap — lopsided, and no thread-store.** MS-AF's store surface is uneven: Redis
is Python-only, Cosmos is the managed-Mongo path, and there is **no** native
Postgres/Mongo thread-store at all. So checkpoint/memory under `backend: mongo`
is the same **serialize-yourself** wiring-point as the Postgres path — serialize
the run's `AgentThread` to a Mongo/Cosmos document yourself. Only the **vector**
slot maps to a real class.

## The honest gap table

| | LangGraph | Agno | MS-AF |
|---|---|---|---|
| checkpoint | `MongoDBSaver` ✅ | `MongoDb` (`db=`) ✅ | serialize-yourself ⚠️ |
| memory (long-term) | **none** ❌ | `MongoDb` + `enable_user_memories` ✅ | serialize-yourself ⚠️ |
| vectors | `MongoDBAtlasVectorSearch` (Atlas) ⚠️ | `MongoVectorDb` (Atlas) ⚠️ | `CosmosMongoCollection` (Cosmos vCore) ⚠️ |

Legend: ✅ real class · ⚠️ works but with a constraint (Atlas/Cosmos-only, or a
serialize wiring-point) · ❌ no slot in the framework.

Two constraints dominate:

1. **`$vectorSearch` is Atlas / Cosmos vCore, not community Mongo.** Self-hosted
   community MongoDB has no vector search operator. A `mongo-atlas` /
   `cosmos` vector backend needs the managed service; a plain self-hosted Mongo
   can hold checkpoint/memory but **not** vectors.
2. **LangGraph has no Mongo long-term Store** and **MS-AF has no native
   thread-store**. Those are framework gaps, not DNA gaps — DNA will emit `null`
   + a documented wiring-point rather than a broken config, exactly as it does
   for the analogous Postgres gaps.

## When Mongo emit ships

The `backend` enum already accepts `mongo` / `cosmos`, so the *declaration* is
stable. When the emitter lands it will map each declared slot to the class in the
tables above, emit `null` + this guide's wiring-note where a framework has no
slot, and read the DSN from the ref's env var — identical in shape to the
Postgres path, so a Copilot switches `postgres` → `mongo` by editing one word.
Until then, use the snippets above by hand.
