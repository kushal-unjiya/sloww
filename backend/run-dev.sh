#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

STAMP="$(date '+%Y-%m-%d')"
LOG_FILE="$LOG_DIR/dev-${STAMP}.log"

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') backend start ====="
} >>"$LOG_FILE"

CMD="LOG_COLOR=${LOG_COLOR:-1} LOG_LEVEL=${LOG_LEVEL:-INFO} uv run python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000 --log-level ${UVICORN_LOG_LEVEL:-info}"

bash -lc "$CMD" 2>&1 \
  | while IFS= read -r line; do
      printf '%s\n' "$line"
      if [[ "${KEEP_ANSI_LOG:-0}" == "1" ]]; then
        printf '%s\n' "$line" >>"$LOG_FILE"
      else
        printf '%s\n' "$line" | perl -pe 's/\e\[[0-9;]*[mK]//g' >>"$LOG_FILE"
      fi
    done
