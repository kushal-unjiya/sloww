# Sloww `inference` service (Python 3.13 + uv)

**Internal** FastAPI service: **dense Qdrant retrieval**, cross-encoder rerank, LLM providers, **`POST /chat/stream`** (SSE). Called by the **backend** with **`Authorization: Bearer <INTERNAL_TOKEN>`** — not by the browser.

**Onboarding:** **[../SETUP.md](../SETUP.md)** — Qdrant Cloud, `EMBEDDING_MODEL`, LLM keys, `INTERNAL_TOKEN`.

---

## Setup

```bash
cd inference
uv sync --extra dev
cp .env.example .env
```

Fill **`DATABASE_URL`** with **`postgresql+asyncpg://...`** (same Postgres as backend; for Supabase include SSL options).

**Must match backend**

- **`INTERNAL_TOKEN`**
- **`EMBEDDING_MODEL`** (and vector dimension expectations) with **`data-loader`**

**Qdrant**

- **`QDRANT_URL`**, **`QDRANT_API_KEY`** (if cluster requires it)
- **`QDRANT_COLLECTION_PREFIX`** default `proj_` → collection per project: `proj_<notebook_id>`

---

## Run locally

Prereq: Postgres + Qdrant (e.g. `docker compose up -d postgres qdrant` from repo root).

```bash
cd inference
./run-dev.sh
# or: LOG_FORMAT=pretty ./run-dev.sh
```

Health: `curl -s http://127.0.0.1:8001/health`

If the **UI** shows no tokens, verify **backend** `INFERENCE_URL` (host uses `http://127.0.0.1:8001`) and matching **`INTERNAL_TOKEN`**.

---

## `POST /chat/stream`

JSON body:

```json
{
  "query": "your question",
  "conversation_id": "uuid-string",
  "notebook_id": "project-uuid"
}
```

Stream: `data: {"type":"token","content":"..."}\n\n` then `data: {"type":"done",...}\n\n` with **`citations`**.

Example:

```bash
curl -N \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer changeme" \
  -d '{"query":"hi","conversation_id":"00000000-0000-4000-8000-000000000001","notebook_id":"00000000-0000-4000-8000-000000000002"}' \
  http://127.0.0.1:8001/chat/stream
```

---

## Architecture note

v1 retrieval is **Qdrant-centric**; citations are built from retrieved chunk payloads. For a longer spec, see `INFERENCE.md` if present, and **[../SETUP.md](../SETUP.md)** for ops.

See **[../.cursor/inference.md](../.cursor/inference.md)** for historical / narrative context (may mention NDJSON or headers that differ from current `Bearer` auth — prefer this README + code).
