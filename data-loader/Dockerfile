FROM ghcr.io/astral-sh/uv:python3.13-alpine AS base

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/app/.venv

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-cache

COPY . .

CMD ["uv", "run", "python", "-m", "data_loader.main"]

