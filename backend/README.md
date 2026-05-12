# Sloww `backend` service (Python 3.13 + uv)

Public **FastAPI** control plane: Clerk JWTs, users, projects, documents, uploads (**GCS**), and **chat** (relay to inference + Postgres persistence).

**Onboarding:** see **[../SETUP.md](../SETUP.md)** for env vars, Supabase, Docker, and GCP.

---

## Database / migrations

- **Schema** for app tables: **`sloww_ai`** (`DB_SCHEMA` in `.env`).
- **Alembic** lives in **`backend/migrations/`** — this service owns all migrations.

```bash
cd backend
uv sync
uv run python -m alembic upgrade head
```

For connection strings against **Supabase**, use `sslmode=require` and URL-encode passwords in `DATABASE_URL`.

---

## Run locally

Work from **`backend/`** (contains `pyproject.toml`). The Python package is **`api/`** (imports like `from api.main import app`).

```bash
cd backend
uv sync
uv run sloww-backend
# or: uv run python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

With **`./run-dev.sh`**, logs append to `backend/logs/dev-YYYY-MM-DD.log`.

---

## Package layout (short)

| Area | Role |
|------|------|
| `api/auth/` | Clerk verify + `Depends` |
| `api/user/` | `GET /me`, sign-in audit |
| `api/projects/`, `api/documents/`, `api/uploads/` | Core product |
| `api/chat/` | Conversations, messages, `POST /chat/stream` relay + DB writes |
| `api/shared/` | DB session, access checks |

---

## Chat routes (high level)

- `GET/POST /chat/projects/{project_id}/conversations`
- `GET /chat/projects/{project_id}/conversations/{id}/messages`
- `POST /chat/stream` — body: `query`, `notebook_id` (project UUID), optional `conversation_id`; requires `INFERENCE_URL` + `INTERNAL_TOKEN` matching inference.

See `api/chat/routes.py` for the live contract.
