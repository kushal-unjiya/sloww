# Sloww `data-loader` service (Python 3.13 + uv)

Background **ingestion worker**: claims **`ingestion_jobs`**, downloads source bytes from **Google Cloud Storage**, runs **PDF/DOCX** extract → chunk → embed → **upsert Qdrant** into collection **`proj_<project_id>`**. Updates job/document status in Postgres.

**Onboarding:** **[../SETUP.md](../SETUP.md)** — `GCS_BUCKET_NAME`, `GOOGLE_APPLICATION_CREDENTIALS`, Qdrant, Supabase, embedding parity with inference.

---

## Setup

```bash
cd data-loader
uv sync
```

Environment is loaded from **repo root `.env`**. Required:

- **`DATABASE_URL`**, **`DB_SCHEMA=sloww_ai`**
- **`GCS_BUCKET_NAME`** (same bucket as backend uploads)
- **`GOOGLE_APPLICATION_CREDENTIALS`** (local path to service account JSON) **or** GCP runtime identity on Cloud Run
- **`QDRANT_URL`**, **`QDRANT_API_KEY`**
- **`EMBEDDING_MODEL`** (same as inference)

---

## Run

```bash
cd data-loader
./run-dev.sh
```

Logs: `data-loader/logs/dev-YYYY-MM-DD.log`

There is **no HTTP port**; the process is a long-running poller.

---

## Operational notes

- **Chunk text** and metadata for citations live in **Qdrant payloads**.
- If ingestion succeeds but chat is not grounded, verify collection **`proj_<uuid>`** and **`notebook_id`** / project id alignment.

See **[../.cursor/data-loader.md](../.cursor/data-loader.md)** for extended editor-oriented notes.
