#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

STAMP="$(date '+%Y-%m-%d')"
LOG_FILE="$LOG_DIR/dev-${STAMP}.log"

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') inference start ====="
} >>"$LOG_FILE"

CMD="LOG_COLOR=${LOG_COLOR:-1} uv run sloww-inference"

bash -lc "$CMD" 2>&1 \
  | while IFS= read -r line; do
      printf '%s\n' "$line"
      if [[ "${KEEP_ANSI_LOG:-0}" == "1" ]]; then
        printf '%s\n' "$line" >>"$LOG_FILE"
      else
        printf '%s\n' "$line" | perl -pe 's/\e\[[0-9;]*[mK]//g' >>"$LOG_FILE"
      fi
    done
