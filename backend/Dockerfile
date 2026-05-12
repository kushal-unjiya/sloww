FROM ghcr.io/astral-sh/uv:python3.13-alpine AS base

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/app/.venv

# Copy full project before `uv sync` so the local `app` package is installed into `.venv`.
COPY . .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-cache

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
