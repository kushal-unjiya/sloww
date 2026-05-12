# Sloww

Upload **PDF and DOCX** sources into **projects**, ask questions in **chat**, and get **streamed answers with citations**. Data is **per user** (Clerk auth).

**New here?** Start with **[SETUP.md](SETUP.md)** — local dev, Docker, Supabase, Qdrant, GCP, env vars, and chat wiring.

---

## Architecture (v1)

| Layer | Tech | Responsibility |
|-------|------|----------------|
| `ui/` | React, Vite, pnpm | Projects, sources, chat UI |
| `backend/` | FastAPI, uv, Alembic | Auth, CRUD, uploads (**GCS**), **chat relay + persistence** |
| `inference/` | FastAPI, LangGraph-style RAG | **Qdrant** dense retrieval, rerank, LLM, SSE |
| `data-loader/` | Python worker | Ingestion: extract → chunk → embed → **Qdrant** (`proj_<projectId>`) |

- **Postgres** (e.g. Supabase): users, projects, documents, jobs, **conversations/messages/citations** — not chunk rows for retrieval.
- **GCS**: uploaded document bytes (`storage_key` is the object path in your bucket).
- **Qdrant**: vectors + chunk payloads used for retrieval and citation text.

---

## Quick start (local)

```bash
# Docker Compose env (repo root)
cp compose.env.example compose.env

# Service envs (for host-run or migrations)
cp backend/.env.example backend/.env
cp inference/.env.example inference/.env
cp data-loader/.env.example data-loader/.env
# UI (only needed if you run Vite on the host)
cp ui/.env.example ui/.env

docker compose --env-file compose.env up -d postgres qdrant
cd backend && uv sync && uv run python -m alembic upgrade head && cd ..
docker compose --env-file compose.env up --build
```

Open **http://127.0.0.1:3000** (UI in Compose) or run `ui` with `pnpm dev` and set `VITE_APP_URL` in `ui/.env`.

Details, hybrid workflows, and production: **[SETUP.md](SETUP.md)**.

---

## Ports (Docker Compose defaults)

| Service | Port |
|---------|------|
| UI | 3000 |
| Backend API | 8000 |
| Inference | 8001 |
| Postgres | 5432 |
| Qdrant | 6333 |

---

## Repo layout

```
backend/      FastAPI + migrations
inference/    Internal RAG + /chat/stream
data-loader/  Ingestion worker
ui/           Frontend SPA
.cursor/      Editor/AI context docs → see .cursor/README.md
PAI/          Legacy reference tree (not used by root compose)
```

---

## Docs index

| Doc | Purpose |
|-----|---------|
| [SETUP.md](SETUP.md) | **Operator guide**: env, local & cloud, GCP, Qdrant, chat |
| [backend/README.md](backend/README.md) | Backend package layout & commands |
| [inference/README.md](inference/README.md) | Inference & SSE |
| [data-loader/README.md](data-loader/README.md) | Worker |
| [ui/README.md](ui/README.md) | Frontend |
| [.cursor/README.md](.cursor/README.md) | How to use the Cursor folder |
| [.cursor/PROJECT.md](.cursor/PROJECT.md) | Long-form architecture (may include historical notes) |
