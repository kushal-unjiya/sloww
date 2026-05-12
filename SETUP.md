# Sloww — Setup & operations (solo developer guide)

This is the **onboarding and runbook** for the monorepo. Read this when you are new to the project or returning after a break.

**Quick links**


| Topic                                                         | Where                                    |
| ------------------------------------------------------------- | ---------------------------------------- |
| **How to start each service (Docker vs host)**               | [§3.0](#30-how-to-start-each-service)    |
| One-page project overview                                     | [README.md](README.md)                   |
| Cursor / architecture deep-dive (may be partially historical) | [.cursor/PROJECT.md](.cursor/PROJECT.md) |
| Per-service notes for AI/editor context                       | [.cursor/README.md](.cursor/README.md)   |


---

## 1. What you are running

Sloww is a **multi-service monorepo**:


| Path           | Role                                                                                                                                            |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend/`     | Public FastAPI API: Clerk auth, projects, documents, uploads (**GCS**), **chat relay + Postgres persistence**         |
| `inference/`   | Internal FastAPI: **dense Qdrant retrieval**, rerank, LLM, **SSE** `POST /chat/stream` (called only by backend with `INTERNAL_TOKEN`)           |
| `data-loader/` | Worker: polls `ingestion_jobs`, downloads bytes from storage, **PDF/DOCX → chunk → embed → Qdrant** (one collection per project: `proj_<uuid>`) |
| `ui/`          | Vite + React SPA: projects, sources, chat with citations                                                                                        |


**v1 product shape**

- **PDF + DOCX** ingestion; chunks live **only in Qdrant** (not as Postgres chunk tables for retrieval).
- **Chat** is persisted in Postgres (`conversations`, `messages`, `retrieval_runs`, `citations`); UI loads history from the backend.
- **Notebook UI**: **Sources** + **Chat** (no separate “Studio / audio” product panel in the main flow).

The legacy **`PAI/`** tree is not used by root `docker-compose.yml`; you can ignore or delete it for a smaller workspace.

---

## 2. Prerequisites

Install on your machine:

- **Git**
- **Docker Desktop** (for local Postgres + Qdrant, or use hosted services)
- **GCP** account with a **GCS bucket** and a **service account** key (local dev) or Cloud Run SA (prod)
- **Node 20+** and **pnpm** (`npm i -g pnpm`)
- **Python 3.13** and **[uv](https://docs.astral.sh/uv/)** (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

Accounts you will use in production-like setups:

- **Clerk** (auth)
- **Supabase** (Postgres) or local Postgres
- **Qdrant Cloud** or local Qdrant
- **GCP** (GCS bucket + Cloud Run) when you deploy
- At least one **LLM / embedding** provider (see `inference/.env.example`)

---

## 3. Local development (step by step)

### 3.0 How to start each service

Pick **one** workflow. For Docker Compose, fill `compose.env` first. For host-run, each service uses its own `.env`.

#### Option A — Full stack in Docker

From the **repository root** (run §3.3 migrations when the schema changes, or before the first boot):

```bash
docker compose --env-file compose.env up --build
```

- **Background:** `docker compose --env-file compose.env up --build -d` then `docker compose logs -f app inference data-loader`.
- **Stop:** `docker compose down` (or `docker compose --env-file compose.env down`).

| Compose name  | Source folder    | Role              | URL / port                                      |
| ------------- | ---------------- | ----------------- | ----------------------------------------------- |
| `postgres`    | (image)          | PostgreSQL        | Host: `localhost:5432`                          |
| `qdrant`      | (image)          | Vector DB         | `http://127.0.0.1:6333` (dashboard `/dashboard`) |
| `app`         | `backend/`       | FastAPI backend   | `http://127.0.0.1:8000` (`/docs`)               |
| `inference`   | `inference/`     | RAG + LLM + SSE    | `http://127.0.0.1:8001` (`/health`)             |
| `data-loader` | `data-loader/`   | Ingestion worker  | No HTTP port                                    |
| `ui`          | `ui/`            | Frontend          | `http://127.0.0.1:3000`                         |

**One service only:** e.g. `docker compose --env-file compose.env up -d app`, `docker compose --env-file compose.env restart inference`.

**Infra only** (for Option B): `docker compose --env-file compose.env up -d postgres qdrant`.

#### Option B — Hot reload (Docker = Postgres + Qdrant)

1. **Infrastructure** (repo root):

   ```bash
   docker compose --env-file compose.env up -d postgres qdrant
   ```

2. **Install deps** (after clone or lockfile changes):

   ```bash
   (cd backend && uv sync)
   (cd inference && uv sync --extra dev)
   (cd data-loader && uv sync)
   (cd ui && pnpm install)
   ```

3. **Migrations:** §3.3.

4. **Run each process in its own terminal** (working directory = that folder):

| Service        | Command                    | Default URL                          |
| -------------- | -------------------------- | ------------------------------------ |
| Backend        | `./run-dev.sh`             | http://127.0.0.1:8000                |
| Inference      | `./run-dev.sh`             | http://127.0.0.1:8001                |
| Data-loader    | `./run-dev.sh`             | —                                    |
| UI             | `./run-dev.sh` or `pnpm dev` | http://127.0.0.1:5173 (Vite)       |

Equivalents: backend `uv run python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000`; inference `uv run sloww-inference`; data-loader `uv run sloww-data-loader`.

**Option B env (service-local `.env` files):** set `GCS_BUCKET_NAME`, optional `GCS_PROJECT_ID`, and **`GOOGLE_APPLICATION_CREDENTIALS`** in **`backend/.env`** and **`data-loader/.env`**. Also set `INFERENCE_URL=http://127.0.0.1:8001` in **`backend/.env`**. `DATABASE_URL` and `QDRANT_URL` must use **`localhost`** (not Docker hostnames `postgres` / `qdrant`). **`ui/.env`:** `VITE_APP_URL=http://127.0.0.1:8000`.

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8001/health
```

---

### 3.1 Clone and environment files

```bash
git clone <your-repo-url>
cd sloww

# Docker Compose env (repo root)
cp compose.env.example compose.env

# Service envs (host-run)
cp backend/.env.example backend/.env
cp inference/.env.example inference/.env
cp data-loader/.env.example data-loader/.env

# UI env (only if you run UI with pnpm dev)
cp ui/.env.example ui/.env
```

Edit **service `.env` files**. Minimum for a working stack:

- **Backend (`backend/.env`)**: `DATABASE_URL`, `DB_SCHEMA`, `CLERK_*`, `INTERNAL_TOKEN`, `INFERENCE_URL`, `QDRANT_URL`, `GCS_*`, `GOOGLE_APPLICATION_CREDENTIALS` (local).
- **Inference (`inference/.env`)**: `DATABASE_URL` (`postgresql+asyncpg://...`), `QDRANT_URL`, `INTERNAL_TOKEN`, embedding/LLM keys.
- **Data-loader (`data-loader/.env`)**: `DATABASE_URL`, `DB_SCHEMA`, `QDRANT_URL`, `GCS_*`, `GOOGLE_APPLICATION_CREDENTIALS`, `EMBEDDING_*`.
- **UI (`ui/.env`)**: `VITE_*` variables only.

Edit **`ui/.env`**:

- **`VITE_CLERK_PUBLISHABLE_KEY`**
- **`VITE_APP_URL`** — must be a URL your **browser** can reach (e.g. `http://127.0.0.1:8000`), not `http://app:8000`

### 3.2 Start infrastructure

```bash
docker compose --env-file compose.env up -d postgres qdrant
```

(Optional) **Docker Compose + GCS:** the API and worker need credentials inside the container. Add a `docker-compose.override.yml` that mounts your key and sets `GOOGLE_APPLICATION_CREDENTIALS` to the in-container path (same pattern for `app` and `data-loader`).

Wait until Postgres is healthy (~10s).

### 3.3 Run database migrations (authoritative)

Migrations live in **`backend/migrations/`**. Run from **`backend/`**:

```bash
cd backend
uv sync
uv run python -m alembic upgrade head
cd ..
```

Use the same `DATABASE_URL` / `DB_SCHEMA` as the running backend (for local Docker Postgres, match `.env`; for Supabase, use the Supabase connection string with `sslmode=require`).

### 3.4 Full stack with Docker Compose

```bash
docker compose --env-file compose.env up --build
```

Typical ports:


| Service          | URL                                                                |
| ---------------- | ------------------------------------------------------------------ |
| UI (container)   | [http://127.0.0.1:3000](http://127.0.0.1:3000)                     |
| Backend          | [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)           |
| Inference        | [http://127.0.0.1:8001/health](http://127.0.0.1:8001/health)       |
| Postgres (host)  | `localhost:5432`                                                   |
| Qdrant dashboard | [http://127.0.0.1:6333/dashboard](http://127.0.0.1:6333/dashboard) |


### 3.5 Hybrid: hot-reload UI / Python on the host

This is the same as **§3.0 Option B**; kept here for a short checklist.

1. Keep `postgres` and `qdrant` running in Docker.
2. Terminal 1 — backend:

   ```bash
   cd backend && ./run-dev.sh
   ```

   Ensure `backend/.env` has `INFERENCE_URL=http://127.0.0.1:8001`.

3. Terminal 2 — inference:

   ```bash
   cd inference && cp .env.example .env  # first time only
   ./run-dev.sh
   ```

4. Terminal 3 — data-loader:

   ```bash
   cd data-loader && ./run-dev.sh
   ```

5. Terminal 4 — UI:

   ```bash
   cd ui && pnpm install && pnpm dev
   ```

### 3.5.1 Stop and free ports

**Docker** (repo root):

```bash
docker compose down
```

**Processes on your Mac** (backend, inference, data-loader, Vite): stop the terminals you started, or find listeners:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:8001 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

If **Docker Postgres** fails because **port 5432** is already in use (e.g. Homebrew PostgreSQL):

```bash
lsof -nP -iTCP:5432 -sTCP:LISTEN
brew services list | grep -i postgresql || true
brew services stop postgresql@16 || true
brew services stop postgresql || true
```

### 3.5.2 Clean restart (Option B)

```bash
cd /path/to/sloww   # your clone
docker compose down --remove-orphans || true
docker compose --env-file compose.env up -d postgres qdrant
cd backend && uv sync && uv run python -m alembic upgrade head && cd ..
# Then start Option A or Option B from §3.0 again.
```

---

### 3.6 Smoke test (local)

1. Open UI → sign in with Clerk.
2. Create or open a **project**.
3. **Upload a PDF or DOCX** → wait until processing finishes (`chunk_count` / status).
4. Ask a question in **Chat** → streaming answer + **Sources** citations under the assistant message.
5. **Refresh** the page → messages should **reload** from the backend.

If chat streams but citations are empty, check Qdrant has points in collection **`proj_<project-uuid>`** and that ingestion used the same **`EMBEDDING_MODEL`** as inference.

---

## 4. Building Docker images

You rarely build Dockerfiles by hand; **Compose** builds them:

```bash
docker compose build          # all services
docker compose build app      # backend only
docker compose build inference
docker compose build data-loader
docker compose build ui
```

Dockerfiles:

- `backend/Dockerfile`
- `inference/Dockerfile`
- `data-loader/Dockerfile`
- `ui/Dockerfile` (bakes `VITE_*` at build time for containerized UI)

For **production**, build in CI, push to **Artifact Registry**, deploy to **Cloud Run** (below).

---

## 5. Supabase Postgres + DBeaver

### 5.1 Create Supabase project

1. [Supabase](https://supabase.com) → New project → note the **database password**.

### 5.2 Connection string

In Supabase: **Project Settings → Database → Connection string → URI**.

Build `**DATABASE_URL`** for the backend:

- Use `**postgresql+psycopg://`** for Alembic/sync SQLAlchemy.
- Append `**?sslmode=require**` if not already present.
- URL-encode special characters in the password (`@` → `%40`, etc.).

For **inference**, use the **same host/user/password/database** with `**postgresql+asyncpg://`**.

### 5.3 DBeaver

1. New connection → **PostgreSQL**.
2. Host / port / database / user from Supabase (often host `db.<ref>.supabase.co`, db `postgres`, user `postgres`).
3. Enable **SSL**.
4. Browse schema `**sloww_ai`** after migrations.

### 5.4 Run migrations against Supabase

From your laptop (not necessarily from Cloud Run):

```bash
cd backend
DATABASE_URL='postgresql+psycopg://postgres:YOUR_PASSWORD@db.xxx.supabase.co:5432/postgres?sslmode=require' \
DB_SCHEMA=sloww_ai \
uv run python -m alembic upgrade head
```

---

## 6. Qdrant (local vs cloud)

### Local (Docker Compose)

- `**QDRANT_URL=http://qdrant:6333**` inside Compose; `**http://127.0.0.1:6333**` from host.
- `**QDRANT_API_KEY**` empty.

### Qdrant Cloud

1. Create a cluster → copy **endpoint** (HTTPS).
2. Set `**QDRANT_URL`** to that base URL (include port if shown).
3. Set `**QDRANT_API_KEY`** if the cluster requires it.

### Collections

The app uses `**QDRANT_COLLECTION_PREFIX**` (default `proj_`) + project UUID → collection name `**proj_<project-uuid>**`. You **do not** need to pre-create collections for normal operation; the worker/inference ensure usage. Check the Qdrant dashboard to verify points after ingestion.

**Vector dimension changes:** If you change `**EMBEDDING_VECTOR_SIZE**` (e.g. **2048** for `nvidia/llama-nemotron-embed-vl-1b-v2`), existing collections built with the old size are invalid. **Delete** affected `proj_*` collections in Qdrant (HTTP API or dashboard), then **re-upload** or **reprocess** documents so they are re-ingested.

**Important:** `**EMBEDDING_MODEL`** and vector size must match between `**data-loader`** and `**inference**`.

---

## 7. Google Cloud Platform (production-shaped)

High-level order of operations:

1. **Create GCP project** (e.g. `sloww-dev`).
2. **Enable APIs**: Cloud Run, Artifact Registry, Secret Manager, Cloud Storage, IAM.
3. **GCS bucket** (private): uploads live here; IAM for:
  - Backend service account: `roles/storage.objectAdmin` (or tighter: sign + read/delete as needed).
  - Data-loader: at least **objectViewer** to read source files by `storage_key`.
4. **Artifact Registry**: create Docker repository; configure `docker push` from CI.
5. **Secrets**: store `DATABASE_URL`, `INTERNAL_TOKEN`, `QDRANT_*`, Clerk secrets, LLM keys, `GCS_BUCKET_NAME`, NVIDIA NIM / embedding keys, optional Pub/Sub settings, etc. in **Secret Manager**; reference them as **environment variables** on Cloud Run.
6. **Cloud Run services** (three):
   - `**backend`** — public HTTP; env: full backend vars + `INFERENCE_URL` pointing to inference service URL; **CORS** `cors_origins` must include your **Vercel** origin. Optional: **`PUBSUB_ENABLED=true`**, **`PUBSUB_PROJECT_ID`**, **`PUBSUB_INGESTION_TOPIC`** (see §7.1).
   - `**inference`** — prefer **internal ingress** or IAM; `**INTERNAL_TOKEN`** must match backend; `**DATABASE_URL`** async for inference.
   - `**data-loader`** — two deployment shapes:
     - **Local-style:** `**INGEST_MODE=poll**` (default), one container polling Postgres (no HTTP port needed).
     - **Event-driven (recommended on GCP):** `**INGEST_MODE=push**`, **`PORT=8080`**, **HTTP** service. Create a **Pub/Sub topic** (e.g. `ingestion-jobs`); add a **push subscription** to `https://<service-url>/pubsub/push` with **OIDC** (push identity = a GCP SA that can invoke Cloud Run). Grant the **backend** runtime SA **`roles/pubsub.publisher`** on that topic. Data-loader SA needs **GCS object read**, **Postgres**, **Qdrant**; use a unique **`WORKER_ID`** per replica if you scale. See §7.1.
7. **Networking / Supabase**: if you turn on **IP allowlisting** in Supabase, Cloud Run egress IPs are **not static** unless you add **Cloud NAT** with a reserved static IP. Simplest dev path: no DB IP allowlist + strong passwords + secrets in Secret Manager.

### 7.1 Pub/Sub → data-loader (optional)

After a successful upload + DB commit, the backend can publish a small JSON message to Pub/Sub:

`{"job_id":"...","document_id":"...","project_id":"...","storage_key":"..."}`

Configure:

1. **Topic:** `gcloud pubsub topics create ingestion-jobs` (or your name).
2. **Backend env:** `PUBSUB_ENABLED=true`, `PUBSUB_PROJECT_ID=<id>`, `PUBSUB_INGESTION_TOPIC=ingestion-jobs` (or full `projects/.../topics/...`).
3. **Cloud Run (data-loader):** `INGEST_MODE=push`, image from `data-loader/Dockerfile`, CPU/memory as needed for embeddings; set all existing data-loader + NIM + Qdrant + DB + GCS vars. **Configure logging** via Cloud Logging.
4. **Push subscription:** push endpoint `**POST /pubsub/push**`, audience = your Cloud Run service URL, authenticated push enabled. If the handler cannot claim the job (e.g. concurrency limit), it returns **503** so Pub/Sub retries (with backoff).
5. **Fallback:** If Pub/Sub publish fails, ingestion still works when `INGEST_MODE=poll` workers are running (they claim from Postgres).

If Pub/Sub is disabled, leave `**PUBSUB_ENABLED=false**` (default for local dev).

After deploy, run **migrations once** against Supabase from CI or your laptop (section 5.4).

---

## 8. Frontend on Vercel

1. Import the `**ui/`** directory as a Vercel project (or monorepo root with root dir `ui`).
2. Environment variables:
  - `**VITE_APP_URL`** — public **Cloud Run backend** URL (https).
  - `**VITE_CLERK_PUBLISHABLE_KEY`**
3. Redeploy when these change (Vite bakes them at build time).

---

## 9. Chat: how it is wired

```
Browser → POST /chat/stream (Clerk JWT) → Backend
       → POST /chat/stream (Bearer INTERNAL_TOKEN) → Inference (SSE)
       → Backend streams SSE back to browser
       → After `type: done`, backend persists assistant message + citations in Postgres
```

**You must configure**

- Backend: `**INFERENCE_URL`**, `**INTERNAL_TOKEN`**
- Inference: `**INTERNAL_TOKEN**` (same string)
- Both: access to **Postgres** and inference to **Qdrant**

**History endpoints** (used by UI): under `/chat/projects/{project_id}/conversations` and `.../messages` — see `backend/api/chat/routes.py`.

---

## 10. Environment variables cheat sheet


| Variable                                     | Service                         | Purpose                                       |
| -------------------------------------------- | ------------------------------- | --------------------------------------------- |
| `DATABASE_URL`                               | backend, inference, data-loader | Postgres (driver differs: psycopg vs asyncpg) |
| `DB_SCHEMA`                                  | all                             | Default `sloww_ai`                            |
| `GCS_BUCKET_NAME`                            | backend, data-loader            | Required GCS bucket for uploads + ingestion     |
| `GCS_PROJECT_ID`                           | backend, data-loader            | Optional; defaults from ADC / client            |
| `GOOGLE_APPLICATION_CREDENTIALS`           | backend, data-loader            | Local / Compose: SA JSON path; Cloud Run: usually omit |
| `QDRANT_URL`, `QDRANT_API_KEY`               | inference, data-loader          | Vector DB                                     |
| `QDRANT_COLLECTION_PREFIX`                   | inference, data-loader          | Default `proj_`                               |
| `INFERENCE_URL`                              | backend                         | Base URL of inference service                 |
| `INTERNAL_TOKEN`                             | backend, inference              | Shared bearer secret                          |
| `CLERK_`*                                    | backend                         | JWT verification                              |
| `VITE_APP_URL`, `VITE_CLERK_PUBLISHABLE_KEY` | ui                              | Browser-facing config                         |
| `EMBEDDING_MODEL`                            | inference, data-loader          | Must match (e.g. NVIDIA NIM model id)        |
| `EMBEDDING_VECTOR_SIZE`                     | data-loader                     | e.g. **2048** for `llama-nemotron-embed-vl-1b-v2` |
| `NVIDIA_NIM_API_KEY`, `NVIDIA_NIM_BASE_URL` | inference, data-loader          | Embeddings via NIM                            |
| `INGEST_MODE`                                | data-loader                     | `poll` (default) or `push` (Cloud Run HTTP)   |
| `PUBSUB_ENABLED`                           | backend                         | `true` to publish after upload (GCP)          |
| `PUBSUB_PROJECT_ID`, `PUBSUB_INGESTION_TOPIC` | backend                      | Pub/Sub topic for ingestion messages          |
| `WORKER_ID`                                  | data-loader                     | Unique per replica when scaling push/poll     |


---

## 11. Managing the project as a solo developer

**Branching:** Use short-lived branches off `main`; merge via PR so you keep a description and CI trail.

**When you pull new code:** check for new Alembic revisions → `alembic upgrade head`.

**Where to look when something breaks**


| Symptom                     | Check                                                                      |
| --------------------------- | -------------------------------------------------------------------------- |
| Upload fails                | Backend logs; GCS bucket IAM + `GOOGLE_APPLICATION_CREDENTIALS` / SA; presign URL      |
| Job stuck / never completes | `data-loader` logs; Postgres `ingestion_jobs`                              |
| Chat 401/403                | Clerk keys; JWT issuer/JWKS match                                          |
| Chat 502 to inference       | `INFERENCE_URL`, `INTERNAL_TOKEN`, inference health                        |
| No citations / poor answers | Qdrant collection `proj_<uuid>`; embedding model match; ingested documents |


**Logs:** each service can use `./run-dev.sh` or `docker compose logs -f <service>`.

---

## 12. Optional: `uv` and `pnpm` commands per service

See **§3.0** for the recommended **Docker vs host** startup flow. One-liners after dependencies are installed:

```bash
# Backend
cd backend && uv sync && uv run python -m alembic upgrade head

# Inference
cd inference && uv sync --extra dev && ./run-dev.sh

# Data-loader
cd data-loader && uv sync && ./run-dev.sh

# UI
cd ui && pnpm install && pnpm dev
```

---

If anything in this file disagrees with code, **trust the code** and open a PR to fix this doc.
