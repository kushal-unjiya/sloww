# Inference service (`/inference`)

Agentic RAG execution service for Sloww AI.

## What this service does

- Runs the **LangGraph** state machine (one request = one graph execution)
- Uses **hybrid retrieval**:
  - dense: Qdrant vector search scoped by `notebook_id`
  - sparse: Postgres term pre-filter + BM25 scoring
  - merge: Reciprocal Rank Fusion (RRF)
  - rerank: Cross-encoder (loaded once at startup)
- Generates an answer (cited or parametric)
- Streams results and agent activity over **SSE**

## HTTP surface

- `GET /health`
- `POST /chat/stream` (SSE)

The UI **does not call inference directly** in normal usage.
Instead:

UI → backend `POST /chat/stream` (Clerk JWT) → backend relays to inference (internal token) → UI consumes SSE

## Critical invariants

1) **Notebook security boundary**
- Every Qdrant search MUST include `notebook_id` filter.
- `QdrantClientWrapper.search()` rejects missing filters.

2) **Embedding model lock**
- `EMBEDDING_MODEL` must exactly match what was used at ingest time.

3) **Cross-encoder loads once**
- Loaded in FastAPI lifespan.
- Never load per request.

4) **Loop guard**
- Orchestrator may loop retrieval up to `LOOP_MAX`.

5) **Graceful degradation**
- Citation assertion can degrade (stream continues with warning).
- Visualizer can degrade (chart omitted).

## Pipeline stages (current implementation)

Graph state is a single Pydantic `GraphState` threaded through all nodes:

- `base_query_processor`
  - normalize query
  - HyDE expansion
  - intent classification
- `retrieval_engine`
  - runs dense researcher and sparse researcher in parallel
  - Qdrant dense + BM25 sparse
  - RRF merge
  - cross-encoder rerank
- `orchestrator`
  - coverage scoring
  - emits `ExecutionPlan` and may loop
- `aggregator` (optional)
- `cited_summary_generator` OR `normal_text_generator`
- `visualizer` (optional)
- `response_assembler`

## Agent activity stream

The inference service emits structured `agent_trace` SSE frames while work is running. These are intentionally summaries of agent behavior, not hidden chain-of-thought. They include:

- `agent_id`
- `label`
- `role`
- `phase`: `start`, `progress`, `end`, or `error`
- `message`
- `input_preview`
- `output_preview`
- `metadata`
- `ts`

The backend relays these frames live and persists them in assistant message metadata as `agent_traces`.

## Logging

Default format is JSON. For terminal readability:

```bash
LOG_FORMAT=pretty ./run-dev.sh
```

All logs include `request_id` if provided via `X-Request-ID` (or auto-generated).

## What’s not fully implemented yet

### Chat persistence

The backend `api/chat/` module is still scaffolded. Once implemented, it will:
- create conversations + messages in Postgres
- relay streaming to inference
- persist the final assistant message + citations after stream end

Inference currently attempts a best-effort `messages.status` update and writes an audit row to `retrieval_cache` (if the table exists).

### Vector database population

Qdrant only becomes useful after ingestion writes vectors + chunk payloads.
That ingestion path lives in `data-loader/` and backend migrations:
- chunking + embeddings
- write chunk metadata to Postgres (`chunks_metadata`)
- upsert vectors + payloads to Qdrant (`documents` collection)

## Next steps to “start saving chat” and “start vector DB”

See the repo root `README.md` (Roadmap section) for the concrete checklist.
